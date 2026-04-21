from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from services.api.core.dependencies import get_current_admin_user, get_current_plynomery_user
from services.api.schemas.plynomery import (
    PlynomeryAlertRuleRow,
    PlynomeryAlertRulesResponse,
    PlynomeryAlertRuleUpsertRequest,
    PlynomeryDeviceListResponse,
)
from services.api.services.dashboard_auth import DashboardUserContext
from services.api.services.plynomery import list_accessible_devices
from services.api.services.plynomery_admin import (
    PlynomeryAdminOperationError,
    create_alert_rule_admin,
    delete_alert_rule_admin,
    list_alert_rules_admin,
    update_alert_rule_admin,
)


router = APIRouter(prefix="/api/v1/plynomery", tags=["plynomery"])


@router.get(
    "/devices",
    response_model=PlynomeryDeviceListResponse,
    summary="List plynoměry devices",
    description="Vrací seznam plynoměrů dostupných pro přihlášeného uživatele. "
    "Oprávnění jsou omezená dle konfigurace uživatele.",
)
def get_plynomery_devices(
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: DashboardUserContext = Depends(get_current_plynomery_user),
) -> PlynomeryDeviceListResponse:
    devices = list_accessible_devices(current_user, limit=limit)
    return PlynomeryDeviceListResponse(
        total=len(devices),
        devices=devices,
    )


@router.get(
    "/alert-rules",
    response_model=PlynomeryAlertRulesResponse,
    summary="Get alert rules",
    description="Vrací seznam konfigurovaných alert pravidel pro plynoměry. "
    "Vyžaduje admin oprávnění.",
)
def get_plynomery_alert_rules(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> PlynomeryAlertRulesResponse:
    rows = list_alert_rules_admin(current_user)
    return PlynomeryAlertRulesResponse(total=len(rows), rows=rows)


@router.post(
    "/alert-rules",
    response_model=PlynomeryAlertRuleRow,
    status_code=status.HTTP_201_CREATED,
    summary="Create alert rule",
    description="Vytvoří nové alert pravidlo pro plynoměry. "
    "Vyžaduje admin oprávnění.",
)
def create_plynomery_alert_rule(
    payload: PlynomeryAlertRuleUpsertRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> PlynomeryAlertRuleRow:
    try:
        row = create_alert_rule_admin(
            current_user,
            rule_name=payload.rule_name,
            recipient_email=payload.recipient_email,
            identifikace=payload.identifikace,
            event_type=payload.event_type,
            severity_min=payload.severity_min,
            min_duration_minutes=payload.min_duration_minutes,
            send_on=payload.send_on,
            enabled=payload.enabled,
            note=payload.note,
        )
    except PlynomeryAdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return PlynomeryAlertRuleRow(**row)


@router.patch(
    "/alert-rules/{rule_id}",
    response_model=PlynomeryAlertRuleRow,
    summary="Update alert rule",
    description="Aktualizuje existující alert pravidlo pro plynoměry. "
    "Vyžaduje admin oprávnění.",
)
def update_plynomery_alert_rule(
    rule_id: int,
    payload: PlynomeryAlertRuleUpsertRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> PlynomeryAlertRuleRow:
    try:
        row = update_alert_rule_admin(
            current_user,
            rule_id=rule_id,
            rule_name=payload.rule_name,
            recipient_email=payload.recipient_email,
            identifikace=payload.identifikace,
            event_type=payload.event_type,
            severity_min=payload.severity_min,
            min_duration_minutes=payload.min_duration_minutes,
            send_on=payload.send_on,
            enabled=payload.enabled,
            note=payload.note,
        )
    except (PlynomeryAdminOperationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return PlynomeryAlertRuleRow(**row)


@router.delete(
    "/alert-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete alert rule",
    description="Smaže alert pravidlo pro plynoměry. "
    "Vyžaduje admin oprávnění.",
)
def delete_plynomery_alert_rule(
    rule_id: int,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> Response:
    delete_alert_rule_admin(current_user, rule_id=rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
