import pytest

from moduly.apps.dashboard.database import users
from moduly.apps.dashboard.database.models import Streamlit_Users


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
