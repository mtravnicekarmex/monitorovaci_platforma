from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from typing import Iterable


DEFAULT_DATABASE_AVAILABILITY_PATH = (
    Path(__file__).resolve().parent / "data" / "database_availability.sqlite3"
)


@dataclass(frozen=True)
class DatabaseAvailabilityObservation:
    service_key: str
    service_label: str
    is_available: bool
    reason: str | None = None


@dataclass(frozen=True)
class DatabaseAvailabilityEvent:
    id: int
    service_key: str
    service_label: str
    event_type: str
    occurred_at: datetime
    outage_started_at: datetime
    outage_ended_at: datetime | None
    reason: str | None
    failed_check_count: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class DatabaseAvailabilityStore:
    def __init__(self, path: Path | None = None):
        self.path = path or DEFAULT_DATABASE_AVAILABILITY_PATH

    def record_observations(
        self,
        observations: Iterable[DatabaseAvailabilityObservation],
        *,
        checked_at: datetime | None = None,
    ) -> None:
        resolved_checked_at = checked_at or _utc_now()
        checked_at_text = _serialize_datetime(resolved_checked_at)
        resolved_observations = tuple(observations)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=5) as connection:
            self._ensure_schema(connection)
            for observation in resolved_observations:
                self._record_observation(
                    connection,
                    observation,
                    checked_at=resolved_checked_at,
                    checked_at_text=checked_at_text,
                )

    def load_pending_events(self) -> tuple[DatabaseAvailabilityEvent, ...]:
        if not self.path.exists():
            return ()

        with sqlite3.connect(self.path, timeout=5) as connection:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT
                    id,
                    service_key,
                    service_label,
                    event_type,
                    occurred_at,
                    outage_started_at,
                    outage_ended_at,
                    reason,
                    failed_check_count
                FROM database_availability_events
                WHERE delivered_at IS NULL
                ORDER BY id
                """
            ).fetchall()

        return tuple(
            DatabaseAvailabilityEvent(
                id=int(row[0]),
                service_key=str(row[1]),
                service_label=str(row[2]),
                event_type=str(row[3]),
                occurred_at=_parse_datetime(str(row[4])),
                outage_started_at=_parse_datetime(str(row[5])),
                outage_ended_at=(
                    _parse_datetime(str(row[6]))
                    if row[6] is not None
                    else None
                ),
                reason=str(row[7]) if row[7] is not None else None,
                failed_check_count=int(row[8]),
            )
            for row in rows
        )

    def mark_events_delivered(
        self,
        event_ids: Iterable[int],
        *,
        delivered_at: datetime | None = None,
    ) -> None:
        resolved_ids = tuple(dict.fromkeys(int(event_id) for event_id in event_ids))
        if not resolved_ids:
            return

        placeholders = ",".join("?" for _ in resolved_ids)
        delivered_at_text = _serialize_datetime(delivered_at or _utc_now())
        with sqlite3.connect(self.path, timeout=5) as connection:
            self._ensure_schema(connection)
            connection.execute(
                f"""
                UPDATE database_availability_events
                SET delivered_at = ?
                WHERE id IN ({placeholders})
                """,
                (delivered_at_text, *resolved_ids),
            )

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS database_availability_state (
                service_key TEXT PRIMARY KEY,
                service_label TEXT NOT NULL,
                is_available INTEGER NOT NULL,
                outage_started_at TEXT,
                last_checked_at TEXT NOT NULL,
                last_changed_at TEXT NOT NULL,
                last_reason TEXT,
                failed_check_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS database_availability_events (
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

            CREATE INDEX IF NOT EXISTS
                ix_database_availability_events_pending
            ON database_availability_events (delivered_at, id);
            """
        )

    @staticmethod
    def _record_observation(
        connection: sqlite3.Connection,
        observation: DatabaseAvailabilityObservation,
        *,
        checked_at: datetime,
        checked_at_text: str,
    ) -> None:
        existing = connection.execute(
            """
            SELECT
                service_label,
                is_available,
                outage_started_at,
                last_reason,
                failed_check_count
            FROM database_availability_state
            WHERE service_key = ?
            """,
            (observation.service_key,),
        ).fetchone()

        if existing is None:
            outage_started_at = None
            failed_check_count = 0
            if not observation.is_available:
                outage_started_at = checked_at_text
                failed_check_count = 1
                DatabaseAvailabilityStore._insert_event(
                    connection,
                    observation=observation,
                    event_type="unavailable",
                    occurred_at=checked_at,
                    outage_started_at=checked_at,
                    outage_ended_at=None,
                    reason=observation.reason,
                    failed_check_count=failed_check_count,
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
                    observation.service_key,
                    observation.service_label,
                    int(observation.is_available),
                    outage_started_at,
                    checked_at_text,
                    checked_at_text,
                    observation.reason if not observation.is_available else None,
                    failed_check_count,
                ),
            )
            return

        was_available = bool(existing[1])
        previous_outage_started_at = (
            _parse_datetime(str(existing[2]))
            if existing[2] is not None
            else None
        )
        previous_reason = str(existing[3]) if existing[3] is not None else None
        previous_failed_check_count = int(existing[4] or 0)

        if was_available and not observation.is_available:
            DatabaseAvailabilityStore._insert_event(
                connection,
                observation=observation,
                event_type="unavailable",
                occurred_at=checked_at,
                outage_started_at=checked_at,
                outage_ended_at=None,
                reason=observation.reason,
                failed_check_count=1,
            )
            connection.execute(
                """
                UPDATE database_availability_state
                SET
                    service_label = ?,
                    is_available = 0,
                    outage_started_at = ?,
                    last_checked_at = ?,
                    last_changed_at = ?,
                    last_reason = ?,
                    failed_check_count = 1
                WHERE service_key = ?
                """,
                (
                    observation.service_label,
                    checked_at_text,
                    checked_at_text,
                    checked_at_text,
                    observation.reason,
                    observation.service_key,
                ),
            )
            return

        if not was_available and not observation.is_available:
            connection.execute(
                """
                UPDATE database_availability_state
                SET
                    service_label = ?,
                    last_checked_at = ?,
                    last_reason = ?,
                    failed_check_count = failed_check_count + 1
                WHERE service_key = ?
                """,
                (
                    observation.service_label,
                    checked_at_text,
                    observation.reason,
                    observation.service_key,
                ),
            )
            return

        if not was_available and observation.is_available:
            outage_started_at = previous_outage_started_at or checked_at
            DatabaseAvailabilityStore._insert_event(
                connection,
                observation=observation,
                event_type="recovered",
                occurred_at=checked_at,
                outage_started_at=outage_started_at,
                outage_ended_at=checked_at,
                reason=previous_reason,
                failed_check_count=previous_failed_check_count,
            )
            connection.execute(
                """
                UPDATE database_availability_state
                SET
                    service_label = ?,
                    is_available = 1,
                    outage_started_at = NULL,
                    last_checked_at = ?,
                    last_changed_at = ?,
                    last_reason = NULL,
                    failed_check_count = 0
                WHERE service_key = ?
                """,
                (
                    observation.service_label,
                    checked_at_text,
                    checked_at_text,
                    observation.service_key,
                ),
            )
            return

        connection.execute(
            """
            UPDATE database_availability_state
            SET
                service_label = ?,
                last_checked_at = ?,
                last_reason = NULL,
                failed_check_count = 0
            WHERE service_key = ?
            """,
            (
                observation.service_label,
                checked_at_text,
                observation.service_key,
            ),
        )

    @staticmethod
    def _insert_event(
        connection: sqlite3.Connection,
        *,
        observation: DatabaseAvailabilityObservation,
        event_type: str,
        occurred_at: datetime,
        outage_started_at: datetime,
        outage_ended_at: datetime | None,
        reason: str | None,
        failed_check_count: int,
    ) -> None:
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
                failed_check_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.service_key,
                observation.service_label,
                event_type,
                _serialize_datetime(occurred_at),
                _serialize_datetime(outage_started_at),
                (
                    _serialize_datetime(outage_ended_at)
                    if outage_ended_at is not None
                    else None
                ),
                reason,
                failed_check_count,
            ),
        )
