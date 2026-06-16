import asyncio
import re
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.api.core import dependencies, tokens
from services.api.core.dependencies import (
    get_current_admin_user,
    get_current_browser_session_user,
    get_current_manometry_user,
    get_current_plynomery_user,
    get_current_user,
    get_current_vodomery_user,
    get_current_web_search_user,
)
from services.api.main import app
from services.api.routes import manometry as manometry_routes
from services.api.routes import plynomery as plynomery_routes
from services.api.routes import vodomery as vodomery_routes
from services.api.services import manometry as manometry_service
from services.api.services import plynomery as plynomery_service
from services.api.services import vodomery as vodomery_service
from services.api.services.dashboard_auth import AuthorizationError, require_device_access


PUBLIC_OPERATIONS = {
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/api/v1/auth/users-exist"),
    ("POST", "/api/v1/auth/login"),
    ("DELETE", "/api/v1/auth/browser-session"),
}

EXPECTED_ADMIN_OPERATIONS = {
    ("GET", "/health/scheduler"),
    ("GET", "/health/scheduler/log"),
    ("POST", "/health/scheduler/jobs/{job_id}/run"),
    ("GET", "/api/v1/admin/device-options"),
    ("GET", "/api/v1/admin/users"),
    ("POST", "/api/v1/admin/users"),
    ("PATCH", "/api/v1/admin/users/{username}"),
    ("DELETE", "/api/v1/admin/users/{username}"),
    ("GET", "/api/v1/admin/map-layers"),
    ("POST", "/api/v1/admin/map-layers"),
    ("PATCH", "/api/v1/admin/map-layers/{layer_id}"),
    ("DELETE", "/api/v1/admin/map-layers/{layer_id}"),
    ("POST", "/api/v1/admin/revize"),
    ("PATCH", "/api/v1/admin/revize/{revize_id}"),
    ("POST", "/api/v1/admin/devices/{meter_key}"),
    ("PATCH", "/api/v1/admin/devices/{meter_key}"),
    ("GET", "/api/v1/kalorimetry/devices"),
    ("GET", "/api/v1/kalorimetry/outlier-reviews"),
    ("PATCH", "/api/v1/kalorimetry/outlier-reviews/{review_id}"),
    ("GET", "/api/v1/plynomery/outlier-reviews"),
    ("PATCH", "/api/v1/plynomery/outlier-reviews/{review_id}"),
    ("GET", "/api/v1/plynomery/expected-zero"),
    ("PUT", "/api/v1/plynomery/expected-zero"),
    ("GET", "/api/v1/plynomery/alert-rules"),
    ("POST", "/api/v1/plynomery/alert-rules"),
    ("PATCH", "/api/v1/plynomery/alert-rules/{rule_id}"),
    ("DELETE", "/api/v1/plynomery/alert-rules/{rule_id}"),
    ("GET", "/api/v1/vodomery/billing-options"),
    ("GET", "/api/v1/vodomery/billing-period"),
    ("GET", "/api/v1/vodomery/outlier-reviews"),
    ("PATCH", "/api/v1/vodomery/outlier-reviews/{review_id}"),
    ("GET", "/api/v1/vodomery/expected-zero"),
    ("PUT", "/api/v1/vodomery/expected-zero"),
    ("GET", "/api/v1/vodomery/alert-rules"),
    ("POST", "/api/v1/vodomery/alert-rules"),
    ("PATCH", "/api/v1/vodomery/alert-rules/{rule_id}"),
    ("DELETE", "/api/v1/vodomery/alert-rules/{rule_id}"),
}

