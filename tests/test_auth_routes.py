from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.dashboard_session import DASHBOARD_SESSION_COOKIE_NAME
from services.api.core.login_throttle import LoginFailureStatus
from services.api.routes import auth as auth_routes
from services.api.schemas.auth import LoginRequest, PasswordChangeRequest
from services.api.services.dashboard_auth import AuthenticationError


def _request(*, scheme: str = "http", forwarded_proto: str | None = None) -> Request:
    headers = []
    if forwarded_proto:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": scheme,
            "path": "/api/v1/auth/browser-session",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 443 if scheme == "https" else 80),
        }
    )


def test_persist_browser_session_sets_secure_httponly_cookie(monkeypatch):
    monkeypatch.setattr(
        auth_routes,
        "decode_access_token",
        lambda _token: SimpleNamespace(expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)),
    )

    response = auth_routes.persist_browser_session(
        _request(forwarded_proto="https"),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-value"),
        SimpleNamespace(username="tester"),
    )

    cookie = response.headers["set-cookie"]
    assert response.status_code == 204
    assert f"{DASHBOARD_SESSION_COOKIE_NAME}=token-value" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/" in cookie
    assert "SameSite=lax" in cookie
    assert "Secure" in cookie


def test_clear_browser_session_expires_cookie():
    response = auth_routes.clear_browser_session(_request(scheme="https"))

    cookie = response.headers["set-cookie"]
    assert response.status_code == 204
    assert f"{DASHBOARD_SESSION_COOKIE_NAME}=" in cookie
    assert "Max-Age=0" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie


class _LoginLimiterStub:
    def __init__(self, *, initial_retry_after=0, failure_retry_after=0):
        self.initial_retry_after = initial_retry_after
        self.failure_retry_after = failure_retry_after
        self.failures = []
        self.successes = []

    def retry_after(self, username, client_ip):
        return self.initial_retry_after

    def register_failure_status(self, username, client_ip):
        self.failures.append((username, client_ip))
        return LoginFailureStatus(
            retry_after=self.failure_retry_after,
            account_failure_count=5 if self.failure_retry_after else 1,
            ip_failure_count=1,
            account_lock_started=bool(self.failure_retry_after),
            ip_lock_started=False,
        )

    def register_success(self, username):
        self.successes.append(username)


class _AuthAuditStub:
    def __init__(self):
        self.login_failures = []
        self.login_successes = []
        self.login_throttles = []
        self.security_events = []

    def record_login_failure(self, **kwargs):
        self.login_failures.append(kwargs)

    def record_login_success(self, **kwargs):
        self.login_successes.append(kwargs)

    def record_login_throttled(self, **kwargs):
        self.login_throttles.append(kwargs)

    def record_security_event(self, **kwargs):
        self.security_events.append(kwargs)


@pytest.fixture(autouse=True)
def auth_audit_stub(monkeypatch):
    stub = _AuthAuditStub()
    monkeypatch.setattr(auth_routes, "auth_audit_service", stub)
    return stub


