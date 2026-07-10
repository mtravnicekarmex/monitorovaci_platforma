from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import http.client
import json
import platform
import re
import socket
import ssl
import subprocess
from time import perf_counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from core.db.connect import get_session_pg
from core.scheduler.job_schedule import get_scheduler_job_specs
from core.scheduler.metrics import (
    JobMetrics,
    SCHEDULER_HEARTBEAT_TTL_SECONDS,
    get_metrics_store,
)
from moduly.apps.smartfuelpass.service import (
    current_month_period,
    last_completed_week_period,
    previous_month_period,
)
from services.api.schemas.admin import (
    SystemDatabaseHealthResponse,
    SystemPostgresConnectionStatus,
    SystemPostgresSchemaStatus,
    SystemSmartFuelPassHealthResponse,
    SystemSmartFuelPassJobMetricStatus,
    SystemSmartFuelPassPeriodSummary,
    SystemSmartFuelPassTableStatus,
    SystemSchedulerHealthResponse,
    SystemSchedulerJobStatus,
    SystemProxyHeaderStatus,
    SystemProxyHealthResponse,
    SystemProxyRouteStatus,
    SystemRuntimeBootStatus,
    SystemRuntimeHealthResponse,
    SystemRuntimeListenerStatus,
    SystemRuntimeStartupTaskStatus,
)


STARTUP_TASK_NAME = "API_dashboard_caddy"
RUNTIME_CHECK_PORTS = (80, 443, 2019, 8000, 8001, 8010, 8011)
TEMPORARY_PORTS = (8010, 8011)
PUBLIC_DASHBOARD_HOST = "monitoring.armexholding.cz"
LOCAL_CADDY_HOST = "127.0.0.1"
LOCAL_CADDY_TIMEOUT_SECONDS = 8
SCHEDULER_CORE_JOB_ID = "quarter_hour_job"
SCHEDULER_CORE_JOB_MAX_AGE_SECONDS = 45 * 60
SMARTFUELPASS_SYNC_JOB_ID = "sync_charge_sessions_to_db"
SMARTFUELPASS_WEEKLY_REPORT_JOB_ID = "smartfuelpass_weekly_report_job"
SMARTFUELPASS_TABLE_MAX_IMPORT_AGE_SECONDS = 36 * 60 * 60
EXPECTED_POSTGRES_SCHEMAS = (
    "dashboard",
    "dbo",
    "evidence",
    "monitoring",
    "revize",
    "web_search",
)


@dataclass(frozen=True)
class ListenerExpectation:
    key: str
    label: str
    local_port: int
    local_address: str | None = None


EXPECTED_LISTENERS = (
    ListenerExpectation("caddy_http", "Caddy HTTP", 80),
    ListenerExpectation("caddy_https", "Caddy HTTPS", 443),
    ListenerExpectation("caddy_admin", "Caddy admin", 2019, "127.0.0.1"),
    ListenerExpectation("fastapi", "FastAPI", 8000, "127.0.0.1"),
    ListenerExpectation("streamlit", "Streamlit", 8001, "127.0.0.1"),
)


@dataclass(frozen=True)
class ProxyRouteExpectation:
    key: str
    label: str
    method: str
    scheme: str
    host: str
    connect_host: str
    local_port: int
    path: str
    expected_status_code: int
    expected_content_type_prefix: str | None = None
    expected_location: str | None = None


@dataclass(frozen=True)
class ProxyHeaderExpectation:
    key: str
    header_name: str
    expected_present: bool
    required_value: str | None = None
    required_contains: str | None = None


@dataclass(frozen=True)
class LocalHttpResponse:
    status_code: int
    headers: dict[str, str]