EXPECTED_SCOPED_OPERATIONS = {
    get_current_vodomery_user: {
        ("GET", "/api/v1/vodomery/devices"),
        ("GET", "/api/v1/vodomery/overview-metrics"),
        ("GET", "/api/v1/vodomery/measurement-series"),
        ("GET", "/api/v1/vodomery/prediction-profiles"),
        ("GET", "/api/v1/vodomery/recent-anomalies"),
        ("GET", "/api/v1/vodomery/open-events"),
        ("GET", "/api/v1/vodomery/resolved-events"),
        ("GET", "/api/v1/vodomery/event-history"),
        ("GET", "/api/v1/vodomery/device-detail"),
        ("GET", "/api/v1/vodomery/branch-day-overview"),
    },
    get_current_manometry_user: {
        ("GET", "/api/v1/manometry/devices"),
        ("GET", "/api/v1/manometry/measurement-series"),
        ("GET", "/api/v1/manometry/device-detail"),
    },
    get_current_plynomery_user: {
        ("GET", "/api/v1/plynomery/devices"),
        ("GET", "/api/v1/plynomery/recent-anomalies"),
        ("GET", "/api/v1/plynomery/open-events"),
        ("GET", "/api/v1/plynomery/resolved-events"),
    },
    get_current_web_search_user: {
        ("GET", "/api/v1/web-search/monitors"),
        ("POST", "/api/v1/web-search/preview"),
        ("GET", "/api/v1/web-search/results"),
        ("POST", "/api/v1/web-search/monitors"),
        ("PATCH", "/api/v1/web-search/monitors/{monitor_id}"),
        ("DELETE", "/api/v1/web-search/monitors/{monitor_id}"),
    },
}

DEVICE_ROUTE_CASES = (
    (
        "vodomery-measurement-series",
        vodomery_routes,
        "load_measurement_series",
        vodomery_routes.get_vodomery_measurement_series,
        {
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 2),
            "source": "VSE",
        },
        [],
    ),
    (
        "vodomery-prediction-profiles",
        vodomery_routes,
        "load_prediction_profiles",
        vodomery_routes.get_vodomery_prediction_profiles,
        {},
        [],
    ),
    (
        "vodomery-recent-anomalies",
        vodomery_routes,
        "load_recent_anomalies",
        vodomery_routes.get_vodomery_recent_anomalies,
        {
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 2),
            "source": "VSE",
            "limit": 50,
        },
        [],
    ),
    (
        "vodomery-event-history",
        vodomery_routes,
        "load_event_history",
        vodomery_routes.get_vodomery_event_history,
        {"limit": 20},
        [],
    ),
    (
        "vodomery-device-detail",
        vodomery_routes,
        "load_device_detail",
        vodomery_routes.get_vodomery_device_detail,
        {},
        None,
    ),
    (
        "manometry-measurement-series",
        manometry_routes,
        "load_measurement_series",
        manometry_routes.get_manometry_measurement_series,
        {
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 2),
        },
        [],
    ),
    (
        "manometry-device-detail",
        manometry_routes,
        "load_device_detail",
        manometry_routes.get_manometry_device_detail,
        {},
        None,
    ),
    (
        "plynomery-recent-anomalies",
        plynomery_routes,
        "load_recent_anomalies",
        plynomery_routes.get_plynomery_recent_anomalies,
        {
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 2),
            "limit": 50,
        },
        [],
    ),
)

DEVICE_SERVICE_CASES = (
    (
        "vodomery-measurement-series",
        vodomery_service,
        vodomery_service.load_measurement_series,
        {
            "source_filter": "VSE",
            "identifikace": "V-2",
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 2),
        },
        ("get_session_pg",),
    ),
    (
        "vodomery-prediction-profiles",
        vodomery_service,
        vodomery_service.load_prediction_profiles,
        {"identifikace": "V-2"},
        ("get_session_pg",),
    ),
    (
        "vodomery-recent-anomalies",
        vodomery_service,
        vodomery_service.load_recent_anomalies,
        {
            "source_filter": "VSE",
            "identifikace": "V-2",
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 2),
            "limit": 50,
        },
        ("get_session_pg",),
    ),
    (
        "vodomery-event-history",
        vodomery_service,
        vodomery_service.load_event_history,
        {"identifikace": "V-2", "limit": 20},
        ("get_session_pg",),
    ),
    (
        "vodomery-device-detail",
        vodomery_service,
        vodomery_service.load_device_detail,
        {"identifikace": "V-2"},
        ("get_session_ms",),
    ),
    (
        "manometry-measurement-series",
        manometry_service,
        manometry_service.load_measurement_series,
        {
            "identifikace": "V-2",
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 2),
        },
        ("get_session_pg",),
    ),
    (
        "manometry-device-detail",
        manometry_service,
        manometry_service.load_device_detail,
        {"identifikace": "V-2"},
        ("get_session_ms", "get_session_pg"),
    ),
    (
        "plynomery-recent-anomalies",
        plynomery_service,
        plynomery_service.load_recent_anomalies,
        {
            "identifikace": "V-2",
            "start_date": date(2026, 6, 1),
            "end_date": date(2026, 6, 2),
            "limit": 50,
        },
        ("get_session_pg",),
    ),
)


