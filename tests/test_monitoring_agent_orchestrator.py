from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from monitoring_agent.orchestrator import (
    CORRELATION_DATABASE_PATH_CONFIRMED,
    CORRELATION_SCHEDULER_HISTORICAL_STATUS_ONLY,
    CORRELATION_SOURCE_INVALID,
    CORRELATION_SOURCE_STALE,
    FRESHNESS_INVALID,
    FRESHNESS_STALE,
    OrchestratorError,
    build_orchestrator_snapshot,
    load_registry_file,
)
from monitoring_agent.orchestrator_cli import main


BASE_TIME = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def test_file_only_orchestrator_correlates_sanitized_snapshots(tmp_path):
    registry = _write_registry(
        tmp_path,
        agents=[
            _registry_agent(
                "external_health",
                "remote_observer",
                "supervision_center",
                "external.json",
                payload_kind="agent_snapshot_v1",
            ),
            _registry_agent(
                "database_availability",
                "local_facade_agent",
                "main_workstation",
                "database.json",
                payload_kind="local_agent_facade_v1",
            ),
            _registry_agent(
                "scheduler_metrics",
                "local_facade_agent",
                "main_workstation",
                "scheduler.json",
                payload_kind="local_agent_facade_v1",
            ),
        ],
    )
    _write_json(
        tmp_path / "external.json",
        _generic_snapshot(
            agent_key="external_health",
            status="degraded",
            signals=["external_database_endpoint_degraded"],
            summary_counts={"endpoint_count": 9},
        ),
    )
    _write_json(
        tmp_path / "database.json",
        _database_facade(status="degraded", unavailable_service_count=1),
    )
    _write_json(
        tmp_path / "scheduler.json",
        _scheduler_facade(status="ok", error_job_count=0),
    )

    snapshot = build_orchestrator_snapshot(
        load_registry_file(registry),
        generated_at=BASE_TIME,
    )

    payload = snapshot.to_dict()
    assert payload["event"] == "monitoring_orchestrator_snapshot"
    assert payload["mode"] == "file_only"
    assert payload["status"] == "degraded"
    assert payload["metrics"]["agent_count"] == 3
    assert all("source_digest" in agent for agent in payload["agents"])
    assert {item["kind"] for item in payload["correlations"]} == {
        CORRELATION_DATABASE_PATH_CONFIRMED,
    }
    assert "does not poll endpoints" in payload["safety_boundary"][1]


def test_scheduler_historical_errors_degrade_without_error(tmp_path):
    registry = _write_registry(
        tmp_path,
        agents=[
            _registry_agent(
                "external_health",
                "remote_observer",
                "supervision_center",
                "external.json",
                payload_kind="agent_snapshot_v1",
            ),
            _registry_agent(
                "database_availability",
                "local_facade_agent",
                "main_workstation",
                "database.json",
                payload_kind="local_agent_facade_v1",
            ),
            _registry_agent(
                "scheduler_metrics",
                "local_facade_agent",
                "main_workstation",
                "scheduler.json",
                payload_kind="local_agent_facade_v1",
            ),
        ],
    )
    _write_json(
        tmp_path / "external.json",
        _generic_snapshot(agent_key="external_health", status="ok"),
    )
    _write_json(tmp_path / "database.json", _database_facade(status="ok"))
    _write_json(
        tmp_path / "scheduler.json",
        _scheduler_facade(
            status="degraded",
            error_job_count=2,
            failure_count_24h=0,
        ),
    )

    snapshot = build_orchestrator_snapshot(
        load_registry_file(registry),
        generated_at=BASE_TIME,
    )

    assert snapshot.status == "degraded"
    assert {finding.kind for finding in snapshot.correlations} == {
        CORRELATION_SCHEDULER_HISTORICAL_STATUS_ONLY,
    }


def test_contract_mismatch_is_isolated_to_source_snapshot(tmp_path):
    registry = _write_registry(
        tmp_path,
        agents=[
            _registry_agent(
                "external_health",
                "remote_observer",
                "supervision_center",
                "external.json",
                payload_kind="agent_snapshot_v1",
            )
        ],
    )
    source = _generic_snapshot(agent_key="external_health", status="ok")
    source["contract_version"] = 99
    _write_json(tmp_path / "external.json", source)

    snapshot = build_orchestrator_snapshot(
        load_registry_file(registry),
        generated_at=BASE_TIME,
    )

    agent = snapshot.agents[0]
    assert agent.status == "unavailable"
    assert agent.freshness_status == FRESHNESS_INVALID
    assert agent.evidence_gaps == ("source_contract_mismatch",)
    assert snapshot.correlations[0].kind == CORRELATION_SOURCE_INVALID


