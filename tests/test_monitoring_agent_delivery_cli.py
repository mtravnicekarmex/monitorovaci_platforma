from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os

from monitoring_agent import delivery_cli
from monitoring_agent.client import CURRENT_ENDPOINT_KEYS
from monitoring_agent.delivery import hash_delivery_recipient
from monitoring_agent.incident_store import IncidentStateStore, OUTBOX_DEAD_LETTER
from monitoring_agent.incidents import (
    CycleSnapshot,
    EndpointObservationFact,
    evaluate_incident_lifecycle,
)


BASE_TIME = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
TEST_RECIPIENT = "monitoring-test@unit.local"


class FakeTransport:
    envelopes = []
    sender_aliases = []

    def __init__(self, *, sender_alias=None) -> None:
        self.sender_aliases.append(sender_alias)

    def send(self, envelope) -> None:
        self.envelopes.append(envelope)


def _cycle(
    sequence: int,
    *,
    payload_status: dict[str, str] | None = None,
) -> CycleSnapshot:
    payload_status = payload_status or {}
    return CycleSnapshot(
        cycle_sequence=sequence,
        observed_at=BASE_TIME + timedelta(seconds=60 * sequence),
        endpoint_observations=tuple(
            EndpointObservationFact(
                endpoint_key=endpoint_key,
                transport_status="success",
                http_status=200,
                payload_status=payload_status.get(endpoint_key, "ok"),
            )
            for endpoint_key in CURRENT_ENDPOINT_KEYS
        ),
    )


def _store_with_pending_outbox(tmp_path) -> tuple[IncidentStateStore, str]:
    store = IncidentStateStore(tmp_path)
    evaluation = evaluate_incident_lifecycle(
        [
            _cycle(1, payload_status={"system_database": "degraded"}),
            _cycle(2, payload_status={"system_database": "degraded"}),
        ]
    )
    snapshot = store.apply_evaluation(evaluation, now=BASE_TIME)
    return store, snapshot.outbox_items[0].report_reference


def _set_delivery_env(monkeypatch) -> None:
    monkeypatch.setenv("DELIVERY_TEST_RECIPIENT", TEST_RECIPIENT)


def _set_smtp_env(monkeypatch) -> None:
    monkeypatch.setenv("O_EMAIL", "sender@unit.local")
    monkeypatch.setenv("O_APP", "placeholder-password")


def _read_json(capsys) -> dict[str, object]:
    captured = capsys.readouterr()
    return json.loads(captured.out)


def test_hash_recipient_cli_outputs_hash_without_raw_recipient(monkeypatch, capsys):
    _set_delivery_env(monkeypatch)

    exit_code = delivery_cli.main(["hash-recipient"])

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["event"] == "monitoring_test_delivery_recipient_hash"
    assert payload["recipient_hash"] == hash_delivery_recipient(TEST_RECIPIENT)
    assert TEST_RECIPIENT not in capsys.readouterr().out


def test_hash_recipient_cli_can_load_default_env_file_with_bom_without_printing_value(
    monkeypatch,
    capsys,
    tmp_path,
):
    monkeypatch.delenv("DELIVERY_TEST_RECIPIENT", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DELIVERY_TEST_RECIPIENT={TEST_RECIPIENT}\n",
        encoding="utf-8-sig",
    )

    exit_code = delivery_cli.main(["hash-recipient", "--env-file", str(env_file)])

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["recipient_hash"] == hash_delivery_recipient(TEST_RECIPIENT)
    assert TEST_RECIPIENT not in json.dumps(payload)


