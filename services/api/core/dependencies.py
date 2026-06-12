from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer

from app.dashboard_session import DASHBOARD_SESSION_COOKIE_NAME
from services.api.core.tokens import TokenError, decode_access_token
from services.api.services.dashboard_auth import (
    AuthorizationError,
    DashboardUserContext,
    get_dashboard_user_context,
    require_page_access,
    require_section_access,
)


bearer_scheme = HTTPBearer(auto_error=False)
browser_session_scheme = APIKeyCookie(
    name=DASHBOARD_SESSION_COOKIE_NAME,
    auto_error=False,
)


def _get_user_context_from_access_token(access_token: str) -> DashboardUserContext:
    try:
        payload = decode_access_token(access_token)
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


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> DashboardUserContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chybi bearer token.",
        )
    return _get_user_context_from_access_token(credentials.credentials)


def get_current_browser_session_user(
    access_token: str | None = Depends(browser_session_scheme),
) -> DashboardUserContext:
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chybi dashboard session cookie.",
        )
    return _get_user_context_from_access_token(access_token)


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


def get_current_web_search_user(
    current_user: DashboardUserContext = Depends(get_current_user),
) -> DashboardUserContext:
    try:
        require_page_access(current_user, "web_search_monitor")
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return current_user
