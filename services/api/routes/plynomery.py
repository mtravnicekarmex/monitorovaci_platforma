from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from services.api.core.dependencies import get_current_admin_user, get_current_plynomery_user
from services.api.schemas.plynomery import (
    PlynomeryAlertRuleRow,
    PlynomeryAlertRulesResponse,
    PlynomeryAlertRuleUpsertRequest,
    PlynomeryDeviceListResponse,
    PlynomeryExpectedZeroListResponse,
    PlynomeryExpectedZeroUpdateRequest,
    PlynomeryOpenEventsResponse,
    PlynomeryRecentAnomaliesResponse,
    PlynomeryResolvedEventsResponse,
)
from services.api.services.dashboard_auth import DashboardUserContext
from services.api.services.dashboard_auth import AuthorizationError
from services.api.services.plynomery import (
    list_accessible_devices,
    load_all_open_events,
    load_recent_anomalies,
    load_recent_resolved_events,
)
from services.api.services.plynomery_admin import (
    PlynomeryAdminOperationError,
    create_alert_rule_admin,
    delete_alert_rule_admin,
    list_alert_rules_admin,
    list_expected_zero_devices_admin,
    replace_expected_zero_devices_admin,
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
    "/recent-anomalies",
    response_model=PlynomeryRecentAnomaliesResponse,
    summary="Get recent anomalies",
    description="Vrací seznam nedávných plynoměrových anomálií za zvolené období.",
)
def get_plynomery_recent_anomalies(
    start_date: date,
    end_date: date,
    identifikace: str | None = None,
    limit: int = Query(default=50, ge=1, le=1000),
    current_user: DashboardUserContext = Depends(get_current_plynomery_user),
) -> PlynomeryRecentAnomaliesResponse:
    try:
        rows = load_recent_anomalies(
            current_user,
            identifikace=identifikace,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return PlynomeryRecentAnomaliesResponse(
        identifikace=identifikace,
        start_date=start_date,
        end_date=end_date,
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/open-events",
    response_model=PlynomeryOpenEventsResponse,
    summary="Get open events",
    description="Vrací seznam otevřených plynoměrových eventů.",
)
def get_plynomery_open_events(
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: DashboardUserContext = Depends(get_current_plynomery_user),
) -> PlynomeryOpenEventsResponse:
    rows = load_all_open_events(
        current_user,
        limit=limit,
    )
    return PlynomeryOpenEventsResponse(
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/resolved-events",
    response_model=PlynomeryResolvedEventsResponse,
    summary="Get resolved events",
    description="Vrací seznam uzavřených plynoměrových eventů za zvolené období.",
)
def get_plynomery_resolved_events(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: DashboardUserContext = Depends(get_current_plynomery_user),
) -> PlynomeryResolvedEventsResponse:
    rows = load_recent_resolved_events(
        current_user,
        days=days,
        limit=limit,
    )
    return PlynomeryResolvedEventsResponse(
        days=days,
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/expected-zero",
    response_model=PlynomeryExpectedZeroListResponse,
    summary="Get expected zero devices",
    description="Vraci seznam plynomeru s ocekavanim nulove spotreby. "
    "Vyuziva se pro event EXPECTED_ZERO_USAGE. "
    "Vyžaduje admin oprávnění.",
)
def get_plynomery_expected_zero(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> PlynomeryExpectedZeroListResponse:
    rows = list_expected_zero_devices_admin(current_user)
    return PlynomeryExpectedZeroListResponse(total=len(rows), rows=rows)


@router.put(
    "/expected-zero",
    response_model=PlynomeryExpectedZeroListResponse,
    summary="Update expected zero devices",
    description="Nahradi seznam plynomeru s ocekavanim nulove spotreby. "
    "Vyuziva se pro event EXPECTED_ZERO_USAGE. "
    "Vyžaduje admin oprávnění.",
)
def update_plynomery_expected_zero(
    payload: PlynomeryExpectedZeroUpdateRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> PlynomeryExpectedZeroListResponse:
    rows = replace_expected_zero_devices_admin(
        current_user,
        identifikace_list=payload.identifikace_list,
    )
    return PlynomeryExpectedZeroListResponse(total=len(rows), rows=rows)


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
