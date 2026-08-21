from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile

from core.scheduler.database_availability_state import (
    DEFAULT_DATABASE_AVAILABILITY_PATH,
)
from monitoring_agent.store import StateWriterLock


DATABASE_AVAILABILITY_LOCAL_AGENT_CONTRACT_VERSION = 1
DATABASE_AVAILABILITY_LOCAL_AGENT_KEY = "database_availability"
LOCAL_AGENT_MODE = "local_agent"
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_ERROR = "error"
STATUS_UNAVAILABLE = "unavailable"
LOCAL_AGENT_STATUSES = {
    STATUS_OK,
    STATUS_DEGRADED,
    STATUS_ERROR,
    STATUS_UNAVAILABLE,
}
DEFAULT_STALE_AFTER_SECONDS = 1_800.0
DEFAULT_RECENT_WINDOW_SECONDS = 86_400.0
DEFAULT_MAX_SERVICES = 20
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_AVAILABILITY_LOCAL_AGENT_STATE_FILE = (
    PROJECT_ROOT
    / ".local-monitoring-agent-state"
    / DATABASE_AVAILABILITY_LOCAL_AGENT_KEY
    / "state.json"
)
REQUIRED_SOURCE_TABLES = {
    "database_availability_state",
    "database_availability_events",
}


class DatabaseAvailabilityLocalAgentError(ValueError):
    """The local database-availability agent state is invalid or ambiguous."""


@dataclass(frozen=True)
class DatabaseAvailabilityServiceAggregate:
    service_key: str
    status: str
    available: bool
    failed_check_count: int
    last_checked_at: datetime | None
    last_checked_age_seconds: float | None
    outage_age_seconds: float | None

    def __post_init__(self) -> None:
        if not self.service_key.strip():
            raise ValueError("service_key is required")
        if self.status not in {STATUS_OK, STATUS_DEGRADED}:
            raise ValueError("service status is invalid")
        if (
            isinstance(self.failed_check_count, bool)
            or not isinstance(self.failed_check_count, int)
            or self.failed_check_count < 0
        ):
            raise ValueError("failed_check_count must not be negative")
        if self.last_checked_at is not None:
            _require_aware_datetime(self.last_checked_at, context="last_checked_at")
        _require_non_negative_or_none(
            self.last_checked_age_seconds,
            context="last_checked_age_seconds",
        )
        _require_non_negative_or_none(
            self.outage_age_seconds,
            context="outage_age_seconds",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "failed_check_count": self.failed_check_count,
            "last_checked_age_seconds": self.last_checked_age_seconds,
            "last_checked_at": _format_datetime(self.last_checked_at),
            "outage_age_seconds": self.outage_age_seconds,
            "service_key": self.service_key,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, value: object) -> DatabaseAvailabilityServiceAggregate:
        payload = _require_object(value, context="service aggregate")
        _require_exact_keys(
            payload,
            required={
                "available",
                "failed_check_count",
                "last_checked_age_seconds",
                "last_checked_at",
                "outage_age_seconds",
                "service_key",
                "status",
            },
            context="service aggregate",
        )
        return cls(
            service_key=_require_string(
                payload["service_key"],
                context="service aggregate service_key",
            ),
            status=_require_string(
                payload["status"],
                context="service aggregate status",
            ),
            available=_require_bool(
                payload["available"],
                context="service aggregate available",
            ),
            failed_check_count=_require_int(
                payload["failed_check_count"],
                context="service aggregate failed_check_count",
            ),
            last_checked_at=_parse_datetime_or_none(
                payload["last_checked_at"],
                context="service aggregate last_checked_at",
            ),
            last_checked_age_seconds=_require_number_or_none(
                payload["last_checked_age_seconds"],
                context="service aggregate last_checked_age_seconds",
            ),
            outage_age_seconds=_require_number_or_none(
                payload["outage_age_seconds"],
                context="service aggregate outage_age_seconds",
            ),
        )


