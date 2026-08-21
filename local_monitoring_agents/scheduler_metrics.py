from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from core.scheduler.job_schedule import SCHEDULER_TIMEZONE
from core.scheduler.metrics import (
    SCHEDULER_HEARTBEAT_TTL_SECONDS,
    SCHEDULER_METRICS_PATH,
)
from monitoring_agent.store import StateWriterLock


SCHEDULER_METRICS_LOCAL_AGENT_CONTRACT_VERSION = 1
SCHEDULER_METRICS_LOCAL_AGENT_KEY = "scheduler_metrics"
LOCAL_AGENT_MODE = "local_agent"
STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_ERROR = "error"
STATUS_UNAVAILABLE = "unavailable"
JOB_STATUS_OK = "ok"
JOB_STATUS_DEGRADED = "degraded"
JOB_STATUS_ERROR = "error"
JOB_STATUS_UNKNOWN = "unknown"
LOCAL_AGENT_STATUSES = {
    STATUS_OK,
    STATUS_DEGRADED,
    STATUS_ERROR,
    STATUS_UNAVAILABLE,
}
JOB_STATUSES = {
    JOB_STATUS_OK,
    JOB_STATUS_DEGRADED,
    JOB_STATUS_ERROR,
    JOB_STATUS_UNKNOWN,
}
DEFAULT_MAX_JOBS = 200
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEDULER_METRICS_LOCAL_AGENT_STATE_FILE = (
    PROJECT_ROOT
    / ".local-monitoring-agent-state"
    / SCHEDULER_METRICS_LOCAL_AGENT_KEY
    / "state.json"
)


class SchedulerMetricsLocalAgentError(ValueError):
    """The local scheduler-metrics agent state is invalid or ambiguous."""


