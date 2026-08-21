from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

from local_monitoring_agents.database_availability import (
    collect_database_availability_local_agent_snapshot,
    load_database_availability_local_agent_facade_snapshot,
    run_database_availability_local_agent_once,
)
from scripts.run_database_availability_local_agent import main


BASE_TIME = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_database_availability_local_agent_collects_safe_bounded_aggregate(
    tmp_path,
):
    db_file = tmp_path / "database_availability.sqlite3"
    _write_database_availability_store(db_file)

    snapshot = collect_database_availability_local_agent_snapshot(
        db_file=db_file,
        checked_at=BASE_TIME,
    )

    assert snapshot.status == "degraded"
    assert snapshot.source_store_present is True
    assert snapshot.source_schema_valid is True
    assert snapshot.service_count == 2
    assert snapshot.unavailable_service_count == 1
    assert snapshot.stale_service_count == 0
    assert snapshot.pending_event_count == 1
    assert snapshot.delivered_event_count_24h == 1
    assert snapshot.recent_transition_count == 2
    assert [service.service_key for service in snapshot.services] == [
        "mssql",
        "postgres",
    ]
    assert snapshot.services[0].available is False
    assert snapshot.services[0].failed_check_count == 2

    serialized = json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True)
    assert "password=SHOULD_NOT_LEAK" not in serialized
    assert "MS SQL internal label SHOULD_NOT_LEAK" not in serialized
    assert str(db_file) not in serialized
    assert "reason" not in serialized


def test_database_availability_local_agent_writes_and_loads_agent_owned_state(
    tmp_path,
):
    db_file = tmp_path / "database_availability.sqlite3"
    state_file = tmp_path / "agent-state" / "state.json"
    _write_database_availability_store(db_file)

    snapshot = run_database_availability_local_agent_once(
        db_file=db_file,
        state_file=state_file,
        checked_at=BASE_TIME,
    )
    facade_snapshot = load_database_availability_local_agent_facade_snapshot(
        state_file=state_file,
        checked_at=BASE_TIME + timedelta(seconds=30),
    )

    assert snapshot.status == "degraded"
    assert state_file.is_file()
    assert (state_file.parent / "observer_writer.lock").is_file()
    assert facade_snapshot.status == "degraded"
    assert facade_snapshot.state_updated_at == BASE_TIME
    assert facade_snapshot.state_age_seconds == 30.0
    assert facade_snapshot.service_count == 2
    assert facade_snapshot.evidence_gaps == ()


def test_database_availability_local_agent_missing_state_facade_is_unavailable(
    tmp_path,
):
    facade_snapshot = load_database_availability_local_agent_facade_snapshot(
        state_file=tmp_path / "missing" / "state.json",
        checked_at=BASE_TIME,
    )

    assert facade_snapshot.status == "unavailable"
    assert facade_snapshot.state_updated_at is None
    assert facade_snapshot.state_age_seconds is None
    assert facade_snapshot.evidence_gaps == ("local_agent_state_missing",)


def test_database_availability_local_agent_missing_source_is_safe_error(tmp_path):
    snapshot = collect_database_availability_local_agent_snapshot(
        db_file=tmp_path / "missing.sqlite3",
        checked_at=BASE_TIME,
    )

    assert snapshot.status == "error"
    assert snapshot.source_store_present is False
    assert snapshot.source_schema_valid is False
    assert snapshot.service_count == 0
    assert snapshot.evidence_gaps == ("source_store_missing",)


def test_database_availability_local_agent_cli_writes_sanitized_summary(
    tmp_path,
    capsys,
):
    db_file = tmp_path / "database_availability.sqlite3"
    state_file = tmp_path / "agent-state" / "state.json"
    _write_database_availability_store(db_file)

    result = main(
        [
            "--db-file",
            str(db_file),
            "--state-file",
            str(state_file),
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["event"] == "database_availability_local_agent_cycle"
    assert payload["agent_key"] == "database_availability"
    assert payload["status"] == "degraded"
    assert "password=SHOULD_NOT_LEAK" not in json.dumps(payload)
    assert state_file.is_file()


def test_database_availability_local_agent_task_registration_is_bounded():
    source = (
        PROJECT_ROOT
        / "scripts"
        / "register_database_availability_local_agent_task.ps1"
    ).read_text(encoding="utf-8")

    assert "MonitoringDatabaseAvailabilityLocalAgent" in source
    assert "run_database_availability_local_agent.py" in source
    assert "New-ScheduledTaskAction" in source
    assert "-WorkingDirectory $resolvedProjectRoot" in source
    assert "-RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)" in source
    assert "-MultipleInstances IgnoreNew" in source
    assert "-ExecutionTimeLimit (New-TimeSpan -Minutes 2)" in source
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
                "PostgreSQL internal label SHOULD_NOT_LEAK",
                1,
                None,
                (BASE_TIME - timedelta(minutes=3)).isoformat(),
                (BASE_TIME - timedelta(minutes=3)).isoformat(),
                None,
                0,
            ),
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
                "mssql",
                "MS SQL internal label SHOULD_NOT_LEAK",
                0,
                (BASE_TIME - timedelta(minutes=10)).isoformat(),
                (BASE_TIME - timedelta(minutes=2)).isoformat(),
                (BASE_TIME - timedelta(minutes=10)).isoformat(),
                "password=SHOULD_NOT_LEAK",
                2,
            ),
        )
        connection.execute(
            """
            INSERT INTO database_availability_events (
                service_key,
                service_label,
                event_type,
                occurred_at,
                outage_started_at,
                reason,
                failed_check_count,
                delivered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "mssql",
                "MS SQL internal label SHOULD_NOT_LEAK",
                "unavailable",
                (BASE_TIME - timedelta(minutes=10)).isoformat(),
                (BASE_TIME - timedelta(minutes=10)).isoformat(),
                "password=SHOULD_NOT_LEAK",
                1,
                (BASE_TIME - timedelta(minutes=9)).isoformat(),
            ),
        )
        connection.execute(
            """
            INSERT INTO database_availability_events (
                service_key,
                service_label,
                event_type,
                occurred_at,
                outage_started_at,
                reason,
                failed_check_count,
                delivered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "postgres",
                "PostgreSQL internal label SHOULD_NOT_LEAK",
                "unavailable",
                (BASE_TIME - timedelta(minutes=5)).isoformat(),
                (BASE_TIME - timedelta(minutes=5)).isoformat(),
                "password=SHOULD_NOT_LEAK",
                1,
                None,
            ),
        )