def test_stale_source_is_degraded_without_mutating_other_sources(tmp_path):
    registry = _write_registry(
        tmp_path,
        agents=[
            _registry_agent(
                "database_availability",
                "local_facade_agent",
                "main_workstation",
                "database.json",
                payload_kind="local_agent_facade_v1",
                stale_after_seconds=60,
            ),
            _registry_agent(
                "scheduler_metrics",
                "local_facade_agent",
                "main_workstation",
                "scheduler.json",
                payload_kind="local_agent_facade_v1",
            ),
        ],
    )
    _write_json(
        tmp_path / "database.json",
        _database_facade(status="ok", state_age_seconds=120),
    )
    _write_json(tmp_path / "scheduler.json", _scheduler_facade(status="ok"))

    snapshot = build_orchestrator_snapshot(
        load_registry_file(registry),
        generated_at=BASE_TIME,
    )

    by_key = {agent.agent_key: agent for agent in snapshot.agents}
    assert by_key["database_availability"].freshness_status == FRESHNESS_STALE
    assert by_key["database_availability"].status == "degraded"
    assert by_key["scheduler_metrics"].status == "ok"
    assert any(item.kind == CORRELATION_SOURCE_STALE for item in snapshot.correlations)


def test_duplicate_agent_key_fails_closed(tmp_path):
    registry = _write_registry(
        tmp_path,
        agents=[
            _registry_agent(
                "database_availability",
                "local_facade_agent",
                "main_workstation",
                "a.json",
                payload_kind="local_agent_facade_v1",
            ),
            _registry_agent(
                "database_availability",
                "local_facade_agent",
                "main_workstation",
                "b.json",
                payload_kind="local_agent_facade_v1",
            ),
        ],
    )

    with pytest.raises(OrchestratorError, match="duplicate_agent_key"):
        load_registry_file(registry)


def test_registry_rejects_env_source_file(tmp_path):
    registry = _write_registry(
        tmp_path,
        agents=[
            _registry_agent(
                "external_health",
                "remote_observer",
                "supervision_center",
                ".env",
                payload_kind="agent_snapshot_v1",
            )
        ],
    )

    with pytest.raises(OrchestratorError, match="env_source_forbidden"):
        load_registry_file(registry)


def test_remote_audit_payload_is_supported_without_raw_endpoint_details(tmp_path):
    registry = _write_registry(
        tmp_path,
        agents=[
            _registry_agent(
                "external_health",
                "remote_observer",
                "supervision_center",
                "audit.json",
                payload_kind="remote_agent_audit_v8",
                contract_version_min=8,
                contract_version_max=8,
            )
        ],
    )
    _write_json(
        tmp_path / "audit.json",
        {
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
                "active_state_count": 0,
                "outbox_pending_count": 0,
                "transition_record_count": 0,
            },
        },
    )

    snapshot = build_orchestrator_snapshot(
        load_registry_file(registry),
        generated_at=BASE_TIME,
    )

    agent = snapshot.agents[0]
    assert agent.status == "ok"
    assert agent.summary_counts["endpoint_count"] == 9
    assert "source_timestamp_missing" in agent.evidence_gaps


def test_remote_audit_payload_uses_captured_at_without_timestamp_gap(tmp_path):
    captured_at = "2026-08-18T05:49:09+00:00"
    registry = _write_registry(
        tmp_path,
        agents=[
            _registry_agent(
                "external_health",
                "remote_observer",
                "supervision_center",
                "audit.json",
                payload_kind="remote_agent_audit_v8",
                contract_version_min=8,
                contract_version_max=8,
            )
        ],
    )
    _write_json(
        tmp_path / "audit.json",
        {
            "audit_contract_version": 8,
            "captured_at": captured_at,
            "configuration": {"endpoint_count": 9},
            "event": "agent_state_audit",
            "evidence_gaps": ["heartbeat_transition_history_not_persisted"],
            "latest_heartbeat": {
                "observation_count": 9,
                "status": "healthy",
                "transport_failure_count": 0,
            },
        },
    )

    snapshot = build_orchestrator_snapshot(
        load_registry_file(registry),
        generated_at=BASE_TIME,
    )

    agent = snapshot.agents[0]
    assert agent.status == "ok"
    assert agent.source_checked_at == datetime.fromisoformat(captured_at)
    assert agent.source_state_updated_at == datetime.fromisoformat(captured_at)
    assert "heartbeat_transition_history_not_persisted" in agent.evidence_gaps
    assert "source_timestamp_missing" not in agent.evidence_gaps


