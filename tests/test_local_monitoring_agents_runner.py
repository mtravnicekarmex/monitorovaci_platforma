from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from scripts.run_local_monitoring_agents import main


BASE_TIME = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_local_monitoring_agents_runner_runs_all_agents_with_sanitized_summary(
    tmp_path,
    capsys,
):
    db_file = tmp_path / "database_availability.sqlite3"
    metrics_file = tmp_path / "scheduler_metrics.json"
    database_state_file = tmp_path / "state" / "database" / "state.json"
    scheduler_state_file = tmp_path / "state" / "scheduler" / "state.json"
    _write_database_availability_store(db_file)
    _write_scheduler_metrics(metrics_file)

    result = main(
        [
            "--database-availability-db-file",
            str(db_file),
            "--database-availability-state-file",
            str(database_state_file),
            "--scheduler-metrics-file",
            str(metrics_file),
            "--scheduler-metrics-state-file",
            str(scheduler_state_file),
            "--scheduler-heartbeat-ttl-seconds",
            "999999999",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "local_monitoring_agents_cycle"
    assert payload["runner_version"] == 1
    assert payload["agent_count"] == 2
    assert payload["status"] == "degraded"
    assert [agent["agent_key"] for agent in payload["agents"]] == [
        "database_availability",
        "scheduler_metrics",
    ]
    assert database_state_file.is_file()
    assert scheduler_state_file.is_file()

    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "SHOULD_NOT_LEAK" not in serialized
    assert "database_unavailable" not in serialized
    assert str(db_file) not in serialized
    assert str(metrics_file) not in serialized
    assert "reason" not in serialized
    assert "label" not in serialized


def test_local_monitoring_agents_runner_can_select_one_agent(tmp_path, capsys):
    db_file = tmp_path / "database_availability.sqlite3"
    database_state_file = tmp_path / "state" / "database" / "state.json"
    scheduler_state_file = tmp_path / "state" / "scheduler" / "state.json"
    _write_database_availability_store(db_file)

    result = main(
        [
            "--agent",
            "database_availability",
            "--database-availability-db-file",
            str(db_file),
            "--database-availability-state-file",
            str(database_state_file),
            "--scheduler-metrics-state-file",
            str(scheduler_state_file),
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["agent_count"] == 1
    assert payload["agents"][0]["agent_key"] == "database_availability"
    assert database_state_file.is_file()
    assert not scheduler_state_file.exists()


def test_local_monitoring_agents_task_registration_is_bounded():
    source = (
        PROJECT_ROOT / "scripts" / "register_local_monitoring_agents_task.ps1"
    ).read_text(encoding="utf-8")

    assert "MonitoringLocalAgents" in source
    assert "run_local_monitoring_agents.py" in source
    assert "New-ScheduledTaskAction" in source
    assert "-WorkingDirectory $resolvedProjectRoot" in source
    assert "-RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)" in source
    assert "-MultipleInstances IgnoreNew" in source
    assert "-ExecutionTimeLimit (New-TimeSpan -Minutes 3)" in source
    assert "-LogonType Interactive" in source
    assert "-RunLevel Limited" in source
    assert "Start-ScheduledTask" not in source
    assert "Stop-ScheduledTask" not in source
    assert "Unregister-ScheduledTask" not in source
    assert "ExecutionPolicy" not in source
    assert ".env" not in source


def _write_database_availability_store(db_file):
    with sqlite3.connect(db_file) as connection:
        connection.executescript(
            """
            CREATE TABLE database_availability_state (
                service_key TEXT PRIMARY KEY,
                service_label TEXT NOT NULL,
                is_available INTEGER NOT NULL,
                outage_started_at TEXT,
                last_checked_at TEXT NOT NULL,
                last_changed_at TEXT NOT NULL,
                last_reason TEXT,
                failed_check_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE database_availability_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_key TEXT NOT NULL,
                service_label TEXT NOT NULL,
                event_type TEXT NOT NULL
                    CHECK (event_type IN ('unavailable', 'recovered')),
                occurred_at TEXT NOT NULL,
                outage_started_at TEXT NOT NULL,
                outage_ended_at TEXT,
                reason TEXT,
                failed_check_count INTEGER NOT NULL DEFAULT 0,
                delivered_at TEXT
            );
            """
        )
        connection.execute(
            """
            INSERT INTO database_availability_state (
                service_key,
                service_label,
                is_available,
                outage_started_at,
                last_checked_at,
                last_changed_at,
                last_reason,
                failed_check_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "postgres",
                "PostgreSQL label SHOULD_NOT_LEAK",
                1,
                None,
                (BASE_TIME - timedelta(minutes=1)).isoformat(),
                (BASE_TIME - timedelta(minutes=1)).isoformat(),
                None,
                0,
            ),
        )


def _write_scheduler_metrics(metrics_file):
    payload = {
        "scheduler_running": True,
        "last_heartbeat": "2026-08-17T10:00:00",
        "jobs": {
            "quarter_hour_job": {
                "last_run": "2026-08-17T09:55:00",
                "last_status": "success",
                "last_duration_seconds": 1.0,
                "next_run": "2026-08-17T10:16:05+02:00",
                "failure_count_24h": 0,
                "success_count_24h": 1,
            },
            "skipped_job": {
                "last_run": "2026-08-17T09:40:00",
                "last_status": "skipped (database_unavailable SHOULD_NOT_LEAK)",
                "last_duration_seconds": None,
                "next_run": None,
                "failure_count_24h": 0,
                "success_count_24h": 0,
            },
        },
    }
    metrics_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
