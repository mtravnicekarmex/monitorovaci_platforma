from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
import pytest

from services.api.core import monitoring_auth
from services.api.core.runtime_state import api_readiness
from services.api.routes import monitoring
from services.api.services.monitoring_facade import (
    project_scheduler_health,
    project_system_database_health,
    project_system_proxy_health,
    project_system_runtime_health,
    project_system_scheduler_health,
    project_system_smartfuelpass_health,
)


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_monitoring_auth_is_closed_when_not_configured(monkeypatch):
    monkeypatch.setattr(
        monitoring_auth,
        "get_configured_monitoring_token_hashes",
        lambda: (),
    )

    with pytest.raises(HTTPException) as exc_info:
        monitoring_auth.require_monitoring_agent(_credentials("unused"))

    assert exc_info.value.status_code == 503


def test_monitoring_auth_accepts_only_matching_bearer_hash(monkeypatch):
    token = "test-only-monitoring-credential"
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        monitoring_auth,
        "get_configured_monitoring_token_hashes",
        lambda: (token_hash,),
    )

    assert monitoring_auth.require_monitoring_agent(_credentials(token)) == (
        "monitoring-agent"
    )

    with pytest.raises(HTTPException) as exc_info:
        monitoring_auth.require_monitoring_agent(_credentials("wrong"))
    assert exc_info.value.status_code == 401
    assert exc_info.value.headers == {"WWW-Authenticate": "Bearer"}


def test_monitoring_hash_configuration_supports_rotation(monkeypatch):
    values = {
        "MONITORING_AGENT_TOKEN_SHA256": "a" * 64,
        "MONITORING_AGENT_PREVIOUS_TOKEN_SHA256": "B" * 64,
    }
    monkeypatch.setattr(
        monitoring_auth,
        "config",
        lambda name, default="": values.get(name, default),
    )

    assert monitoring_auth.get_configured_monitoring_token_hashes() == (
        "a" * 64,
        "b" * 64,
    )


def test_monitoring_hash_configuration_rejects_raw_token(monkeypatch):
    monkeypatch.setattr(
        monitoring_auth,
        "config",
        lambda name, default="": (
            "this-is-not-a-hash"
            if name == "MONITORING_AGENT_TOKEN_SHA256"
            else default
        ),
    )

    with pytest.raises(ValueError, match="SHA-256"):
        monitoring_auth.get_configured_monitoring_token_hashes()


def test_monitoring_readiness_preserves_unavailable_state():
    api_readiness.mark_not_ready()
    response = Response()

    payload = monitoring.get_monitoring_readiness(response)

    assert response.status_code == 503
    assert payload == {"status": "unavailable"}


@pytest.mark.parametrize(
    ("route_name", "collector_name", "projector_name"),
    [
        (
            "get_monitoring_scheduler_health",
            "collect_system_scheduler_health",
            "project_system_scheduler_health",
        ),
        (
            "get_monitoring_detailed_scheduler_health",
            "collect_scheduler_health",
            "project_scheduler_health",
        ),
        (
            "get_monitoring_runtime_health",
            "collect_system_runtime_health",
            "project_system_runtime_health",
        ),
        (
            "get_monitoring_database_health",
            "collect_system_database_health",
            "project_system_database_health",
        ),
        (
            "get_monitoring_proxy_health",
            "collect_system_proxy_health",
            "project_system_proxy_health",
        ),
        (
            "get_monitoring_smartfuelpass_health",
            "collect_system_smartfuelpass_health",
            "project_system_smartfuelpass_health",
        ),
    ],
)
def test_monitoring_routes_reuse_collectors_through_safe_projection(
    monkeypatch,
    route_name,
    collector_name,
    projector_name,
):
    source = object()
    expected = object()
    monkeypatch.setattr(monitoring, collector_name, lambda: source)
    monkeypatch.setattr(
        monitoring,
        projector_name,
        lambda value: expected if value is source else None,
    )

    assert getattr(monitoring, route_name)() is expected


def test_monitoring_router_exposes_authenticated_get_only_surface():
    app = FastAPI()
    app.include_router(monitoring.router)
    monitored_routes = [
        route
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/monitoring/")
    ]

    assert {route.path for route in monitored_routes} == {
        "/api/v1/monitoring/health/live",
        "/api/v1/monitoring/health/ready",
        "/api/v1/monitoring/health/scheduler",
        "/api/v1/monitoring/health/system/database",
        "/api/v1/monitoring/health/system/proxy",
        "/api/v1/monitoring/health/system/scheduler",
        "/api/v1/monitoring/health/system/runtime",
        "/api/v1/monitoring/health/system/smartfuelpass",
    }
    assert all(route.methods == {"GET"} for route in monitored_routes)
    assert all(
        any(
            dependency.call is monitoring_auth.require_monitoring_agent
            for dependency in route.dependant.dependencies
        )
        for route in monitored_routes
    )

    schema_properties = {
        property_name
        for schema in app.openapi().get("components", {}).get("schemas", {}).values()
        for property_name in schema.get("properties", {})
    }
    assert {
        "status",
        "checked_at",
        "scheduler_running",
        "transaction_read_only",
        "missing_ended_at_utc_count",
    } <= schema_properties
    assert {
        "actual_content_type",
        "actual_location",
        "description",
        "detail",
        "is_manual_runnable",
        "label",
        "local_address",
        "next_run_time",
        "process_ids",
        "public_host",
        "report_periods",
        "server_time",
        "server_timezone",
        "server_version",
        "table_count",
        "total_amount",
    }.isdisjoint(schema_properties)