@dataclass(frozen=True)
class DatabaseAvailabilityLocalAgentSnapshot:
    checked_at: datetime
    status: str
    source_store_present: bool
    source_schema_valid: bool
    stale_after_seconds: float
    service_count: int
    unavailable_service_count: int
    stale_service_count: int
    pending_event_count: int
    delivered_event_count_24h: int
    recent_transition_count: int
    services: tuple[DatabaseAvailabilityServiceAggregate, ...]
    evidence_gaps: tuple[str, ...] = ()
    contract_version: int = DATABASE_AVAILABILITY_LOCAL_AGENT_CONTRACT_VERSION
    agent_key: str = DATABASE_AVAILABILITY_LOCAL_AGENT_KEY
    mode: str = LOCAL_AGENT_MODE

    def __post_init__(self) -> None:
        if self.contract_version != DATABASE_AVAILABILITY_LOCAL_AGENT_CONTRACT_VERSION:
            raise ValueError("local agent contract version is unsupported")
        if self.agent_key != DATABASE_AVAILABILITY_LOCAL_AGENT_KEY:
            raise ValueError("local agent key is invalid")
        if self.mode != LOCAL_AGENT_MODE:
            raise ValueError("local agent mode is invalid")
        if self.status not in LOCAL_AGENT_STATUSES:
            raise ValueError("local agent status is invalid")
        _require_aware_datetime(self.checked_at, context="checked_at")
        if self.stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds must be positive")
        for name in (
            "service_count",
            "unavailable_service_count",
            "stale_service_count",
            "pending_event_count",
            "delivered_event_count_24h",
            "recent_transition_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must not be negative")
        services = tuple(self.services)
        if len(services) != self.service_count:
            raise ValueError("service_count does not match services")
        service_keys = [service.service_key for service in services]
        if len(service_keys) != len(set(service_keys)):
            raise ValueError("duplicate service_key in local agent snapshot")
        object.__setattr__(self, "services", services)
        object.__setattr__(
            self,
            "evidence_gaps",
            tuple(_require_string(gap, context="evidence gap") for gap in self.evidence_gaps),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_key": self.agent_key,
            "checked_at": _format_datetime(self.checked_at),
            "contract_version": self.contract_version,
            "delivered_event_count_24h": self.delivered_event_count_24h,
            "evidence_gaps": list(self.evidence_gaps),
            "mode": self.mode,
            "pending_event_count": self.pending_event_count,
            "recent_transition_count": self.recent_transition_count,
            "service_count": self.service_count,
            "services": [service.to_dict() for service in self.services],
            "source_schema_valid": self.source_schema_valid,
            "source_store_present": self.source_store_present,
            "stale_after_seconds": self.stale_after_seconds,
            "stale_service_count": self.stale_service_count,
            "status": self.status,
            "unavailable_service_count": self.unavailable_service_count,
        }

    @classmethod
    def from_dict(cls, value: object) -> DatabaseAvailabilityLocalAgentSnapshot:
        payload = _require_object(value, context="local agent snapshot")
        _require_exact_keys(
            payload,
            required={
                "agent_key",
                "checked_at",
                "contract_version",
                "delivered_event_count_24h",
                "evidence_gaps",
                "mode",
                "pending_event_count",
                "recent_transition_count",
                "service_count",
                "services",
                "source_schema_valid",
                "source_store_present",
                "stale_after_seconds",
                "stale_service_count",
                "status",
                "unavailable_service_count",
            },
            context="local agent snapshot",
        )
        services = payload["services"]
        if not isinstance(services, list):
            raise DatabaseAvailabilityLocalAgentError("services must be an array")
        evidence_gaps = payload["evidence_gaps"]
        if not isinstance(evidence_gaps, list):
            raise DatabaseAvailabilityLocalAgentError(
                "evidence_gaps must be an array"
            )
        return cls(
            checked_at=_parse_datetime(payload["checked_at"], context="checked_at"),
            status=_require_string(payload["status"], context="status"),
            source_store_present=_require_bool(
                payload["source_store_present"],
                context="source_store_present",
            ),
            source_schema_valid=_require_bool(
                payload["source_schema_valid"],
                context="source_schema_valid",
            ),
            stale_after_seconds=_require_number(
                payload["stale_after_seconds"],
                context="stale_after_seconds",
            ),
            service_count=_require_int(
                payload["service_count"],
                context="service_count",
            ),
            unavailable_service_count=_require_int(
                payload["unavailable_service_count"],
                context="unavailable_service_count",
            ),
            stale_service_count=_require_int(
                payload["stale_service_count"],
                context="stale_service_count",
            ),
            pending_event_count=_require_int(
                payload["pending_event_count"],
                context="pending_event_count",
            ),
            delivered_event_count_24h=_require_int(
                payload["delivered_event_count_24h"],
                context="delivered_event_count_24h",
            ),
            recent_transition_count=_require_int(
                payload["recent_transition_count"],
                context="recent_transition_count",
            ),
            services=tuple(
                DatabaseAvailabilityServiceAggregate.from_dict(service)
                for service in services
            ),
            evidence_gaps=tuple(
                _require_string(gap, context="evidence gap")
                for gap in evidence_gaps
            ),
            contract_version=_require_int(
                payload["contract_version"],
                context="contract_version",
            ),
            agent_key=_require_string(payload["agent_key"], context="agent_key"),
            mode=_require_string(payload["mode"], context="mode"),
        )