def test_delivery_cli_env_file_loads_only_command_delivery_keys(
    monkeypatch,
    capsys,
    tmp_path,
):
    monkeypatch.delenv("DELIVERY_TEST_RECIPIENT", raising=False)
    monkeypatch.delenv("EMAIL", raising=False)
    monkeypatch.delenv("APP", raising=False)
    monkeypatch.delenv("O_EMAIL", raising=False)
    monkeypatch.delenv("O_APP", raising=False)
    monkeypatch.delenv("MONITORING_AGENT_BEARER_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "MONITORING_AGENT_BEARER_TOKEN=SHOULD_NOT_LOAD",
                "EMAIL=sender@unit.local",
                "APP=placeholder-password",
                "O_EMAIL=sender@unit.local",
                "O_APP=placeholder-password",
                f"DELIVERY_TEST_RECIPIENT={TEST_RECIPIENT}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = delivery_cli.main(["hash-recipient", "--env-file", str(env_file)])

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["recipient_hash"] == hash_delivery_recipient(TEST_RECIPIENT)
    assert os.environ["DELIVERY_TEST_RECIPIENT"] == TEST_RECIPIENT
    assert "EMAIL" not in os.environ
    assert "APP" not in os.environ
    assert "O_EMAIL" not in os.environ
    assert "O_APP" not in os.environ
    assert "MONITORING_AGENT_BEARER_TOKEN" not in os.environ


def test_dry_run_cli_does_not_claim_or_send(monkeypatch, capsys, tmp_path):
    _set_delivery_env(monkeypatch)
    store, report_reference = _store_with_pending_outbox(tmp_path)

    exit_code = delivery_cli.main(
        [
            "dry-run",
            "--state-dir",
            str(tmp_path),
            "--report-reference",
            report_reference,
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["event"] == "monitoring_test_delivery_dry_run"
    assert payload["due_count"] == 1
    assert payload["status"] == "dry_run_ok"
    assert store.load().outbox_items[0].status == "pending"


def test_review_outbox_cli_is_read_only_and_does_not_require_delivery_env(
    monkeypatch,
    capsys,
    tmp_path,
):
    monkeypatch.delenv("DELIVERY_TEST_RECIPIENT", raising=False)
    store, report_reference = _store_with_pending_outbox(tmp_path)

    exit_code = delivery_cli.main(
        [
            "review-outbox",
            "--state-dir",
            str(tmp_path),
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["event"] == "monitoring_delivery_outbox_review"
    assert payload["status"] == "reviewed"
    assert payload["item_count"] == 1
    assert payload["review_item_count"] == 1
    assert payload["due_pending_count"] == 1
    assert payload["status_counts"] == {"pending": 1}
    assert payload["action_counts"] == {"opened": 1}
    assert payload["items"][0]["report_reference"] == report_reference
    assert payload["items"][0]["due"] is True
    assert store.load().outbox_items[0].status == "pending"
    assert TEST_RECIPIENT not in json.dumps(payload)
    assert "placeholder-password" not in json.dumps(payload)


def test_review_outbox_cli_filters_and_limits_without_claiming(
    capsys,
    tmp_path,
):
    store, report_reference = _store_with_pending_outbox(tmp_path)

    exit_code = delivery_cli.main(
        [
            "review-outbox",
            "--state-dir",
            str(tmp_path),
            "--report-reference",
            "other-report",
            "--limit",
            "1",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["item_count"] == 1
    assert payload["review_item_count"] == 0
    assert payload["due_pending_count"] == 1
    assert payload["items"] == []
    assert payload["truncated_item_count"] == 0
    assert store.load().outbox_items[0].report_reference == report_reference
    assert store.load().outbox_items[0].status == "pending"


def test_skip_outbox_cli_requires_confirm_without_writing(capsys, tmp_path):
    store, report_reference = _store_with_pending_outbox(tmp_path)

    exit_code = delivery_cli.main(
        [
            "skip-outbox",
            "--state-dir",
            str(tmp_path),
            "--report-reference",
            report_reference,
            "--limit",
            "1",
            "--confirm",
            "NO",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 2
    assert payload["event"] == "monitoring_delivery_outbox_skip"
    assert payload["status"] == "configuration_error"
    assert payload["error_code"] == "confirmation_required"
    assert store.load().outbox_items[0].status == "pending"


def test_skip_outbox_cli_marks_pending_item_without_delivery_env_or_smtp(
    monkeypatch,
    capsys,
    tmp_path,
):
    monkeypatch.delenv("DELIVERY_TEST_RECIPIENT", raising=False)
    monkeypatch.delenv("O_EMAIL", raising=False)
    monkeypatch.delenv("O_APP", raising=False)
    store, report_reference = _store_with_pending_outbox(tmp_path)
    cutoff = BASE_TIME + timedelta(seconds=1)

    exit_code = delivery_cli.main(
        [
            "skip-outbox",
            "--state-dir",
            str(tmp_path),
            "--created-before",
            cutoff.isoformat(),
            "--limit",
            "1",
            "--confirm",
            "SKIP_PENDING_OUTBOX",
            "--now",
            (BASE_TIME + timedelta(seconds=2)).isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["event"] == "monitoring_delivery_outbox_skip"
    assert payload["status"] == "skipped"
    assert payload["skipped_count"] == 1
    assert payload["requested_limit"] == 1
    assert payload["created_before"] == cutoff.isoformat()
    assert payload["reason_code"] == "operator_skipped"
    assert payload["terminal_status"] == OUTBOX_DEAD_LETTER
    assert payload["items"][0]["report_reference"] == report_reference
    assert payload["items"][0]["status"] == OUTBOX_DEAD_LETTER
    assert payload["items"][0]["last_error_code"] == "operator_skipped"
    assert payload["items"][0]["attempt_count"] == 0
    assert payload["items"][0]["due"] is False
    assert store.load().outbox_items[0].status == OUTBOX_DEAD_LETTER
    assert TEST_RECIPIENT not in json.dumps(payload)
    assert "placeholder-password" not in json.dumps(payload)

    exit_code = delivery_cli.main(
        [
            "review-outbox",
            "--state-dir",
            str(tmp_path),
            "--now",
            (BASE_TIME + timedelta(seconds=3)).isoformat(),
        ]
    )
    review_payload = _read_json(capsys)
    assert exit_code == 0
    assert review_payload["item_count"] == 1
    assert review_payload["review_item_count"] == 0
    assert review_payload["due_pending_count"] == 0
    assert review_payload["status_counts"] == {OUTBOX_DEAD_LETTER: 1}
    assert review_payload["items"] == []

    exit_code = delivery_cli.main(
        [
            "review-outbox",
            "--state-dir",
            str(tmp_path),
            "--include-terminal",
            "--now",
            (BASE_TIME + timedelta(seconds=4)).isoformat(),
        ]
    )
    terminal_review_payload = _read_json(capsys)
    assert exit_code == 0
    assert terminal_review_payload["review_item_count"] == 1
    assert terminal_review_payload["items"][0]["status"] == OUTBOX_DEAD_LETTER


def test_skip_outbox_cli_requires_filter(capsys, tmp_path):
    store, _ = _store_with_pending_outbox(tmp_path)

    exit_code = delivery_cli.main(
        [
            "skip-outbox",
            "--state-dir",
            str(tmp_path),
            "--limit",
            "1",
            "--confirm",
            "SKIP_PENDING_OUTBOX",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 2
    assert payload["error_code"] == "skip_filter_required"
    assert store.load().outbox_items[0].status == "pending"


def test_send_due_cli_requires_confirm_before_reading_report_or_smtp(
    monkeypatch,
    capsys,
    tmp_path,
):
    _set_delivery_env(monkeypatch)
    store, report_reference = _store_with_pending_outbox(tmp_path)

    exit_code = delivery_cli.main(
        [
            "send-due",
            "--env-file",
            str(tmp_path / "missing.env"),
            "--state-dir",
            str(tmp_path),
            "--report-reference",
            report_reference,
            "--report-file",
            str(tmp_path / "missing-report.txt"),
            "--claim-id",
            "worker-1",
            "--confirm",
            "NO",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 2
    assert payload["error_code"] == "confirmation_required"
    assert store.load().outbox_items[0].status == "pending"


def test_send_due_cli_requires_outlook_credentials_without_claiming(
    monkeypatch,
    capsys,
    tmp_path,
):
    _set_delivery_env(monkeypatch)
    monkeypatch.delenv("EMAIL", raising=False)
    monkeypatch.delenv("APP", raising=False)
    monkeypatch.delenv("O_EMAIL", raising=False)
    monkeypatch.delenv("O_APP", raising=False)
    store, report_reference = _store_with_pending_outbox(tmp_path)
    report_file = tmp_path / "report.txt"
    report_file.write_text("sanitized report", encoding="utf-8")

    exit_code = delivery_cli.main(
        [
            "send-due",
            "--env-file",
            str(tmp_path / "missing.env"),
            "--state-dir",
            str(tmp_path),
            "--report-reference",
            report_reference,
            "--report-file",
            str(report_file),
            "--claim-id",
            "worker-1",
            "--confirm",
            "SEND_TEST_DELIVERY",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 2
    assert payload["error_code"] == "email_env_missing"
    assert store.load().outbox_items[0].status == "pending"


def test_prepare_synthetic_requires_confirm_without_writing(capsys, tmp_path):
    report_file = tmp_path / "report.txt"

    exit_code = delivery_cli.main(
        [
            "prepare-synthetic",
            "--state-dir",
            str(tmp_path / "state"),
            "--report-file",
            str(report_file),
            "--confirm",
            "NO",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 2
    assert payload["error_code"] == "confirmation_required"
    assert not report_file.exists()
    assert not (tmp_path / "state" / "incident_state.json").exists()


def test_prepare_synthetic_creates_outbox_and_sanitized_report(capsys, tmp_path):
    state_dir = tmp_path / "state"
    report_file = tmp_path / "report.txt"

    exit_code = delivery_cli.main(
        [
            "prepare-synthetic",
            "--state-dir",
            str(state_dir),
            "--report-file",
            str(report_file),
            "--confirm",
            "PREPARE_SYNTHETIC_DELIVERY_TEST_STATE",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["status"] == "prepared"
    assert payload["report_reference"] == (
        "controlled-test-report:v1:synthetic-endpoint-system-database"
    )
    assert "system_database" in payload["incident_key"]
    snapshot = IncidentStateStore(state_dir).load()
    assert len(snapshot.outbox_items) == 1
    assert snapshot.outbox_items[0].status == "pending"
    report_text = report_file.read_text(encoding="utf-8")
    assert "controlled synthetic delivery test" in report_text
    assert "@" not in report_text
    assert "password" not in report_text.lower()


def test_send_due_cli_uses_fake_transport_and_marks_sent(
    monkeypatch,
    capsys,
    tmp_path,
):
    _set_delivery_env(monkeypatch)
    _set_smtp_env(monkeypatch)
    FakeTransport.envelopes = []
    FakeTransport.sender_aliases = []
    monkeypatch.setattr(delivery_cli, "OutlookEmailTransport", FakeTransport)
    store, report_reference = _store_with_pending_outbox(tmp_path)
    report_file = tmp_path / "report.txt"
    report_file.write_text("sanitized report", encoding="utf-8")

    exit_code = delivery_cli.main(
        [
            "send-due",
            "--state-dir",
            str(tmp_path),
            "--report-reference",
            report_reference,
            "--report-file",
            str(report_file),
            "--claim-id",
            "worker-1",
            "--confirm",
            "SEND_TEST_DELIVERY",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["status"] == "sent"
    assert payload["results"][0]["status"] == "sent"
    assert TEST_RECIPIENT not in json.dumps(payload)
    assert "placeholder-password" not in json.dumps(payload)
    assert len(FakeTransport.envelopes) == 1
    assert FakeTransport.sender_aliases == [None]
    assert FakeTransport.envelopes[0].recipient == TEST_RECIPIENT
    assert store.load().outbox_items[0].status == "sent"


def test_send_due_cli_loads_o_email_o_app_and_recipient_from_env_file(
    monkeypatch,
    capsys,
    tmp_path,
):
    for key in (
        "DELIVERY_TEST_RECIPIENT",
        "O_EMAIL",
        "O_APP",
        "EMAIL",
        "APP",
    ):
        monkeypatch.delenv(key, raising=False)
    FakeTransport.envelopes = []
    FakeTransport.sender_aliases = []
    monkeypatch.setattr(delivery_cli, "OutlookEmailTransport", FakeTransport)
    store, report_reference = _store_with_pending_outbox(tmp_path)
    report_file = tmp_path / "report.txt"
    report_file.write_text("sanitized report", encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "O_EMAIL=sender@unit.local",
                "O_APP=placeholder-password",
                f"DELIVERY_TEST_RECIPIENT={TEST_RECIPIENT}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    exit_code = delivery_cli.main(
        [
            "send-due",
            "--env-file",
            str(env_file),
            "--state-dir",
            str(tmp_path),
            "--report-reference",
            report_reference,
            "--report-file",
            str(report_file),
            "--claim-id",
            "worker-1",
            "--confirm",
            "SEND_TEST_DELIVERY",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 0
    assert payload["status"] == "sent"
    assert "placeholder-password" not in json.dumps(payload)
    assert TEST_RECIPIENT not in json.dumps(payload)
    assert len(FakeTransport.envelopes) == 1
    assert FakeTransport.envelopes[0].recipient == TEST_RECIPIENT
    assert store.load().outbox_items[0].status == "sent"


def test_send_due_cli_rejects_env_file_report_without_smtp(
    monkeypatch,
    capsys,
    tmp_path,
):
    _set_delivery_env(monkeypatch)
    _, report_reference = _store_with_pending_outbox(tmp_path)
    rejected_report = tmp_path / ".env"
    rejected_report.write_text("token=SHOULD_NOT_LEAK", encoding="utf-8")

    exit_code = delivery_cli.main(
        [
            "send-due",
            "--state-dir",
            str(tmp_path),
            "--report-reference",
            report_reference,
            "--report-file",
            str(rejected_report),
            "--claim-id",
            "worker-1",
            "--confirm",
            "SEND_TEST_DELIVERY",
            "--now",
            BASE_TIME.isoformat(),
        ]
    )

    payload = _read_json(capsys)
    assert exit_code == 2
    assert payload["error_code"] == "report_file_rejected"
    assert "SHOULD_NOT_LEAK" not in json.dumps(payload)
