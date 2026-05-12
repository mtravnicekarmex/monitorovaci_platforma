from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
import threading


DEFAULT_WINDOW_HOURS = 24
SCHEDULER_HEARTBEAT_TTL_SECONDS = 300
SCHEDULER_METRICS_PATH = Path(__file__).resolve().parent / "logs" / "scheduler_metrics.json"


@dataclass
class JobMetrics:
    last_run: datetime | None = None
    last_status: str = "unknown"
    last_duration_seconds: float | None = None
    next_run: datetime | None = None
    failure_count_24h: int = 0
    success_count_24h: int = 0


@dataclass
class DurationSample:
    recorded_at: datetime
    duration_seconds: float


class SchedulerMetricsStore:
    _instance: "SchedulerMetricsStore | None" = None
    _instance_lock = threading.Lock()

    def __init__(self, metrics_path: Path | None = None):
        self._metrics_path = metrics_path or SCHEDULER_METRICS_PATH
        self._lock = threading.RLock()
        self.jobs: dict[str, JobMetrics] = defaultdict(JobMetrics)
        self.scheduler_running = False
        self.last_heartbeat: datetime | None = None
        self._job_durations_24h: dict[str, list[DurationSample]] = defaultdict(list)
        self._job_success_timestamps: dict[str, list[datetime]] = defaultdict(list)
        self._job_failure_timestamps: dict[str, list[datetime]] = defaultdict(list)
        self._load_from_disk_locked()

    @classmethod
    def get_instance(cls) -> "SchedulerMetricsStore":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def refresh_from_disk(self) -> None:
        with self._lock:
            self._load_from_disk_locked()

    def mark_scheduler_started(self) -> None:
        with self._lock:
            now = datetime.now()
            self.scheduler_running = True
            self.last_heartbeat = now
            self._prune_locked()
            self._save_locked()

    def heartbeat(self) -> None:
        with self._lock:
            self.scheduler_running = True
            self.last_heartbeat = datetime.now()
            self._prune_locked()
            self._save_locked()

    def mark_scheduler_stopped(self) -> None:
        with self._lock:
            self.scheduler_running = False
            self.last_heartbeat = datetime.now()
            self._save_locked()

    def set_job_next_run(self, job_id: str, next_run: datetime | None) -> None:
        with self._lock:
            self.jobs[job_id].next_run = next_run
            self._prune_job_locked(job_id)
            self._save_locked()

    def update_job_next_runs(self, next_runs: dict[str, datetime | None]) -> None:
        with self._lock:
            for job_id, next_run in next_runs.items():
                self.jobs[job_id].next_run = next_run
                self._prune_job_locked(job_id)
            self._save_locked()

    def record_job_success(self, job_id: str, duration_seconds: float | None = None) -> None:
        with self._lock:
            metrics = self.jobs[job_id]
            now = datetime.now()
            metrics.last_run = now
            metrics.last_status = "success"
            metrics.last_duration_seconds = duration_seconds
            self._job_success_timestamps[job_id].append(now)
            if duration_seconds is not None:
                self._job_durations_24h[job_id].append(
                    DurationSample(recorded_at=now, duration_seconds=duration_seconds)
                )
            self._prune_job_locked(job_id)
            self._save_locked()

    def record_job_error(self, job_id: str, duration_seconds: float | None = None) -> None:
        with self._lock:
            metrics = self.jobs[job_id]
            now = datetime.now()
            metrics.last_run = now
            metrics.last_status = "error"
            metrics.last_duration_seconds = duration_seconds
            self._job_failure_timestamps[job_id].append(now)
            self._prune_job_locked(job_id)
            self._save_locked()

    def record_job_skipped(self, job_id: str, reason: str) -> None:
        with self._lock:
            metrics = self.jobs[job_id]
            metrics.last_run = datetime.now()
            metrics.last_status = f"skipped ({reason})"
            metrics.last_duration_seconds = None
            self._prune_job_locked(job_id)
            self._save_locked()

    def get_avg_duration(self, job_id: str, window_hours: int = DEFAULT_WINDOW_HOURS) -> float | None:
        with self._lock:
            self._prune_job_locked(job_id, window_hours=window_hours)
            durations = self._job_durations_24h.get(job_id, [])
            if not durations:
                return None
            return round(sum(item.duration_seconds for item in durations) / len(durations), 2)

    def get_failure_rate(self, job_id: str, window_hours: int = DEFAULT_WINDOW_HOURS) -> float:
        with self._lock:
            self._prune_job_locked(job_id, window_hours=window_hours)
            metrics = self.jobs[job_id]
            total = metrics.success_count_24h + metrics.failure_count_24h
            if total == 0:
                return 0.0
            return round(metrics.failure_count_24h / total, 4)

    def is_scheduler_running(
        self,
        stale_after_seconds: int = SCHEDULER_HEARTBEAT_TTL_SECONDS,
    ) -> bool:
        with self._lock:
            self._refresh_running_state_locked(stale_after_seconds=stale_after_seconds)
            return self.scheduler_running

    def _load_from_disk_locked(self) -> None:
        self.jobs = defaultdict(JobMetrics)
        self.scheduler_running = False
        self.last_heartbeat = None
        self._job_durations_24h = defaultdict(list)
        self._job_success_timestamps = defaultdict(list)
        self._job_failure_timestamps = defaultdict(list)

        if not self._metrics_path.exists():
            return

        try:
            payload = json.loads(self._metrics_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return

        self.scheduler_running = bool(payload.get("scheduler_running", False))
        self.last_heartbeat = self._parse_datetime(payload.get("last_heartbeat"))

        for job_id, raw_job in dict(payload.get("jobs") or {}).items():
            self.jobs[job_id] = JobMetrics(
                last_run=self._parse_datetime(raw_job.get("last_run")),
                last_status=str(raw_job.get("last_status") or "unknown"),
                last_duration_seconds=self._parse_float(raw_job.get("last_duration_seconds")),
                next_run=self._parse_datetime(raw_job.get("next_run")),
                failure_count_24h=int(raw_job.get("failure_count_24h") or 0),
                success_count_24h=int(raw_job.get("success_count_24h") or 0),
            )

        for job_id, timestamps in dict(payload.get("job_success_timestamps") or {}).items():
            self._job_success_timestamps[job_id] = [
                parsed
                for parsed in (self._parse_datetime(item) for item in list(timestamps or ()))
                if parsed is not None
            ]

        for job_id, timestamps in dict(payload.get("job_failure_timestamps") or {}).items():
            self._job_failure_timestamps[job_id] = [
                parsed
                for parsed in (self._parse_datetime(item) for item in list(timestamps or ()))
                if parsed is not None
            ]

        for job_id, rows in dict(payload.get("job_duration_samples") or {}).items():
            samples: list[DurationSample] = []
            for row in list(rows or ()):
                if not isinstance(row, dict):
                    continue
                recorded_at = self._parse_datetime(row.get("recorded_at"))
                duration_seconds = self._parse_float(row.get("duration_seconds"))
                if recorded_at is None or duration_seconds is None:
                    continue
                samples.append(
                    DurationSample(
                        recorded_at=recorded_at,
                        duration_seconds=duration_seconds,
                    )
                )
            if samples:
                self._job_durations_24h[job_id] = samples

        self._prune_locked()

    def _save_locked(self) -> None:
        self._metrics_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "scheduler_running": self.scheduler_running,
            "last_heartbeat": self._format_datetime(self.last_heartbeat),
            "jobs": {
                job_id: {
                    "last_run": self._format_datetime(job.last_run),
                    "last_status": job.last_status,
                    "last_duration_seconds": job.last_duration_seconds,
                    "next_run": self._format_datetime(job.next_run),
                    "failure_count_24h": job.failure_count_24h,
                    "success_count_24h": job.success_count_24h,
                }
                for job_id, job in self.jobs.items()
            },
            "job_success_timestamps": {
                job_id: [self._format_datetime(item) for item in values]
                for job_id, values in self._job_success_timestamps.items()
                if values
            },
            "job_failure_timestamps": {
                job_id: [self._format_datetime(item) for item in values]
                for job_id, values in self._job_failure_timestamps.items()
                if values
            },
            "job_duration_samples": {
                job_id: [
                    {
                        "recorded_at": self._format_datetime(item.recorded_at),
                        "duration_seconds": item.duration_seconds,
                    }
                    for item in values
                ]
                for job_id, values in self._job_durations_24h.items()
                if values
            },
        }
        temp_path = self._metrics_path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self._metrics_path)

    def _prune_locked(self, window_hours: int = DEFAULT_WINDOW_HOURS) -> None:
        job_ids = set(self.jobs)
        job_ids.update(self._job_success_timestamps)
        job_ids.update(self._job_failure_timestamps)
        job_ids.update(self._job_durations_24h)

        for job_id in job_ids:
            self._prune_job_locked(job_id, window_hours=window_hours)

    def _prune_job_locked(self, job_id: str, window_hours: int = DEFAULT_WINDOW_HOURS) -> None:
        cutoff = datetime.now() - timedelta(hours=window_hours)
        self._job_success_timestamps[job_id] = [
            item for item in self._job_success_timestamps.get(job_id, []) if item >= cutoff
        ]
        self._job_failure_timestamps[job_id] = [
            item for item in self._job_failure_timestamps.get(job_id, []) if item >= cutoff
        ]
        self._job_durations_24h[job_id] = [
            item for item in self._job_durations_24h.get(job_id, []) if item.recorded_at >= cutoff
        ]
        metrics = self.jobs[job_id]
        metrics.success_count_24h = len(self._job_success_timestamps[job_id])
        metrics.failure_count_24h = len(self._job_failure_timestamps[job_id])

    def _refresh_running_state_locked(self, stale_after_seconds: int) -> None:
        if self.last_heartbeat is None:
            self.scheduler_running = False
            return
        if datetime.now() - self.last_heartbeat > timedelta(seconds=stale_after_seconds):
            self.scheduler_running = False

    @staticmethod
    def _format_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()

    @staticmethod
    def _parse_datetime(value: object) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_float(value: object) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


_metrics_store: SchedulerMetricsStore | None = None


def get_metrics_store(*, refresh_from_disk: bool = False) -> SchedulerMetricsStore:
    global _metrics_store
    if _metrics_store is None:
        _metrics_store = SchedulerMetricsStore.get_instance()
    if refresh_from_disk:
        _metrics_store.refresh_from_disk()
    return _metrics_store
