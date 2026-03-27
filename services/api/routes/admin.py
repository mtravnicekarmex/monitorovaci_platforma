from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.admin import (
    AdminDeviceOptionsResponse,
    AdminUserCreateRequest,
    AdminUserRecord,
    AdminUsersResponse,
    AdminUserUpdateRequest,
)
from services.api.services.dashboard_admin import (
    AdminOperationError,
    create_admin_user,
    delete_admin_user,
    list_admin_users,
    list_all_device_options,
    update_admin_user,
)
from services.api.services.dashboard_auth import DashboardUserContext


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/device-options", response_model=AdminDeviceOptionsResponse)
def get_admin_device_options(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminDeviceOptionsResponse:
    devices = list_all_device_options(current_user)
    return AdminDeviceOptionsResponse(total=len(devices), devices=devices)


@router.get("/users", response_model=AdminUsersResponse)
def get_admin_users(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminUsersResponse:
    users = list_admin_users(current_user)
    return AdminUsersResponse(total=len(users), users=users)


@router.post("/users", response_model=AdminUserRecord, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreateRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminUserRecord:
    try:
        user_record = create_admin_user(
            current_user,
            username=payload.username,
            password=payload.password,
            email=payload.email,
            available_sections=payload.available_sections,
            available_pages=payload.available_pages,
            device_ids=payload.device_ids,
            is_active=payload.is_active,
            is_admin=payload.is_admin,
        )
    except AdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return AdminUserRecord(**user_record)


@router.patch("/users/{username}", response_model=AdminUserRecord)
def update_user(
    username: str,
    payload: AdminUserUpdateRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminUserRecord:
    try:
        updates = payload.model_dump(exclude_unset=True)
        user_record = update_admin_user(
            current_user,
            username=username,
            **updates,
        )
    except AdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return AdminUserRecord(**user_record)


@router.delete("/users/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    username: str,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> Response:
    try:
        delete_admin_user(current_user, username=username)
    except AdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