@dataclass(frozen=True)
class DatabaseAvailabilityLocalAgentFacadeSnapshot:
    status: str
    checked_at: datetime
    state_updated_at: datetime | None
    state_age_seconds: float | None
    stale_after_seconds: float
    service_count: int
    unavailable_service_count: int
    stale_service_count: int
    pending_event_count: int
    delivered_event_count_24h: int
    recent_transition_count: int
    services: tuple[DatabaseAvailabilityServiceAggregate, ...]
    evidence_gaps: tuple[str, ...]
    contract_version: int = DATABASE_AVAILABILITY_LOCAL_AGENT_CONTRACT_VERSION
    agent_key: str = DATABASE_AVAILABILITY_LOCAL_AGENT_KEY
    mode: str = LOCAL_AGENT_MODE


class DatabaseAvailabilityLocalAgentStateStore:
    def __init__(
        self,
        state_file: Path | None = None,
    ) -> None:
        self._state_file = (
            state_file or DEFAULT_DATABASE_AVAILABILITY_LOCAL_AGENT_STATE_FILE
        ).resolve()

    @property
    def state_file(self) -> Path:
        return self._state_file

    @property
    def state_dir(self) -> Path:
        return self._state_file.parent

    def writer_lock(self) -> StateWriterLock:
        return StateWriterLock(self.state_dir)

    def load(self) -> DatabaseAvailabilityLocalAgentSnapshot | None:
        if not self._state_file.exists():
            return None
        try:
            payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatabaseAvailabilityLocalAgentError(
                "local agent state cannot be read"
            ) from exc
        try:
            return DatabaseAvailabilityLocalAgentSnapshot.from_dict(payload)
        except (TypeError, ValueError) as exc:
            raise DatabaseAvailabilityLocalAgentError(
                "local agent state has invalid schema"
            ) from exc

    def write(self, snapshot: DatabaseAvailabilityLocalAgentSnapshot) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            snapshot.to_dict(),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        fd, temporary_name = tempfile.mkstemp(
            prefix="database-availability-agent-",
            suffix=".tmp",
            dir=self._state_file.parent,
            text=True,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.write("\n")
            temporary_path.replace(self._state_file)
        except OSError as exc:
            raise DatabaseAvailabilityLocalAgentError(
                "local agent state could not be written"
            ) from exc
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


def collect_database_availability_local_agent_snapshot(
    *,
    db_file: Path | None = None,
    checked_at: datetime | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    recent_window_seconds: float = DEFAULT_RECENT_WINDOW_SECONDS,
    max_services: int = DEFAULT_MAX_SERVICES,
) -> DatabaseAvailabilityLocalAgentSnapshot:
    resolved_checked_at = _normalize_datetime(checked_at or _utc_now())
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds must be positive")
    if recent_window_seconds <= 0:
        raise ValueError("recent_window_seconds must be positive")
    if isinstance(max_services, bool) or max_services < 1:
        raise ValueError("max_services must be positive")
    source_db = (db_file or DEFAULT_DATABASE_AVAILABILITY_PATH).resolve()
    if not source_db.exists():
        return _error_snapshot(
            checked_at=resolved_checked_at,
            stale_after_seconds=stale_after_seconds,
            source_store_present=False,
            source_schema_valid=False,
            evidence_gaps=("source_store_missing",),
        )

    try:
        with _connect_read_only(source_db) as connection:
            connection.row_factory = sqlite3.Row
            missing_tables = REQUIRED_SOURCE_TABLES - _load_table_names(connection)
            if missing_tables:
                return _error_snapshot(
                    checked_at=resolved_checked_at,
                    stale_after_seconds=stale_after_seconds,
                    source_store_present=True,
                    source_schema_valid=False,
                    evidence_gaps=("source_schema_missing_tables",),
                )
            total_services = _count_services(connection)
            if total_services > max_services:
                return _error_snapshot(
                    checked_at=resolved_checked_at,
                    stale_after_seconds=stale_after_seconds,
                    source_store_present=True,
                    source_schema_valid=True,
                    service_count=total_services,
                    evidence_gaps=("service_count_exceeds_bound",),
                )
            service_rows = _load_service_rows(connection)
            event_counts = _load_event_counts(
                connection,
                checked_at=resolved_checked_at,
                recent_window_seconds=recent_window_seconds,
            )
    except sqlite3.Error:
        return _error_snapshot(
            checked_at=resolved_checked_at,
            stale_after_seconds=stale_after_seconds,
            source_store_present=True,
            source_schema_valid=False,
            evidence_gaps=("source_store_unreadable",),
        )

    services = tuple(
        _service_row_to_aggregate(
            row,
            checked_at=resolved_checked_at,
            stale_after_seconds=stale_after_seconds,
        )
        for row in service_rows
    )
    unavailable_service_count = sum(1 for service in services if not service.available)
    stale_service_count = sum(
        1
        for service in services
        if service.last_checked_age_seconds is None
        or service.last_checked_age_seconds > stale_after_seconds
    )
    evidence_gaps: list[str] = []
    if not services:
        evidence_gaps.append("no_service_state")
    status = _derive_snapshot_status(
        service_count=len(services),
        unavailable_service_count=unavailable_service_count,
        stale_service_count=stale_service_count,
        pending_event_count=event_counts["pending_event_count"],
    )
    return DatabaseAvailabilityLocalAgentSnapshot(
        checked_at=resolved_checked_at,
        status=status,
        source_store_present=True,
        source_schema_valid=True,
        stale_after_seconds=stale_after_seconds,
        service_count=len(services),
        unavailable_service_count=unavailable_service_count,
        stale_service_count=stale_service_count,
        pending_event_count=event_counts["pending_event_count"],
        delivered_event_count_24h=event_counts["delivered_event_count_24h"],
        recent_transition_count=event_counts["recent_transition_count"],
        services=services,
        evidence_gaps=tuple(evidence_gaps),
    )


def run_database_availability_local_agent_once(
    *,
    db_file: Path | None = None,
    state_file: Path | None = None,
    checked_at: datetime | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
    recent_window_seconds: float = DEFAULT_RECENT_WINDOW_SECONDS,
    max_services: int = DEFAULT_MAX_SERVICES,
) -> DatabaseAvailabilityLocalAgentSnapshot:
    store = DatabaseAvailabilityLocalAgentStateStore(state_file)
    with store.writer_lock():
        snapshot = collect_database_availability_local_agent_snapshot(
            db_file=db_file,
            checked_at=checked_at,
            stale_after_seconds=stale_after_seconds,
            recent_window_seconds=recent_window_seconds,
            max_services=max_services,
        )
        store.write(snapshot)
    return snapshot


def load_database_availability_local_agent_facade_snapshot(
    *,
    state_file: Path | None = None,
    checked_at: datetime | None = None,
    stale_after_seconds: float = DEFAULT_STALE_AFTER_SECONDS,
) -> DatabaseAvailabilityLocalAgentFacadeSnapshot:
    now = _normalize_datetime(checked_at or _utc_now())
    store = DatabaseAvailabilityLocalAgentStateStore(state_file)
    try:
        snapshot = store.load()
    except DatabaseAvailabilityLocalAgentError:
        return _facade_unavailable(
            checked_at=now,
            stale_after_seconds=stale_after_seconds,
            evidence_gaps=("local_agent_state_invalid",),
        )
    if snapshot is None:
        return _facade_unavailable(
            checked_at=now,
            stale_after_seconds=stale_after_seconds,
            evidence_gaps=("local_agent_state_missing",),
        )
    state_age_seconds = _age_seconds(snapshot.checked_at, now)
    evidence_gaps = list(snapshot.evidence_gaps)
    status = snapshot.status
    if state_age_seconds > snapshot.stale_after_seconds:
        status = STATUS_DEGRADED if status == STATUS_OK else status
        evidence_gaps.append("local_agent_state_stale")
    return DatabaseAvailabilityLocalAgentFacadeSnapshot(
        status=status,
        checked_at=now,
        state_updated_at=snapshot.checked_at,
        state_age_seconds=state_age_seconds,
        stale_after_seconds=snapshot.stale_after_seconds,
        service_count=snapshot.service_count,
        unavailable_service_count=snapshot.unavailable_service_count,
        stale_service_count=snapshot.stale_service_count,
        pending_event_count=snapshot.pending_event_count,
        delivered_event_count_24h=snapshot.delivered_event_count_24h,
        recent_transition_count=snapshot.recent_transition_count,
        services=snapshot.services,
        evidence_gaps=tuple(dict.fromkeys(evidence_gaps)),
    )


def summarize_database_availability_local_agent(
    snapshot: DatabaseAvailabilityLocalAgentSnapshot,
) -> dict[str, object]:
    return {
        "agent_key": snapshot.agent_key,
        "contract_version": snapshot.contract_version,
        "delivered_event_count_24h": snapshot.delivered_event_count_24h,
        "event": "database_availability_local_agent_cycle",
        "mode": snapshot.mode,
        "pending_event_count": snapshot.pending_event_count,
        "recent_transition_count": snapshot.recent_transition_count,
        "service_count": snapshot.service_count,
        "source_schema_valid": snapshot.source_schema_valid,
        "source_store_present": snapshot.source_store_present,
        "stale_service_count": snapshot.stale_service_count,
        "status": snapshot.status,
        "unavailable_service_count": snapshot.unavailable_service_count,
    }


def _connect_read_only(db_file: Path) -> sqlite3.Connection:
    uri = f"{db_file.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _load_table_names(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name IN ('database_availability_state', 'database_availability_events')
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def _count_services(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT COUNT(*) FROM database_availability_state"
    ).fetchone()
    return int(row[0])


def _load_service_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            service_key,
            is_available,
            outage_started_at,
            last_checked_at,
            failed_check_count
        FROM database_availability_state
        ORDER BY service_key
        """
    ).fetchall()


def _load_event_counts(
    connection: sqlite3.Connection,
    *,
    checked_at: datetime,
    recent_window_seconds: float,
) -> dict[str, int]:
    window_start = checked_at - timedelta(seconds=recent_window_seconds)
    row = connection.execute(
        """
        SELECT
            SUM(CASE WHEN delivered_at IS NULL THEN 1 ELSE 0 END),
            SUM(
                CASE
                    WHEN delivered_at IS NOT NULL
                     AND occurred_at >= ?
                     AND occurred_at < ?
                    THEN 1
                    ELSE 0
                END
            ),
            SUM(
                CASE
                    WHEN occurred_at >= ?
                     AND occurred_at < ?
                    THEN 1
                    ELSE 0
                END
            )
        FROM database_availability_events
        """,
        (
            window_start.isoformat(),
            checked_at.isoformat(),
            window_start.isoformat(),
            checked_at.isoformat(),
        ),
    ).fetchone()
    return {
        "pending_event_count": int(row[0] or 0),
        "delivered_event_count_24h": int(row[1] or 0),
        "recent_transition_count": int(row[2] or 0),
    }


def _service_row_to_aggregate(
    row: sqlite3.Row,
    *,
    checked_at: datetime,
    stale_after_seconds: float,
) -> DatabaseAvailabilityServiceAggregate:
    service_key = str(row["service_key"]).strip().lower()
    available = bool(int(row["is_available"]))
    last_checked_at = _parse_datetime_or_none(
        row["last_checked_at"],
        context="last_checked_at",
    )
    outage_started_at = _parse_datetime_or_none(
        row["outage_started_at"],
        context="outage_started_at",
    )
    last_checked_age_seconds = (
        _age_seconds(last_checked_at, checked_at)
        if last_checked_at is not None
        else None
    )
    outage_age_seconds = (
        _age_seconds(outage_started_at, checked_at)
        if outage_started_at is not None
        else None
    )
    stale = (
        last_checked_age_seconds is None
        or last_checked_age_seconds > stale_after_seconds
    )
    return DatabaseAvailabilityServiceAggregate(
        service_key=service_key,
        status=STATUS_DEGRADED if stale or not available else STATUS_OK,
        available=available,
        failed_check_count=int(row["failed_check_count"] or 0),
        last_checked_at=last_checked_at,
        last_checked_age_seconds=last_checked_age_seconds,
        outage_age_seconds=outage_age_seconds,
    )


def _derive_snapshot_status(
    *,
    service_count: int,
    unavailable_service_count: int,
    stale_service_count: int,
    pending_event_count: int,
) -> str:
    if service_count == 0:
        return STATUS_DEGRADED
    if unavailable_service_count or stale_service_count or pending_event_count:
        return STATUS_DEGRADED
    return STATUS_OK


def _error_snapshot(
    *,
    checked_at: datetime,
    stale_after_seconds: float,
    source_store_present: bool,
    source_schema_valid: bool,
    service_count: int = 0,
    evidence_gaps: tuple[str, ...],
) -> DatabaseAvailabilityLocalAgentSnapshot:
    return DatabaseAvailabilityLocalAgentSnapshot(
        checked_at=checked_at,
        status=STATUS_ERROR,
        source_store_present=source_store_present,
        source_schema_valid=source_schema_valid,
        stale_after_seconds=stale_after_seconds,
        service_count=service_count,
        unavailable_service_count=0,
        stale_service_count=0,
        pending_event_count=0,
        delivered_event_count_24h=0,
        recent_transition_count=0,
        services=(),
        evidence_gaps=evidence_gaps,
    )


def _facade_unavailable(
    *,
    checked_at: datetime,
    stale_after_seconds: float,
    evidence_gaps: tuple[str, ...],
) -> DatabaseAvailabilityLocalAgentFacadeSnapshot:
    return DatabaseAvailabilityLocalAgentFacadeSnapshot(
        status=STATUS_UNAVAILABLE,
        checked_at=checked_at,
        state_updated_at=None,
        state_age_seconds=None,
        stale_after_seconds=stale_after_seconds,
        service_count=0,
        unavailable_service_count=0,
        stale_service_count=0,
        pending_event_count=0,
        delivered_event_count_24h=0,
        recent_transition_count=0,
        services=(),
        evidence_gaps=evidence_gaps,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_datetime(value: datetime) -> datetime:
    _require_aware_datetime(value, context="datetime")
    return value.astimezone(timezone.utc)


def _age_seconds(started_at: datetime, checked_at: datetime) -> float:
    return max(0.0, round((checked_at - started_at).total_seconds(), 3))


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: object, *, context: str) -> datetime:
    text = _require_string(value, context=context).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise DatabaseAvailabilityLocalAgentError(
            f"{context} must be an ISO-8601 datetime"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatabaseAvailabilityLocalAgentError(f"{context} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _parse_datetime_or_none(value: object, *, context: str) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value, context=context)


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{context} must be timezone-aware")


def _require_non_negative_or_none(value: float | None, *, context: str) -> None:
    if value is None:
        return
    if value < 0:
        raise ValueError(f"{context} must not be negative")


def _require_object(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DatabaseAvailabilityLocalAgentError(f"{context} must be an object")
    return value


def _require_exact_keys(
    value: dict[str, object],
    *,
    required: set[str],
    context: str,
) -> None:
    keys = set(value)
    if keys != required:
        raise DatabaseAvailabilityLocalAgentError(
            f"{context} keys mismatch: missing={sorted(required - keys)} "
            f"unexpected={sorted(keys - required)}"
        )


def _require_string(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DatabaseAvailabilityLocalAgentError(f"{context} must be a non-empty string")
    return value


def _require_bool(value: object, *, context: str) -> bool:
    if not isinstance(value, bool):
        raise DatabaseAvailabilityLocalAgentError(f"{context} must be boolean")
    return value


def _require_int(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DatabaseAvailabilityLocalAgentError(f"{context} must be an integer")
    if value < 0:
        raise DatabaseAvailabilityLocalAgentError(f"{context} must not be negative")
    return value


def _require_number(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DatabaseAvailabilityLocalAgentError(f"{context} must be a number")
    if value < 0:
        raise DatabaseAvailabilityLocalAgentError(f"{context} must not be negative")
    return float(value)


def _require_number_or_none(value: object, *, context: str) -> float | None:
    if value is None:
        return None
    return _require_number(value, context=context)
