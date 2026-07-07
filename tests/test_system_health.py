from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from services.api.routes import system_health as system_health_route
from services.api.schemas.admin import (
    SystemRuntimeBootStatus,
    SystemRuntimeHealthResponse,
    SystemRuntimeStartupTaskStatus,
)
from services.api.services import system_health


def _listener_rows(*, include_temp: bool = False, omit_fastapi: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {"LocalAddress": "::", "LocalPort": 80, "OwningProcess": 10},
        {"LocalAddress": "::", "LocalPort": 443, "OwningProcess": 10},
        {"LocalAddress": "127.0.0.1", "LocalPort": 2019, "OwningProcess": 10},
        {"LocalAddress": "127.0.0.1", "LocalPort": 8001, "OwningProcess": 30},
    ]
    if not omit_fastapi:
        rows.append({"LocalAddress": "127.0.0.1", "LocalPort": 8000, "OwningProcess": 20})
    if include_temp:
        rows.append({"LocalAddress": "127.0.0.1", "LocalPort": 8010, "OwningProcess": 40})
    return rows


def test_collect_system_runtime_health_reports_ok(monkeypatch):
    monkeypatch.setattr(system_health.platform, "system", lambda: "Windows")

    def fake_powershell_json(script: str, *, timeout_seconds: int = 10):
        del timeout_seconds
        if "Win32_OperatingSystem" in script:
            return {"LastBootUpTime": "2026-07-07T06:00:00+02:00"}
        if "Get-ScheduledTask" in script:
            return {
                "LastRunTime": "2026-07-07T06:01:00+02:00",
                "LastTaskResult": 0,
                "NextRunTime": None,
            }
        if "Get-NetTCPConnection" in script:
            return _listener_rows()
        raise AssertionError(f"Unexpected PowerShell probe: {script}")

    monkeypatch.setattr(system_health, "_run_powershell_json", fake_powershell_json)

    response = system_health.collect_system_runtime_health()

    assert response.status == "ok"
    assert response.boot.boot_time == datetime.fromisoformat("2026-07-07T06:00:00+02:00")
    assert response.startup_task.last_task_result == 0
    assert {listener.key: listener.present for listener in response.expected_listeners} == {
        "caddy_http": True,
        "caddy_https": True,
        "caddy_admin": True,
        "fastapi": True,
        "streamlit": True,
    }
    assert all(not listener.present for listener in response.temporary_listeners)


def test_collect_system_runtime_health_reports_missing_expected_and_temporary_listener(monkeypatch):
    monkeypatch.setattr(system_health.platform, "system", lambda: "Windows")

    def fake_powershell_json(script: str, *, timeout_seconds: int = 10):
        del timeout_seconds
        if "Win32_OperatingSystem" in script:
            return {"LastBootUpTime": "2026-07-07T06:00:00+02:00"}
        if "Get-ScheduledTask" in script:
            return {
                "LastRunTime": "2026-07-07T06:01:00+02:00",
                "LastTaskResult": 0,
                "NextRunTime": None,
            }
        if "Get-NetTCPConnection" in script:
            return _listener_rows(include_temp=True, omit_fastapi=True)
        raise AssertionError(f"Unexpected PowerShell probe: {script}")

    monkeypatch.setattr(system_health, "_run_powershell_json", fake_powershell_json)

    response = system_health.collect_system_runtime_health()
    expected_by_key = {listener.key: listener for listener in response.expected_listeners}
    temporary_by_key = {listener.key: listener for listener in response.temporary_listeners}

    assert response.status == "error"
    assert expected_by_key["fastapi"].status == "error"
    assert expected_by_key["fastapi"].present is False
    assert temporary_by_key["temporary_8010"].status == "error"
    assert temporary_by_key["temporary_8010"].present is True


def test_collect_system_runtime_health_handles_nonzero_startup_task_result(monkeypatch):
    monkeypatch.setattr(system_health.platform, "system", lambda: "Windows")

    def fake_powershell_json(script: str, *, timeout_seconds: int = 10):
        del timeout_seconds
        if "Win32_OperatingSystem" in script:
            return {"LastBootUpTime": "2026-07-07T06:00:00+02:00"}
        if "Get-ScheduledTask" in script:
            return {
                "LastRunTime": "2026-07-07T06:01:00+02:00",
                "LastTaskResult": 1,
                "NextRunTime": None,
            }
        if "Get-NetTCPConnection" in script:
            return _listener_rows()
        raise AssertionError(f"Unexpected PowerShell probe: {script}")

    monkeypatch.setattr(system_health, "_run_powershell_json", fake_powershell_json)

    response = system_health.collect_system_runtime_health()

    assert response.status == "error"
    assert response.startup_task.status == "error"
    assert response.startup_task.last_task_result == 1


def test_system_runtime_health_route_delegates_to_service(monkeypatch):
    expected = SystemRuntimeHealthResponse(
        status="ok",
        checked_at=datetime(2026, 7, 7, 7, 0),
        boot=SystemRuntimeBootStatus(
            status="ok",
            boot_time=datetime(2026, 7, 7, 6, 0),
            detail="ok",
        ),
        startup_task=SystemRuntimeStartupTaskStatus(
            task_name="API_dashboard_caddy",
            status="ok",
            last_task_result=0,
            detail="ok",
        ),
        expected_listeners=[],
        temporary_listeners=[],
    )
    monkeypatch.setattr(
        system_health_route,
        "collect_system_runtime_health",
        lambda: expected,
    )

    response = system_health_route.get_system_runtime_health(
        current_user=SimpleNamespace(is_admin=True)
    )

    assert response is expected
