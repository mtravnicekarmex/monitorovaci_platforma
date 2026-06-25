from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials

from app.dashboard_session import (
    DASHBOARD_SESSION_COOKIE_NAME,
    LEGACY_DASHBOARD_SESSION_COOKIE_NAME,
    MAP_IMAGE_SESSION_COOKIE_NAME,
    MAP_IMAGE_SESSION_COOKIE_PATH,
)
from services.api.core.auth_audit import auth_audit_service
from services.api.core.dependencies import bearer_scheme, get_current_user
from services.api.core.login_throttle import get_login_client_ip, login_attempt_limiter
from services.api.core.tokens import (
    TokenError,
    create_access_token,
    decode_access_token,
    renew_access_token,
)
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
INVALID_LOGIN_DETAIL = "Neplatne prihlasovaci udaje."
THROTTLED_LOGIN_DETAIL = "Prihlaseni je docasne omezeno. Zkuste to pozdeji."


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
    "Relace používá klouzavý limit API_SESSION_INACTIVITY_MINUTES a pevný "
    "limit API_TOKEN_EXPIRY_MINUTES.",
)
def login(payload: LoginRequest, request: Request) -> TokenResponse:
    client_ip = get_login_client_ip(request)
    retry_after = login_attempt_limiter.retry_after(payload.username, client_ip)
    if retry_after:
        auth_audit_service.record_login_throttled(
            username=payload.username,
            source_ip=client_ip,
            retry_after=retry_after,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=THROTTLED_LOGIN_DETAIL,
            headers={"Retry-After": str(retry_after)},
        )

    try:
        user_context = authenticate_dashboard_user(payload.username, payload.password)
        access_token, expires_at = create_access_token(
            user_context.username,
            token_version=user_context.token_version,
        )
    except AuthenticationError as exc:
        failure_status = login_attempt_limiter.register_failure_status(
            payload.username,
            client_ip,
        )
        auth_audit_service.record_login_failure(
            username=payload.username,
            source_ip=client_ip,
            reason=exc.reason_category,
            is_admin_account=exc.is_admin_account,
            failure_status=failure_status,
        )
        if failure_status.retry_after:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=THROTTLED_LOGIN_DETAIL,
                headers={"Retry-After": str(failure_status.retry_after)},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_LOGIN_DETAIL,
        ) from exc
    except TokenError as exc:
        auth_audit_service.record_security_event(
            event_type="login",
            result="error",
            reason="token_issue_failed",
            actor_username=payload.username,
            target_username=payload.username,
            source_ip=client_ip,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    login_attempt_limiter.register_success(payload.username)
    auth_audit_service.record_login_success(
        username=user_context.username,
        source_ip=client_ip,
        is_admin=user_context.is_admin,
    )
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


@router.post(
    "/session/refresh",
    response_model=TokenResponse,
    summary="Refresh active session",
    description=(
        "Obnovi kratkou platnost aktivni relace bez prekroceni jejiho "
        "absolutniho casoveho limitu."
    ),
)
def refresh_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    current_user: DashboardUserContext = Depends(get_current_user),
) -> TokenResponse:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chybi bearer token.",
        )

    try:
        token_payload = decode_access_token(credentials.credentials)
        access_token, expires_at = renew_access_token(token_payload)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    return TokenResponse(
        access_token=access_token,
        expires_at=expires_at,
        user=_profile_from_context(current_user),
    )


@router.post(
    "/browser-session",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Persist browser session",
    description="Ulozi aktualni bearer token do zabezpecene HttpOnly cookie pro obnovu Streamlit session po reloadu.",
)
def persist_browser_session(
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
        secure=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=MAP_IMAGE_SESSION_COOKIE_NAME,
        value=credentials.credentials,
        expires=expires_at,
        httponly=True,
        secure=True,
        samesite="none",
        path=MAP_IMAGE_SESSION_COOKIE_PATH,
    )
    response.delete_cookie(
        key=LEGACY_DASHBOARD_SESSION_COOKIE_NAME,
        httponly=True,
        secure=True,
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
def clear_browser_session() -> Response:
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    for cookie_name in (
        DASHBOARD_SESSION_COOKIE_NAME,
        LEGACY_DASHBOARD_SESSION_COOKIE_NAME,
    ):
        response.delete_cookie(
            key=cookie_name,
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
    response.delete_cookie(
        key=MAP_IMAGE_SESSION_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="none",
        path=MAP_IMAGE_SESSION_COOKIE_PATH,
    )
    response.headers["Clear-Site-Data"] = '"cache", "storage"'
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
    request: Request,
    current_user: DashboardUserContext = Depends(get_current_user),
) -> Response:
    try:
        change_dashboard_user_password(
            current_user.username,
            payload.current_password,
            payload.new_password,
        )
    except AuthenticationError as exc:
        auth_audit_service.record_security_event(
            event_type="password_change",
            result="failure",
            reason=exc.reason_category,
            actor_username=current_user.username,
            target_username=current_user.username,
            source_ip=get_login_client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    except UserUpdateError as exc:
        auth_audit_service.record_security_event(
            event_type="password_change",
            result="failure",
            reason="password_policy_rejected",
            actor_username=current_user.username,
            target_username=current_user.username,
            source_ip=get_login_client_ip(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    client_ip = get_login_client_ip(request)
    auth_audit_service.record_security_event(
        event_type="password_change",
        result="success",
        reason="self_service",
        actor_username=current_user.username,
        target_username=current_user.username,
        source_ip=client_ip,
    )
    auth_audit_service.record_security_event(
        event_type="token_revocation",
        result="success",
        reason="password_change",
        actor_username=current_user.username,
        target_username=current_user.username,
        source_ip=client_ip,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="User logout",
    description="Odhlášení uživatele. Zruší platnost tokenu.",
)
def logout(
    request: Request,
    current_user: DashboardUserContext = Depends(get_current_user),
) -> Response:
    logout_dashboard_user(current_user.username)
    auth_audit_service.record_security_event(
        event_type="token_revocation",
        result="success",
        reason="logout",
        actor_username=current_user.username,
        target_username=current_user.username,
        source_ip=get_login_client_ip(request),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
