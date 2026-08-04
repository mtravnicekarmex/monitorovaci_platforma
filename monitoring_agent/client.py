from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import socket
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4


CONTRACT_VERSION = 1


@dataclass(frozen=True)
class EndpointSpec:
    key: str
    path: str
    normalizer: Callable[[object], dict[str, object]]
    accepted_http_statuses: tuple[int, ...] = (200,)


@dataclass(frozen=True)
class Observation:
    observation_id: str
    observer_instance_id: str
    endpoint_key: str
    poll_started_at: str
    poll_finished_at: str
    http_status: int | None
    transport_status: str
    attempt_count: int
    contract_version: int
    source_checked_at: str | None
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ContractError(ValueError):
    """The remote response did not match the approved safe contract."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _require_object(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ContractError(f"{context} must be a JSON object")
    return dict(value)


def _require_exact_keys(
    value: dict[str, object],
    *,
    required: set[str],
    context: str,
) -> None:
    actual = set(value)
    missing = required - actual
    unexpected = actual - required
    if missing or unexpected:
        raise ContractError(
            f"{context} schema mismatch: missing={sorted(missing)!r}, "
            f"unexpected={sorted(unexpected)!r}"
        )


def _require_status(value: object, *, allowed: set[str], context: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ContractError(f"{context} contains an invalid status")
    return value


def _require_bool(value: object, *, context: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{context} must be a boolean")
    return value


def _require_int(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractError(f"{context} must be a non-negative integer")
    return value


def _require_number_or_none(value: object, *, context: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{context} must be numeric or null")
    resolved = float(value)
    if resolved < 0:
        raise ContractError(f"{context} must not be negative")
    return resolved


def _require_string(value: object, *, context: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{context} must be a string")
    return value


def _require_string_or_none(value: object, *, context: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, context=context)


def _normalize_simple_status(value: object, *, allowed: set[str]) -> dict[str, object]:
    payload = _require_object(value, context="payload")
    _require_exact_keys(payload, required={"status"}, context="payload")
    return {
        "status": _require_status(
            payload["status"],
            allowed=allowed,
            context="payload.status",
        )
    }


def _normalize_live(value: object) -> dict[str, object]:
    return _normalize_simple_status(value, allowed={"ok"})


def _normalize_ready(value: object) -> dict[str, object]:
    return _normalize_simple_status(value, allowed={"ready", "unavailable"})


SYSTEM_SCHEDULER_KEYS = {
    "status",
    "checked_at",
    "scheduler_running",
    "last_heartbeat",
    "heartbeat_age_seconds",
    "heartbeat_ttl_seconds",
    "total_success_count_24h",
    "total_failure_count_24h",
    "jobs",
}

SYSTEM_SCHEDULER_JOB_KEYS = {
    "job_id",
    "label",
    "status",
    "last_status",
    "last_run",
    "next_run",
    "success_count_24h",
    "failure_count_24h",
    "last_duration_seconds",
    "detail",
}


def _normalize_system_scheduler_job(value: object) -> dict[str, object]:
    job = _require_object(value, context="scheduler job")
    _require_exact_keys(
        job,
        required=SYSTEM_SCHEDULER_JOB_KEYS,
        context="scheduler job",
    )
    return {
        "job_id": _require_string(job["job_id"], context="scheduler job.job_id"),
        "status": _require_status(
            job["status"],
            allowed={"ok", "degraded", "error"},
            context="scheduler job.status",
        ),
        "last_status": _require_string(
            job["last_status"],
            context="scheduler job.last_status",
        ),
        "last_run": _require_string_or_none(
            job["last_run"],
            context="scheduler job.last_run",
        ),
        "next_run": _require_string_or_none(
            job["next_run"],
            context="scheduler job.next_run",
        ),
        "success_count_24h": _require_int(
            job["success_count_24h"],
            context="scheduler job.success_count_24h",
        ),
        "failure_count_24h": _require_int(
            job["failure_count_24h"],
            context="scheduler job.failure_count_24h",
        ),
        "last_duration_seconds": _require_number_or_none(
            job["last_duration_seconds"],
            context="scheduler job.last_duration_seconds",
        ),
    }


def _normalize_system_scheduler(value: object) -> dict[str, object]:
    payload = _require_object(value, context="system scheduler payload")
    _require_exact_keys(
        payload,
        required=SYSTEM_SCHEDULER_KEYS,
        context="system scheduler payload",
    )
    jobs = payload["jobs"]
    if not isinstance(jobs, list):
        raise ContractError("system scheduler payload.jobs must be an array")
    return {
        "status": _require_status(
            payload["status"],
            allowed={"ok", "degraded", "error"},
            context="system scheduler payload.status",
        ),
        "checked_at": _require_string(
            payload["checked_at"],
            context="system scheduler payload.checked_at",
        ),
        "scheduler_running": _require_bool(
            payload["scheduler_running"],
            context="system scheduler payload.scheduler_running",
        ),
        "last_heartbeat": _require_string_or_none(
            payload["last_heartbeat"],
            context="system scheduler payload.last_heartbeat",
        ),
        "heartbeat_age_seconds": _require_number_or_none(
            payload["heartbeat_age_seconds"],
            context="system scheduler payload.heartbeat_age_seconds",
        ),
        "heartbeat_ttl_seconds": _require_int(
            payload["heartbeat_ttl_seconds"],
            context="system scheduler payload.heartbeat_ttl_seconds",
        ),
        "total_success_count_24h": _require_int(
            payload["total_success_count_24h"],
            context="system scheduler payload.total_success_count_24h",
        ),
        "total_failure_count_24h": _require_int(
            payload["total_failure_count_24h"],
            context="system scheduler payload.total_failure_count_24h",
        ),
        "jobs": [_normalize_system_scheduler_job(job) for job in jobs],
    }


APPROVED_ENDPOINTS: dict[str, EndpointSpec] = {
    "live": EndpointSpec(
        "live",
        "/api/v1/monitoring/health/live",
        _normalize_live,
    ),
    "ready": EndpointSpec(
        "ready",
        "/api/v1/monitoring/health/ready",
        _normalize_ready,
        (200, 503),
    ),
    "system_scheduler": EndpointSpec(
        "system_scheduler",
        "/api/v1/monitoring/health/system/scheduler",
        _normalize_system_scheduler,
    ),
}


def validate_base_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("base URL must use http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("base URL must contain a host and no credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("base URL must not contain query or fragment data")
    if parsed.path not in {"", "/"}:
        raise ValueError("base URL must not contain a path")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("plain HTTP is allowed only for loopback synthetic tests")
    return base_url.rstrip("/") + "/"


class HealthClient:
    def __init__(
        self,
        *,
        base_url: str,
        observer_instance_id: str,
        timeout_seconds: float = 3.0,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
        bearer_credential: str | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if not observer_instance_id.strip():
            raise ValueError("observer_instance_id is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            raise ValueError("max_attempts must be an integer")
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")
        self._base_url = validate_base_url(base_url)
        if self._base_url.startswith("https://") and not bearer_credential:
            raise ValueError("remote HTTPS monitoring requires a bearer credential")
        if bearer_credential is not None and (
            not bearer_credential
            or any(character.isspace() for character in bearer_credential)
        ):
            raise ValueError("bearer credential has an invalid format")
        self._observer_instance_id = observer_instance_id.strip()
        self._timeout_seconds = float(timeout_seconds)
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = float(retry_backoff_seconds)
        self._bearer_credential = bearer_credential
        self._sleep_fn = sleep_fn
        self._opener = build_opener(ProxyHandler({}))

    def poll(self, endpoint_key: str) -> Observation:
        try:
            spec = APPROVED_ENDPOINTS[endpoint_key]
        except KeyError as exc:
            raise ValueError(f"endpoint is not approved: {endpoint_key}") from exc

        started_at = _utc_now()
        headers = {
            "Accept": "application/json",
            "User-Agent": "monitoring-agent-test/1",
        }
        if self._bearer_credential:
            headers["Authorization"] = f"Bearer {self._bearer_credential}"
        attempt_count = 0
        http_status: int | None = None
        transport_status = "connection_error"
        payload: dict[str, object] = {}
        source_checked_at: str | None = None
        for attempt_count in range(1, self._max_attempts + 1):
            request = Request(
                urljoin(self._base_url, spec.path.lstrip("/")),
                method="GET",
                headers=headers,
            )
            try:
                try:
                    response = self._opener.open(
                        request,
                        timeout=self._timeout_seconds,
                    )
                except HTTPError as exc:
                    response = exc
                with response:
                    http_status = int(response.status)
                    raw_body = response.read()
                if http_status not in spec.accepted_http_statuses:
                    transport_status = "http_error"
                    payload = {}
                else:
                    decoded = json.loads(raw_body.decode("utf-8"))
                    payload = spec.normalizer(decoded)
                    checked_at = payload.get("checked_at")
                    source_checked_at = (
                        checked_at if isinstance(checked_at, str) else None
                    )
                    transport_status = "success"
            except ContractError:
                transport_status = "schema_error"
                payload = {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                transport_status = "schema_error"
                payload = {}
            except (TimeoutError, socket.timeout):
                transport_status = "timeout"
                http_status = None
                payload = {}
            except URLError as exc:
                transport_status = (
                    "timeout"
                    if isinstance(exc.reason, (TimeoutError, socket.timeout))
                    else "connection_error"
                )
                http_status = None
                payload = {}
            except OSError:
                transport_status = "connection_error"
                http_status = None
                payload = {}

            if transport_status not in {"connection_error", "timeout"}:
                break
            if attempt_count < self._max_attempts:
                self._sleep_fn(
                    self._retry_backoff_seconds * (2 ** (attempt_count - 1))
                )

        finished_at = _utc_now()
        return Observation(
            observation_id=str(uuid4()),
            observer_instance_id=self._observer_instance_id,
            endpoint_key=spec.key,
            poll_started_at=_format_datetime(started_at),
            poll_finished_at=_format_datetime(finished_at),
            http_status=http_status,
            transport_status=transport_status,
            attempt_count=attempt_count,
            contract_version=CONTRACT_VERSION,
            source_checked_at=source_checked_at,
            payload=payload,
        )
