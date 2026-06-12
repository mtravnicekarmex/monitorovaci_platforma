from datetime import datetime
from types import SimpleNamespace

from starlette.requests import Request

from services.api.routes import admin as admin_routes
from services.api.schemas.admin import AdminUserCreateRequest, AdminUserUpdateRequest
from services.api.services.dashboard_admin import AdminUserUpdateResult


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/api/v1/admin/users",
            "query_string": b"",
            "headers": [],
            "client": ("192.0.2.10", 12345),
            "server": ("testserver", 443),
        }
    )


def _user_record(**updates):
    record = {
        "username": "target",
        "email": None,
        "available_sections": [],
        "available_pages": [],
        "device_ids": [],
        "is_active": True,
        "is_admin": False,
        "created_at": datetime(2026, 6, 12, 8, 0),
        "updated_at": datetime(2026, 6, 12, 8, 0),
        "last_login_at": None,
    }
    record.update(updates)
    return record


class _AuditStub:
    def __init__(self) -> None:
        self.events = []

    def record_security_event(self, **kwargs) -> None:
        self.events.append(kwargs)


def test_create_user_audits_initial_role_and_activation(monkeypatch):
    audit = _AuditStub()
    monkeypatch.setattr(admin_routes, "auth_audit_service", audit)
    monkeypatch.setattr(
        admin_routes,
        "create_admin_user",
        lambda *_args, **_kwargs: _user_record(is_admin=True),
    )

    response = admin_routes.create_user(
        AdminUserCreateRequest(
            username="target",
            password="not-recorded",
            is_admin=True,
        ),
        _request(),
        SimpleNamespace(username="admin"),
    )

    assert response.username == "target"
    assert audit.events[0]["event_type"] == "account_created"
    assert audit.events[0]["details"] == {"is_active": True, "is_admin": True}
    assert "not-recorded" not in repr(audit.events)


def test_update_user_audits_password_role_activation_and_revocation(monkeypatch):
    audit = _AuditStub()
    monkeypatch.setattr(admin_routes, "auth_audit_service", audit)
    monkeypatch.setattr(
        admin_routes,
        "update_admin_user",
        lambda *_args, **_kwargs: AdminUserUpdateResult(
            record=_user_record(is_active=False, is_admin=True),
            changed_fields=("password", "is_active", "is_admin"),
            password_changed=True,
            role_changed=True,
            active_changed=True,
            previous_is_admin=False,
            previous_is_active=True,
        ),
    )

    response = admin_routes.update_user(
        "target",
        AdminUserUpdateRequest(
            password="not-recorded",
            is_active=False,
            is_admin=True,
        ),
        _request(),
        SimpleNamespace(username="admin"),
    )

    assert response.is_admin is True
    assert response.is_active is False
    assert [event["event_type"] for event in audit.events] == [
        "account_updated",
        "password_change",
        "token_revocation",
        "role_change",
        "account_activation_change",
    ]
    assert "not-recorded" not in repr(audit.events)


def test_delete_user_audits_account_deletion_and_token_revocation(monkeypatch):
    audit = _AuditStub()
    monkeypatch.setattr(admin_routes, "auth_audit_service", audit)
    monkeypatch.setattr(
        admin_routes,
        "delete_admin_user",
        lambda *_args, **_kwargs: {"is_admin": False, "is_active": True},
    )

    response = admin_routes.delete_user(
        "target",
        _request(),
        SimpleNamespace(username="admin"),
    )

    assert response.status_code == 204
    assert [event["event_type"] for event in audit.events] == [
        "account_deleted",
        "token_revocation",
    ]
