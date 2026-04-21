from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from services.api.core.tokens import TokenError, decode_access_token
from services.api.services.dashboard_auth import (
    AuthorizationError,
    DashboardUserContext,
    get_dashboard_user_context,
    require_section_access,
)


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> DashboardUserContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chybi bearer token.",
        )

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    user_context = get_dashboard_user_context(payload.subject)
    if user_context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Uzivatel neexistuje nebo je neaktivni.",
        )
    if payload.token_version != user_context.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token uz byl odhlasen nebo revokovan.",
        )

    return user_context


def get_current_vodomery_user(
    current_user: DashboardUserContext = Depends(get_current_user),
) -> DashboardUserContext:
    try:
        require_section_access(current_user, "vodomery")
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return current_user


def get_current_manometry_user(
    current_user: DashboardUserContext = Depends(get_current_user),
) -> DashboardUserContext:
    try:
        require_section_access(current_user, "manometry")
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return current_user


def get_current_plynomery_user(
    current_user: DashboardUserContext = Depends(get_current_user),
) -> DashboardUserContext:
    try:
        require_section_access(current_user, "plynomery")
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return current_user


def get_current_admin_user(
    current_user: DashboardUserContext = Depends(get_current_user),
) -> DashboardUserContext:
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tato operace je dostupna pouze adminovi.",
        )
    return current_user
