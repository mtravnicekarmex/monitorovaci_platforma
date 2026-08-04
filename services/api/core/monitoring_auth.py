from __future__ import annotations

import hashlib
import hmac
import re

from decouple import config
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
monitoring_bearer_scheme = HTTPBearer(auto_error=False)


def get_configured_monitoring_token_hashes() -> tuple[str, ...]:
    hashes: list[str] = []
    for name in (
        "MONITORING_AGENT_TOKEN_SHA256",
        "MONITORING_AGENT_PREVIOUS_TOKEN_SHA256",
    ):
        value = str(config(name, default="")).strip()
        if not value:
            continue
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError(f"{name} must contain one SHA-256 hexadecimal digest.")
        normalized = value.casefold()
        if normalized not in hashes:
            hashes.append(normalized)
    return tuple(hashes)


def require_monitoring_agent(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        monitoring_bearer_scheme
    ),
) -> str:
    try:
        configured_hashes = get_configured_monitoring_token_hashes()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Monitoring facade configuration is invalid.",
        ) from exc
    if not configured_hashes:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Monitoring facade is not configured.",
        )
    if (
        credentials is None
        or credentials.scheme.casefold() != "bearer"
        or not credentials.credentials
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid monitoring credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    presented_hash = hashlib.sha256(
        credentials.credentials.encode("utf-8")
    ).hexdigest()
    if not any(
        hmac.compare_digest(presented_hash, configured_hash)
        for configured_hash in configured_hashes
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid monitoring credential.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return "monitoring-agent"