def test_monitoring_projections_drop_transient_sensitive_and_capability_fields():
    now = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
    job = SimpleNamespace(
        id="job",
        label="drop-label",
        description="drop-description",
        is_scheduled=True,
        is_manual_runnable=True,
        last_run=now,
        last_status="success",
        last_duration_seconds=1.0,
        next_run=now,
        failure_rate_24h=0.0,
        avg_duration_24h=1.0,
    )
    scheduled_run = SimpleNamespace(
        job_id="job",
        job_label="drop-label",
        description="drop-description",
        scheduled_at=now,
    )
    detailed = project_scheduler_health(
        SimpleNamespace(
            status="ok",
            scheduler_running=True,
            jobs=[job],
            schedule=[scheduled_run],
            checked_at=now,
        )
    ).model_dump()
    assert set(detailed["jobs"][0]) == {
        "id",
        "is_scheduled",
        "last_run",
        "last_status",
        "last_duration_seconds",
        "next_run",
        "failure_rate_24h",
        "avg_duration_24h",
    }
    assert set(detailed["schedule"][0]) == {"job_id", "scheduled_at"}

    system_scheduler = project_system_scheduler_health(
        SimpleNamespace(
            status="ok",
            checked_at=now,
            scheduler_running=True,
            last_heartbeat=now,
            heartbeat_age_seconds=0.0,
            heartbeat_ttl_seconds=300,
            total_success_count_24h=1,
            total_failure_count_24h=0,
            jobs=[
                SimpleNamespace(
                    job_id="job",
                    label="drop-label",
                    status="ok",
                    last_status="success",
                    last_run=now,
                    next_run=now,
                    success_count_24h=1,
                    failure_count_24h=0,
                    last_duration_seconds=1.0,
                    detail="drop-detail",
                )
            ],
        )
    ).model_dump()
    assert "label" not in system_scheduler["jobs"][0]
    assert "detail" not in system_scheduler["jobs"][0]

    listener = SimpleNamespace(
        key="api",
        label="drop-label",
        status="ok",
        expected=True,
        present=True,
        local_address="drop-address",
        local_port=8000,
        process_ids=[1234],
        detail="drop-detail",
    )
    runtime = project_system_runtime_health(
        SimpleNamespace(
            status="ok",
            checked_at=now,
            boot=SimpleNamespace(status="ok", boot_time=now, detail="drop-detail"),
            startup_task=SimpleNamespace(
                task_name="task",
                status="ok",
                last_run_time=now,
                next_run_time=now,
                last_task_result=0,
                detail="drop-detail",
            ),
            expected_listeners=[listener],
            temporary_listeners=[],
        )
    ).model_dump()
    assert set(runtime["expected_listeners"][0]) == {
        "key",
        "status",
        "expected",
        "present",
        "local_port",
    }

    database = project_system_database_health(
        SimpleNamespace(
            status="ok",
            checked_at=now,
            postgres=SimpleNamespace(
                status="ok",
                connected=True,
                latency_ms=1.0,
                server_time=now,
                server_timezone="drop-timezone",
                server_version="drop-version",
                transaction_read_only=False,
                detail="drop-detail",
            ),
            expected_schemas=[
                SimpleNamespace(
                    schema_name="monitoring",
                    status="ok",
                    present=True,
                    table_count=10,
                    detail="drop-detail",
                )
            ],
        )
    ).model_dump()
    assert set(database["postgres"]) == {
        "status",
        "connected",
        "latency_ms",
        "transaction_read_only",
    }
    assert set(database["expected_schemas"][0]) == {
        "schema_name",
        "status",
        "present",
    }

    proxy = project_system_proxy_health(
        SimpleNamespace(
            status="ok",
            checked_at=now,
            public_host="drop-host",
            routes=[
                SimpleNamespace(
                    key="https_dashboard",
                    label="drop-label",
                    status="ok",
                    method="GET",
                    scheme="https",
                    host="drop-host",
                    path="/drop-path",
                    expected_status_code=200,
                    actual_status_code=200,
                    expected_content_type_prefix="text/html",
                    actual_content_type="text/html",
                    expected_location=None,
                    actual_location=None,
                    detail="drop-detail",
                )
            ],
            headers=[
                SimpleNamespace(
                    key="header",
                    header_name="drop-header-name",
                    status="ok",
                    expected="present",
                    present=True,
                    detail="drop-detail",
                )
            ],
        )
    ).model_dump()
    assert set(proxy["routes"][0]) == {
        "key",
        "status",
        "expected_status_code",
        "actual_status_code",
    }
    assert set(proxy["headers"][0]) == {"key", "status", "expected", "present"}

    smartfuelpass_job = SimpleNamespace(
        job_id="job",
        label="drop-label",
        status="ok",
        last_status="success",
        last_run=now,
        success_count_24h=1,
        failure_count_24h=0,
        last_duration_seconds=1.0,
        detail="drop-detail",
    )
    smartfuelpass = project_system_smartfuelpass_health(
        SimpleNamespace(
            status="ok",
            checked_at=now,
            source="drop-source",
            period_basis="drop-period",
            table=SimpleNamespace(
                status="ok",
                table_present=True,
                missing_ended_at_utc_count=0,
                last_imported_at=now,
                last_import_age_seconds=0.0,
                total_amount=999.0,
                detail="drop-detail",
            ),
            sync_job=smartfuelpass_job,
            weekly_report_job=smartfuelpass_job,
            report_periods=[SimpleNamespace(total_amount=999.0)],
        )
    ).model_dump()
    assert set(smartfuelpass["table"]) == {
        "status",
        "table_present",
        "missing_ended_at_utc_count",
        "last_imported_at",
        "last_import_age_seconds",
    }
    assert "report_periods" not in smartfuelpass
