from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
import socket
import ssl
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4


CONTRACT_VERSION = 4
MAX_JSON_RESPONSE_BYTES = 1_000_000
MAX_RETAINED_CLOCK_SKEW_SECONDS = 86_400.0


@dataclass(frozen=True)
class EndpointSpec:
    key: str
    path: str
    normalizer: Callable[[object], dict[str, object]]
    accepted_http_statuses: tuple[int, ...] = (200,)
    target: str = "facade"
    response_kind: str = "json"


@dataclass(frozen=True)
class Observation:
    observation_id: str
    observer_instance_id: str
    run_id: str
    cycle_id: str
    cycle_sequence: int
    endpoint_key: str
    poll_started_at: str
    poll_finished_at: str
    http_status: int | None
    transport_status: str
    attempt_count: int
    contract_version: int
    endpoint_set_version: int
    source_checked_at: str | None
    clock_skew_seconds: float | None
    payload: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if self.contract_version < 4:
            payload.pop("clock_skew_seconds")
        return payload


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
    if not math.isfinite(resolved) or resolved < 0:
        raise ContractError(f"{context} must be finite and non-negative")
    return resolved


def _require_unit_interval(value: object, *, context: str) -> float:
    resolved = _require_number_or_none(value, context=context)
    if resolved is None or resolved > 1:
        raise ContractError(f"{context} must be between zero and one")
    return resolved