def _application_operations():
    operations = {}
    for route in app.routes:
        if not (
            route.path.startswith("/api/v1/")
            or route.path.startswith("/health/")
        ):
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            operations[(method, route.path)] = route
    return operations


def _operations_with_dependency(dependency):
    return {
        operation
        for operation, route in _application_operations().items()
        if any(
            route_dependency.call is dependency
            for route_dependency in route.dependant.dependencies
        )
    }


def _dependency_calls(route):
    calls = set()
    pending = list(route.dependant.dependencies)
    while pending:
        route_dependency = pending.pop()
        calls.add(route_dependency.call)
        pending.extend(route_dependency.dependencies)
    return calls


def _materialize_path(path):
    replacements = {
        "job_id": "quarter_hour_job",
        "username": "operator",
        "layer_id": "vodomery",
        "meter_key": "vodomery",
    }

    def replace(match):
        name = match.group(1)
        if name in replacements:
            return replacements[name]
        if name.endswith("_id"):
            return "1"
        return "test"

    return re.sub(r"{([^}]+)}", replace, path)


def _request_status(method, path, *, headers=()):
    async def call_app():
        messages = []
        request_sent = False

        async def receive():
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        materialized_path = _materialize_path(path)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": materialized_path,
            "raw_path": materialized_path.encode("ascii"),
            "query_string": b"",
            "root_path": "",
            "headers": list(headers),
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443),
            "state": {},
        }
        await app(scope, receive, send)
        return next(
            message["status"]
            for message in messages
            if message["type"] == "http.response.start"
        )

    return asyncio.run(call_app())


@pytest.fixture
def access_token(monkeypatch):
    settings = SimpleNamespace(
        token_secret="authorization-regression-secret",
        token_expiry_minutes=480,
        session_inactivity_minutes=30,
    )
    now = datetime(2026, 6, 15, 9, 0)
    monkeypatch.setattr(tokens, "get_api_settings", lambda: settings)
    monkeypatch.setattr(tokens, "utc_now_naive", lambda: now)
    token, _expires_at = tokens.create_access_token("operator", token_version=7)
    return token


def _authorization_headers(access_token):
    return [(b"authorization", f"Bearer {access_token}".encode("ascii"))]


def test_public_operation_inventory_is_explicit():
    assert PUBLIC_OPERATIONS <= set(_application_operations())


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(set(_application_operations()) - PUBLIC_OPERATIONS),
)
def test_every_protected_api_operation_rejects_missing_authentication(method, path):
    route = _application_operations()[(method, path)]
    assert _dependency_calls(route) & {
        get_current_user,
        get_current_browser_session_user,
    }
    assert _request_status(method, path) == 401


def test_admin_operation_inventory_uses_admin_dependency():
    assert _operations_with_dependency(get_current_admin_user) == EXPECTED_ADMIN_OPERATIONS


@pytest.mark.parametrize(("method", "path"), sorted(EXPECTED_ADMIN_OPERATIONS))
def test_every_admin_operation_rejects_non_admin_token(
    monkeypatch,
    access_token,
    method,
    path,
):
    current_user = SimpleNamespace(
        username="operator",
        token_version=7,
        is_admin=False,
    )
    monkeypatch.setattr(
        dependencies,
        "get_dashboard_user_context",
        lambda username: current_user if username == "operator" else None,
    )

    assert (
        _request_status(
            method,
            path,
            headers=_authorization_headers(access_token),
        )
        == 403
    )


@pytest.mark.parametrize(
    ("dependency", "expected_operations"),
    tuple(EXPECTED_SCOPED_OPERATIONS.items()),
    ids=lambda value: getattr(value, "__name__", None),
)
def test_section_and_page_route_inventory_is_explicit(
    dependency,
    expected_operations,
):
    assert _operations_with_dependency(dependency) == expected_operations


