from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from services.api.core.dependencies import get_current_user
from services.api.core.tokens import TokenError, create_access_token
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


@router.get("/users-exist", response_model=UsersExistResponse)
def users_exist() -> UsersExistResponse:
    return UsersExistResponse(users_exist=dashboard_users_exist())


@router.post("/login", response_model=TokenResponse)
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


@router.get("/me", response_model=UserProfileResponse)
def me(current_user: DashboardUserContext = Depends(get_current_user)) -> UserProfileResponse:
    return _profile_from_context(current_user)


@router.patch("/me/email", response_model=UserProfileResponse)
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


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT)
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: DashboardUserContext = Depends(get_current_user)) -> Response:
    logout_dashboard_user(current_user.username)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
