from __future__ import annotations

import json

import pytest

from scripts import export_monitoring_orchestrator_local_inputs as exporter


class _Model:
    def __init__(self, payload):
        self.payload = payload

    def model_dump(self, *, mode):
        assert mode == "json"
        return self.payload


def test_export_local_inputs_writes_local_only_registry(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        exporter,
        "load_database_availability_local_agent_facade_snapshot",
        lambda: object(),
    )
    monkeypatch.setattr(
        exporter,
        "load_scheduler_metrics_local_agent_facade_snapshot",
        lambda: object(),
    )
    monkeypatch.setattr(
        exporter,
        "project_database_availability_local_agent",
        lambda snapshot: _Model(_database_payload()),
    )
    monkeypatch.setattr(
        exporter,
        "project_scheduler_metrics_local_agent",
        lambda snapshot: _Model(_scheduler_payload()),
    )

    result = exporter.main(["--artifact-dir", str(tmp_path)])

    assert result == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["status"] == "local_preflight_only_remote_audit_required"
    assert stdout["remote_audit_included"] is False
    registry = json.loads(
        (tmp_path / "orchestrator-registry-local-only.json").read_text(
            encoding="utf-8",
        )
    )
    assert [agent["agent_key"] for agent in registry["agents"]] == [
        "database_availability",
        "scheduler_metrics",
    ]
    assert (tmp_path / "database-availability.json").exists()
    assert (tmp_path / "scheduler-metrics.json").exists()


def test_export_local_inputs_can_include_supplied_remote_audit(
    tmp_path,
    monkeypatch,
    capsys,
):
    _patch_local_models(monkeypatch)
    remote_audit = tmp_path / "input-remote-audit.json"
    remote_audit.write_text(
        json.dumps(
            {
                "audit_contract_version": 8,
                "event": "agent_state_audit",
                "latest_heartbeat": {"status": "healthy"},
            }
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    result = exporter.main(
        [
            "--artifact-dir",
            str(output_dir),
            "--remote-audit-file",
            str(remote_audit),
        ]
    )

    assert result == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["status"] == "ready_for_full_pilot"
    assert stdout["remote_audit_included"] is True
    registry = json.loads(
        (output_dir / "orchestrator-registry.json").read_text(encoding="utf-8")
    )
    assert [agent["agent_key"] for agent in registry["agents"]] == [
        "external_health",
        "database_availability",
        "scheduler_metrics",
    ]
    assert (output_dir / "remote-audit.json").exists()


def test_export_local_inputs_rejects_env_remote_audit_path(
    tmp_path,
    monkeypatch,
):
    _patch_local_models(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("SECRET=value\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must not be an .env path"):
        exporter.main(
            [
                "--artifact-dir",
                str(tmp_path / "out"),
                "--remote-audit-file",
                str(env_path),
            ]
        )


def _patch_local_models(monkeypatch):
    monkeypatch.setattr(
        exporter,
        "load_database_availability_local_agent_facade_snapshot",
        lambda: object(),
    )
    monkeypatch.setattr(
        exporter,
        "load_scheduler_metrics_local_agent_facade_snapshot",
        lambda: object(),
    )
    monkeypatch.setattr(
        exporter,
        "project_database_availability_local_agent",
        lambda snapshot: _Model(_database_payload()),
    )
    monkeypatch.setattr(
        exporter,
        "project_scheduler_metrics_local_agent",
        lambda snapshot: _Model(_scheduler_payload()),
    )


def _database_payload():
    return {
        "agent_key": "database_availability",
        "checked_at": "2026-08-18T05:00:00Z",
        "contract_version": 1,
        "evidence_gaps": [],
        "mode": "local_agent",
        "service_count": 2,
        "state_age_seconds": 5,
        "status": "ok",
        "unavailable_service_count": 0,
    }


def _scheduler_payload():
    return {
        "agent_key": "scheduler_metrics",
        "checked_at": "2026-08-18T05:00:00Z",
        "contract_version": 1,
        "error_job_count": 2,
        "evidence_gaps": [],
        "failure_count_24h": 0,
        "job_count": 51,
        "mode": "local_agent",
        "state_age_seconds": 5,
        "status": "degraded",
    }