PROXY_ROUTE_EXPECTATIONS = (
    ProxyRouteExpectation(
        key="https_dashboard",
        label="HTTPS dashboard",
        method="GET",
        scheme="https",
        host=PUBLIC_DASHBOARD_HOST,
        connect_host=LOCAL_CADDY_HOST,
        local_port=443,
        path="/",
        expected_status_code=200,
        expected_content_type_prefix="text/html",
    ),
    ProxyRouteExpectation(
        key="users_exist",
        label="Public auth bootstrap",
        method="GET",
        scheme="https",
        host=PUBLIC_DASHBOARD_HOST,
        connect_host=LOCAL_CADDY_HOST,
        local_port=443,
        path="/api/v1/auth/users-exist",
        expected_status_code=200,
        expected_content_type_prefix="application/json",
    ),
    ProxyRouteExpectation(
        key="protected_api_no_bearer",
        label="Protected API without bearer",
        method="GET",
        scheme="https",
        host=PUBLIC_DASHBOARD_HOST,
        connect_host=LOCAL_CADDY_HOST,
        local_port=443,
        path="/api/v1/auth/me",
        expected_status_code=401,
        expected_content_type_prefix="application/json",
    ),
    ProxyRouteExpectation(
        key="map_image_no_cookie",
        label="Map image without cookie",
        method="GET",
        scheme="https",
        host=PUBLIC_DASHBOARD_HOST,
        connect_host=LOCAL_CADDY_HOST,
        local_port=443,
        path="/api/v1/map/images?layer_id=healthcheck&device_id=healthcheck",
        expected_status_code=401,
        expected_content_type_prefix="application/json",
    ),
    ProxyRouteExpectation(
        key="docs_blocked",
        label="Docs blocked",
        method="GET",
        scheme="https",
        host=PUBLIC_DASHBOARD_HOST,
        connect_host=LOCAL_CADDY_HOST,
        local_port=443,
        path="/docs",
        expected_status_code=404,
    ),
    ProxyRouteExpectation(
        key="redoc_blocked",
        label="Redoc blocked",
        method="GET",
        scheme="https",
        host=PUBLIC_DASHBOARD_HOST,
        connect_host=LOCAL_CADDY_HOST,
        local_port=443,
        path="/redoc",
        expected_status_code=404,
    ),
    ProxyRouteExpectation(
        key="openapi_blocked",
        label="OpenAPI blocked",
        method="GET",
        scheme="https",
        host=PUBLIC_DASHBOARD_HOST,
        connect_host=LOCAL_CADDY_HOST,
        local_port=443,
        path="/openapi.json",
        expected_status_code=404,
    ),
    ProxyRouteExpectation(
        key="http_redirect",
        label="HTTP to HTTPS redirect",
        method="GET",
        scheme="http",
        host=PUBLIC_DASHBOARD_HOST,
        connect_host=LOCAL_CADDY_HOST,
        local_port=80,
        path="/",
        expected_status_code=308,
        expected_location=f"https://{PUBLIC_DASHBOARD_HOST}/",
    ),
)


PROXY_HEADER_EXPECTATIONS = (
    ProxyHeaderExpectation("hsts", "Strict-Transport-Security", True),
    ProxyHeaderExpectation("nosniff", "X-Content-Type-Options", True, required_value="nosniff"),
    ProxyHeaderExpectation(
        "referrer_policy",
        "Referrer-Policy",
        True,
        required_value="strict-origin-when-cross-origin",
    ),
    ProxyHeaderExpectation("x_frame_options", "X-Frame-Options", True, required_value="SAMEORIGIN"),
    ProxyHeaderExpectation(
        "permissions_policy",
        "Permissions-Policy",
        True,
        required_contains="geolocation=(self)",
    ),
    ProxyHeaderExpectation("csp_report_only", "Content-Security-Policy-Report-Only", True),
    ProxyHeaderExpectation("server", "Server", False),
    ProxyHeaderExpectation("via", "Via", False),
)


class SystemHealthProbeError(RuntimeError):
    pass


def _status_rank(status: str) -> int:
    return {"ok": 0, "degraded": 1, "error": 2}.get(status, 2)


def _worst_status(statuses: list[str]) -> str:
    if not statuses:
        return "degraded"
    return max(statuses, key=_status_rank)


def _seconds_since(now: datetime, value: datetime | None) -> float | None:
    if value is None:
        return None
    reference_now = now.astimezone(value.tzinfo) if value.tzinfo is not None else datetime.now()
    return max(0.0, (reference_now - value).total_seconds())


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None

    cleaned = value.strip().replace("Z", "+00:00")
    # Windows ISO strings may contain 7 fractional second digits.
    cleaned = re.sub(r"(\.\d{6})\d+([+-]\d{2}:\d{2})$", r"\1\2", cleaned)
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _normalize_json_rows(payload: Any) -> list[dict[str, Any]]:
    if payload in (None, ""):
        return []
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _parse_postgres_read_only(value: Any) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"on", "true", "1", "yes"}:
        return True
    if normalized in {"off", "false", "0", "no"}:
        return False
    return None


def _unchecked_postgres_schema_statuses(detail: str) -> list[SystemPostgresSchemaStatus]:
    return [
        SystemPostgresSchemaStatus(
            schema_name=schema_name,
            status="degraded",
            present=False,
            table_count=None,
            detail=detail,
        )
        for schema_name in EXPECTED_POSTGRES_SCHEMAS
    ]


def _build_postgres_schema_statuses(
    rows: list[dict[str, Any]],
) -> list[SystemPostgresSchemaStatus]:
    counts_by_schema: dict[str, int] = {}
    for row in rows:
        schema_name = str(row.get("schema_name") or "").strip()
        if not schema_name:
            continue
        try:
            table_count = int(row.get("table_count") or 0)
        except (TypeError, ValueError):
            table_count = 0
        counts_by_schema[schema_name] = max(0, table_count)

    statuses: list[SystemPostgresSchemaStatus] = []
    for schema_name in EXPECTED_POSTGRES_SCHEMAS:
        present = schema_name in counts_by_schema
        statuses.append(
            SystemPostgresSchemaStatus(
                schema_name=schema_name,
                status="ok" if present else "error",
                present=present,
                table_count=counts_by_schema.get(schema_name),
                detail=(
                    "Expected PostgreSQL schema is present."
                    if present
                    else "Expected PostgreSQL schema is missing."
                ),
            )
        )
    return statuses


def _run_powershell_json(script: str, *, timeout_seconds: int = 10) -> Any:
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise SystemHealthProbeError("PowerShell probe failed.")

    output = completed.stdout.strip()
    if not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise SystemHealthProbeError("PowerShell probe returned invalid JSON.") from exc


