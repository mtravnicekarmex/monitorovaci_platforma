from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from core.scheduler.job_schedule import get_scheduler_job_specs
from core.scheduler.metrics import JobMetrics
from services.api.routes import system_health as system_health_route
from services.api.schemas.admin import (
    SystemSchedulerHealthResponse,
    SystemProxyHealthResponse,
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


def _expected_proxy_headers(*, include_server: bool = False, omit_hsts: bool = False) -> dict[str, str]:
    headers = {
        "content-type": "text/html; charset=utf-8",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin-when-cross-origin",
        "x-frame-options": "SAMEORIGIN",
        "permissions-policy": "camera=(), geolocation=(self), microphone=()",
        "content-security-policy-report-only": "default-src 'self'",
    }
    if not omit_hsts:
        headers["strict-transport-security"] = "max-age=31536000"
    if include_server:
        headers["server"] = "unexpected"
    return headers


def _proxy_response_for_expectation(
    expectation: system_health.ProxyRouteExpectation,
    *,
    protected_status: int = 401,
    header_overrides: dict[str, str] | None = None,
) -> system_health.LocalHttpResponse:
    headers: dict[str, str] = {}
    if expectation.key == "https_dashboard":
        headers = _expected_proxy_headers()
    elif expectation.key == "users_exist":
        headers = {"content-type": "application/json"}
    elif expectation.key in {"protected_api_no_bearer", "map_image_no_cookie"}:
        headers = {"content-type": "application/json"}
    elif expectation.key == "http_redirect":
        headers = {"location": f"https://{system_health.PUBLIC_DASHBOARD_HOST}/"}

    if header_overrides:
        headers.update(header_overrides)

    status_by_key = {
        "https_dashboard": 200,
        "users_exist": 200,
        "protected_api_no_bearer": protected_status,
        "map_image_no_cookie": 401,
        "docs_blocked": 404,
        "redoc_blocked": 404,
        "openapi_blocked": 404,
        "http_redirect": 308,
    }
    return system_health.LocalHttpResponse(
        status_code=status_by_key[expectation.key],
        headers=headers,
    )


def test_collect_system_proxy_health_reports_ok(monkeypatch):
    def fake_request(
        expectation: system_health.ProxyRouteExpectation,
        *,
        timeout_seconds: int = system_health.LOCAL_CADDY_TIMEOUT_SECONDS,
    ) -> system_health.LocalHttpResponse:
        del timeout_seconds
        return _proxy_response_for_expectation(expectation)

    monkeypatch.setattr(system_health, "_request_local_host", fake_request)

    response = system_health.collect_system_proxy_health()

    assert response.status == "ok"
    assert response.public_host == system_health.PUBLIC_DASHBOARD_HOST
    assert {route.key: route.status for route in response.routes} == {
        "https_dashboard": "ok",
        "users_exist": "ok",
        "protected_api_no_bearer": "ok",
        "map_image_no_cookie": "ok",
        "docs_blocked": "ok",
        "redoc_blocked": "ok",
        "openapi_blocked": "ok",
        "http_redirect": "ok",
    }
    assert all(header.status == "ok" for header in response.headers)


def test_collect_system_proxy_health_reports_unexpected_route_and_header(monkeypatch):
    def fake_request(
        expectation: system_health.ProxyRouteExpectation,
        *,
        timeout_seconds: int = system_health.LOCAL_CADDY_TIMEOUT_SECONDS,
    ) -> system_health.LocalHttpResponse:
        del timeout_seconds
        if expectation.key == "https_dashboard":
            headers = _expected_proxy_headers(include_server=True, omit_hsts=True)
            return system_health.LocalHttpResponse(status_code=200, headers=headers)
        return _proxy_response_for_expectation(expectation, protected_status=200)

    monkeypatch.setattr(system_health, "_request_local_host", fake_request)

    response = system_health.collect_system_proxy_health()
    routes_by_key = {route.key: route for route in response.routes}
    headers_by_key = {header.key: header for header in response.headers}

    assert response.status == "error"
    assert routes_by_key["protected_api_no_bearer"].status == "error"
    assert routes_by_key["protected_api_no_bearer"].actual_status_code == 200
    assert headers_by_key["hsts"].status == "error"
    assert headers_by_key["hsts"].present is False
    assert headers_by_key["server"].status == "error"
    assert headers_by_key["server"].present is True


def _fake_scheduler_jobs(
    *,
    reference_time: datetime,
    failing_job_id: str | None = None,
) -> dict[str, JobMetrics]:
    jobs: dict[str, JobMetrics] = {}
    for offset, job_spec in enumerate(get_scheduler_job_specs()):
        failed = job_spec.id == failing_job_id
        jobs[job_spec.id] = JobMetrics(
            last_run=reference_time - timedelta(minutes=10),
            last_status="error" if failed else "success",
            last_duration_seconds=1.5,
            next_run=reference_time + timedelta(minutes=offset + 1),
            failure_count_24h=1 if failed else 0,
            success_count_24h=0 if failed else 2,
        )
    return jobs


def test_collect_system_scheduler_health_reports_ok(monkeypatch):
    reference_time = datetime.now()

    class FakeMetricsStore:
        jobs = _fake_scheduler_jobs(reference_time=reference_time)
        last_heartbeat = reference_time - timedelta(seconds=30)

        def is_scheduler_running(self):
            return True

    monkeypatch.setattr(
        system_health,
        "get_metrics_store",
        lambda *args, **kwargs: FakeMetricsStore(),
    )

    response = system_health.collect_system_scheduler_health()

    assert response.status == "ok"
    assert response.scheduler_running is True
    assert response.total_failure_count_24h == 0
    assert response.heartbeat_age_seconds is not None
    assert {job.job_id: job.status for job in response.jobs}["quarter_hour_job"] == "ok"


def test_collect_system_scheduler_health_reports_failure_metrics(monkeypatch):
    reference_time = datetime.now()

    class FakeMetricsStore:
        jobs = _fake_scheduler_jobs(
            reference_time=reference_time,
            failing_job_id="daily_job",
        )
        last_heartbeat = reference_time - timedelta(seconds=30)

        def is_scheduler_running(self):
            return True

    monkeypatch.setattr(
        system_health,
        "get_metrics_store",
        lambda *args, **kwargs: FakeMetricsStore(),
    )

    response = system_health.collect_system_scheduler_health()
    jobs_by_id = {job.job_id: job for job in response.jobs}

    assert response.status == "degraded"
    assert response.total_failure_count_24h == 1
    assert jobs_by_id["daily_job"].status == "degraded"
    assert "failures" in jobs_by_id["daily_job"].detail


def test_collect_system_scheduler_health_reports_stopped_scheduler(monkeypatch):
    reference_time = datetime.now()

    class FakeMetricsStore:
        jobs = _fake_scheduler_jobs(reference_time=reference_time)
        last_heartbeat = reference_time - timedelta(minutes=10)

        def is_scheduler_running(self):
            return False

    monkeypatch.setattr(
        system_health,
        "get_metrics_store",
        lambda *args, **kwargs: FakeMetricsStore(),
    )

    response = system_health.collect_system_scheduler_health()

    assert response.status == "error"
    assert response.scheduler_running is False


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


def test_system_proxy_health_route_delegates_to_service(monkeypatch):
    expected = SystemProxyHealthResponse(
        status="ok",
        checked_at=datetime(2026, 7, 7, 7, 0),
        public_host=system_health.PUBLIC_DASHBOARD_HOST,
        routes=[],
        headers=[],
    )
    monkeypatch.setattr(
        system_health_route,
        "collect_system_proxy_health",
        lambda: expected,
    )

    response = system_health_route.get_system_proxy_health(
        current_user=SimpleNamespace(is_admin=True)
    )

    assert response is expected


def test_system_scheduler_health_route_delegates_to_service(monkeypatch):
    expected = SystemSchedulerHealthResponse(
        status="ok",
        checked_at=datetime(2026, 7, 7, 7, 0),
        scheduler_running=True,
        last_heartbeat=datetime(2026, 7, 7, 6, 59),
        heartbeat_age_seconds=60.0,
        heartbeat_ttl_seconds=300,
        total_success_count_24h=1,
        total_failure_count_24h=0,
        jobs=[],
    )
    monkeypatch.setattr(
        system_health_route,
        "collect_system_scheduler_health",
        lambda: expected,
    )

    response = system_health_route.get_system_scheduler_health(
        current_user=SimpleNamespace(is_admin=True)
    )

    assert response is expected
