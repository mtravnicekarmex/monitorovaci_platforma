import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.api.core.dependencies import get_current_admin_user
from services.api.routes import admin as admin_routes
from services.api.services import device_admin, revize_admin
from services.api.services.dashboard_auth import AuthorizationError


@pytest.mark.parametrize(
    "route_function",
    (
        admin_routes.create_revize,
        admin_routes.update_revize,
        admin_routes.create_device,
        admin_routes.update_device,
    ),
)
def test_privileged_write_routes_require_admin_dependency(route_function):
    dependency = inspect.signature(route_function).parameters["current_user"].default.dependency
    assert dependency is get_current_admin_user


def test_non_admin_cannot_invoke_revize_write_service(monkeypatch):
    monkeypatch.setattr(
        revize_admin,
        "get_session_pg",
        lambda: pytest.fail("Database session must not open for a non-admin."),
    )

    with pytest.raises(AuthorizationError):
        revize_admin.create_revize_admin(
            SimpleNamespace(is_admin=False),
            payload={},
            linked_device_ids=[],
        )


def test_non_admin_cannot_invoke_device_write_service(monkeypatch):
    monkeypatch.setattr(
        device_admin,
        "get_session_ms",
        lambda: pytest.fail("Database session must not open for a non-admin."),
    )

    with pytest.raises(AuthorizationError):
        device_admin.create_device_admin(
            SimpleNamespace(is_admin=False),
            meter_key="vodomery",
            form_values={},
        )


def test_admin_dependency_returns_http_403_for_non_admin():
    with pytest.raises(HTTPException) as exc_info:
        get_current_admin_user(SimpleNamespace(is_admin=False))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Tato operace je dostupna pouze adminovi."


def test_active_streamlit_modules_do_not_define_direct_privileged_writes():
    revize_source = inspect.getsource(
        __import__(
            "moduly.apps.dashboard.revize_shared",
            fromlist=["revize_shared"],
        )
    )
    device_source = inspect.getsource(
        __import__(
            "moduly.apps.dashboard.device_list_shared",
            fromlist=["device_list_shared"],
        )
    )

    assert "def create_revize_record(" not in revize_source
    assert "def update_revize_record(" not in revize_source
    assert "def create_device_record(" not in device_source
    assert "def update_device_record(" not in device_source
    assert "session.commit()" not in revize_source
    assert "session.commit()" not in device_source
