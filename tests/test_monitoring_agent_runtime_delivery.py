from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from monitoring_agent.client import CURRENT_ENDPOINT_KEYS
from monitoring_agent.delivery import DELIVERY_ERROR_INVALID_POLICY
from monitoring_agent.incident_store import IncidentStateStore
from monitoring_agent.incidents import (
    CycleSnapshot,
    EndpointObservationFact,
    evaluate_incident_lifecycle,
)
from monitoring_agent.runtime_delivery import run_runtime_delivery
from monitoring_agent.settings import RuntimeSettings


BASE_TIME = datetime(2026, 8, 21, 8, 0, tzinfo=timezone.utc)
TEST_RECIPIENT = "monitoring-test@unit.local"


class FakeTransport:
    envelopes = []
    envs = []
    sender_aliases = []

    def __init__(self, *, sender_alias=None, env=None) -> None:
        self.sender_aliases.append(sender_alias)
        self.envs.append(dict(env or {}))

    def send(self, envelope) -> None:
        self.envelopes.append(envelope)


def _settings(tmp_path, *, delivery_enabled: bool = False) -> RuntimeSettings:
    return RuntimeSettings(
        env_contract_version=3,
        mode="test",
        instance_id="center-test",
        base_url="http://127.0.0.1:8020",
        external_web_url="http://127.0.0.1:8020",
        state_dir=tmp_path / "state",
        timeout_seconds=2.0,
        max_attempts=3,
        retry_backoff_seconds=0.5,
        poll_interval_seconds=60.0,
        poll_jitter_seconds=5.0,
        endpoint_keys=CURRENT_ENDPOINT_KEYS,
        endpoint_set_version=3,
        observation_contract_version=4,
        max_observation_records=10_000,
        max_incident_states=200,
        max_incident_transition_records=2_000,
        max_outbox_items=1_000,
        outbox_max_attempts=3,
        outbox_retry_backoff_seconds=300.0,
        outbox_claim_timeout_seconds=600.0,
        bearer_credential="t" * 48,
        delivery_automation_enabled=delivery_enabled,
    )


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


def _open_incident(store: IncidentStateStore, endpoint_key: str, *, now: datetime):
    evaluation = evaluate_incident_lifecycle(
        [
            _cycle(1, payload_status={endpoint_key: "degraded"}),
            _cycle(2, payload_status={endpoint_key: "degraded"}),
        ],
        now=now,
    )
    return store.apply_evaluation(evaluation, now=now)


def _write_delivery_env(tmp_path, *, enabled: bool = True) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                f"DELIVERY_AUTOMATION_ENABLED={'true' if enabled else 'false'}",
                "O_EMAIL=sender@unit.local",
                "O_APP=placeholder-password",
                f"DELIVERY_TEST_RECIPIENT={TEST_RECIPIENT}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_runtime_delivery_disabled_does_not_read_or_claim(tmp_path):
    settings = _settings(tmp_path, delivery_enabled=False)
    store = IncidentStateStore(settings.state_dir)
    snapshot = _open_incident(store, "system_database", now=BASE_TIME)

    summary = run_runtime_delivery(
        settings=settings,
        env_file=tmp_path / "missing.env",
        store=store,
        now=BASE_TIME,
        transport_factory=FakeTransport,
    )

    assert summary.to_dict()["status"] == "disabled"
    assert summary.enabled is False
    assert summary.state_changed is False
    assert store.load().outbox_items[0].idempotency_key == (
        snapshot.outbox_items[0].idempotency_key
    )
    assert store.load().outbox_items[0].status == "pending"


def test_runtime_delivery_enabled_missing_recipient_fails_before_claim(tmp_path):
    settings = _settings(tmp_path, delivery_enabled=True)
    store = IncidentStateStore(settings.state_dir)
    _open_incident(store, "system_database", now=BASE_TIME)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DELIVERY_AUTOMATION_ENABLED=true",
                "O_EMAIL=sender@unit.local",
                "O_APP=placeholder-password",
                "",
            ]
        ),
        encoding="utf-8",
    )

    summary = run_runtime_delivery(
        settings=settings,
        env_file=tmp_path / ".env",
        store=store,
        now=BASE_TIME,
        transport_factory=FakeTransport,
    )

    payload = summary.to_dict()
    assert payload["status"] == "configuration_error"
    assert payload["error_code"] == DELIVERY_ERROR_INVALID_POLICY
    assert summary.state_changed is False
    assert store.load().outbox_items[0].status == "pending"


def test_runtime_delivery_enabled_no_due_items_does_not_send(tmp_path):
    settings = _settings(tmp_path, delivery_enabled=True)
    store = IncidentStateStore(settings.state_dir)
    _write_delivery_env(tmp_path)

    summary = run_runtime_delivery(
        settings=settings,
        env_file=tmp_path / ".env",
        store=store,
        now=BASE_TIME,
        transport_factory=FakeTransport,
    )

    payload = summary.to_dict()
    assert payload["status"] == "no_due_items"
    assert payload["no_due_count"] == 1
    assert payload["sent_count"] == 0
    assert summary.state_changed is False
    assert FakeTransport.envelopes == []


def test_runtime_delivery_sends_one_due_item_and_marks_sent(tmp_path):
    FakeTransport.envelopes = []
    FakeTransport.envs = []
    FakeTransport.sender_aliases = []
    settings = _settings(tmp_path, delivery_enabled=True)
    store = IncidentStateStore(settings.state_dir)
    _write_delivery_env(tmp_path)
    _open_incident(store, "system_database", now=BASE_TIME)
    _open_incident(store, "system_proxy", now=BASE_TIME + timedelta(seconds=1))

    summary = run_runtime_delivery(
        settings=settings,
        env_file=tmp_path / ".env",
        store=store,
        now=BASE_TIME + timedelta(seconds=2),
        transport_factory=FakeTransport,
    )

    payload = summary.to_dict()
    assert payload["status"] == "sent"
    assert payload["sent_count"] == 1
    assert payload["attempted_count"] == 1
    assert summary.state_changed is True
    assert len(FakeTransport.envelopes) == 1
    assert FakeTransport.envelopes[0].recipient == TEST_RECIPIENT
    assert "automatic TEST delivery" in FakeTransport.envelopes[0].body_text
    assert "placeholder-password" not in FakeTransport.envelopes[0].body_text
    assert TEST_RECIPIENT not in json.dumps(payload)
    outbox_statuses = {item.status for item in store.load().outbox_items}
    assert outbox_statuses == {"pending", "sent"}
    assert FakeTransport.envs[0]["O_EMAIL"] == "sender@unit.local"
