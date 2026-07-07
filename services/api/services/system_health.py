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
from typing import Any

from core.scheduler.job_schedule import get_scheduler_job_specs
from core.scheduler.metrics import (
    JobMetrics,
    SCHEDULER_HEARTBEAT_TTL_SECONDS,
    get_metrics_store,
)
from services.api.schemas.admin import (
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
