from __future__ import annotations

from datetime import datetime, timezone
import io
import json
import sys

from monitoring_agent.orchestrator_export_cli import (
    main,
    wrap_remote_audit_payload,
)


CAPTURED_AT = "2026-08-18T05:49:09+00:00"


def test_wrap_remote_audit_payload_adds_captured_at_without_mutating_source():
    source = _remote_audit_payload()

    wrapped = wrap_remote_audit_payload(
        source,
        captured_at=datetime.fromisoformat(CAPTURED_AT),
    )

    assert source.get("captured_at") is None
    assert wrapped["captured_at"] == "2026-08-18T05:49:09Z"
    assert wrapped["event"] == "agent_state_audit"
    assert wrapped["audit_contract_version"] == 8
    assert wrapped["latest_heartbeat"]["status"] == "healthy"


def test_cli_wrap_remote_audit_reads_stdin_and_writes_stdout(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps(_remote_audit_payload())),
    )

    result = main(
        [
            "wrap-remote-audit",
            "--captured-at",
            CAPTURED_AT,
        ]
    )

    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert output["captured_at"] == "2026-08-18T05:49:09Z"
    assert output["event"] == "agent_state_audit"


def test_cli_wrap_remote_audit_writes_output_file_and_summary(tmp_path, capsys):
    input_path = tmp_path / "remote-audit.json"
    output_path = tmp_path / "wrapped" / "remote-audit.json"
    input_path.write_text(
        json.dumps(_remote_audit_payload()),
        encoding="utf-8",
    )

    result = main(
        [
            "wrap-remote-audit",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--captured-at",
            CAPTURED_AT,
        ]
    )

    assert result == 0
    wrapped = json.loads(output_path.read_text(encoding="utf-8"))
    assert wrapped["captured_at"] == "2026-08-18T05:49:09Z"
    summary = json.loads(capsys.readouterr().out)
    assert summary["event"] == "monitoring_orchestrator_remote_audit_wrapped"
    assert summary["status"] == "wrapped"


def test_cli_wrap_remote_audit_rejects_env_input_path(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(json.dumps(_remote_audit_payload()), encoding="utf-8")

    try:
        main(
            [
                "wrap-remote-audit",
                "--input",
                str(env_path),
                "--captured-at",
                CAPTURED_AT,
            ]
        )
    except SystemExit as exc:
        assert "env_source_forbidden" in str(exc)
    else:
        raise AssertionError("expected CLI to reject .env input path")


def test_wrap_remote_audit_rejects_wrong_event():
    payload = _remote_audit_payload()
    payload["event"] = "configuration_valid"

    try:
        wrap_remote_audit_payload(
            payload,
            captured_at=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        assert "agent_state_audit" in str(exc)
    else:
        raise AssertionError("expected wrong remote audit event rejection")


def test_wrap_remote_audit_rejects_naive_capture_timestamp():
    try:
        wrap_remote_audit_payload(
            _remote_audit_payload(),
            captured_at=datetime(2026, 8, 18, 5, 49, 9),
        )
    except ValueError as exc:
        assert "timezone-aware" in str(exc)
    else:
        raise AssertionError("expected naive captured_at rejection")


def _remote_audit_payload() -> dict[str, object]:
    return {
        "audit_contract_version": 8,
        "configuration": {"endpoint_count": 9},
        "event": "agent_state_audit",
        "evidence_gaps": ["heartbeat_transition_history_not_persisted"],
        "latest_heartbeat": {
            "observation_count": 9,
            "status": "healthy",
            "transport_failure_count": 0,
        },
        "shadow_incidents": {
            "delivery_enabled": False,
            "mode": "shadow_only",
            "outbox_pending_count": 2,
        },
    }
