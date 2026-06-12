from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.time_utils import utc_now_naive
from services.api.core.config import get_api_settings


class TokenError(ValueError):
    """Raised when a bearer token is missing, invalid, or expired."""


@dataclass(frozen=True)
class AccessTokenPayload:
    subject: str
    expires_at: datetime
    token_version: int
    issued_at: datetime
    session_started_at: datetime
    absolute_expires_at: datetime


def _get_token_secret() -> str:
    token_secret = get_api_settings().token_secret
    if not token_secret:
        raise TokenError("API_TOKEN_SECRET neni nastaveno v prostredi.")
    return token_secret


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _sign(value: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), value.encode("ascii"), hashlib.sha256).digest()
    return _b64encode(digest)


def _to_unix_timestamp(value: datetime) -> int:
    return int(value.replace(tzinfo=timezone.utc).timestamp())


def _from_unix_timestamp(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc).replace(tzinfo=None)


def create_access_token(
    subject: str,
    token_version: int,
    *,
    session_started_at: datetime | None = None,
) -> tuple[str, datetime]:
    settings = get_api_settings()
    secret = _get_token_secret()
    issued_at = utc_now_naive()
    session_started_at = session_started_at or issued_at
    absolute_expires_at = session_started_at + timedelta(
        minutes=settings.token_expiry_minutes
    )
    if absolute_expires_at <= issued_at:
        raise TokenError("Absolutni platnost relace vyprsela.")
    expires_at = min(
        issued_at + timedelta(minutes=settings.session_inactivity_minutes),
        absolute_expires_at,
    )
    payload = {
        "sub": subject,
        "exp": _to_unix_timestamp(expires_at),
        "ver": int(token_version),
        "iat": _to_unix_timestamp(issued_at),
        "ses": _to_unix_timestamp(session_started_at),
        "abs": _to_unix_timestamp(absolute_expires_at),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_encoded = _b64encode(payload_json)
    signature = _sign(payload_encoded, secret)
    return f"{payload_encoded}.{signature}", expires_at


def renew_access_token(payload: AccessTokenPayload) -> tuple[str, datetime]:
    return create_access_token(
        payload.subject,
        payload.token_version,
        session_started_at=payload.session_started_at,
    )


def decode_access_token(token: str) -> AccessTokenPayload:
    secret = _get_token_secret()
    try:
        payload_encoded, signature = token.split(".", 1)
    except ValueError as exc:
        raise TokenError("Token nema platny format.") from exc

    expected_signature = _sign(payload_encoded, secret)
    if not hmac.compare_digest(signature, expected_signature):
        raise TokenError("Token podpis nesouhlasi.")

    try:
        payload = json.loads(_b64decode(payload_encoded))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("Token payload nelze dekodovat.") from exc

    subject = str(payload.get("sub") or "").strip()
    expires_raw = payload.get("exp")
    token_version = payload.get("ver")
    issued_raw = payload.get("iat")
    session_started_raw = payload.get("ses")
    absolute_expires_raw = payload.get("abs")
    if (
        not subject
        or not isinstance(expires_raw, int)
        or not isinstance(token_version, int)
        or not isinstance(issued_raw, int)
        or not isinstance(session_started_raw, int)
        or not isinstance(absolute_expires_raw, int)
    ):
        raise TokenError("Token payload je neuplny.")

    expires_at = _from_unix_timestamp(expires_raw)
    issued_at = _from_unix_timestamp(issued_raw)
    session_started_at = _from_unix_timestamp(session_started_raw)
    absolute_expires_at = _from_unix_timestamp(absolute_expires_raw)
    now = utc_now_naive()
    if expires_at <= now:
        raise TokenError("Token expiroval.")
    if absolute_expires_at <= now:
        raise TokenError("Absolutni platnost relace vyprsela.")
    if session_started_at > issued_at or issued_at > now + timedelta(minutes=1):
        raise TokenError("Token obsahuje neplatne casove udaje.")
    if expires_at > absolute_expires_at:
        raise TokenError("Token prekrocil absolutni platnost relace.")

    return AccessTokenPayload(
        subject=subject,
        expires_at=expires_at,
        token_version=token_version,
        issued_at=issued_at,
        session_started_at=session_started_at,
        absolute_expires_at=absolute_expires_at,
    )
