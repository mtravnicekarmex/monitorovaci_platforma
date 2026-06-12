from types import SimpleNamespace

import pytest

from moduly.apps.dashboard.database import users
from services.api.services.dashboard_auth import AuthorizationError, require_page_access


def test_require_page_access_allows_configurable_overview_when_assigned():
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=(),
        allowed_pages=("dashboard_overview",),
        allowed_devices=(),
    )

    require_page_access(current_user, "dashboard_overview")


def test_require_page_access_rejects_unassigned_configurable_overview():
    current_user = SimpleNamespace(
        is_admin=False,
        allowed_sections=(),
        allowed_pages=(),
        allowed_devices=(),
    )

    with pytest.raises(AuthorizationError):
        require_page_access(current_user, "dashboard_overview")


class _FakeSession:
    def __init__(self, user):
        self.user = user
        self.closed = False
        self.expunge_calls = []

    def get(self, _model, _username):
        return self.user

    def expunge(self, user):
        self.expunge_calls.append(user)

    def close(self):
        self.closed = True


def test_unknown_user_still_runs_password_hash_verification(monkeypatch):
    session = _FakeSession(None)
    verification_calls = []
    monkeypatch.setattr(users, "get_session_pg", lambda: session)
    monkeypatch.setattr(
        users,
        "verify_password",
        lambda password, password_hash: verification_calls.append((password, password_hash)) or False,
    )

    assert users.authenticate_user("missing", "candidate-password") is None
    assert verification_calls == [("candidate-password", users.DUMMY_PASSWORD_HASH)]
    assert session.closed is True


def test_inactive_user_runs_normal_password_verification(monkeypatch):
    user = SimpleNamespace(is_active=False, heslo="stored-hash")
    session = _FakeSession(user)
    verification_calls = []
    monkeypatch.setattr(users, "get_session_pg", lambda: session)
    monkeypatch.setattr(
        users,
        "verify_password",
        lambda password, password_hash: verification_calls.append((password, password_hash)) or True,
    )

    assert users.authenticate_user("inactive", "candidate-password") is None
    assert verification_calls == [("candidate-password", "stored-hash")]
    assert session.expunge_calls == []
