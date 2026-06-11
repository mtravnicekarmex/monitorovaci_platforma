from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.dashboard_session import DASHBOARD_SESSION_COOKIE_NAME
from services.api.routes import auth as auth_routes


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
