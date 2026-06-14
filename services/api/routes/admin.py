from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from services.api.core.auth_audit import auth_audit_service
from services.api.core.dependencies import get_current_admin_user
from services.api.core.login_throttle import get_login_client_ip
from services.api.schemas.admin import (
    AdminDeviceMutationRequest,
    AdminDeviceOptionsResponse,
    AdminDeviceUpdateRequest,
    AdminMapLayerCreateRequest,
    AdminMapLayerRecord,
    AdminMapLayersResponse,
    AdminMapLayerUpdateRequest,
    AdminRevizeMutationRequest,
    AdminRevizeMutationResponse,
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
from services.api.services.device_admin import create_device_admin, update_device_admin
from services.api.services.map_layers import (
    MapLayerOperationError,
    create_map_layer_admin,
    delete_map_layer_admin,
    list_map_layers_admin,
    update_map_layer_admin,
)
from services.api.services.revize_admin import create_revize_admin, update_revize_admin


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
    request: Request,
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
    auth_audit_service.record_security_event(
        event_type="account_created",
        result="success",
        reason="admin_create",
        actor_username=current_user.username,
        target_username=str(user_record["username"]),
        source_ip=get_login_client_ip(request),
        details={
            "is_active": bool(user_record["is_active"]),
            "is_admin": bool(user_record["is_admin"]),
        },
    )
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
    request: Request,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminUserRecord:
    try:
        updates = payload.model_dump(exclude_unset=True)
        update_result = update_admin_user(
            current_user,
            username=username,
            **updates,
        )
    except AdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    client_ip = get_login_client_ip(request)
    target_username = str(update_result.record["username"])
    if update_result.changed_fields:
        auth_audit_service.record_security_event(
            event_type="account_updated",
            result="success",
            reason="admin_update",
            actor_username=current_user.username,
            target_username=target_username,
            source_ip=client_ip,
            details={"changed_fields": list(update_result.changed_fields)},
        )
    if update_result.password_changed:
        auth_audit_service.record_security_event(
            event_type="password_change",
            result="success",
            reason="admin_reset",
            actor_username=current_user.username,
            target_username=target_username,
            source_ip=client_ip,
        )
    revoked_fields = tuple(
        field
        for field in update_result.changed_fields
        if field
        in {
            "password",
            "available_sections",
            "available_pages",
            "device_ids",
            "is_active",
            "is_admin",
        }
    )
    if revoked_fields:
        auth_audit_service.record_security_event(
            event_type="token_revocation",
            result="success",
            reason="admin_security_update",
            actor_username=current_user.username,
            target_username=target_username,
            source_ip=client_ip,
            details={"changed_fields": list(revoked_fields)},
        )
    if update_result.role_changed:
        auth_audit_service.record_security_event(
            event_type="role_change",
            result="success",
            reason="admin_role_update",
            actor_username=current_user.username,
            target_username=target_username,
            source_ip=client_ip,
            details={
                "previous_is_admin": update_result.previous_is_admin,
                "is_admin": bool(update_result.record["is_admin"]),
            },
        )
    if update_result.active_changed:
        auth_audit_service.record_security_event(
            event_type="account_activation_change",
            result="success",
            reason=(
                "account_activated"
                if bool(update_result.record["is_active"])
                else "account_deactivated"
            ),
            actor_username=current_user.username,
            target_username=target_username,
            source_ip=client_ip,
            details={
                "previous_is_active": update_result.previous_is_active,
                "is_active": bool(update_result.record["is_active"]),
            },
        )
    return AdminUserRecord(**update_result.record)


@router.delete(
    "/users/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
    description="Smaže uživatele dashboardu. "
    "Vyžaduje admin oprávnění.",
)
def delete_user(
    username: str,
    request: Request,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> Response:
    try:
        deleted_state = delete_admin_user(current_user, username=username)
    except AdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if deleted_state is not None:
        client_ip = get_login_client_ip(request)
        auth_audit_service.record_security_event(
            event_type="account_deleted",
            result="success",
            reason="admin_delete",
            actor_username=current_user.username,
            target_username=username,
            source_ip=client_ip,
            details=deleted_state,
        )
        auth_audit_service.record_security_event(
            event_type="token_revocation",
            result="success",
            reason="account_deleted",
            actor_username=current_user.username,
            target_username=username,
            source_ip=client_ip,
        )
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


@router.post(
    "/revize",
    response_model=AdminRevizeMutationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create revision record",
    description="Vytvori revizi a vazby na zarizeni. Vyzaduje admin opravneni.",
)
def create_revize(
    payload: AdminRevizeMutationRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminRevizeMutationResponse:
    values = payload.model_dump(exclude={"linked_device_ids"})
    try:
        revize_id = create_revize_admin(
            current_user,
            payload=values,
            linked_device_ids=payload.linked_device_ids,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return AdminRevizeMutationResponse(id=revize_id)


@router.patch(
    "/revize/{revize_id}",
    response_model=AdminRevizeMutationResponse,
    summary="Update revision record",
    description="Aktualizuje revizi a jeji vazby na zarizeni. Vyzaduje admin opravneni.",
)
def update_revize(
    revize_id: int,
    payload: AdminRevizeMutationRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> AdminRevizeMutationResponse:
    values = payload.model_dump(exclude={"linked_device_ids"})
    try:
        updated_id = update_revize_admin(
            current_user,
            revize_id=revize_id,
            payload=values,
            linked_device_ids=payload.linked_device_ids,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return AdminRevizeMutationResponse(id=updated_id)


@router.post(
    "/devices/{meter_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Create device record",
    description="Vytvori zaznam zarizeni v provozni databazi. Vyzaduje admin opravneni.",
)
def create_device(
    meter_key: str,
    payload: AdminDeviceMutationRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> Response:
    try:
        create_device_admin(
            current_user,
            meter_key=meter_key,
            form_values=payload.fields,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/devices/{meter_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update device record",
    description="Aktualizuje zaznam zarizeni v provozni databazi. Vyzaduje admin opravneni.",
)
def update_device(
    meter_key: str,
    payload: AdminDeviceUpdateRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> Response:
    try:
        update_device_admin(
            current_user,
            meter_key=meter_key,
            primary_key_value=payload.primary_key_value,
            form_values=payload.fields,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
