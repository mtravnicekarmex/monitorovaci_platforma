from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.time_utils import utc_now_naive
from services.api.core.config import get_api_settings


class TokenError(ValueError):
    """Raised when a bearer token is missing, invalid, or expired."""


@dataclass(frozen=True)
class AccessTokenPayload:
    subject: str
    expires_at: datetime
    token_version: int


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


def create_access_token(subject: str, token_version: int) -> tuple[str, datetime]:
    settings = get_api_settings()
    secret = _get_token_secret()
    expires_at = utc_now_naive() + timedelta(minutes=settings.token_expiry_minutes)
    payload = {
        "sub": subject,
        "exp": int(expires_at.timestamp()),
        "ver": int(token_version),
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_encoded = _b64encode(payload_json)
    signature = _sign(payload_encoded, secret)
    return f"{payload_encoded}.{signature}", expires_at


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
    if not subject or not isinstance(expires_raw, int) or not isinstance(token_version, int):
        raise TokenError("Token payload je neuplny.")

    expires_at = datetime.utcfromtimestamp(expires_raw)
    if expires_at <= utc_now_naive():
        raise TokenError("Token expiroval.")

    return AccessTokenPayload(subject=subject, expires_at=expires_at, token_version=token_version)
