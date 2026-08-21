from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from local_monitoring_agents.scheduler_metrics import (
    collect_scheduler_metrics_local_agent_snapshot,
    load_scheduler_metrics_local_agent_facade_snapshot,
    run_scheduler_metrics_local_agent_once,
)
from scripts.run_scheduler_metrics_local_agent import main


BASE_TIME = datetime(2026, 8, 17, 11, 0, tzinfo=timezone.utc)
PRAGUE_NOW = "2026-08-17T13:00:00"


def test_scheduler_metrics_local_agent_collects_safe_bounded_aggregate(tmp_path):
    metrics_file = tmp_path / "scheduler_metrics.json"
    _write_scheduler_metrics(metrics_file)

    snapshot = collect_scheduler_metrics_local_agent_snapshot(
        metrics_file=metrics_file,
        checked_at=BASE_TIME,
    )

    assert snapshot.status == "degraded"
    assert snapshot.source_metrics_present is True
    assert snapshot.source_schema_valid is True
    assert snapshot.scheduler_running is True
    assert snapshot.heartbeat_age_seconds == 0.0
    assert snapshot.job_count == 3
    assert snapshot.success_count_24h == 10
    assert snapshot.failure_count_24h == 1
    assert snapshot.error_job_count == 1
    assert snapshot.degraded_job_count == 1
    assert [job.job_id for job in snapshot.jobs] == [
        "daily_job",
        "quarter_hour_job",
        "skipped_job",
    ]
    assert [job.last_status_class for job in snapshot.jobs] == [
        "error",
        "success",
        "skipped",
    ]

    serialized = json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True)
    assert "SHOULD_NOT_LEAK" not in serialized
    assert "database_unavailable" not in serialized
    assert str(metrics_file) not in serialized
    assert "skipped (" not in serialized


def test_scheduler_metrics_local_agent_writes_and_loads_agent_owned_state(tmp_path):
    metrics_file = tmp_path / "scheduler_metrics.json"
    state_file = tmp_path / "agent-state" / "state.json"
    _write_scheduler_metrics(metrics_file)

    snapshot = run_scheduler_metrics_local_agent_once(
        metrics_file=metrics_file,
        state_file=state_file,
        checked_at=BASE_TIME,
    )
    facade_snapshot = load_scheduler_metrics_local_agent_facade_snapshot(
        state_file=state_file,
        checked_at=BASE_TIME + timedelta(seconds=15),
    )

    assert snapshot.status == "degraded"
    assert state_file.is_file()
    assert (state_file.parent / "observer_writer.lock").is_file()
    assert facade_snapshot.status == "degraded"
    assert facade_snapshot.state_updated_at == BASE_TIME
    assert facade_snapshot.state_age_seconds == 15.0
    assert facade_snapshot.job_count == 3
    assert facade_snapshot.evidence_gaps == ()


def test_scheduler_metrics_local_agent_missing_source_is_safe_error(tmp_path):
    snapshot = collect_scheduler_metrics_local_agent_snapshot(
        metrics_file=tmp_path / "missing.json",
        checked_at=BASE_TIME,
    )

    assert snapshot.status == "error"
    assert snapshot.source_metrics_present is False
    assert snapshot.source_schema_valid is False
    assert snapshot.evidence_gaps == ("source_metrics_missing",)


def test_scheduler_metrics_local_agent_cli_writes_sanitized_summary(
    tmp_path,
    capsys,
):
    metrics_file = tmp_path / "scheduler_metrics.json"
    state_file = tmp_path / "agent-state" / "state.json"
    _write_scheduler_metrics(metrics_file)

    result = main(
        [
            "--metrics-file",
            str(metrics_file),
            "--state-file",
            str(state_file),
            "--heartbeat-ttl-seconds",
            "999999999",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "scheduler_metrics_local_agent_cycle"
    assert payload["agent_key"] == "scheduler_metrics"
    assert payload["status"] == "degraded"
    assert "SHOULD_NOT_LEAK" not in json.dumps(payload)
    assert state_file.is_file()


def _write_scheduler_metrics(metrics_file):
    payload = {
        "scheduler_running": True,
        "last_heartbeat": PRAGUE_NOW,
        "jobs": {
            "quarter_hour_job": {
                "last_run": "2026-08-17T12:55:00",
                "last_status": "success",
                "last_duration_seconds": 1.5,
                "next_run": "2026-08-17T13:16:05+02:00",
                "failure_count_24h": 0,
                "success_count_24h": 10,
            },
            "daily_job": {
                "last_run": "2026-08-17T00:15:00",
                "last_status": "error",
                "last_duration_seconds": 2.0,
                "next_run": "2026-08-18T00:15:05+02:00",
                "failure_count_24h": 1,
                "success_count_24h": 0,
            },
            "skipped_job": {
                "last_run": "2026-08-17T12:40:00",
                "last_status": "skipped (database_unavailable SHOULD_NOT_LEAK)",
                "last_duration_seconds": None,
                "next_run": None,
                "failure_count_24h": 0,
                "success_count_24h": 0,
            },
        },
        "job_success_timestamps": {
            "quarter_hour_job": ["2026-08-17T12:55:00"],
        },
        "job_failure_timestamps": {
            "daily_job": ["2026-08-17T00:15:00"],
        },
        "job_duration_samples": {
            "quarter_hour_job": [
                {
                    "recorded_at": "2026-08-17T12:55:00",
                    "duration_seconds": 1.5,
                }
            ],
        },
    }
    metrics_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
