from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials

from app.dashboard_session import DASHBOARD_SESSION_COOKIE_NAME
from services.api.core.dependencies import bearer_scheme, get_current_user
from services.api.core.tokens import TokenError, create_access_token, decode_access_token
from services.api.schemas.auth import LoginRequest, TokenResponse, UserProfileResponse
from services.api.schemas.auth import EmailUpdateRequest, PasswordChangeRequest, UsersExistResponse
from services.api.services.dashboard_auth import (
    AuthenticationError,
    DashboardUserContext,
    UserUpdateError,
    authenticate_dashboard_user,
    change_dashboard_user_password,
    dashboard_users_exist,
    logout_dashboard_user,
    update_dashboard_user_email,
)


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _profile_from_context(user_context: DashboardUserContext) -> UserProfileResponse:
    return UserProfileResponse(**user_context.to_profile_dict())


@router.get(
    "/users-exist",
    response_model=UsersExistResponse,
    summary="Check if users exist",
    description="Kontroluje zda existuje alespoň jeden uživatel v systému. "
    "Používá se pro rozhodnutí zda zobrazit login nebo registrační formulář.",
)
def users_exist() -> UsersExistResponse:
    return UsersExistResponse(users_exist=dashboard_users_exist())


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User login",
    description="Přihlášení uživatele. Vrací JWT access token a profil uživatele. "
    "Token je platný po dobu nastavenou v API_TOKEN_EXPIRE_MINUTES.",
)
def login(payload: LoginRequest) -> TokenResponse:
    try:
        user_context = authenticate_dashboard_user(payload.username, payload.password)
        access_token, expires_at = create_access_token(
            user_context.username,
            token_version=user_context.token_version,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return TokenResponse(
        access_token=access_token,
        expires_at=expires_at,
        user=_profile_from_context(user_context),
    )


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get current user profile",
    description="Vrací profil aktuálně přihlášeného uživatele.",
)
def me(current_user: DashboardUserContext = Depends(get_current_user)) -> UserProfileResponse:
    return _profile_from_context(current_user)


def _request_uses_https(request: Request) -> bool:
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    if forwarded_proto:
        return forwarded_proto.split(",", 1)[0].strip().lower() == "https"
    return request.url.scheme == "https"


@router.post(
    "/browser-session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Persist browser session",
    description="Ulozi aktualni bearer token do zabezpecene HttpOnly cookie pro obnovu Streamlit session po reloadu.",
)
def persist_browser_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    _current_user: DashboardUserContext = Depends(get_current_user),
) -> Response:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chybi bearer token.",
        )

    token_payload = decode_access_token(credentials.credentials)
    expires_at = token_payload.expires_at.replace(tzinfo=timezone.utc)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.set_cookie(
        key=DASHBOARD_SESSION_COOKIE_NAME,
        value=credentials.credentials,
        expires=expires_at,
        httponly=True,
        secure=_request_uses_https(request),
        samesite="lax",
        path="/",
    )
    return response


@router.delete(
    "/browser-session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear browser session",
    description="Odstrani cookie pouzivanou pro obnovu Streamlit session.",
)
def clear_browser_session(request: Request) -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=DASHBOARD_SESSION_COOKIE_NAME,
        httponly=True,
        secure=_request_uses_https(request),
        samesite="lax",
        path="/",
    )
    return response


@router.patch(
    "/me/email",
    response_model=UserProfileResponse,
    summary="Update current user email",
    description="Aktualizuje e-mailovou adresu aktuálně přihlášeného uživatele.",
)
def update_my_email(
    payload: EmailUpdateRequest,
    current_user: DashboardUserContext = Depends(get_current_user),
) -> UserProfileResponse:
    try:
        updated_user = update_dashboard_user_email(current_user.username, payload.email)
    except UserUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _profile_from_context(updated_user)


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change current user password",
    description="Změna hesla aktuálně přihlášeného uživatele. Vyžaduje zadání stávajícího hesla.",
)
def change_my_password(
    payload: PasswordChangeRequest,
    current_user: DashboardUserContext = Depends(get_current_user),
) -> Response:
    try:
        change_dashboard_user_password(
            current_user.username,
            payload.current_password,
            payload.new_password,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except UserUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="User logout",
    description="Odhlášení uživatele. Zruší platnost tokenu.",
)
def logout(current_user: DashboardUserContext = Depends(get_current_user)) -> Response:
    logout_dashboard_user(current_user.username)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