@pytest.mark.parametrize(
    ("dependency", "method", "path"),
    [
        (dependency, method, path)
        for dependency, operations in EXPECTED_SCOPED_OPERATIONS.items()
        for method, path in sorted(operations)
    ],
    ids=lambda value: getattr(value, "__name__", None),
)
def test_every_section_or_page_scoped_operation_rejects_missing_permission(
    monkeypatch,
    access_token,
    dependency,
    method,
    path,
):
    allowed_sections = ("sprava",) if dependency is get_current_web_search_user else ()
    current_user = SimpleNamespace(
        username="operator",
        token_version=7,
        is_admin=False,
        allowed_sections=allowed_sections,
        allowed_pages=(),
        allowed_devices=("V-1",),
    )
    monkeypatch.setattr(
        dependencies,
        "get_dashboard_user_context",
        lambda username: current_user if username == "operator" else None,
    )

    assert (
        _request_status(
            method,
            path,
            headers=_authorization_headers(access_token),
        )
        == 403
    )


@pytest.mark.parametrize(
    ("dependency", "section_key"),
    (
        (get_current_vodomery_user, "vodomery"),
        (get_current_manometry_user, "manometry"),
        (get_current_plynomery_user, "plynomery"),
    ),
)
def test_section_dependencies_allow_assigned_section_and_device(
    dependency,
    section_key,
):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=(section_key,),
        allowed_pages=(),
        allowed_devices=("V-1",),
    )

    assert dependency(current_user) is current_user


def test_page_dependency_allows_assigned_web_search_page():
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=("sprava",),
        allowed_pages=("web_search_monitor",),
        allowed_devices=(),
    )

    assert get_current_web_search_user(current_user) is current_user


@pytest.mark.parametrize(
    (
        "_case_name",
        "route_module",
        "service_name",
        "route_function",
        "route_kwargs",
        "service_result",
    ),
    DEVICE_ROUTE_CASES,
    ids=[case[0] for case in DEVICE_ROUTE_CASES],
)
def test_device_scoped_route_allows_assigned_identifier(
    monkeypatch,
    _case_name,
    route_module,
    service_name,
    route_function,
    route_kwargs,
    service_result,
):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_devices=("V-1",),
    )

    def gated_service(user_context, **kwargs):
        require_device_access(user_context, kwargs["identifikace"])
        return service_result

    monkeypatch.setattr(route_module, service_name, gated_service)

    response = route_function(
        identifikace="V-1",
        current_user=current_user,
        **route_kwargs,
    )

    assert response.identifikace == "V-1"


@pytest.mark.parametrize(
    (
        "_case_name",
        "route_module",
        "service_name",
        "route_function",
        "route_kwargs",
        "service_result",
    ),
    DEVICE_ROUTE_CASES,
    ids=[case[0] for case in DEVICE_ROUTE_CASES],
)
def test_device_scoped_route_rejects_unassigned_identifier(
    monkeypatch,
    _case_name,
    route_module,
    service_name,
    route_function,
    route_kwargs,
    service_result,
):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_devices=("V-1",),
    )

    def gated_service(user_context, **kwargs):
        require_device_access(user_context, kwargs["identifikace"])
        return service_result

    monkeypatch.setattr(route_module, service_name, gated_service)

    with pytest.raises(HTTPException) as exc_info:
        route_function(
            identifikace="V-2",
            current_user=current_user,
            **route_kwargs,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.parametrize(
    (
        "_case_name",
        "service_module",
        "service_function",
        "service_kwargs",
        "session_factories",
    ),
    DEVICE_SERVICE_CASES,
    ids=[case[0] for case in DEVICE_SERVICE_CASES],
)
def test_device_services_reject_unassigned_identifier_before_database_access(
    monkeypatch,
    _case_name,
    service_module,
    service_function,
    service_kwargs,
    session_factories,
):
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=("vodomery", "manometry", "plynomery"),
        allowed_devices=("V-1",),
    )

    for factory_name in session_factories:
        monkeypatch.setattr(
            service_module,
            factory_name,
            lambda: pytest.fail(
                "Database session must not open for an unassigned device."
            ),
        )

    with pytest.raises(AuthorizationError):
        service_function(current_user, **service_kwargs)
