from fastapi import Response

from services.api.core.config import ApiSettings
from services.api.core.runtime_state import api_readiness
from services.api.main import create_api_app
from services.api.routes.health import health_live, health_ready


def _settings(*, enable_docs: bool) -> ApiSettings:
    return ApiSettings(
        title="Test API",
        version="test",
        token_secret="test-secret",
        token_expiry_minutes=480,
        session_inactivity_minutes=30,
        cors_origins=(),
        enable_docs=enable_docs,
    )


def _route_paths(app) -> set[str]:
    return {getattr(route, "path", "") for route in app.routes}


def test_api_documentation_routes_are_disabled_for_production_settings():
    app = create_api_app(_settings(enable_docs=False))

    paths = _route_paths(app)

    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/openapi.json" not in paths


def test_api_documentation_routes_require_explicit_enablement():
    app = create_api_app(_settings(enable_docs=True))

    paths = _route_paths(app)

    assert "/docs" in paths
    assert "/redoc" in paths
    assert "/openapi.json" in paths


def test_health_responses_remain_minimal():
    api_readiness.mark_not_ready()
    response = Response()

    assert health_live() == {"status": "ok"}
    assert health_ready(response) == {"status": "unavailable"}
    assert response.status_code == 503

    api_readiness.mark_ready()
    response = Response()
    try:
        assert health_ready(response) == {"status": "ready"}
        assert response.status_code == 200
    finally:
        api_readiness.mark_not_ready()
