from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys


DEFAULT_DB_PATH = (
    Path(__file__).resolve().parents[1]
    / "core"
    / "scheduler"
    / "data"
    / "database_availability.sqlite3"
)
DEFAULT_INCIDENT_KEY = "endpoint:system_database"
OUTPUT_CONTRACT_VERSION = 1
SOURCE_LEGACY_ALERT = "legacy_alert"
ACTION_BY_EVENT_TYPE = {
    "unavailable": "alerted",
    "recovered": "resolved",
}


def export_database_availability_events(
    *,
    db_file: Path,
    period_start: datetime,
    period_end: datetime,
    incident_key: str = DEFAULT_INCIDENT_KEY,
    delivered_only: bool = True,
) -> dict[str, object]:
    _require_aware_period(period_start, period_end)
    if not incident_key.strip():
        raise ValueError("incident_key must not be empty")
    if not db_file.exists():
        raise ValueError(f"database availability store does not exist: {db_file}")

    rows = _load_rows(
        db_file=db_file,
        period_start=period_start,
        period_end=period_end,
        delivered_only=delivered_only,
    )
    events = [
        _row_to_shadow_event(row, incident_key=incident_key.strip())
        for row in rows
    ]
    return {
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "delivered_only": delivered_only,
        "event": "database_availability_legacy_alert_shadow_events",
        "event_count": len(events),
        "events": events,
        "period": {
            "boundary": "start_inclusive_end_exclusive",
            "end": period_end.isoformat(),
            "start": period_start.isoformat(),
        },
        "source": SOURCE_LEGACY_ALERT,
        "source_store": "core.scheduler.database_availability_events",
    }


def _load_rows(
    *,
    db_file: Path,
    period_start: datetime,
    period_end: datetime,
    delivered_only: bool,
) -> list[dict[str, object]]:
    delivered_filter = "AND delivered_at IS NOT NULL" if delivered_only else ""
    query = f"""
        SELECT
            id,
            service_key,
            event_type,
            occurred_at,
            delivered_at
        FROM database_availability_events
        WHERE occurred_at >= ?
          AND occurred_at < ?
          {delivered_filter}
        ORDER BY occurred_at, id
    """
    with sqlite3.connect(db_file) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            query,
            (period_start.isoformat(), period_end.isoformat()),
        ).fetchall()
    return [dict(row) for row in rows]


def _row_to_shadow_event(
    row: dict[str, object],
    *,
    incident_key: str,
) -> dict[str, object]:
    event_type = str(row["event_type"])
    action = ACTION_BY_EVENT_TYPE.get(event_type)
    if action is None:
        raise ValueError(f"unsupported database availability event_type: {event_type}")
    service_key = str(row["service_key"]).strip().lower()
    if not service_key:
        raise ValueError("database availability service_key must not be empty")
    event_id = int(row["id"])
    occurred_at = _parse_datetime(str(row["occurred_at"]), context="occurred_at")
    return {
        "action": action,
        "contract_version": OUTPUT_CONTRACT_VERSION,
        "event_reference": f"database_availability_event:{event_id}",
        "incident_key": incident_key,
        "occurred_at": occurred_at.isoformat(),
        "severity": "critical",
        "source": SOURCE_LEGACY_ALERT,
        "summary": f"database_availability service={service_key} event={event_type}",
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Export delivered database-availability legacy alerts as sanitized "
            "shadow-pilot event JSON."
        )
    )
    parser.add_argument("--db-file", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--period-start", required=True)
    parser.add_argument("--period-end", required=True)
    parser.add_argument("--incident-key", default=DEFAULT_INCIDENT_KEY)
    parser.add_argument(
        "--include-undelivered",
        action="store_true",
        help="Include pending availability events that were not marked delivered.",
    )
    parser.add_argument("--json-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        payload = export_database_availability_events(
            db_file=args.db_file,
            period_start=_parse_datetime(args.period_start, context="period_start"),
            period_end=_parse_datetime(args.period_end, context="period_end"),
            incident_key=args.incident_key,
            delivered_only=not args.include_undelivered,
        )
    except (OSError, sqlite3.Error, ValueError) as exc:
        raise SystemExit(f"database availability shadow export error: {exc}") from exc

    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.json_output is None:
        sys.stdout.write(content)
    else:
        output_path = args.json_output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
    return 0


def _parse_datetime(value: str, *, context: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{context} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{context} must be timezone-aware")
    return parsed


def _require_aware_period(period_start: datetime, period_end: datetime) -> None:
    for name, value in (
        ("period_start", period_start),
        ("period_end", period_end),
    ):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
    if period_start >= period_end:
        raise ValueError("period_start must be before period_end")


if __name__ == "__main__":
    raise SystemExit(main())