def test_cli_writes_json_and_markdown_without_stdout(tmp_path, capsys):
    registry = _write_registry(
        tmp_path,
        agents=[
            _registry_agent(
                "external_health",
                "remote_observer",
                "supervision_center",
                "external.json",
                payload_kind="agent_snapshot_v1",
            )
        ],
    )
    _write_json(
        tmp_path / "external.json",
        _generic_snapshot(agent_key="external_health", status="ok"),
    )
    output_json = tmp_path / "out" / "orchestrator.json"
    output_md = tmp_path / "out" / "orchestrator.md"

    result = main(
        [
            "run",
            "--registry-file",
            str(registry),
            "--json-output",
            str(output_json),
            "--markdown-output",
            str(output_md),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == ""
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["event"] == "monitoring_orchestrator_snapshot"
    assert payload["status"] == "ok"
    assert "Safety boundary" in output_md.read_text(encoding="utf-8")


def _write_registry(tmp_path, *, agents):
    path = tmp_path / "registry.json"
    _write_json(
        path,
        {
            "agents": agents,
            "contract_version": 1,
            "event": "monitoring_orchestrator_registry",
            "mode": "file_only",
        },
    )
    return path


def _registry_agent(
    agent_key,
    agent_kind,
    location,
    source_file,
    *,
    payload_kind,
    contract_version_min=1,
    contract_version_max=1,
    stale_after_seconds=300,
):
    return {
        "agent_key": agent_key,
        "agent_kind": agent_kind,
        "contract_version_max": contract_version_max,
        "contract_version_min": contract_version_min,
        "enabled": True,
        "location": location,
        "payload_kind": payload_kind,
        "source_file": source_file,
        "stale_after_seconds": stale_after_seconds,
        "status_mapping_version": 1,
    }


def _generic_snapshot(
    *,
    agent_key,
    status,
    signals=None,
    summary_counts=None,
    state_age_seconds=10,
):
    return {
        "agent_key": agent_key,
        "checked_at": BASE_TIME.isoformat(),
        "contract_version": 1,
        "event": "monitoring_orchestrator_source_snapshot",
        "evidence_gaps": [],
        "signals": signals or [],
        "state_age_seconds": state_age_seconds,
        "state_updated_at": BASE_TIME.isoformat(),
        "status": status,
        "summary_counts": summary_counts or {},
    }


def _database_facade(
    *,
    status,
    unavailable_service_count=0,
    state_age_seconds=10,
):
    return {
        "agent_key": "database_availability",
        "checked_at": BASE_TIME.isoformat(),
        "contract_version": 1,
        "delivered_event_count_24h": 0,
        "evidence_gaps": [],
        "mode": "local_agent",
        "pending_event_count": 0,
        "recent_transition_count": 0,
        "service_count": 2,
        "stale_after_seconds": 300,
        "stale_service_count": 0,
        "state_age_seconds": state_age_seconds,
        "state_updated_at": BASE_TIME.isoformat(),
        "status": status,
        "unavailable_service_count": unavailable_service_count,
    }


def _scheduler_facade(
    *,
    status,
    error_job_count=0,
    failure_count_24h=0,
    state_age_seconds=10,
):
    return {
        "agent_key": "scheduler_metrics",
        "checked_at": BASE_TIME.isoformat(),
        "contract_version": 1,
        "degraded_job_count": 0,
        "error_job_count": error_job_count,
        "evidence_gaps": [],
        "failure_count_24h": failure_count_24h,
        "job_count": 51,
        "mode": "local_agent",
        "scheduler_running": True,
        "stale_after_seconds": 300,
        "state_age_seconds": state_age_seconds,
        "state_updated_at": BASE_TIME.isoformat(),
        "status": status,
        "success_count_24h": 2594,
    }


def _write_json(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