def _read_windows_boot_time() -> SystemRuntimeBootStatus:
    if platform.system().lower() != "windows":
        return SystemRuntimeBootStatus(
            status="degraded",
            boot_time=None,
            detail="Boot time probe is available only on Windows.",
        )

    try:
        payload = _run_powershell_json(
            """
            Get-CimInstance Win32_OperatingSystem |
              Select-Object @{Name='LastBootUpTime';Expression={$_.LastBootUpTime.ToString('o')}} |
              ConvertTo-Json -Compress
            """
        )
    except (OSError, subprocess.SubprocessError, SystemHealthProbeError):
        return SystemRuntimeBootStatus(
            status="degraded",
            boot_time=None,
            detail="Boot time probe failed.",
        )

    rows = _normalize_json_rows(payload)
    boot_time = _parse_datetime(rows[0].get("LastBootUpTime")) if rows else None
    if boot_time is None:
        return SystemRuntimeBootStatus(
            status="degraded",
            boot_time=None,
            detail="Boot time was not available.",
        )
    return SystemRuntimeBootStatus(
        status="ok",
        boot_time=boot_time,
        detail="Boot time is available.",
    )


def _read_startup_task_status(task_name: str = STARTUP_TASK_NAME) -> SystemRuntimeStartupTaskStatus:
    if platform.system().lower() != "windows":
        return SystemRuntimeStartupTaskStatus(
            task_name=task_name,
            status="degraded",
            detail="Scheduled task probe is available only on Windows.",
        )

    escaped_task_name = task_name.replace("'", "''")
    try:
        payload = _run_powershell_json(
            f"""
            $task = Get-ScheduledTask -TaskName '{escaped_task_name}' -ErrorAction SilentlyContinue
            if ($null -eq $task) {{
              @() | ConvertTo-Json -Compress
            }} else {{
              $task | Get-ScheduledTaskInfo |
                Select-Object `
                  @{{Name='LastRunTime';Expression={{if ($_.LastRunTime) {{$_.LastRunTime.ToString('o')}} else {{$null}}}}}},
                  LastTaskResult,
                  @{{Name='NextRunTime';Expression={{if ($_.NextRunTime) {{$_.NextRunTime.ToString('o')}} else {{$null}}}}}} |
                ConvertTo-Json -Compress
            }}
            """
        )
    except (OSError, subprocess.SubprocessError, SystemHealthProbeError):
        return SystemRuntimeStartupTaskStatus(
            task_name=task_name,
            status="degraded",
            detail="Scheduled task probe failed.",
        )

    rows = _normalize_json_rows(payload)
    if not rows:
        return SystemRuntimeStartupTaskStatus(
            task_name=task_name,
            status="error",
            detail="Startup scheduled task was not found.",
        )

    row = rows[0]
    last_task_result = row.get("LastTaskResult")
    try:
        last_task_result = int(last_task_result) if last_task_result is not None else None
    except (TypeError, ValueError):
        last_task_result = None

    status = "ok" if last_task_result == 0 else "error"
    detail = (
        "Startup scheduled task last run succeeded."
        if status == "ok"
        else "Startup scheduled task last run did not report result 0."
    )
    return SystemRuntimeStartupTaskStatus(
        task_name=task_name,
        status=status,
        last_run_time=_parse_datetime(row.get("LastRunTime")),
        next_run_time=_parse_datetime(row.get("NextRunTime")),
        last_task_result=last_task_result,
        detail=detail,
    )


def _read_listener_rows() -> list[dict[str, Any]]:
    if platform.system().lower() != "windows":
        return []

    ports = ",".join(str(port) for port in RUNTIME_CHECK_PORTS)
    try:
        payload = _run_powershell_json(
            f"""
            Get-NetTCPConnection -State Listen |
              Where-Object {{ @({ports}) -contains $_.LocalPort }} |
              Select-Object LocalAddress,LocalPort,OwningProcess |
              ConvertTo-Json -Compress
            """
        )
    except (OSError, subprocess.SubprocessError, SystemHealthProbeError):
        return []

    return _normalize_json_rows(payload)


