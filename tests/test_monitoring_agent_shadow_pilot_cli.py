from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from monitoring_agent.incident_store import IncidentStateStore
from monitoring_agent.incidents import IncidentEvaluation, IncidentTransition
from monitoring_agent.shadow_pilot_cli import main


BASE_TIME = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)


def test_export_agent_events_reads_incident_state_without_env(tmp_path):
    state_file = _write_incident_state(tmp_path)
    output_path = tmp_path / "agent-events.json"

    result = main(
        [
            "export-agent-events",
            "--agent-state-file",
            str(state_file),
            "--period-start",
            BASE_TIME.isoformat(),
            "--period-end",
            (BASE_TIME + timedelta(hours=1)).isoformat(),
            "--json-output",
            str(output_path),
        ]
    )

    assert result == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["event"] == "monitoring_shadow_pilot_events"
    assert payload["source"] == "monitoring_agent"
    assert [event["action"] for event in payload["events"]] == [
        "opened",
        "recovered",
    ]
    assert all(event["source"] == "monitoring_agent" for event in payload["events"])


def test_compare_uses_supplied_json_files_and_writes_review_outputs(tmp_path, capsys):
    state_file = _write_incident_state(tmp_path)
    legacy_events = {
        "events": [
            {
                "action": "alerted",
                "contract_version": 1,
                "event_reference": "legacy-db-event:1",
                "incident_key": "endpoint:system_database",
                "occurred_at": (BASE_TIME + timedelta(seconds=90)).isoformat(),
                "severity": "critical",
                "source": "legacy_alert",
                "summary": "sanitized database alert",
            },
            {
                "action": "resolved",
                "contract_version": 1,
                "event_reference": "legacy-db-event:2",
                "incident_key": "endpoint:system_database",
                "occurred_at": (BASE_TIME + timedelta(seconds=260)).isoformat(),
                "severity": "critical",
                "source": "legacy_alert",
                "summary": "sanitized database recovery",
            },
        ]
    }
    legacy_path = tmp_path / "legacy-events.json"
    legacy_path.write_text(
        json.dumps(legacy_events, ensure_ascii=False),
        encoding="utf-8",
    )
    comparison_json_path = tmp_path / "comparison.json"
    comparison_md_path = tmp_path / "comparison.md"

    result = main(
        [
            "compare",
            "--agent-state-file",
            str(state_file),
            "--legacy-events-file",
            str(legacy_path),
            "--period-start",
            BASE_TIME.isoformat(),
            "--period-end",
            (BASE_TIME + timedelta(hours=1)).isoformat(),
            "--match-window-seconds",
            "120",
            "--duplicate-window-seconds",
            "60",
            "--json-output",
            str(comparison_json_path),
            "--markdown-output",
            str(comparison_md_path),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == ""
    payload = json.loads(comparison_json_path.read_text(encoding="utf-8"))
    assert payload["event"] == "monitoring_shadow_pilot_comparison"
    assert payload["mode"] == "shadow_only"
    assert payload["metrics"]["matched_detection_count"] == 1
    assert payload["metrics"]["matched_recovery_count"] == 1
    assert payload["metrics"]["false_positive_count"] == 0
    assert payload["metrics"]["false_negative_count"] == 0
    assert "legacy alerts remain authoritative" in comparison_md_path.read_text(
        encoding="utf-8",
    )


def test_compare_rejects_wrong_stream_source(tmp_path):
    state_file = _write_incident_state(tmp_path)
    legacy_path = tmp_path / "legacy-events.json"
    legacy_path.write_text(
        json.dumps(
            [
                {
                    "action": "alerted",
                    "incident_key": "endpoint:system_database",
                    "occurred_at": BASE_TIME.isoformat(),
                    "source": "monitoring_agent",
                }
            ]
        ),
        encoding="utf-8",
    )

    try:
        main(
            [
                "compare",
                "--agent-state-file",
                str(state_file),
                "--legacy-events-file",
                str(legacy_path),
                "--period-start",
                BASE_TIME.isoformat(),
                "--period-end",
                (BASE_TIME + timedelta(hours=1)).isoformat(),
            ]
        )
    except SystemExit as exc:
        assert "source does not match input stream" in str(exc)
    else:
        raise AssertionError("expected shadow pilot CLI to reject wrong source")


def _write_incident_state(tmp_path):
    state_dir = tmp_path / "state"
    store = IncidentStateStore(state_dir)
    store.apply_evaluation(
        IncidentEvaluation(
            rule_version=1,
            states=(),
            transitions=(
                _transition("opened", 120),
                _transition("recovered", 300),
            ),
        ),
        now=BASE_TIME + timedelta(seconds=301),
    )
    return state_dir / "incident_state.json"


def _transition(action: str, offset_seconds: int) -> IncidentTransition:
    return IncidentTransition(
        incident_key="endpoint:system_database",
        action=action,
        kind="endpoint",
        subject="system_database",
        severity="critical",
        status="resolved" if action == "recovered" else "active",
        reason=f"synthetic_{action}",
        observed_at=BASE_TIME + timedelta(seconds=offset_seconds),
        cycle_sequence=offset_seconds // 60,
        failure_count=2,
        recovery_count=2 if action == "recovered" else 0,
        occurrence_count=1,
    )
