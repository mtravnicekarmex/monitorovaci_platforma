from types import SimpleNamespace

from app.dashboard_session import DASHBOARD_SESSION_COOKIE_NAME
from moduly.apps.dashboard import auth
from moduly.apps.dashboard.api_client import DashboardApiError, DashboardSessionPayload


class FakeStreamlit:
    def __init__(self, cookies=None, headers=None):
        self.session_state = {}
        self.context = SimpleNamespace(cookies=cookies or {}, headers=headers or {})
        self.html_calls = []

    def html(self, body, *, unsafe_allow_javascript=False):
        self.html_calls.append((body, unsafe_allow_javascript))


def _user_payload():
    return {
        "username": "tester",
        "email": "tester@example.com",
        "is_admin": False,
        "allowed_sections": ["vodomery"],
        "allowed_pages": ["dashboard_overview"],
        "allowed_devices": ["V-1"],
        "last_login_at": None,
    }


def test_restore_auth_state_from_browser_cookie(monkeypatch):
    fake_st = FakeStreamlit({DASHBOARD_SESSION_COOKIE_NAME: "persisted-token"})
    monkeypatch.setattr(auth, "st", fake_st)
    monkeypatch.setattr(auth, "api_get_me", lambda token: _user_payload() if token == "persisted-token" else None)

    restored = auth.restore_auth_state_from_browser_cookie()

    assert restored is True
    assert fake_st.session_state["authenticated"] is True
    assert fake_st.session_state["auth_token"] == "persisted-token"
    assert fake_st.session_state["auth_user"] == "tester"
    assert fake_st.session_state["auth_cookie_sync_runs_remaining"] == 0


def test_invalid_browser_cookie_is_scheduled_for_deletion(monkeypatch):
    fake_st = FakeStreamlit({DASHBOARD_SESSION_COOKIE_NAME: "expired-token"})
    monkeypatch.setattr(auth, "st", fake_st)

    def reject_token(_token):
        raise DashboardApiError("Token expiroval.", status_code=401)

    monkeypatch.setattr(auth, "api_get_me", reject_token)

    assert auth.restore_auth_state_from_browser_cookie() is False
    assert fake_st.session_state["auth_cookie_clear_pending"] is True

    auth.sync_browser_auth_session()

    assert fake_st.session_state["auth_cookie_clear_pending"] is False
    assert len(fake_st.html_calls) == 1
    assert 'method: "DELETE"' in fake_st.html_calls[0][0]
    assert fake_st.html_calls[0][1] is True


def test_login_schedules_cookie_sync_for_navigation_reruns(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(auth, "st", fake_st)
    monkeypatch.setattr(
        auth,
        "api_login",
        lambda _username, _password: DashboardSessionPayload(
            access_token="new-token",
            expires_at="2026-06-11T18:00:00",
            user=_user_payload(),
        ),
    )

    assert auth.login("tester", "secret") is True

    auth.sync_browser_auth_session()
    auth.sync_browser_auth_session()
    auth.sync_browser_auth_session()

    assert len(fake_st.html_calls) == 2
    assert all("/api/v1/auth/browser-session" in body for body, _ in fake_st.html_calls)
    assert all("Bearer new-token" in body for body, _ in fake_st.html_calls)
    assert fake_st.session_state["auth_cookie_sync_runs_remaining"] == 0


def test_login_forwards_browser_ip_from_streamlit_context(monkeypatch):
    fake_st = FakeStreamlit(headers={"X-Forwarded-For": "203.0.113.99, 127.0.0.1"})
    monkeypatch.setattr(auth, "st", fake_st)
    captured = {}

    def fake_login(username, password, *, client_ip=None):
        captured.update(username=username, password=password, client_ip=client_ip)
        return DashboardSessionPayload(
            access_token="new-token",
            expires_at="2026-06-11T18:00:00",
            user=_user_payload(),
        )

    monkeypatch.setattr(auth, "api_login", fake_login)

    assert auth.login("tester", "secret") is True
    assert captured == {
        "username": "tester",
        "password": "secret",
        "client_ip": "203.0.113.99",
    }


def test_api_outage_does_not_delete_persisted_cookie(monkeypatch):
    fake_st = FakeStreamlit({DASHBOARD_SESSION_COOKIE_NAME: "persisted-token"})
    monkeypatch.setattr(auth, "st", fake_st)
    monkeypatch.setattr(
        auth,
        "api_get_me",
        lambda _token: (_ for _ in ()).throw(DashboardApiError("API neni dostupne.")),
    )

    assert auth.restore_auth_state_from_browser_cookie() is False
    assert fake_st.session_state["auth_cookie_clear_pending"] is False
