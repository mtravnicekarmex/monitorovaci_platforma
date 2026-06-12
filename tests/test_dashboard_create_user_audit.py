from types import SimpleNamespace

from moduly.apps.dashboard.database import create_user


class _AuditStub:
    def __init__(self) -> None:
        self.events = []

    def record_security_event(self, **kwargs) -> None:
        self.events.append(kwargs)


def _args(**updates):
    values = {
        "username": "target",
        "email": "",
        "password": "not-recorded-but-strong",
        "zarizeni": "",
        "sekce": "",
        "stranky": "",
        "admin": False,
        "inactive": False,
    }
    values.update(updates)
    return SimpleNamespace(**values)


def test_cli_create_user_audits_account_without_password(monkeypatch):
    audit = _AuditStub()
    monkeypatch.setattr(create_user, "parse_args", lambda: _args(admin=True))
    monkeypatch.setattr(create_user, "ensure_dashboard_tables", lambda: None)
    monkeypatch.setattr(create_user, "get_user", lambda _username: None)
    monkeypatch.setattr(create_user, "upsert_user", lambda **_kwargs: None)
    monkeypatch.setattr(create_user, "auth_audit_service", audit)
    monkeypatch.setattr(create_user.getpass, "getuser", lambda: "operator")

    create_user.main()

    assert audit.events[0]["event_type"] == "account_created"
    assert audit.events[0]["details"] == {"is_admin": True, "is_active": True}
    assert "not-recorded-but-strong" not in repr(audit.events)


def test_cli_update_user_audits_password_role_activation_and_revocation(monkeypatch):
    audit = _AuditStub()
    monkeypatch.setattr(
        create_user,
        "parse_args",
        lambda: _args(admin=True, inactive=True),
    )
    monkeypatch.setattr(create_user, "ensure_dashboard_tables", lambda: None)
    monkeypatch.setattr(
        create_user,
        "get_user",
        lambda _username: SimpleNamespace(is_admin=False, is_active=True),
    )
    monkeypatch.setattr(create_user, "upsert_user", lambda **_kwargs: None)
    monkeypatch.setattr(create_user, "auth_audit_service", audit)
    monkeypatch.setattr(create_user.getpass, "getuser", lambda: "operator")

    create_user.main()

    assert [event["event_type"] for event in audit.events] == [
        "account_updated",
        "password_change",
        "token_revocation",
        "role_change",
        "account_activation_change",
    ]
    assert "not-recorded-but-strong" not in repr(audit.events)