@dataclass(frozen=True)
class SchedulerMetricsJobAggregate:
    job_id: str
    status: str
    last_status_class: str
    last_run_at: datetime | None
    last_run_age_seconds: float | None
    next_run_at: datetime | None
    success_count_24h: int
    failure_count_24h: int
    failure_rate_24h: float

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("job_id is required")
        if self.status not in JOB_STATUSES:
            raise ValueError("job status is invalid")
        if self.last_status_class not in {
            "success",
            "error",
            "skipped",
            "unknown",
            "other",
        }:
            raise ValueError("last_status_class is invalid")
        for name in ("last_run_at", "next_run_at"):
            value = getattr(self, name)
            if value is not None:
                _require_aware_datetime(value, context=name)
        _require_non_negative_or_none(
            self.last_run_age_seconds,
            context="last_run_age_seconds",
        )
        for name in ("success_count_24h", "failure_count_24h"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.failure_rate_24h < 0 or self.failure_rate_24h > 1:
            raise ValueError("failure_rate_24h must be between 0 and 1")

    def to_dict(self) -> dict[str, object]:
        return {
            "failure_count_24h": self.failure_count_24h,
            "failure_rate_24h": self.failure_rate_24h,
            "job_id": self.job_id,
            "last_run_age_seconds": self.last_run_age_seconds,
            "last_run_at": _format_datetime(self.last_run_at),
            "last_status_class": self.last_status_class,
            "next_run_at": _format_datetime(self.next_run_at),
            "status": self.status,
            "success_count_24h": self.success_count_24h,
        }

    @classmethod
    def from_dict(cls, value: object) -> SchedulerMetricsJobAggregate:
        payload = _require_object(value, context="scheduler metrics job aggregate")
        _require_exact_keys(
            payload,
            required={
                "failure_count_24h",
                "failure_rate_24h",
                "job_id",
                "last_run_age_seconds",
                "last_run_at",
                "last_status_class",
                "next_run_at",
                "status",
                "success_count_24h",
            },
            context="scheduler metrics job aggregate",
        )
        return cls(
            job_id=_require_string(payload["job_id"], context="job_id"),
            status=_require_string(payload["status"], context="job status"),
            last_status_class=_require_string(
                payload["last_status_class"],
                context="last_status_class",
            ),
            last_run_at=_parse_datetime_or_none(
                payload["last_run_at"],
                context="last_run_at",
            ),
            last_run_age_seconds=_require_number_or_none(
                payload["last_run_age_seconds"],
                context="last_run_age_seconds",
            ),
            next_run_at=_parse_datetime_or_none(
                payload["next_run_at"],
                context="next_run_at",
            ),
            success_count_24h=_require_int(
                payload["success_count_24h"],
                context="success_count_24h",
            ),
            failure_count_24h=_require_int(
                payload["failure_count_24h"],
                context="failure_count_24h",
            ),
            failure_rate_24h=_require_number(
                payload["failure_rate_24h"],
                context="failure_rate_24h",
            ),
        )


@dataclass(frozen=True)
class SchedulerMetricsLocalAgentSnapshot:
    checked_at: datetime
    status: str
    source_metrics_present: bool
    source_schema_valid: bool
    scheduler_running: bool
    heartbeat_at: datetime | None
    heartbeat_age_seconds: float | None
    heartbeat_ttl_seconds: int
    job_count: int
    success_count_24h: int
    failure_count_24h: int
    error_job_count: int
    degraded_job_count: int
    jobs: tuple[SchedulerMetricsJobAggregate, ...]
    evidence_gaps: tuple[str, ...] = ()
    contract_version: int = SCHEDULER_METRICS_LOCAL_AGENT_CONTRACT_VERSION
    agent_key: str = SCHEDULER_METRICS_LOCAL_AGENT_KEY
    mode: str = LOCAL_AGENT_MODE

    def __post_init__(self) -> None:
        if self.contract_version != SCHEDULER_METRICS_LOCAL_AGENT_CONTRACT_VERSION:
            raise ValueError("local agent contract version is unsupported")
        if self.agent_key != SCHEDULER_METRICS_LOCAL_AGENT_KEY:
            raise ValueError("local agent key is invalid")
        if self.mode != LOCAL_AGENT_MODE:
            raise ValueError("local agent mode is invalid")
        if self.status not in LOCAL_AGENT_STATUSES:
            raise ValueError("local agent status is invalid")
        _require_aware_datetime(self.checked_at, context="checked_at")
        if self.heartbeat_at is not None:
            _require_aware_datetime(self.heartbeat_at, context="heartbeat_at")
        _require_non_negative_or_none(
            self.heartbeat_age_seconds,
            context="heartbeat_age_seconds",
        )
        if (
            isinstance(self.heartbeat_ttl_seconds, bool)
            or not isinstance(self.heartbeat_ttl_seconds, int)
            or self.heartbeat_ttl_seconds < 1
        ):
            raise ValueError("heartbeat_ttl_seconds must be positive")
        for name in (
            "job_count",
            "success_count_24h",
            "failure_count_24h",
            "error_job_count",
            "degraded_job_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must not be negative")
        jobs = tuple(self.jobs)
        if len(jobs) != self.job_count:
            raise ValueError("job_count does not match jobs")
        job_ids = [job.job_id for job in jobs]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("duplicate job_id in local agent snapshot")
        object.__setattr__(self, "jobs", jobs)
        object.__setattr__(
            self,
            "evidence_gaps",
            tuple(
                _require_string(gap, context="evidence gap")
                for gap in self.evidence_gaps
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_key": self.agent_key,
            "checked_at": _format_datetime(self.checked_at),
            "contract_version": self.contract_version,
            "degraded_job_count": self.degraded_job_count,
            "error_job_count": self.error_job_count,
            "evidence_gaps": list(self.evidence_gaps),
            "failure_count_24h": self.failure_count_24h,
            "heartbeat_age_seconds": self.heartbeat_age_seconds,
            "heartbeat_at": _format_datetime(self.heartbeat_at),
            "heartbeat_ttl_seconds": self.heartbeat_ttl_seconds,
            "job_count": self.job_count,
            "jobs": [job.to_dict() for job in self.jobs],
            "mode": self.mode,
            "scheduler_running": self.scheduler_running,
            "source_metrics_present": self.source_metrics_present,
            "source_schema_valid": self.source_schema_valid,
            "status": self.status,
            "success_count_24h": self.success_count_24h,
        }

    @classmethod
    def from_dict(cls, value: object) -> SchedulerMetricsLocalAgentSnapshot:
        payload = _require_object(value, context="local scheduler metrics snapshot")
        _require_exact_keys(
            payload,
            required={
                "agent_key",
                "checked_at",
                "contract_version",
                "degraded_job_count",
                "error_job_count",
                "evidence_gaps",
                "failure_count_24h",
                "heartbeat_age_seconds",
                "heartbeat_at",
                "heartbeat_ttl_seconds",
                "job_count",
                "jobs",
                "mode",
                "scheduler_running",
                "source_metrics_present",
                "source_schema_valid",
                "status",
                "success_count_24h",
            },
            context="local scheduler metrics snapshot",
        )
        jobs = payload["jobs"]
        if not isinstance(jobs, list):
            raise SchedulerMetricsLocalAgentError("jobs must be an array")
        evidence_gaps = payload["evidence_gaps"]
        if not isinstance(evidence_gaps, list):
            raise SchedulerMetricsLocalAgentError("evidence_gaps must be an array")
        return cls(
            checked_at=_parse_datetime(payload["checked_at"], context="checked_at"),
            status=_require_string(payload["status"], context="status"),
            source_metrics_present=_require_bool(
                payload["source_metrics_present"],
                context="source_metrics_present",
            ),
            source_schema_valid=_require_bool(
                payload["source_schema_valid"],
                context="source_schema_valid",
            ),
            scheduler_running=_require_bool(
                payload["scheduler_running"],
                context="scheduler_running",
            ),
            heartbeat_at=_parse_datetime_or_none(
                payload["heartbeat_at"],
                context="heartbeat_at",
            ),
            heartbeat_age_seconds=_require_number_or_none(
                payload["heartbeat_age_seconds"],
                context="heartbeat_age_seconds",
            ),
            heartbeat_ttl_seconds=_require_int(
                payload["heartbeat_ttl_seconds"],
                context="heartbeat_ttl_seconds",
            ),
            job_count=_require_int(payload["job_count"], context="job_count"),
            success_count_24h=_require_int(
                payload["success_count_24h"],
                context="success_count_24h",
            ),
            failure_count_24h=_require_int(
                payload["failure_count_24h"],
                context="failure_count_24h",
            ),
            error_job_count=_require_int(
                payload["error_job_count"],
                context="error_job_count",
            ),
            degraded_job_count=_require_int(
                payload["degraded_job_count"],
                context="degraded_job_count",
            ),
            jobs=tuple(SchedulerMetricsJobAggregate.from_dict(job) for job in jobs),
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
class SchedulerMetricsLocalAgentFacadeSnapshot:
    status: str
    checked_at: datetime
    state_updated_at: datetime | None
    state_age_seconds: float | None
    scheduler_running: bool
    heartbeat_at: datetime | None
    heartbeat_age_seconds: float | None
    heartbeat_ttl_seconds: int
    job_count: int
    success_count_24h: int
    failure_count_24h: int
    error_job_count: int
    degraded_job_count: int
    jobs: tuple[SchedulerMetricsJobAggregate, ...]
    evidence_gaps: tuple[str, ...]
    contract_version: int = SCHEDULER_METRICS_LOCAL_AGENT_CONTRACT_VERSION
    agent_key: str = SCHEDULER_METRICS_LOCAL_AGENT_KEY
    mode: str = LOCAL_AGENT_MODE


class SchedulerMetricsLocalAgentStateStore:
    def __init__(
        self,
        state_file: Path | None = None,
    ) -> None:
        self._state_file = (
            state_file or DEFAULT_SCHEDULER_METRICS_LOCAL_AGENT_STATE_FILE
        ).resolve()

    @property
    def state_file(self) -> Path:
        return self._state_file

    @property
    def state_dir(self) -> Path:
        return self._state_file.parent

    def writer_lock(self) -> StateWriterLock:
        return StateWriterLock(self.state_dir)

    def load(self) -> SchedulerMetricsLocalAgentSnapshot | None:
        if not self._state_file.exists():
            return None
        try:
            payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SchedulerMetricsLocalAgentError(
                "local scheduler metrics state cannot be read"
            ) from exc
        try:
            return SchedulerMetricsLocalAgentSnapshot.from_dict(payload)
        except (TypeError, ValueError) as exc:
            raise SchedulerMetricsLocalAgentError(
                "local scheduler metrics state has invalid schema"
            ) from exc

    def write(self, snapshot: SchedulerMetricsLocalAgentSnapshot) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            snapshot.to_dict(),
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        fd, temporary_name = tempfile.mkstemp(
            prefix="scheduler-metrics-agent-",
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
            raise SchedulerMetricsLocalAgentError(
                "local scheduler metrics state could not be written"
            ) from exc
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


def collect_scheduler_metrics_local_agent_snapshot(
    *,
    metrics_file: Path | None = None,
    checked_at: datetime | None = None,
    heartbeat_ttl_seconds: int = SCHEDULER_HEARTBEAT_TTL_SECONDS,
    max_jobs: int = DEFAULT_MAX_JOBS,
) -> SchedulerMetricsLocalAgentSnapshot:
    resolved_checked_at = _normalize_datetime(checked_at or _utc_now())
    if (
        isinstance(heartbeat_ttl_seconds, bool)
        or not isinstance(heartbeat_ttl_seconds, int)
        or heartbeat_ttl_seconds < 1
    ):
        raise ValueError("heartbeat_ttl_seconds must be positive")
    if isinstance(max_jobs, bool) or max_jobs < 1:
        raise ValueError("max_jobs must be positive")
    source_file = (metrics_file or SCHEDULER_METRICS_PATH).resolve()
    if not source_file.exists():
        return _error_snapshot(
            checked_at=resolved_checked_at,
            heartbeat_ttl_seconds=heartbeat_ttl_seconds,
            source_metrics_present=False,
            source_schema_valid=False,
            evidence_gaps=("source_metrics_missing",),
        )

    try:
        payload = json.loads(source_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return _error_snapshot(
            checked_at=resolved_checked_at,
            heartbeat_ttl_seconds=heartbeat_ttl_seconds,
            source_metrics_present=True,
            source_schema_valid=False,
            evidence_gaps=("source_metrics_unreadable",),
        )

    try:
        jobs_payload = _require_object(payload.get("jobs"), context="jobs")
        if len(jobs_payload) > max_jobs:
            return _error_snapshot(
                checked_at=resolved_checked_at,
                heartbeat_ttl_seconds=heartbeat_ttl_seconds,
                source_metrics_present=True,
                source_schema_valid=True,
                job_count=len(jobs_payload),
                evidence_gaps=("job_count_exceeds_bound",),
            )
        scheduler_running_raw = bool(payload.get("scheduler_running", False))
        heartbeat_at = _parse_source_datetime_or_none(payload.get("last_heartbeat"))
        jobs = tuple(
            _job_payload_to_aggregate(
                job_id=str(job_id),
                raw_job=raw_job,
                checked_at=resolved_checked_at,
            )
            for job_id, raw_job in sorted(jobs_payload.items())
        )
    except (TypeError, ValueError, SchedulerMetricsLocalAgentError):
        return _error_snapshot(
            checked_at=resolved_checked_at,
            heartbeat_ttl_seconds=heartbeat_ttl_seconds,
            source_metrics_present=True,
            source_schema_valid=False,
            evidence_gaps=("source_metrics_invalid_schema",),
        )

    heartbeat_age_seconds = (
        _age_seconds(heartbeat_at, resolved_checked_at)
        if heartbeat_at is not None
        else None
    )
    scheduler_running = (
        scheduler_running_raw
        and heartbeat_age_seconds is not None
        and heartbeat_age_seconds <= heartbeat_ttl_seconds
    )
    success_count = sum(job.success_count_24h for job in jobs)
    failure_count = sum(job.failure_count_24h for job in jobs)
    error_job_count = sum(1 for job in jobs if job.status == JOB_STATUS_ERROR)
    degraded_job_count = sum(1 for job in jobs if job.status == JOB_STATUS_DEGRADED)
    evidence_gaps: list[str] = []
    if heartbeat_at is None:
        evidence_gaps.append("missing_scheduler_heartbeat")
    elif heartbeat_age_seconds is not None and heartbeat_age_seconds > heartbeat_ttl_seconds:
        evidence_gaps.append("stale_scheduler_heartbeat")
    if not jobs:
        evidence_gaps.append("no_scheduler_jobs")
    status = _derive_snapshot_status(
        scheduler_running=scheduler_running,
        job_count=len(jobs),
        failure_count_24h=failure_count,
        error_job_count=error_job_count,
        degraded_job_count=degraded_job_count,
    )
    return SchedulerMetricsLocalAgentSnapshot(
        checked_at=resolved_checked_at,
        status=status,
        source_metrics_present=True,
        source_schema_valid=True,
        scheduler_running=scheduler_running,
        heartbeat_at=heartbeat_at,
        heartbeat_age_seconds=heartbeat_age_seconds,
        heartbeat_ttl_seconds=heartbeat_ttl_seconds,
        job_count=len(jobs),
        success_count_24h=success_count,
        failure_count_24h=failure_count,
        error_job_count=error_job_count,
        degraded_job_count=degraded_job_count,
        jobs=jobs,
        evidence_gaps=tuple(evidence_gaps),
    )


def run_scheduler_metrics_local_agent_once(
    *,
    metrics_file: Path | None = None,
    state_file: Path | None = None,
    checked_at: datetime | None = None,
    heartbeat_ttl_seconds: int = SCHEDULER_HEARTBEAT_TTL_SECONDS,
    max_jobs: int = DEFAULT_MAX_JOBS,
) -> SchedulerMetricsLocalAgentSnapshot:
    store = SchedulerMetricsLocalAgentStateStore(state_file)
    with store.writer_lock():
        snapshot = collect_scheduler_metrics_local_agent_snapshot(
            metrics_file=metrics_file,
            checked_at=checked_at,
            heartbeat_ttl_seconds=heartbeat_ttl_seconds,
            max_jobs=max_jobs,
        )
        store.write(snapshot)
    return snapshot


def load_scheduler_metrics_local_agent_facade_snapshot(
    *,
    state_file: Path | None = None,
    checked_at: datetime | None = None,
) -> SchedulerMetricsLocalAgentFacadeSnapshot:
    now = _normalize_datetime(checked_at or _utc_now())
    store = SchedulerMetricsLocalAgentStateStore(state_file)
    try:
        snapshot = store.load()
    except SchedulerMetricsLocalAgentError:
        return _facade_unavailable(
            checked_at=now,
            evidence_gaps=("local_agent_state_invalid",),
        )
    if snapshot is None:
        return _facade_unavailable(
            checked_at=now,
            evidence_gaps=("local_agent_state_missing",),
        )
    state_age_seconds = _age_seconds(snapshot.checked_at, now)
    evidence_gaps = list(snapshot.evidence_gaps)
    status = snapshot.status
    if state_age_seconds > snapshot.heartbeat_ttl_seconds:
        status = STATUS_DEGRADED if status == STATUS_OK else status
        evidence_gaps.append("local_agent_state_stale")
    return SchedulerMetricsLocalAgentFacadeSnapshot(
        status=status,
        checked_at=now,
        state_updated_at=snapshot.checked_at,
        state_age_seconds=state_age_seconds,
        scheduler_running=snapshot.scheduler_running,
        heartbeat_at=snapshot.heartbeat_at,
        heartbeat_age_seconds=snapshot.heartbeat_age_seconds,
        heartbeat_ttl_seconds=snapshot.heartbeat_ttl_seconds,
        job_count=snapshot.job_count,
        success_count_24h=snapshot.success_count_24h,
        failure_count_24h=snapshot.failure_count_24h,
        error_job_count=snapshot.error_job_count,
        degraded_job_count=snapshot.degraded_job_count,
        jobs=snapshot.jobs,
        evidence_gaps=tuple(dict.fromkeys(evidence_gaps)),
    )


def summarize_scheduler_metrics_local_agent(
    snapshot: SchedulerMetricsLocalAgentSnapshot,
) -> dict[str, object]:
    return {
        "agent_key": snapshot.agent_key,
        "contract_version": snapshot.contract_version,
        "degraded_job_count": snapshot.degraded_job_count,
        "error_job_count": snapshot.error_job_count,
        "event": "scheduler_metrics_local_agent_cycle",
        "failure_count_24h": snapshot.failure_count_24h,
        "job_count": snapshot.job_count,
        "mode": snapshot.mode,
        "scheduler_running": snapshot.scheduler_running,
        "source_metrics_present": snapshot.source_metrics_present,
        "source_schema_valid": snapshot.source_schema_valid,
        "status": snapshot.status,
        "success_count_24h": snapshot.success_count_24h,
    }


def _job_payload_to_aggregate(
    *,
    job_id: str,
    raw_job: object,
    checked_at: datetime,
) -> SchedulerMetricsJobAggregate:
    if not job_id.strip():
        raise SchedulerMetricsLocalAgentError("job_id is required")
    job = _require_object(raw_job, context="job")
    success_count = _coerce_non_negative_int(job.get("success_count_24h"))
    failure_count = _coerce_non_negative_int(job.get("failure_count_24h"))
    total_count = success_count + failure_count
    failure_rate = round(failure_count / total_count, 4) if total_count else 0.0
    last_run_at = _parse_source_datetime_or_none(job.get("last_run"))
    next_run_at = _parse_source_datetime_or_none(job.get("next_run"))
    last_status_class = _normalize_last_status(job.get("last_status"))
    status = _derive_job_status(last_status_class=last_status_class, failure_count=failure_count)
    return SchedulerMetricsJobAggregate(
        job_id=job_id.strip(),
        status=status,
        last_status_class=last_status_class,
        last_run_at=last_run_at,
        last_run_age_seconds=(
            _age_seconds(last_run_at, checked_at) if last_run_at is not None else None
        ),
        next_run_at=next_run_at,
        success_count_24h=success_count,
        failure_count_24h=failure_count,
        failure_rate_24h=failure_rate,
    )


def _normalize_last_status(value: object) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    if text == "success":
        return "success"
    if text == "error":
        return "error"
    if text.startswith("skipped"):
        return "skipped"
    if text == "unknown":
        return "unknown"
    return "other"


def _derive_job_status(*, last_status_class: str, failure_count: int) -> str:
    if last_status_class == "error":
        return JOB_STATUS_ERROR
    if failure_count > 0 or last_status_class in {"skipped", "other"}:
        return JOB_STATUS_DEGRADED
    if last_status_class == "unknown":
        return JOB_STATUS_UNKNOWN
    return JOB_STATUS_OK


def _derive_snapshot_status(
    *,
    scheduler_running: bool,
    job_count: int,
    failure_count_24h: int,
    error_job_count: int,
    degraded_job_count: int,
) -> str:
    if not scheduler_running:
        return STATUS_ERROR
    if job_count == 0:
        return STATUS_ERROR
    if failure_count_24h or degraded_job_count:
        return STATUS_DEGRADED
    if error_job_count:
        return STATUS_DEGRADED
    return STATUS_OK


def _error_snapshot(
    *,
    checked_at: datetime,
    heartbeat_ttl_seconds: int,
    source_metrics_present: bool,
    source_schema_valid: bool,
    job_count: int = 0,
    evidence_gaps: tuple[str, ...],
) -> SchedulerMetricsLocalAgentSnapshot:
    return SchedulerMetricsLocalAgentSnapshot(
        checked_at=checked_at,
        status=STATUS_ERROR,
        source_metrics_present=source_metrics_present,
        source_schema_valid=source_schema_valid,
        scheduler_running=False,
        heartbeat_at=None,
        heartbeat_age_seconds=None,
        heartbeat_ttl_seconds=heartbeat_ttl_seconds,
        job_count=job_count,
        success_count_24h=0,
        failure_count_24h=0,
        error_job_count=0,
        degraded_job_count=0,
        jobs=(),
        evidence_gaps=evidence_gaps,
    )


def _facade_unavailable(
    *,
    checked_at: datetime,
    evidence_gaps: tuple[str, ...],
) -> SchedulerMetricsLocalAgentFacadeSnapshot:
    return SchedulerMetricsLocalAgentFacadeSnapshot(
        status=STATUS_UNAVAILABLE,
        checked_at=checked_at,
        state_updated_at=None,
        state_age_seconds=None,
        scheduler_running=False,
        heartbeat_at=None,
        heartbeat_age_seconds=None,
        heartbeat_ttl_seconds=SCHEDULER_HEARTBEAT_TTL_SECONDS,
        job_count=0,
        success_count_24h=0,
        failure_count_24h=0,
        error_job_count=0,
        degraded_job_count=0,
        jobs=(),
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


def _parse_source_datetime_or_none(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    parsed = _parse_datetime(value, context="source datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=SCHEDULER_TIMEZONE)
    return parsed.astimezone(timezone.utc)


def _parse_datetime(value: object, *, context: str) -> datetime:
    text = _require_string(value, context=context).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise SchedulerMetricsLocalAgentError(
            f"{context} must be an ISO-8601 datetime"
        ) from exc


def _parse_datetime_or_none(value: object, *, context: str) -> datetime | None:
    if value is None:
        return None
    parsed = _parse_datetime(value, context=context)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SchedulerMetricsLocalAgentError(f"{context} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


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
        raise SchedulerMetricsLocalAgentError(f"{context} must be an object")
    return value


def _require_exact_keys(
    value: dict[str, object],
    *,
    required: set[str],
    context: str,
) -> None:
    keys = set(value)
    if keys != required:
        raise SchedulerMetricsLocalAgentError(
            f"{context} keys mismatch: missing={sorted(required - keys)} "
            f"unexpected={sorted(keys - required)}"
        )


def _require_string(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchedulerMetricsLocalAgentError(
            f"{context} must be a non-empty string"
        )
    return value


def _require_bool(value: object, *, context: str) -> bool:
    if not isinstance(value, bool):
        raise SchedulerMetricsLocalAgentError(f"{context} must be boolean")
    return value


def _require_int(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SchedulerMetricsLocalAgentError(f"{context} must be an integer")
    if value < 0:
        raise SchedulerMetricsLocalAgentError(f"{context} must not be negative")
    return value


def _require_number(value: object, *, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchedulerMetricsLocalAgentError(f"{context} must be a number")
    if value < 0:
        raise SchedulerMetricsLocalAgentError(f"{context} must not be negative")
    return float(value)


def _require_number_or_none(value: object, *, context: str) -> float | None:
    if value is None:
        return None
    return _require_number(value, context=context)


def _coerce_non_negative_int(value: object) -> int:
    if value is None or value == "":
        return 0
    parsed = int(value)
    if parsed < 0:
        raise SchedulerMetricsLocalAgentError("count must not be negative")
    return parsed
