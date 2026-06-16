from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from moduly.apps.dashboard.database import users
from moduly.apps.dashboard.database.models import Streamlit_Users
from services.api.core import dependencies, tokens
from services.api.services.dashboard_auth import build_user_context


class _UserSession:
    def __init__(self, user):
        self.user = user
        self.commit_calls = 0
        self.closed = False

    def get(self, _model, _username):
        return self.user

    def add(self, user):
        self.user = user

    def commit(self):
        self.commit_calls += 1

    def close(self):
        self.closed = True


def _user() -> Streamlit_Users:
    return Streamlit_Users(
        uzivatel="operator",
        email="old@example.com",
        heslo="stored-hash",
        dostupne_sekce='["vodomery"]',
        dostupne_stranky='["vodomery_overview"]',
        seznam_zarizeni='["V-1"]',
        is_admin=False,
        is_active=True,
        token_version=7,
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"dostupne_sekce": ["vodomery", "mapove_podklady"]},
        {"dostupne_stranky": ["vodomery_list"]},
        {"seznam_zarizeni": ["V-1", "V-2"]},
        {"is_admin": True},
        {"is_active": False},
    ],
)
def test_security_state_change_revokes_existing_sessions(monkeypatch, updates):
    user = _user()
    session = _UserSession(user)
    monkeypatch.setattr(users, "get_session_pg", lambda: session)

    values = {
        "username": "operator",
        "password": None,
        "email": user.email,
        "dostupne_sekce": ["vodomery"],
        "dostupne_stranky": ["vodomery_overview"],
        "seznam_zarizeni": ["V-1"],
        "is_admin": False,
        "is_active": True,
    }
    values.update(updates)
    users.upsert_user(**values)

    assert user.token_version == 8
    assert session.commit_calls == 1
    assert session.closed is True


def test_email_only_change_keeps_existing_sessions(monkeypatch):
    user = _user()
    session = _UserSession(user)
    monkeypatch.setattr(users, "get_session_pg", lambda: session)

    users.upsert_user(
        username="operator",
        password=None,
        email="new@example.com",
        dostupne_sekce=["vodomery"],
        dostupne_stranky=["vodomery_overview"],
        seznam_zarizeni=["V-1"],
        is_admin=False,
        is_active=True,
    )

    assert user.email == "new@example.com"
    assert user.token_version == 7


@pytest.mark.parametrize(
    "updates",
    [
        {"dostupne_sekce": ["vodomery", "mapove_podklady"]},
        {"dostupne_stranky": ["vodomery_list"]},
        {"seznam_zarizeni": ["V-1", "V-2"]},
        {"is_admin": True},
        {"is_active": False},
    ],
)
@pytest.mark.parametrize("authentication_mode", ["bearer", "browser-cookie"])
def test_permission_change_rejects_previously_issued_tokens(
    monkeypatch,
    updates,
    authentication_mode,
):
    user = _user()
    session = _UserSession(user)
    settings = SimpleNamespace(
        token_secret="permission-change-test-secret",
        token_expiry_minutes=480,
        session_inactivity_minutes=30,
    )
    now = datetime(2026, 6, 15, 9, 0)
    monkeypatch.setattr(users, "get_session_pg", lambda: session)
    monkeypatch.setattr(tokens, "get_api_settings", lambda: settings)
    monkeypatch.setattr(tokens, "utc_now_naive", lambda: now)

    access_token, _expires_at = tokens.create_access_token(
        user.uzivatel,
        token_version=user.token_version,
    )
    values = {
        "username": "operator",
        "password": None,
        "email": user.email,
        "dostupne_sekce": ["vodomery"],
        "dostupne_stranky": ["vodomery_overview"],
        "seznam_zarizeni": ["V-1"],
        "is_admin": False,
        "is_active": True,
    }
    values.update(updates)
    users.upsert_user(**values)

    current_context = build_user_context(user) if user.is_active else None
    monkeypatch.setattr(
        dependencies,
        "get_dashboard_user_context",
        lambda username: current_context if username == user.uzivatel else None,
    )

    with pytest.raises(HTTPException) as exc_info:
        if authentication_mode == "bearer":
            dependencies.get_current_user(
                HTTPAuthorizationCredentials(
                    scheme="Bearer",
                    credentials=access_token,
                )
            )
        else:
            dependencies.get_current_browser_session_user(access_token)

    assert exc_info.value.status_code == 401
