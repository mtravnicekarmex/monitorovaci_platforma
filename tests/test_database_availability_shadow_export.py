from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3

from monitoring_agent.shadow_pilot import (
    SOURCE_LEGACY_ALERT,
    events_from_shadow_pilot_payload,
)
from scripts.export_database_availability_shadow_events import (
    export_database_availability_events,
    main,
)


BASE_TIME = datetime(2026, 7, 18, 6, 0, tzinfo=timezone.utc)


def test_export_database_availability_events_is_sanitized_and_delivered_only(tmp_path):
    db_file = tmp_path / "database_availability.sqlite3"
    _write_store(db_file)

    payload = export_database_availability_events(
        db_file=db_file,
        period_start=BASE_TIME,
        period_end=BASE_TIME + timedelta(hours=2),
    )

    assert payload["event"] == "database_availability_legacy_alert_shadow_events"
    assert payload["source"] == SOURCE_LEGACY_ALERT
    assert payload["delivered_only"] is True
    assert payload["event_count"] == 2
    assert [event["action"] for event in payload["events"]] == [
        "alerted",
        "resolved",
    ]
    assert {event["incident_key"] for event in payload["events"]} == {
        "endpoint:system_database",
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    assert "SHOULD_NOT_LEAK" not in serialized
    assert "reason" not in serialized

    parsed_events = events_from_shadow_pilot_payload(
        payload,
        default_source=SOURCE_LEGACY_ALERT,
    )
    assert len(parsed_events) == 2
    assert all(event.source == SOURCE_LEGACY_ALERT for event in parsed_events)


def test_export_database_availability_cli_writes_json_output(tmp_path):
    db_file = tmp_path / "database_availability.sqlite3"
    output_path = tmp_path / "legacy-alert-events.json"
    _write_store(db_file)

    result = main(
        [
            "--db-file",
            str(db_file),
            "--period-start",
            BASE_TIME.isoformat(),
            "--period-end",
            (BASE_TIME + timedelta(hours=2)).isoformat(),
            "--json-output",
            str(output_path),
        ]
    )

    assert result == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["event_count"] == 2
    assert output_path.read_text(encoding="utf-8").endswith("\n")


def _write_store(db_file):
    with sqlite3.connect(db_file) as connection:
        connection.executescript(
            """
            CREATE TABLE database_availability_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_key TEXT NOT NULL,
                service_label TEXT NOT NULL,
                event_type TEXT NOT NULL,
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
                "PostgreSQL",
                "unavailable",
                (BASE_TIME + timedelta(minutes=30)).isoformat(),
                (BASE_TIME + timedelta(minutes=30)).isoformat(),
                "password=SHOULD_NOT_LEAK",
                1,
                (BASE_TIME + timedelta(minutes=31)).isoformat(),
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
                outage_ended_at,
                reason,
                failed_check_count,
                delivered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "postgres",
                "PostgreSQL",
                "recovered",
                (BASE_TIME + timedelta(minutes=45)).isoformat(),
                (BASE_TIME + timedelta(minutes=30)).isoformat(),
                (BASE_TIME + timedelta(minutes=45)).isoformat(),
                "password=SHOULD_NOT_LEAK",
                1,
                (BASE_TIME + timedelta(minutes=46)).isoformat(),
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
                "MS SQL",
                "unavailable",
                (BASE_TIME + timedelta(minutes=50)).isoformat(),
                (BASE_TIME + timedelta(minutes=50)).isoformat(),
                "pending raw reason",
                1,
                None,
            ),
        )
