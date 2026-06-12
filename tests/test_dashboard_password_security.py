from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from moduly.apps.dashboard import security
from moduly.apps.dashboard.database import create_user, users
from services.api.services import dashboard_admin, dashboard_auth


def _legacy_hash(password: str, *, iterations: int = 390_000) -> str:
    salt = "legacy-password-salt"
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def test_password_policy_accepts_long_unicode_passphrase_with_spaces():
    password = "Příliš žluťoučký kůň bezpečně běží"

    assert security.validate_password(password) == password


def test_password_policy_has_no_character_class_requirement():
    password = "dlouhaheslovafraze"

    assert security.validate_password(password) == password


@pytest.mark.parametrize(
    "password",
    [
        "kratke-heslo",
        "               ",
        "      password      ",
        "passwordpassword",
        "monitoring2026",
    ],
)
def test_password_policy_rejects_short_blank_and_blocklisted_values(password):
    with pytest.raises(security.PasswordPolicyError):
        security.validate_password(password)


def test_password_policy_rejects_username_derivatives():
    with pytest.raises(security.PasswordPolicyError):
        security.validate_password(
            "administratoradministrator",
            username="administrator",
        )


def test_password_policy_accepts_password_manager_length():
    password = "x" * security.MAX_PASSWORD_LENGTH

    assert security.validate_password(password) == password


def test_password_hash_uses_600000_iterations_and_verifies_unicode_equivalence():
    decomposed = "Cafe\u0301 bezpečná přístupová fráze"
    composed = security.normalize_password(decomposed)

    password_hash = security.hash_password(decomposed)

    assert password_hash.split("$", 3)[1] == "600000"
    assert security.verify_password(composed, password_hash) is True
    assert security.password_hash_needs_rehash(password_hash) is False


def test_legacy_hash_verifies_and_is_marked_for_rehash():
    password = "legacy password phrase"
    password_hash = _legacy_hash(password)

    assert security.verify_password(password, password_hash) is True
    assert security.password_hash_needs_rehash(password_hash) is True


class _AuthenticationSession:
    def __init__(self, user):
        self.user = user
        self.commit_calls = 0
        self.closed = False

    def get(self, _model, _username):
        return self.user

    def commit(self):
        self.commit_calls += 1

    def expunge(self, _user):
        return None

    def close(self):
        self.closed = True


def test_successful_login_rehashes_legacy_hash_without_forcing_reset(monkeypatch):
    password = "legacy password phrase"
    user = SimpleNamespace(
        is_active=True,
        is_admin=False,
        heslo=_legacy_hash(password),
    )
    session = _AuthenticationSession(user)
    monkeypatch.setattr(users, "get_session_pg", lambda: session)

    result = users.authenticate_user_with_result("operator", password)

    assert result.user is user
    assert session.commit_calls == 1
    assert user.heslo.split("$", 3)[1] == "600000"
    assert security.verify_password(password, user.heslo) is True
    assert session.closed is True


def test_update_password_enforces_policy_before_database_access(monkeypatch):
    monkeypatch.setattr(
        users,
        "get_session_pg",
        lambda: pytest.fail("database should not be opened for a rejected password"),
    )

    with pytest.raises(security.PasswordPolicyError):
        users.update_password("operator", "short")


def test_upsert_user_enforces_policy_before_database_access(monkeypatch):
    monkeypatch.setattr(
        users,
        "get_session_pg",
        lambda: pytest.fail("database should not be opened for a rejected password"),
    )

    with pytest.raises(security.PasswordPolicyError):
        users.upsert_user("operator", "short")


def test_self_service_change_returns_policy_error(monkeypatch):
    monkeypatch.setattr(
        dashboard_auth,
        "verify_user_password",
        lambda _username, _password: True,
    )
    monkeypatch.setattr(
        dashboard_auth,
        "update_password",
        lambda _username, _password: (_ for _ in ()).throw(
            security.PasswordPolicyError("policy rejected")
        ),
    )

    with pytest.raises(dashboard_auth.UserUpdateError, match="policy rejected"):
        dashboard_auth.change_dashboard_user_password(
            "operator",
            "current password",
            "short",
        )


def test_admin_create_returns_policy_error(monkeypatch):
    monkeypatch.setattr(dashboard_admin, "get_user", lambda _username: None)
    monkeypatch.setattr(
        dashboard_admin,
        "upsert_user",
        lambda **_kwargs: (_ for _ in ()).throw(
            security.PasswordPolicyError("policy rejected")
        ),
    )

    with pytest.raises(dashboard_admin.AdminOperationError, match="policy rejected"):
        dashboard_admin.create_admin_user(
            SimpleNamespace(is_admin=True),
            username="operator",
            password="short",
            email=None,
            available_sections=[],
            available_pages=[],
            device_ids=[],
            is_active=True,
            is_admin=False,
        )


def test_admin_reset_returns_policy_error(monkeypatch):
    existing_user = SimpleNamespace(
        is_admin=False,
        is_active=True,
    )
    monkeypatch.setattr(dashboard_admin, "get_user", lambda _username: existing_user)
    monkeypatch.setattr(
        dashboard_admin,
        "list_users",
        lambda: [
            {
                "uzivatel": "operator",
                "email": None,
                "dostupne_sekce": [],
                "dostupne_stranky": [],
                "seznam_zarizeni": [],
                "is_active": True,
                "is_admin": False,
                "created_at": None,
                "updated_at": None,
                "last_login_at": None,
            }
        ],
    )
    monkeypatch.setattr(
        dashboard_admin,
        "upsert_user",
        lambda **_kwargs: (_ for _ in ()).throw(
            security.PasswordPolicyError("policy rejected")
        ),
    )

    with pytest.raises(dashboard_admin.AdminOperationError, match="policy rejected"):
        dashboard_admin.update_admin_user(
            SimpleNamespace(is_admin=True, username="admin"),
            username="operator",
            password="short",
        )


def test_cli_rejects_weak_password_before_database_bootstrap(monkeypatch):
    monkeypatch.setattr(
        create_user,
        "parse_args",
        lambda: SimpleNamespace(
            username="operator",
            email="",
            password="short",
            zarizeni="",
            sekce="",
            stranky="",
            admin=False,
            inactive=False,
        ),
    )
    monkeypatch.setattr(
        create_user,
        "ensure_dashboard_tables",
        lambda: pytest.fail("bootstrap should not run for a rejected password"),
    )

    with pytest.raises(SystemExit, match="alespon 15"):
        create_user.main()


def test_password_entry_pages_use_shared_validator():
    project_root = Path(__file__).resolve().parents[1]
    admin_page = (
        project_root / "moduly/apps/dashboard/pages/1_sprava_uzivatelu.py"
    ).read_text(encoding="utf-8")
    account_page = (
        project_root / "moduly/apps/dashboard/pages/3_muj_ucet.py"
    ).read_text(encoding="utf-8")
    cli = (
        project_root / "moduly/apps/dashboard/database/create_user.py"
    ).read_text(encoding="utf-8")

    assert "validate_password(new_password" in account_page
    assert "validate_password(new_password" in admin_page
    assert "validate_password(edit_password" in admin_page
    assert "validate_password(password" in cli
    assert "len(new_password) < 8" not in account_page
