from __future__ import annotations

import hashlib

from fastapi import FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials
import pytest

from services.api.core import monitoring_auth
from services.api.core.runtime_state import api_readiness
from services.api.routes import monitoring


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


def test_monitoring_scheduler_route_reuses_safe_collector(monkeypatch):
    expected = object()
    monkeypatch.setattr(
        monitoring,
        "collect_system_scheduler_health",
        lambda: expected,
    )

    assert monitoring.get_monitoring_scheduler_health() is expected


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
        "/api/v1/monitoring/health/system/scheduler",
    }
    assert all(route.methods == {"GET"} for route in monitored_routes)
    assert all(
        any(
            dependency.call is monitoring_auth.require_monitoring_agent
            for dependency in route.dependant.dependencies
        )
        for route in monitored_routes
    )