def _matching_listener_rows(
    rows: list[dict[str, Any]],
    *,
    local_port: int,
    local_address: str | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for row in rows:
        try:
            row_port = int(row.get("LocalPort"))
        except (TypeError, ValueError):
            continue
        if row_port != local_port:
            continue
        if local_address is not None and str(row.get("LocalAddress") or "") != local_address:
            continue
        matches.append(row)
    return matches


def _process_ids(rows: list[dict[str, Any]]) -> list[int]:
    process_ids: set[int] = set()
    for row in rows:
        try:
            process_ids.add(int(row.get("OwningProcess")))
        except (TypeError, ValueError):
            continue
    return sorted(process_ids)


def _build_expected_listener_statuses(rows: list[dict[str, Any]]) -> list[SystemRuntimeListenerStatus]:
    statuses: list[SystemRuntimeListenerStatus] = []
    for expectation in EXPECTED_LISTENERS:
        matches = _matching_listener_rows(
            rows,
            local_port=expectation.local_port,
            local_address=expectation.local_address,
        )
        present = bool(matches)
        statuses.append(
            SystemRuntimeListenerStatus(
                key=expectation.key,
                label=expectation.label,
                status="ok" if present else "error",
                expected=True,
                present=present,
                local_address=expectation.local_address,
                local_port=expectation.local_port,
                process_ids=_process_ids(matches),
                detail="Expected listener is present." if present else "Expected listener is missing.",
            )
        )
    return statuses


def _build_temporary_listener_statuses(rows: list[dict[str, Any]]) -> list[SystemRuntimeListenerStatus]:
    statuses: list[SystemRuntimeListenerStatus] = []
    for port in TEMPORARY_PORTS:
        matches = _matching_listener_rows(rows, local_port=port)
        present = bool(matches)
        statuses.append(
            SystemRuntimeListenerStatus(
                key=f"temporary_{port}",
                label=f"Temporary port {port}",
                status="error" if present else "ok",
                expected=False,
                present=present,
                local_address=None,
                local_port=port,
                process_ids=_process_ids(matches),
                detail="Temporary listener is present." if present else "Temporary listener is absent.",
            )
        )
    return statuses


def _request_local_host(
    expectation: ProxyRouteExpectation,
    *,
    timeout_seconds: int = LOCAL_CADDY_TIMEOUT_SECONDS,
) -> LocalHttpResponse:
    connection = http.client.HTTPConnection(
        expectation.host,
        expectation.local_port,
        timeout=timeout_seconds,
    )
    pending_socket: socket.socket | ssl.SSLSocket | None = None

    try:
        pending_socket = socket.create_connection(
            (expectation.connect_host, expectation.local_port),
            timeout=timeout_seconds,
        )
        if expectation.scheme == "https":
            pending_socket = ssl.create_default_context().wrap_socket(
                pending_socket,
                server_hostname=expectation.host,
            )

        connection.sock = pending_socket
        pending_socket = None
        connection.request(
            expectation.method,
            expectation.path,
            headers={
                "Host": expectation.host,
                "Accept": "*/*",
                "User-Agent": "monitoring-system-health",
            },
        )
        response = connection.getresponse()
        headers = {name.lower(): value for name, value in response.getheaders()}
        response.read(1024)
        return LocalHttpResponse(status_code=int(response.status), headers=headers)
    except (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException) as exc:
        raise SystemHealthProbeError("Local Caddy request failed.") from exc
    finally:
        if pending_socket is not None:
            pending_socket.close()
        connection.close()


def _build_proxy_route_status(expectation: ProxyRouteExpectation) -> SystemProxyRouteStatus:
    try:
        response = _request_local_host(expectation)
    except SystemHealthProbeError:
        return SystemProxyRouteStatus(
            key=expectation.key,
            label=expectation.label,
            status="error",
            method=expectation.method,
            scheme=expectation.scheme,
            host=expectation.host,
            path=expectation.path,
            expected_status_code=expectation.expected_status_code,
            expected_content_type_prefix=expectation.expected_content_type_prefix,
            expected_location=expectation.expected_location,
            detail="Local Caddy route request failed.",
        )

    details: list[str] = []
    content_type = response.headers.get("content-type")
    location = response.headers.get("location")

    if response.status_code != expectation.expected_status_code:
        details.append("Unexpected HTTP status.")
    if expectation.expected_content_type_prefix:
        expected_prefix = expectation.expected_content_type_prefix.lower()
        if not content_type or not content_type.lower().startswith(expected_prefix):
            details.append("Unexpected content type.")
    if expectation.expected_location is not None and location != expectation.expected_location:
        details.append("Unexpected redirect location.")

    status = "error" if details else "ok"
    return SystemProxyRouteStatus(
        key=expectation.key,
        label=expectation.label,
        status=status,
        method=expectation.method,
        scheme=expectation.scheme,
        host=expectation.host,
        path=expectation.path,
        expected_status_code=expectation.expected_status_code,
        actual_status_code=response.status_code,
        expected_content_type_prefix=expectation.expected_content_type_prefix,
        actual_content_type=content_type,
        expected_location=expectation.expected_location,
        actual_location=location,
        detail="; ".join(details) if details else "Route returned the expected response.",
    )


def _header_lookup(headers: dict[str, str], header_name: str) -> str | None:
    return headers.get(header_name.lower())


def _build_proxy_header_statuses() -> list[SystemProxyHeaderStatus]:
    probe_expectation = PROXY_ROUTE_EXPECTATIONS[0]
    try:
        response = _request_local_host(probe_expectation)
    except SystemHealthProbeError:
        return [
            SystemProxyHeaderStatus(
                key=expectation.key,
                header_name=expectation.header_name,
                status="error",
                expected="present" if expectation.expected_present else "absent",
                present=False,
                detail="Header probe request failed.",
            )
            for expectation in PROXY_HEADER_EXPECTATIONS
        ]

    statuses: list[SystemProxyHeaderStatus] = []
    for expectation in PROXY_HEADER_EXPECTATIONS:
        value = _header_lookup(response.headers, expectation.header_name)
        present = value is not None
        details: list[str] = []
        if expectation.expected_present and not present:
            details.append("Expected header is missing.")
        elif not expectation.expected_present and present:
            details.append("Header should be stripped.")
        elif expectation.required_value is not None and value is not None:
            if value.lower() != expectation.required_value.lower():
                details.append("Header value does not match the expected policy.")
        elif expectation.required_contains is not None and value is not None:
            if expectation.required_contains.lower() not in value.lower():
                details.append("Header value does not contain the expected policy.")

        statuses.append(
            SystemProxyHeaderStatus(
                key=expectation.key,
                header_name=expectation.header_name,
                status="error" if details else "ok",
                expected="present" if expectation.expected_present else "absent",
                present=present,
                detail="; ".join(details)
                if details
                else (
                    "Header is present with the expected policy."
                    if expectation.expected_present
                    else "Header is absent as expected."
                ),
            )
        )
    return statuses


def collect_system_runtime_health() -> SystemRuntimeHealthResponse:
    checked_at = datetime.now().astimezone()
    boot = _read_windows_boot_time()
    startup_task = _read_startup_task_status()
    listener_rows = _read_listener_rows()
    expected_listeners = _build_expected_listener_statuses(listener_rows)
    temporary_listeners = _build_temporary_listener_statuses(listener_rows)

    status = _worst_status(
        [
            boot.status,
            startup_task.status,
            *(item.status for item in expected_listeners),
            *(item.status for item in temporary_listeners),
        ]
    )
    return SystemRuntimeHealthResponse(
        status=status,
        checked_at=checked_at,
        boot=boot,
        startup_task=startup_task,
        expected_listeners=expected_listeners,
        temporary_listeners=temporary_listeners,
    )


def collect_system_proxy_health() -> SystemProxyHealthResponse:
    checked_at = datetime.now().astimezone()
    routes = [_build_proxy_route_status(expectation) for expectation in PROXY_ROUTE_EXPECTATIONS]
    headers = _build_proxy_header_statuses()

    status = _worst_status(
        [
            *(item.status for item in routes),
            *(item.status for item in headers),
        ]
    )
    return SystemProxyHealthResponse(
        status=status,
        checked_at=checked_at,
        public_host=PUBLIC_DASHBOARD_HOST,
        routes=routes,
        headers=headers,
    )


def _build_scheduler_job_status(
    job_id: str,
    label: str,
    metrics: JobMetrics,
    *,
    now: datetime,
) -> SystemSchedulerJobStatus:
    details: list[str] = []
    status = "ok"
    last_status = str(metrics.last_status or "unknown")
    last_status_lower = last_status.lower()

    if metrics.failure_count_24h > 0:
        status = "degraded"
        if last_status_lower.startswith("error"):
            details.append("Last run ended with error.")
        details.append("Job reported failures in the last 24 hours.")
    elif last_status_lower.startswith("error"):
        details.append("Last recorded run ended with error outside the current 24-hour window.")
    if metrics.next_run is None:
        status = "degraded"
        details.append("Job has no next run in scheduler metrics.")

    if job_id == SCHEDULER_CORE_JOB_ID:
        last_run_age_seconds = _seconds_since(now, metrics.last_run)
        if metrics.last_run is None:
            status = "degraded"
            details.append("Core quarter-hour job has not recorded a run.")
        elif (
            last_run_age_seconds is not None
            and last_run_age_seconds > SCHEDULER_CORE_JOB_MAX_AGE_SECONDS
        ):
            status = "degraded"
            details.append("Core quarter-hour job last run is older than expected.")

    return SystemSchedulerJobStatus(
        job_id=job_id,
        label=label,
        status=status,
        last_status=last_status,
        last_run=metrics.last_run,
        next_run=metrics.next_run,
        success_count_24h=max(0, int(metrics.success_count_24h)),
        failure_count_24h=max(0, int(metrics.failure_count_24h)),
        last_duration_seconds=metrics.last_duration_seconds,
        detail=" ".join(details) if details else "Scheduler job metrics are in the expected state.",
    )


def collect_system_scheduler_health() -> SystemSchedulerHealthResponse:
    checked_at = datetime.now().astimezone()
    metrics = get_metrics_store(refresh_from_disk=True)
    scheduler_running = metrics.is_scheduler_running()

    jobs = [
        _build_scheduler_job_status(
            job_spec.id,
            job_spec.label,
            metrics.jobs.get(job_spec.id) or JobMetrics(),
            now=checked_at,
        )
        for job_spec in get_scheduler_job_specs()
    ]
    total_success_count_24h = sum(max(0, int(job.success_count_24h)) for job in metrics.jobs.values())
    total_failure_count_24h = sum(max(0, int(job.failure_count_24h)) for job in metrics.jobs.values())

    if not scheduler_running:
        status = "error"
    else:
        status = _worst_status(
            [
                *(job.status for job in jobs),
                "degraded" if total_failure_count_24h > 0 else "ok",
            ]
        )

    return SystemSchedulerHealthResponse(
        status=status,
        checked_at=checked_at,
        scheduler_running=scheduler_running,
        last_heartbeat=metrics.last_heartbeat,
        heartbeat_age_seconds=_seconds_since(checked_at, metrics.last_heartbeat),
        heartbeat_ttl_seconds=SCHEDULER_HEARTBEAT_TTL_SECONDS,
        total_success_count_24h=total_success_count_24h,
        total_failure_count_24h=total_failure_count_24h,
        jobs=jobs,
    )


def _empty_smartfuelpass_period_summary(
    *,
    key: str,
    label: str,
    start: datetime | None,
    end: datetime | None,
) -> SystemSmartFuelPassPeriodSummary:
    return SystemSmartFuelPassPeriodSummary(
        key=key,
        label=label,
        start=start,
        end=end,
        session_count=0,
        total_amount=0.0,
        location_count=0,
        connector_count=0,
        first_session_at=None,
        last_session_at=None,
    )


def _empty_smartfuelpass_period_summaries(
    reference_datetime: datetime,
) -> list[SystemSmartFuelPassPeriodSummary]:
    last_week_start, last_week_end = last_completed_week_period(reference_datetime)
    current_month_start, current_month_end = current_month_period(reference_datetime)
    previous_month_start, previous_month_end = previous_month_period(reference_datetime)
    return [
        _empty_smartfuelpass_period_summary(
            key="last_week",
            label="Posledni uzavreny tyden",
            start=last_week_start,
            end=last_week_end,
        ),
        _empty_smartfuelpass_period_summary(
            key="current_month",
            label="Tento mesic",
            start=current_month_start,
            end=current_month_end,
        ),
        _empty_smartfuelpass_period_summary(
            key="previous_month",
            label="Minuly mesic",
            start=previous_month_start,
            end=previous_month_end,
        ),
        _empty_smartfuelpass_period_summary(
            key="total",
            label="Celkem",
            start=None,
            end=None,
        ),
    ]


def _build_smartfuelpass_job_metric_status(
    job_id: str,
    label: str,
    metrics: JobMetrics | None,
) -> SystemSmartFuelPassJobMetricStatus:
    resolved_metrics = metrics or JobMetrics()
    last_status = str(resolved_metrics.last_status or "unknown")
    last_status_lower = last_status.lower()
    details: list[str] = []
    status = "ok"

    if resolved_metrics.last_run is None:
        status = "degraded"
        details.append("Scheduler metrics do not contain a recorded run for this job.")
    if resolved_metrics.failure_count_24h > 0:
        status = "degraded"
        details.append("Scheduler metrics contain failures in the last 24 hours.")
    if last_status_lower.startswith("error"):
        status = "error"
        details.append("Last recorded run ended with error.")
    elif last_status_lower == "unknown":
        status = "degraded"
        details.append("Last recorded status is unknown.")

    return SystemSmartFuelPassJobMetricStatus(
        job_id=job_id,
        label=label,
        status=status,
        last_status=last_status,
        last_run=resolved_metrics.last_run,
        success_count_24h=max(0, int(resolved_metrics.success_count_24h)),
        failure_count_24h=max(0, int(resolved_metrics.failure_count_24h)),
        last_duration_seconds=resolved_metrics.last_duration_seconds,
        detail=" ".join(details) if details else "Scheduler metrics are in the expected state.",
    )


def _build_smartfuelpass_table_status(
    row: dict[str, Any],
    *,
    now: datetime,
    sync_job: SystemSmartFuelPassJobMetricStatus | None = None,
) -> SystemSmartFuelPassTableStatus:
    total_session_count = max(0, int(row.get("total_session_count") or 0))
    sessions_with_utc_count = max(0, int(row.get("sessions_with_utc_count") or 0))
    missing_ended_at_utc_count = max(0, int(row.get("missing_ended_at_utc_count") or 0))
    last_imported_at = _parse_datetime(row.get("last_imported_at"))
    last_import_age_seconds = _seconds_since(now, last_imported_at)

    details: list[str] = []
    status = "ok"
    if total_session_count <= 0:
        status = "degraded"
        details.append("SmartFuelPass sync table is present but contains no synced sessions.")
    if last_imported_at is None:
        status = "degraded"
        details.append("Last import timestamp is not available.")
    elif (
        last_import_age_seconds is not None
        and last_import_age_seconds > SMARTFUELPASS_TABLE_MAX_IMPORT_AGE_SECONDS
    ):
        sync_age_seconds = (
            _seconds_since(now, sync_job.last_run)
            if sync_job is not None and sync_job.last_run is not None
            else None
        )
        recent_successful_sync = (
            sync_job is not None
            and sync_job.status == "ok"
            and str(sync_job.last_status or "").lower() == "success"
            and sync_age_seconds is not None
            and sync_age_seconds <= SMARTFUELPASS_TABLE_MAX_IMPORT_AGE_SECONDS
        )
        if recent_successful_sync:
            details.append(
                "No newly inserted SmartFuelPass sessions were recorded recently, "
                "but the scheduler sync ran successfully within the expected daily window."
            )
        else:
            status = "degraded"
            details.append(
                "Last newly inserted SmartFuelPass session is older than the expected daily sync window."
            )
    if missing_ended_at_utc_count > 0:
        status = "degraded"
        details.append("Some synced sessions are missing normalized UTC end time.")

    return SystemSmartFuelPassTableStatus(
        status=status,
        table_present=True,
        total_session_count=total_session_count,
        sessions_with_utc_count=sessions_with_utc_count,
        missing_ended_at_utc_count=missing_ended_at_utc_count,
        first_session_at=_parse_datetime(row.get("first_session_at")),
        last_session_at=_parse_datetime(row.get("last_session_at")),
        last_imported_at=last_imported_at,
        last_import_age_seconds=last_import_age_seconds,
        total_amount=round(float(row.get("total_amount") or 0), 2),
        location_count=max(0, int(row.get("location_count") or 0)),
        connector_count=max(0, int(row.get("connector_count") or 0)),
        detail=" ".join(details) if details else "SmartFuelPass sync table and timestamps are in the expected state.",
    )


def _missing_smartfuelpass_table_status() -> SystemSmartFuelPassTableStatus:
    return SystemSmartFuelPassTableStatus(
        status="error",
        table_present=False,
        total_session_count=0,
        sessions_with_utc_count=0,
        missing_ended_at_utc_count=0,
        first_session_at=None,
        last_session_at=None,
        last_imported_at=None,
        last_import_age_seconds=None,
        total_amount=0.0,
        location_count=0,
        connector_count=0,
        detail="SmartFuelPass sync table monitoring.smartfuelpass_relace is missing.",
    )


def _failed_smartfuelpass_table_status() -> SystemSmartFuelPassTableStatus:
    return SystemSmartFuelPassTableStatus(
        status="error",
        table_present=False,
        total_session_count=0,
        sessions_with_utc_count=0,
        missing_ended_at_utc_count=0,
        first_session_at=None,
        last_session_at=None,
        last_imported_at=None,
        last_import_age_seconds=None,
        total_amount=0.0,
        location_count=0,
        connector_count=0,
        detail="SmartFuelPass database summary query failed.",
    )


def _query_smartfuelpass_period_summary(
    session,
    *,
    key: str,
    label: str,
    start: datetime | None,
    end: datetime | None,
) -> SystemSmartFuelPassPeriodSummary:
    row = (
        session.execute(
            text(
                """
                SELECT
                    COUNT(*)::int AS session_count,
                    COALESCE(SUM(suma), 0)::float AS total_amount,
                    COUNT(DISTINCT NULLIF(btrim(lokace), ''))::int AS location_count,
                    COUNT(DISTINCT NULLIF(btrim(connector_id), ''))::int AS connector_count,
                    MIN(ended_at) AS first_session_at,
                    MAX(ended_at) AS last_session_at
                FROM monitoring.smartfuelpass_relace
                WHERE (:start_at IS NULL OR ended_at >= :start_at)
                  AND (:end_at IS NULL OR ended_at <= :end_at)
                """
            ),
            {"start_at": start, "end_at": end},
        )
        .mappings()
        .one()
    )
    return SystemSmartFuelPassPeriodSummary(
        key=key,
        label=label,
        start=start,
        end=end,
        session_count=max(0, int(row.get("session_count") or 0)),
        total_amount=round(float(row.get("total_amount") or 0), 2),
        location_count=max(0, int(row.get("location_count") or 0)),
        connector_count=max(0, int(row.get("connector_count") or 0)),
        first_session_at=_parse_datetime(row.get("first_session_at")),
        last_session_at=_parse_datetime(row.get("last_session_at")),
    )


def _query_smartfuelpass_period_summaries(
    session,
    *,
    reference_datetime: datetime,
) -> list[SystemSmartFuelPassPeriodSummary]:
    last_week_start, last_week_end = last_completed_week_period(reference_datetime)
    current_month_start, current_month_end = current_month_period(reference_datetime)
    previous_month_start, previous_month_end = previous_month_period(reference_datetime)
    periods = (
        ("last_week", "Posledni uzavreny tyden", last_week_start, last_week_end),
        ("current_month", "Tento mesic", current_month_start, current_month_end),
        ("previous_month", "Minuly mesic", previous_month_start, previous_month_end),
        ("total", "Celkem", None, None),
    )
    return [
        _query_smartfuelpass_period_summary(
            session,
            key=key,
            label=label,
            start=start,
            end=end,
        )
        for key, label, start, end in periods
    ]


def collect_system_smartfuelpass_health() -> SystemSmartFuelPassHealthResponse:
    reference_datetime = datetime.now()
    checked_at = reference_datetime.astimezone()
    metrics = get_metrics_store(refresh_from_disk=True)
    sync_job = _build_smartfuelpass_job_metric_status(
        SMARTFUELPASS_SYNC_JOB_ID,
        "Databazovy sync relaci",
        metrics.jobs.get(SMARTFUELPASS_SYNC_JOB_ID),
    )
    weekly_report_job = _build_smartfuelpass_job_metric_status(
        SMARTFUELPASS_WEEKLY_REPORT_JOB_ID,
        "Tydenni email report",
        metrics.jobs.get(SMARTFUELPASS_WEEKLY_REPORT_JOB_ID),
    )

    session = None
    try:
        session = get_session_pg()
        table_present = bool(
            session.execute(
                text("SELECT to_regclass('monitoring.smartfuelpass_relace') IS NOT NULL")
            ).scalar()
        )
        if not table_present:
            table = _missing_smartfuelpass_table_status()
            report_periods = _empty_smartfuelpass_period_summaries(reference_datetime)
        else:
            aggregate_row = (
                session.execute(
                    text(
                        """
                        SELECT
                            COUNT(*)::int AS total_session_count,
                            COUNT(ended_at_utc)::int AS sessions_with_utc_count,
                            COALESCE(SUM(CASE WHEN ended_at_utc IS NULL THEN 1 ELSE 0 END), 0)::int
                                AS missing_ended_at_utc_count,
                            MIN(ended_at) AS first_session_at,
                            MAX(ended_at) AS last_session_at,
                            MAX(imported_at) AS last_imported_at,
                            COALESCE(SUM(suma), 0)::float AS total_amount,
                            COUNT(DISTINCT NULLIF(btrim(lokace), ''))::int AS location_count,
                            COUNT(DISTINCT NULLIF(btrim(connector_id), ''))::int AS connector_count
                        FROM monitoring.smartfuelpass_relace
                        """
                    )
                )
                .mappings()
                .one()
            )
            table = _build_smartfuelpass_table_status(
                dict(aggregate_row),
                now=checked_at,
                sync_job=sync_job,
            )
            report_periods = _query_smartfuelpass_period_summaries(
                session,
                reference_datetime=reference_datetime,
            )
    except (OSError, RuntimeError, SQLAlchemyError):
        table = _failed_smartfuelpass_table_status()
        report_periods = _empty_smartfuelpass_period_summaries(reference_datetime)
    finally:
        if session is not None:
            session.close()

    status = _worst_status([table.status, sync_job.status, weekly_report_job.status])
    return SystemSmartFuelPassHealthResponse(
        status=status,
        checked_at=checked_at,
        source="monitoring.smartfuelpass_relace",
        period_basis="ended_at",
        table=table,
        sync_job=sync_job,
        weekly_report_job=weekly_report_job,
        report_periods=report_periods,
    )


def collect_system_database_health() -> SystemDatabaseHealthResponse:
    checked_at = datetime.now().astimezone()
    schema_list_sql = ", ".join(f"'{schema_name}'" for schema_name in EXPECTED_POSTGRES_SCHEMAS)
    session = None

    try:
        session = get_session_pg()
        started_at = perf_counter()
        metadata = (
            session.execute(
                text(
                    """
                    SELECT
                        CURRENT_TIMESTAMP AS server_time,
                        current_setting('TimeZone') AS server_timezone,
                        current_setting('server_version') AS server_version,
                        current_setting('transaction_read_only') AS transaction_read_only
                    """
                )
            )
            .mappings()
            .one()
        )
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        schema_rows = (
            session.execute(
                text(
                    f"""
                    SELECT
                        n.nspname AS schema_name,
                        COUNT(c.oid)::int AS table_count
                    FROM pg_namespace n
                    LEFT JOIN pg_class c
                      ON c.relnamespace = n.oid
                     AND c.relkind IN ('r', 'p')
                    WHERE n.nspname IN ({schema_list_sql})
                    GROUP BY n.nspname
                    ORDER BY n.nspname
                    """
                )
            )
            .mappings()
            .all()
        )
    except (OSError, RuntimeError, SQLAlchemyError):
        postgres = SystemPostgresConnectionStatus(
            status="error",
            connected=False,
            latency_ms=None,
            server_time=None,
            server_timezone=None,
            server_version=None,
            transaction_read_only=None,
            detail="PostgreSQL connection or metadata query failed.",
        )
        return SystemDatabaseHealthResponse(
            status="error",
            checked_at=checked_at,
            postgres=postgres,
            expected_schemas=_unchecked_postgres_schema_statuses(
                "Schema presence was not checked because PostgreSQL was unavailable."
            ),
        )
    finally:
        if session is not None:
            session.close()

    read_only = _parse_postgres_read_only(metadata.get("transaction_read_only"))
    if read_only is True:
        postgres_status = "error"
        postgres_detail = "PostgreSQL is reachable but reports a read-only transaction state."
    elif read_only is None:
        postgres_status = "degraded"
        postgres_detail = "PostgreSQL is reachable but read-only state could not be parsed."
    else:
        postgres_status = "ok"
        postgres_detail = "PostgreSQL metadata query succeeded."

    postgres = SystemPostgresConnectionStatus(
        status=postgres_status,
        connected=True,
        latency_ms=latency_ms,
        server_time=_parse_datetime(metadata.get("server_time")),
        server_timezone=str(metadata.get("server_timezone") or ""),
        server_version=str(metadata.get("server_version") or ""),
        transaction_read_only=read_only,
        detail=postgres_detail,
    )
    schema_statuses = _build_postgres_schema_statuses([dict(row) for row in schema_rows])
    status = _worst_status([postgres.status, *(item.status for item in schema_statuses)])

    return SystemDatabaseHealthResponse(
        status=status,
        checked_at=checked_at,
        postgres=postgres,
        expected_schemas=schema_statuses,
    )
