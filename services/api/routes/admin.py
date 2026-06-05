from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.admin import (
    AdminDeviceOptionsResponse,
    AdminMapLayerCreateRequest,
    AdminMapLayerRecord,
    AdminMapLayersResponse,
    AdminMapLayerUpdateRequest,
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
from services.api.services.map_layers import (
    MapLayerOperationError,
    create_map_layer_admin,
    delete_map_layer_admin,
    list_map_layers_admin,
    update_map_layer_admin,
)


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get(
    "/device-options",
    response_model=AdminDeviceOptionsResponse,
    summary="List all device options",
    description="Vrací seznam všech dostupných zařízení pro konfiguraci uživatelů. "
    "Vyžaduje admin oprávnění.",
)
def get_admin_device_options(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminDeviceOptionsResponse:
    devices = list_all_device_options(current_user)
    return AdminDeviceOptionsResponse(total=len(devices), devices=devices)


@router.get(
    "/users",
    response_model=AdminUsersResponse,
    summary="List all users",
    description="Vrací seznam všech uživatelů dashboardu. "
    "Vyžaduje admin oprávnění.",
)
def get_admin_users(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminUsersResponse:
    users = list_admin_users(current_user)
    return AdminUsersResponse(total=len(users), users=users)


@router.post(
    "/users",
    response_model=AdminUserRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Create new user",
    description="Vytvoří nového uživatele dashboardu. "
    "Vyžaduje admin oprávnění.",
)
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


@router.patch(
    "/users/{username}",
    response_model=AdminUserRecord,
    summary="Update user",
    description="Aktualizuje existujícího uživatele (e-mail, oprávnění, zařízení). "
    "Vyžaduje admin oprávnění.",
)
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


@router.delete(
    "/users/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Smaže uživatele dashboardu. "
    "Vyžaduje admin oprávnění.",
)
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


@router.get(
    "/map-layers",
    response_model=AdminMapLayersResponse,
    summary="List map layers",
    description="Vraci konfiguraci mapovych vrstev pro spravu mapovych podkladu. Vyzaduje admin opravneni.",
)
def get_admin_map_layers(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminMapLayersResponse:
    layers = list_map_layers_admin(current_user)
    return AdminMapLayersResponse(total=len(layers), layers=layers)


@router.post(
    "/map-layers",
    response_model=AdminMapLayerRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Create map layer",
    description="Vytvori novou konfigurovatelnou mapovou vrstvu. Vyzaduje admin opravneni.",
)
def create_map_layer(
    payload: AdminMapLayerCreateRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminMapLayerRecord:
    try:
        record = create_map_layer_admin(current_user, **payload.model_dump())
    except MapLayerOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return AdminMapLayerRecord(**record)


@router.patch(
    "/map-layers/{layer_id}",
    response_model=AdminMapLayerRecord,
    summary="Update map layer",
    description="Aktualizuje konfiguraci mapove vrstvy vcetne stylu a viditelnosti. Vyzaduje admin opravneni.",
)
def update_map_layer(
    layer_id: str,
    payload: AdminMapLayerUpdateRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminMapLayerRecord:
    try:
        updates = payload.model_dump(exclude={"layer_id"})
        record = update_map_layer_admin(current_user, layer_id=layer_id, **updates)
    except MapLayerOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return AdminMapLayerRecord(**record)


@router.delete(
    "/map-layers/{layer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete map layer",
    description="Smaze konfiguraci mapove vrstvy. Zdrojova data zustavaji beze zmeny. Vyzaduje admin opravneni.",
)
def delete_map_layer(
    layer_id: str,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> Response:
    try:
        delete_map_layer_admin(current_user, layer_id=layer_id)
    except MapLayerOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