def test_login_returns_generic_error_for_all_authentication_failures(
    monkeypatch,
    auth_audit_stub,
):
    limiter = _LoginLimiterStub()
    monkeypatch.setattr(auth_routes, "login_attempt_limiter", limiter)
    monkeypatch.setattr(
        auth_routes,
        "authenticate_dashboard_user",
        lambda _username, _password: (_ for _ in ()).throw(
            AuthenticationError("Uzivatel je neaktivni.")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        auth_routes.login(
            LoginRequest(username="admin", password="wrong"),
            _request(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == auth_routes.INVALID_LOGIN_DETAIL
    assert limiter.failures == [("admin", "127.0.0.1")]
    assert auth_audit_stub.login_failures[0]["reason"] == "invalid_credentials"


def test_login_rejects_throttled_attempt_before_password_verification(
    monkeypatch,
    auth_audit_stub,
):
    limiter = _LoginLimiterStub(initial_retry_after=42)
    monkeypatch.setattr(auth_routes, "login_attempt_limiter", limiter)
    authentication_called = False

    def authenticate(_username, _password):
        nonlocal authentication_called
        authentication_called = True

    monkeypatch.setattr(auth_routes, "authenticate_dashboard_user", authenticate)

    with pytest.raises(HTTPException) as exc_info:
        auth_routes.login(
            LoginRequest(username="admin", password="secret"),
            _request(),
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == auth_routes.THROTTLED_LOGIN_DETAIL
    assert exc_info.value.headers == {"Retry-After": "42"}
    assert authentication_called is False
    assert auth_audit_stub.login_throttles == [
        {
            "username": "admin",
            "source_ip": "127.0.0.1",
            "retry_after": 42,
        }
    ]


def test_login_attempt_crossing_limit_returns_retry_after(
    monkeypatch,
    auth_audit_stub,
):
    limiter = _LoginLimiterStub(failure_retry_after=30)
    monkeypatch.setattr(auth_routes, "login_attempt_limiter", limiter)
    monkeypatch.setattr(
        auth_routes,
        "authenticate_dashboard_user",
        lambda _username, _password: (_ for _ in ()).throw(
            AuthenticationError("Neplatne prihlasovaci udaje.")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        auth_routes.login(
            LoginRequest(username="admin", password="wrong"),
            _request(),
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers == {"Retry-After": "30"}
    assert auth_audit_stub.login_failures[0]["failure_status"].retry_after == 30


def test_successful_login_is_allowed_after_lockout_expires(
    monkeypatch,
    auth_audit_stub,
):
    from services.api.core.login_throttle import LoginAttemptLimiter, LoginThrottlePolicy
    from services.api.services.dashboard_auth import DashboardUserContext

    now = [0.0]
    limiter = LoginAttemptLimiter(
        policy=LoginThrottlePolicy(
            window_seconds=60,
            account_failure_limit=1,
            account_lock_seconds=(5,),
            ip_failure_limit=100,
            ip_lock_seconds=60,
        ),
        clock=lambda: now[0],
    )
    limiter.register_failure("admin", "127.0.0.1")
    now[0] = 6.0

    user_context = DashboardUserContext(
        username="admin",
        email=None,
        is_admin=True,
        is_active=True,
        allowed_sections=(),
        allowed_pages=(),
        allowed_devices=(),
        last_login_at=None,
        token_version=0,
    )
    monkeypatch.setattr(auth_routes, "login_attempt_limiter", limiter)
    monkeypatch.setattr(
        auth_routes,
        "authenticate_dashboard_user",
        lambda _username, _password: user_context,
    )
    monkeypatch.setattr(
        auth_routes,
        "create_access_token",
        lambda _username, token_version: (
            "new-token",
            datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1),
        ),
    )

    response = auth_routes.login(
        LoginRequest(username="admin", password="correct"),
        _request(),
    )

    assert response.access_token == "new-token"
    assert limiter.retry_after("admin", "127.0.0.1") == 0
    assert auth_audit_stub.login_successes == [
        {
            "username": "admin",
            "source_ip": "127.0.0.1",
            "is_admin": True,
        }
    ]


def test_password_change_audits_change_and_token_revocation(
    monkeypatch,
    auth_audit_stub,
):
    monkeypatch.setattr(
        auth_routes,
        "change_dashboard_user_password",
        lambda _username, _current_password, _new_password: None,
    )

    response = auth_routes.change_my_password(
        PasswordChangeRequest(
            current_password="old-secret",
            new_password="new-secret",
        ),
        _request(),
        SimpleNamespace(username="Operator"),
    )

    assert response.status_code == 204
    assert [event["event_type"] for event in auth_audit_stub.security_events] == [
        "password_change",
        "token_revocation",
    ]
    assert all(
        "old-secret" not in repr(event) and "new-secret" not in repr(event)
        for event in auth_audit_stub.security_events
    )


def test_logout_audits_token_revocation(monkeypatch, auth_audit_stub):
    revoked = []
    monkeypatch.setattr(
        auth_routes,
        "logout_dashboard_user",
        lambda username: revoked.append(username),
    )

    response = auth_routes.logout(
        _request(),
        SimpleNamespace(username="Operator"),
    )

    assert response.status_code == 204
    assert revoked == ["Operator"]
    assert auth_audit_stub.security_events[0]["event_type"] == "token_revocation"
    assert auth_audit_stub.security_events[0]["reason"] == "logout"