def _require_string(value: object, *, context: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{context} must be a string")
    return value


def _require_string_or_none(value: object, *, context: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, context=context)


def _require_datetime_string(value: object, *, context: str) -> str:
    raw_value = _require_string(value, context=context)
    try:
        resolved = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{context} must be an ISO datetime") from exc
    if resolved.tzinfo is None:
        raise ContractError(f"{context} must include a timezone")
    return _format_datetime(resolved)


def _bounded_clock_skew_seconds(
    *,
    source_checked_at: str | None,
    poll_started_at: datetime,
    poll_finished_at: datetime,
) -> float | None:
    if source_checked_at is None:
        return None
    source_time = datetime.fromisoformat(source_checked_at)
    midpoint = poll_started_at + (poll_finished_at - poll_started_at) / 2
    skew = abs((source_time - midpoint).total_seconds())
    return round(min(skew, MAX_RETAINED_CLOCK_SKEW_SECONDS), 3)


def _require_signed_int_or_none(value: object, *, context: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{context} must be an integer or null")
    return value


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
    "status",
    "last_status",
    "last_run",
    "next_run",
    "success_count_24h",
    "failure_count_24h",
    "last_duration_seconds",
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
        "checked_at": _require_datetime_string(
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


SYSTEM_RUNTIME_KEYS = {
    "status",
    "checked_at",
    "boot",
    "startup_task",
    "expected_listeners",
    "temporary_listeners",
}
SYSTEM_RUNTIME_BOOT_KEYS = {"status", "boot_time"}
SYSTEM_RUNTIME_STARTUP_TASK_KEYS = {
    "task_name",
    "status",
    "last_run_time",
    "last_task_result",
}
SYSTEM_RUNTIME_LISTENER_KEYS = {
    "key",
    "status",
    "expected",
    "present",
    "local_port",
}


def _normalize_system_runtime_boot(value: object) -> dict[str, object]:
    boot = _require_object(value, context="system runtime boot")
    _require_exact_keys(
        boot,
        required=SYSTEM_RUNTIME_BOOT_KEYS,
        context="system runtime boot",
    )
    return {
        "status": _require_status(
            boot["status"],
            allowed={"ok", "degraded", "error"},
            context="system runtime boot.status",
        ),
        "boot_time": _require_string_or_none(
            boot["boot_time"],
            context="system runtime boot.boot_time",
        ),
    }


def _normalize_system_runtime_startup_task(value: object) -> dict[str, object]:
    task = _require_object(value, context="system runtime startup task")
    _require_exact_keys(
        task,
        required=SYSTEM_RUNTIME_STARTUP_TASK_KEYS,
        context="system runtime startup task",
    )
    return {
        "task_name": _require_string(
            task["task_name"],
            context="system runtime startup task.task_name",
        ),
        "status": _require_status(
            task["status"],
            allowed={"ok", "degraded", "error"},
            context="system runtime startup task.status",
        ),
        "last_run_time": _require_string_or_none(
            task["last_run_time"],
            context="system runtime startup task.last_run_time",
        ),
        "last_task_result": _require_signed_int_or_none(
            task["last_task_result"],
            context="system runtime startup task.last_task_result",
        ),
    }


def _normalize_system_runtime_listener(value: object) -> dict[str, object]:
    listener = _require_object(value, context="system runtime listener")
    _require_exact_keys(
        listener,
        required=SYSTEM_RUNTIME_LISTENER_KEYS,
        context="system runtime listener",
    )
    local_port = _require_int(
        listener["local_port"],
        context="system runtime listener.local_port",
    )
    if local_port < 1 or local_port > 65535:
        raise ContractError("system runtime listener.local_port is out of range")
    return {
        "key": _require_string(
            listener["key"],
            context="system runtime listener.key",
        ),
        "status": _require_status(
            listener["status"],
            allowed={"ok", "degraded", "error"},
            context="system runtime listener.status",
        ),
        "expected": _require_bool(
            listener["expected"],
            context="system runtime listener.expected",
        ),
        "present": _require_bool(
            listener["present"],
            context="system runtime listener.present",
        ),
        "local_port": local_port,
    }


def _normalize_system_runtime(value: object) -> dict[str, object]:
    payload = _require_object(value, context="system runtime payload")
    _require_exact_keys(
        payload,
        required=SYSTEM_RUNTIME_KEYS,
        context="system runtime payload",
    )
    expected_listeners = payload["expected_listeners"]
    temporary_listeners = payload["temporary_listeners"]
    if not isinstance(expected_listeners, list):
        raise ContractError(
            "system runtime payload.expected_listeners must be an array"
        )
    if not isinstance(temporary_listeners, list):
        raise ContractError(
            "system runtime payload.temporary_listeners must be an array"
        )
    return {
        "status": _require_status(
            payload["status"],
            allowed={"ok", "degraded", "error"},
            context="system runtime payload.status",
        ),
        "checked_at": _require_datetime_string(
            payload["checked_at"],
            context="system runtime payload.checked_at",
        ),
        "boot": _normalize_system_runtime_boot(payload["boot"]),
        "startup_task": _normalize_system_runtime_startup_task(
            payload["startup_task"]
        ),
        "expected_listeners": [
            _normalize_system_runtime_listener(listener)
            for listener in expected_listeners
        ],
        "temporary_listeners": [
            _normalize_system_runtime_listener(listener)
            for listener in temporary_listeners
        ],
    }


SCHEDULER_DETAIL_KEYS = {
    "status",
    "scheduler_running",
    "jobs",
    "schedule",
    "checked_at",
}
SCHEDULER_DETAIL_JOB_KEYS = {
    "id",
    "is_scheduled",
    "last_run",
    "last_status",
    "last_duration_seconds",
    "next_run",
    "failure_rate_24h",
    "avg_duration_24h",
}
SCHEDULER_DETAIL_RUN_KEYS = {"job_id", "scheduled_at"}


def _normalize_scheduler_detail_job(value: object) -> dict[str, object]:
    job = _require_object(value, context="detailed scheduler job")
    _require_exact_keys(
        job,
        required=SCHEDULER_DETAIL_JOB_KEYS,
        context="detailed scheduler job",
    )
    return {
        "id": _require_string(job["id"], context="detailed scheduler job.id"),
        "is_scheduled": _require_bool(
            job["is_scheduled"], context="detailed scheduler job.is_scheduled"
        ),
        "last_run": _require_string_or_none(
            job["last_run"], context="detailed scheduler job.last_run"
        ),
        "last_status": _require_string(
            job["last_status"], context="detailed scheduler job.last_status"
        ),
        "last_duration_seconds": _require_number_or_none(
            job["last_duration_seconds"],
            context="detailed scheduler job.last_duration_seconds",
        ),
        "next_run": _require_string_or_none(
            job["next_run"], context="detailed scheduler job.next_run"
        ),
        "failure_rate_24h": _require_unit_interval(
            job["failure_rate_24h"],
            context="detailed scheduler job.failure_rate_24h",
        ),
        "avg_duration_24h": _require_number_or_none(
            job["avg_duration_24h"],
            context="detailed scheduler job.avg_duration_24h",
        ),
    }


def _normalize_scheduler_detail_run(value: object) -> dict[str, object]:
    scheduled_run = _require_object(value, context="detailed scheduler run")
    _require_exact_keys(
        scheduled_run,
        required=SCHEDULER_DETAIL_RUN_KEYS,
        context="detailed scheduler run",
    )
    return {
        "job_id": _require_string(
            scheduled_run["job_id"], context="detailed scheduler run.job_id"
        ),
        "scheduled_at": _require_string(
            scheduled_run["scheduled_at"],
            context="detailed scheduler run.scheduled_at",
        ),
    }


def _normalize_scheduler_detail(value: object) -> dict[str, object]:
    payload = _require_object(value, context="detailed scheduler payload")
    _require_exact_keys(
        payload,
        required=SCHEDULER_DETAIL_KEYS,
        context="detailed scheduler payload",
    )
    jobs = payload["jobs"]
    schedule = payload["schedule"]
    if not isinstance(jobs, list):
        raise ContractError("detailed scheduler payload.jobs must be an array")
    if not isinstance(schedule, list):
        raise ContractError("detailed scheduler payload.schedule must be an array")
    return {
        "status": _require_status(
            payload["status"],
            allowed={"ok", "degraded", "error"},
            context="detailed scheduler payload.status",
        ),
        "scheduler_running": _require_bool(
            payload["scheduler_running"],
            context="detailed scheduler payload.scheduler_running",
        ),
        "jobs": [_normalize_scheduler_detail_job(job) for job in jobs],
        "schedule": [
            _normalize_scheduler_detail_run(scheduled_run)
            for scheduled_run in schedule
        ],
        "checked_at": _require_datetime_string(
            payload["checked_at"], context="detailed scheduler payload.checked_at"
        ),
    }


SYSTEM_DATABASE_KEYS = {"status", "checked_at", "postgres", "expected_schemas"}
SYSTEM_DATABASE_POSTGRES_KEYS = {
    "status",
    "connected",
    "latency_ms",
    "transaction_read_only",
}
SYSTEM_DATABASE_SCHEMA_KEYS = {"schema_name", "status", "present"}


def _normalize_system_database_postgres(value: object) -> dict[str, object]:
    postgres = _require_object(value, context="system database postgres")
    _require_exact_keys(
        postgres,
        required=SYSTEM_DATABASE_POSTGRES_KEYS,
        context="system database postgres",
    )
    transaction_read_only = postgres["transaction_read_only"]
    if transaction_read_only is not None:
        transaction_read_only = _require_bool(
            transaction_read_only,
            context="system database postgres.transaction_read_only",
        )
    return {
        "status": _require_status(
            postgres["status"],
            allowed={"ok", "degraded", "error"},
            context="system database postgres.status",
        ),
        "connected": _require_bool(
            postgres["connected"], context="system database postgres.connected"
        ),
        "latency_ms": _require_number_or_none(
            postgres["latency_ms"], context="system database postgres.latency_ms"
        ),
        "transaction_read_only": transaction_read_only,
    }


def _normalize_system_database_schema(value: object) -> dict[str, object]:
    schema = _require_object(value, context="system database schema")
    _require_exact_keys(
        schema,
        required=SYSTEM_DATABASE_SCHEMA_KEYS,
        context="system database schema",
    )
    return {
        "schema_name": _require_string(
            schema["schema_name"], context="system database schema.schema_name"
        ),
        "status": _require_status(
            schema["status"],
            allowed={"ok", "degraded", "error"},
            context="system database schema.status",
        ),
        "present": _require_bool(
            schema["present"], context="system database schema.present"
        ),
    }


def _normalize_system_database(value: object) -> dict[str, object]:
    payload = _require_object(value, context="system database payload")
    _require_exact_keys(
        payload,
        required=SYSTEM_DATABASE_KEYS,
        context="system database payload",
    )
    expected_schemas = payload["expected_schemas"]
    if not isinstance(expected_schemas, list):
        raise ContractError("system database expected_schemas must be an array")
    return {
        "status": _require_status(
            payload["status"],
            allowed={"ok", "degraded", "error"},
            context="system database payload.status",
        ),
        "checked_at": _require_datetime_string(
            payload["checked_at"], context="system database payload.checked_at"
        ),
        "postgres": _normalize_system_database_postgres(payload["postgres"]),
        "expected_schemas": [
            _normalize_system_database_schema(schema) for schema in expected_schemas
        ],
    }


SYSTEM_PROXY_KEYS = {"status", "checked_at", "routes", "headers"}
SYSTEM_PROXY_ROUTE_KEYS = {
    "key",
    "status",
    "expected_status_code",
    "actual_status_code",
}
SYSTEM_PROXY_HEADER_KEYS = {"key", "status", "expected", "present"}


def _require_http_status_or_none(value: object, *, context: str) -> int | None:
    if value is None:
        return None
    status = _require_int(value, context=context)
    if status < 100 or status > 599:
        raise ContractError(f"{context} is outside the HTTP status range")
    return status


def _normalize_system_proxy_route(value: object) -> dict[str, object]:
    route = _require_object(value, context="system proxy route")
    _require_exact_keys(
        route,
        required=SYSTEM_PROXY_ROUTE_KEYS,
        context="system proxy route",
    )
    expected_status = _require_http_status_or_none(
        route["expected_status_code"], context="system proxy route.expected_status"
    )
    if expected_status is None:
        raise ContractError("system proxy route.expected_status must not be null")
    return {
        "key": _require_string(route["key"], context="system proxy route.key"),
        "status": _require_status(
            route["status"],
            allowed={"ok", "degraded", "error"},
            context="system proxy route.status",
        ),
        "expected_status_code": expected_status,
        "actual_status_code": _require_http_status_or_none(
            route["actual_status_code"], context="system proxy route.actual_status"
        ),
    }


def _normalize_system_proxy_header(value: object) -> dict[str, object]:
    header = _require_object(value, context="system proxy header")
    _require_exact_keys(
        header,
        required=SYSTEM_PROXY_HEADER_KEYS,
        context="system proxy header",
    )
    return {
        "key": _require_string(header["key"], context="system proxy header.key"),
        "status": _require_status(
            header["status"],
            allowed={"ok", "degraded", "error"},
            context="system proxy header.status",
        ),
        "expected": _require_status(
            header["expected"],
            allowed={"present", "absent"},
            context="system proxy header.expected",
        ),
        "present": _require_bool(
            header["present"], context="system proxy header.present"
        ),
    }


def _normalize_system_proxy(value: object) -> dict[str, object]:
    payload = _require_object(value, context="system proxy payload")
    _require_exact_keys(
        payload,
        required=SYSTEM_PROXY_KEYS,
        context="system proxy payload",
    )
    routes = payload["routes"]
    headers = payload["headers"]
    if not isinstance(routes, list):
        raise ContractError("system proxy routes must be an array")
    if not isinstance(headers, list):
        raise ContractError("system proxy headers must be an array")
    return {
        "status": _require_status(
            payload["status"],
            allowed={"ok", "degraded", "error"},
            context="system proxy payload.status",
        ),
        "checked_at": _require_datetime_string(
            payload["checked_at"], context="system proxy payload.checked_at"
        ),
        "routes": [_normalize_system_proxy_route(route) for route in routes],
        "headers": [_normalize_system_proxy_header(header) for header in headers],
    }


SYSTEM_SMARTFUELPASS_KEYS = {
    "status",
    "checked_at",
    "table",
    "sync_job",
    "weekly_report_job",
}
SYSTEM_SMARTFUELPASS_TABLE_KEYS = {
    "status",
    "table_present",
    "missing_ended_at_utc_count",
    "last_imported_at",
    "last_import_age_seconds",
}
SYSTEM_SMARTFUELPASS_JOB_KEYS = {
    "job_id",
    "status",
    "last_status",
    "last_run",
    "success_count_24h",
    "failure_count_24h",
    "last_duration_seconds",
}


def _normalize_smartfuelpass_table(value: object) -> dict[str, object]:
    table = _require_object(value, context="SmartFuelPass table")
    _require_exact_keys(
        table,
        required=SYSTEM_SMARTFUELPASS_TABLE_KEYS,
        context="SmartFuelPass table",
    )
    return {
        "status": _require_status(
            table["status"],
            allowed={"ok", "degraded", "error"},
            context="SmartFuelPass table.status",
        ),
        "table_present": _require_bool(
            table["table_present"], context="SmartFuelPass table.table_present"
        ),
        "missing_ended_at_utc_count": _require_int(
            table["missing_ended_at_utc_count"],
            context="SmartFuelPass table.missing_ended_at_utc_count",
        ),
        "last_imported_at": _require_string_or_none(
            table["last_imported_at"], context="SmartFuelPass table.last_imported_at"
        ),
        "last_import_age_seconds": _require_number_or_none(
            table["last_import_age_seconds"],
            context="SmartFuelPass table.last_import_age_seconds",
        ),
    }


def _normalize_smartfuelpass_job(value: object) -> dict[str, object]:
    job = _require_object(value, context="SmartFuelPass job")
    _require_exact_keys(
        job,
        required=SYSTEM_SMARTFUELPASS_JOB_KEYS,
        context="SmartFuelPass job",
    )
    return {
        "job_id": _require_string(job["job_id"], context="SmartFuelPass job.id"),
        "status": _require_status(
            job["status"],
            allowed={"ok", "degraded", "error"},
            context="SmartFuelPass job.status",
        ),
        "last_status": _require_string(
            job["last_status"], context="SmartFuelPass job.last_status"
        ),
        "last_run": _require_string_or_none(
            job["last_run"], context="SmartFuelPass job.last_run"
        ),
        "success_count_24h": _require_int(
            job["success_count_24h"], context="SmartFuelPass job.success_count_24h"
        ),
        "failure_count_24h": _require_int(
            job["failure_count_24h"], context="SmartFuelPass job.failure_count_24h"
        ),
        "last_duration_seconds": _require_number_or_none(
            job["last_duration_seconds"],
            context="SmartFuelPass job.last_duration_seconds",
        ),
    }


def _normalize_system_smartfuelpass(value: object) -> dict[str, object]:
    payload = _require_object(value, context="SmartFuelPass payload")
    _require_exact_keys(
        payload,
        required=SYSTEM_SMARTFUELPASS_KEYS,
        context="SmartFuelPass payload",
    )
    return {
        "status": _require_status(
            payload["status"],
            allowed={"ok", "degraded", "error"},
            context="SmartFuelPass payload.status",
        ),
        "checked_at": _require_datetime_string(
            payload["checked_at"], context="SmartFuelPass payload.checked_at"
        ),
        "table": _normalize_smartfuelpass_table(payload["table"]),
        "sync_job": _normalize_smartfuelpass_job(payload["sync_job"]),
        "weekly_report_job": _normalize_smartfuelpass_job(
            payload["weekly_report_job"]
        ),
    }


def _normalize_external_web_metadata(value: object) -> dict[str, object]:
    metadata = _require_object(value, context="external web metadata")
    _require_exact_keys(
        metadata,
        required={"content_type"},
        context="external web metadata",
    )
    content_type = _require_string(
        metadata["content_type"], context="external web metadata.content_type"
    )
    if content_type.split(";", 1)[0].strip().lower() != "text/html":
        raise ContractError("external web response is not HTML")
    return {"status": "ok", "content_type_valid": True}


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
    "scheduler_detail": EndpointSpec(
        "scheduler_detail",
        "/api/v1/monitoring/health/scheduler",
        _normalize_scheduler_detail,
    ),
    "system_runtime": EndpointSpec(
        "system_runtime",
        "/api/v1/monitoring/health/system/runtime",
        _normalize_system_runtime,
    ),
    "system_database": EndpointSpec(
        "system_database",
        "/api/v1/monitoring/health/system/database",
        _normalize_system_database,
    ),
    "system_proxy": EndpointSpec(
        "system_proxy",
        "/api/v1/monitoring/health/system/proxy",
        _normalize_system_proxy,
    ),
    "system_smartfuelpass": EndpointSpec(
        "system_smartfuelpass",
        "/api/v1/monitoring/health/system/smartfuelpass",
        _normalize_system_smartfuelpass,
    ),
    "external_web": EndpointSpec(
        "external_web",
        "",
        _normalize_external_web_metadata,
        target="external_web",
        response_kind="metadata",
    ),
}

ENDPOINT_SETS: dict[int, tuple[str, ...]] = {
    1: ("live", "ready", "system_scheduler"),
    2: ("live", "ready", "system_scheduler", "system_runtime"),
    3: (
        "live",
        "ready",
        "system_scheduler",
        "scheduler_detail",
        "system_runtime",
        "system_database",
        "system_proxy",
        "system_smartfuelpass",
        "external_web",
    ),
}
CURRENT_ENDPOINT_SET_VERSION = 3
CURRENT_ENDPOINT_KEYS = ENDPOINT_SETS[CURRENT_ENDPOINT_SET_VERSION]
CONTRACT_ENDPOINT_SET_VERSIONS = {2: 1, 3: 2, CONTRACT_VERSION: 3}


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


def validate_external_web_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("external web URL must use http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("external web URL must contain a host and no credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("external web URL must not contain query or fragment data")
    if parsed.path not in {"", "/"}:
        raise ValueError("external web URL must target the public page root")
    if parsed.scheme == "http" and parsed.hostname not in {
        "127.0.0.1",
        "::1",
        "localhost",
    }:
        raise ValueError(
            "plain HTTP external probing is allowed only for loopback tests"
        )
    return url.rstrip("/") + "/"


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        del req, fp, code, msg, headers, newurl
        return None


class HealthClient:
    def __init__(
        self,
        *,
        base_url: str,
        external_web_url: str | None,
        observer_instance_id: str,
        run_id: str,
        observation_contract_version: int = CONTRACT_VERSION,
        endpoint_set_version: int = CURRENT_ENDPOINT_SET_VERSION,
        timeout_seconds: float = 3.0,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 0.5,
        bearer_credential: str | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if not observer_instance_id.strip():
            raise ValueError("observer_instance_id is required")
        if not run_id.strip():
            raise ValueError("run_id is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            raise ValueError("max_attempts must be an integer")
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("max_attempts must be between 1 and 5")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")
        if (
            observation_contract_version not in CONTRACT_ENDPOINT_SET_VERSIONS
            or CONTRACT_ENDPOINT_SET_VERSIONS[observation_contract_version]
            != endpoint_set_version
        ):
            raise ValueError("observation contract and endpoint set do not match")
        if endpoint_set_version not in ENDPOINT_SETS:
            raise ValueError("endpoint set is unsupported")
        self._base_url = validate_base_url(base_url)
        self._external_web_url = (
            None
            if external_web_url is None
            else validate_external_web_url(external_web_url)
        )
        if (
            "external_web" in ENDPOINT_SETS[endpoint_set_version]
            and self._external_web_url is None
        ):
            raise ValueError("external web URL is required by the endpoint set")
        if self._base_url.startswith("https://") and not bearer_credential:
            raise ValueError("remote HTTPS monitoring requires a bearer credential")
        if bearer_credential is not None and (
            not bearer_credential
            or any(character.isspace() for character in bearer_credential)
        ):
            raise ValueError("bearer credential has an invalid format")
        self._observer_instance_id = observer_instance_id.strip()
        self._run_id = run_id.strip()
        self._observation_contract_version = observation_contract_version
        self._endpoint_set_version = endpoint_set_version
        self._timeout_seconds = float(timeout_seconds)
        self._max_attempts = max_attempts
        self._retry_backoff_seconds = float(retry_backoff_seconds)
        self._bearer_credential = bearer_credential
        self._sleep_fn = sleep_fn
        self._opener = build_opener(ProxyHandler({}), _NoRedirectHandler())

    def poll(
        self,
        endpoint_key: str,
        *,
        cycle_id: str,
        cycle_sequence: int,
    ) -> Observation:
        if not cycle_id.strip():
            raise ValueError("cycle_id is required")
        if (
            isinstance(cycle_sequence, bool)
            or not isinstance(cycle_sequence, int)
            or cycle_sequence < 1
        ):
            raise ValueError("cycle_sequence must be a positive integer")
        try:
            spec = APPROVED_ENDPOINTS[endpoint_key]
        except KeyError as exc:
            raise ValueError(f"endpoint is not approved: {endpoint_key}") from exc
        if endpoint_key not in ENDPOINT_SETS[self._endpoint_set_version]:
            raise ValueError("endpoint is outside the configured endpoint set")

        started_at = _utc_now()
        if spec.target == "facade":
            request_url = urljoin(self._base_url, spec.path.lstrip("/"))
            headers = {
                "Accept": "application/json",
                "User-Agent": "monitoring-agent-test/1",
            }
            if self._bearer_credential:
                headers["Authorization"] = f"Bearer {self._bearer_credential}"
        elif spec.target == "external_web":
            if self._external_web_url is None:
                raise ValueError("external web URL is unavailable")
            request_url = self._external_web_url
            headers = {
                "Accept": "text/html",
                "User-Agent": "monitoring-agent-test/1",
            }
        else:
            raise ValueError(f"endpoint has an unsupported target: {spec.target}")
        attempt_count = 0
        http_status: int | None = None
        transport_status = "connection_error"
        payload: dict[str, object] = {}
        source_checked_at: str | None = None
        for attempt_count in range(1, self._max_attempts + 1):
            request = Request(
                request_url,
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
                    if http_status not in spec.accepted_http_statuses:
                        transport_status = "http_error"
                        payload = {}
                    elif spec.response_kind == "json":
                        raw_body = response.read(MAX_JSON_RESPONSE_BYTES + 1)
                        if len(raw_body) > MAX_JSON_RESPONSE_BYTES:
                            raise ContractError(
                                "response body exceeds the safe size limit"
                            )
                        decoded = json.loads(raw_body.decode("utf-8"))
                        payload = spec.normalizer(decoded)
                        checked_at = payload.get("checked_at")
                        source_checked_at = (
                            checked_at if isinstance(checked_at, str) else None
                        )
                        transport_status = "success"
                    elif spec.response_kind == "metadata":
                        payload = spec.normalizer(
                            {
                                "content_type": response.headers.get(
                                    "Content-Type", ""
                                )
                            }
                        )
                        source_checked_at = None
                        transport_status = "success"
                    else:
                        raise ContractError(
                            "endpoint has an unsupported response kind"
                        )
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
                if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                    transport_status = "timeout"
                elif isinstance(exc.reason, (ssl.SSLError, ssl.CertificateError)):
                    transport_status = "tls_error"
                else:
                    transport_status = "connection_error"
                http_status = None
                payload = {}
            except ssl.SSLError:
                transport_status = "tls_error"
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
        clock_skew_seconds = (
            _bounded_clock_skew_seconds(
                source_checked_at=source_checked_at,
                poll_started_at=started_at,
                poll_finished_at=finished_at,
            )
            if self._observation_contract_version >= 4
            else None
        )
        return Observation(
            observation_id=str(uuid4()),
            observer_instance_id=self._observer_instance_id,
            run_id=self._run_id,
            cycle_id=cycle_id.strip(),
            cycle_sequence=cycle_sequence,
            endpoint_key=spec.key,
            poll_started_at=_format_datetime(started_at),
            poll_finished_at=_format_datetime(finished_at),
            http_status=http_status,
            transport_status=transport_status,
            attempt_count=attempt_count,
            contract_version=self._observation_contract_version,
            endpoint_set_version=self._endpoint_set_version,
            source_checked_at=source_checked_at,
            clock_skew_seconds=clock_skew_seconds,
            payload=payload,
        )
