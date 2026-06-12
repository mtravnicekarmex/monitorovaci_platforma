from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from services.api.core import tokens


def _settings():
    return SimpleNamespace(
        token_secret="test-session-secret",
        token_expiry_minutes=480,
        session_inactivity_minutes=30,
    )


def test_access_token_uses_inactivity_and_absolute_session_limits(monkeypatch):
    now = [datetime(2026, 6, 12, 8, 0)]
    monkeypatch.setattr(tokens, "get_api_settings", _settings)
    monkeypatch.setattr(tokens, "utc_now_naive", lambda: now[0])

    access_token, expires_at = tokens.create_access_token("operator", 3)
    payload = tokens.decode_access_token(access_token)

    assert expires_at == datetime(2026, 6, 12, 8, 30)
    assert payload.subject == "operator"
    assert payload.token_version == 3
    assert payload.issued_at == datetime(2026, 6, 12, 8, 0)
    assert payload.session_started_at == datetime(2026, 6, 12, 8, 0)
    assert payload.absolute_expires_at == datetime(2026, 6, 12, 16, 0)


def test_session_renewal_extends_inactivity_but_not_absolute_limit(monkeypatch):
    now = [datetime(2026, 6, 12, 8, 0)]
    monkeypatch.setattr(tokens, "get_api_settings", _settings)
    monkeypatch.setattr(tokens, "utc_now_naive", lambda: now[0])

    access_token, _ = tokens.create_access_token("operator", 3)
    original_payload = tokens.decode_access_token(access_token)

    now[0] = datetime(2026, 6, 12, 15, 50)
    renewed_token, renewed_expires_at = tokens.renew_access_token(original_payload)
    renewed_payload = tokens.decode_access_token(renewed_token)

    assert renewed_expires_at == datetime(2026, 6, 12, 16, 0)
    assert renewed_payload.session_started_at == original_payload.session_started_at
    assert renewed_payload.absolute_expires_at == original_payload.absolute_expires_at

    now[0] = datetime(2026, 6, 12, 16, 0)
    with pytest.raises(tokens.TokenError, match="Absolutni platnost"):
        tokens.renew_access_token(original_payload)


def test_expired_inactivity_token_is_rejected(monkeypatch):
    now = [datetime(2026, 6, 12, 8, 0)]
    monkeypatch.setattr(tokens, "get_api_settings", _settings)
    monkeypatch.setattr(tokens, "utc_now_naive", lambda: now[0])

    access_token, _ = tokens.create_access_token("operator", 3)
    now[0] = datetime(2026, 6, 12, 8, 30)

    with pytest.raises(tokens.TokenError, match="Token expiroval"):
        tokens.decode_access_token(access_token)
