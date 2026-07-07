from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import platform
import re
import subprocess
from typing import Any

from services.api.schemas.admin import (
    SystemRuntimeBootStatus,
    SystemRuntimeHealthResponse,
    SystemRuntimeListenerStatus,
    SystemRuntimeStartupTaskStatus,
)


STARTUP_TASK_NAME = "API_dashboard_caddy"
RUNTIME_CHECK_PORTS = (80, 443, 2019, 8000, 8001, 8010, 8011)
TEMPORARY_PORTS = (8010, 8011)


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


class SystemHealthProbeError(RuntimeError):
    pass


def _status_rank(status: str) -> int:
    return {"ok": 0, "degraded": 1, "error": 2}.get(status, 2)


def _worst_status(statuses: list[str]) -> str:
    if not statuses:
        return "degraded"
    return max(statuses, key=_status_rank)


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
