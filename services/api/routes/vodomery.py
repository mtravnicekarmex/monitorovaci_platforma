from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from services.api.core.dependencies import get_current_admin_user, get_current_vodomery_user
from services.api.schemas.vodomery import (
    VodomeryAlertRuleRow,
    VodomeryAlertRulesResponse,
    VodomeryAlertRuleUpsertRequest,
    VodomeryBillingOptionsResponse,
    VodomeryBillingPeriodResponse,
    VodomeryBranchOverviewResponse,
    VodomeryDeviceDetailResponse,
    VodomeryDeviceListResponse,
    VodomeryEventHistoryResponse,
    VodomeryExpectedZeroListResponse,
    VodomeryExpectedZeroUpdateRequest,
    VodomeryMeasurementSeriesResponse,
    VodomeryOpenEventsResponse,
    VodomeryOutlierReviewListResponse,
    VodomeryOutlierReviewRow,
    VodomeryOutlierReviewUpdateRequest,
    VodomeryOverviewMetricsResponse,
    VodomeryPredictionProfilesResponse,
    VodomeryRecentAnomaliesResponse,
    VodomeryResolvedEventsResponse,
)
from services.api.services.dashboard_auth import AuthorizationError, DashboardUserContext
from services.api.services.vodomery_admin import (
    VodomeryAdminOperationError,
    create_alert_rule_admin,
    delete_alert_rule_admin,
    list_alert_rules_admin,
    list_expected_zero_devices_admin,
    list_outlier_reviews_admin,
    replace_expected_zero_devices_admin,
    update_outlier_review_admin,
    update_alert_rule_admin,
)
from services.api.services.vodomery import (
    list_branch_billing_options,
    list_accessible_devices,
    load_all_open_events,
    load_branch_billing_period,
    load_branch_day_overview,
    load_device_detail,
    load_event_history,
    load_measurement_series,
    load_overview_metrics,
    load_prediction_profiles,
    load_recent_anomalies,
    load_recent_resolved_events,
)


router = APIRouter(prefix="/api/v1/vodomery", tags=["vodomery"])


@router.get(
    "/devices",
    response_model=VodomeryDeviceListResponse,
    summary="List vodoměry devices",
    description="Vrací seznam vodoměrů dostupných pro přihlášeného uživatele. "
    "Filtrace dle source (VSE = všechny, SCVK, AREAL). "
    "Oprávnění omezena dle konfigurace uživatele.",
)
def get_vodomery_devices(
    source: str = Query(default="VSE"),
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryDeviceListResponse:
    try:
        devices = list_accessible_devices(current_user, source_filter=source, limit=limit)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return VodomeryDeviceListResponse(
        source_filter=source.upper(),
        total=len(devices),
        devices=devices,
    )


@router.get(
    "/billing-options",
    response_model=VodomeryBillingOptionsResponse,
    summary="List billing branches",
    description="Vrací seznam fakturačních vodoměrů a větví dostupných pro fakturaci. "
    "Vyžaduje admin oprávnění.",
)
def get_vodomery_billing_options(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> VodomeryBillingOptionsResponse:
    rows = list_branch_billing_options(current_user)
    return VodomeryBillingOptionsResponse(total=len(rows), rows=rows)


@router.get(
    "/overview-metrics",
    response_model=VodomeryOverviewMetricsResponse,
    summary="Get vodoměry overview metrics",
    description="Vrací přehledové metriky spotřeby vody za zvolené období: "
    "celková spotřeba, počet měřidel, průměrná spotřeba, detekované anomálie. "
    "Oprávnění omezena dle konfigurace uživatele.",
)
def get_vodomery_overview_metrics(
    start_date: date,
    end_date: date,
    source: str = Query(default="VSE"),
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryOverviewMetricsResponse:
    try:
        metrics = load_overview_metrics(
            current_user,
            source_filter=source,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return VodomeryOverviewMetricsResponse(
        source_filter=source.upper(),
        start_date=start_date,
        end_date=end_date,
        **metrics,
    )


@router.get(
    "/measurement-series",
    response_model=VodomeryMeasurementSeriesResponse,
    summary="Get measurement series",
    description="Vrací časovou řadu měření pro vybraný vodoměr. "
    "Obsahuje: datum, spotřeba, predikovaná hodnota, anomaly score. "
    "Oprávnění omezena dle konfigurace uživatele.",
)
def get_vodomery_measurement_series(
    identifikace: str,
    start_date: date,
    end_date: date,
    source: str = Query(default="VSE"),
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryMeasurementSeriesResponse:
    try:
        rows = load_measurement_series(
            current_user,
            source_filter=source,
            identifikace=identifikace,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return VodomeryMeasurementSeriesResponse(
        source_filter=source.upper(),
        identifikace=identifikace,
        start_date=start_date,
        end_date=end_date,
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/prediction-profiles",
    response_model=VodomeryPredictionProfilesResponse,
    summary="Get prediction profiles",
    description="Vrací predikční profily pro vybraný vodoměr. "
    "Obsahuje: den v týdnu, hodina, průměrná spotřeba, rozptyl. "
    "Používá se pro predikci a detekci anomálií.",
)
def get_vodomery_prediction_profiles(
    identifikace: str,
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryPredictionProfilesResponse:
    try:
        rows = load_prediction_profiles(
            current_user,
            identifikace=identifikace,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return VodomeryPredictionProfilesResponse(
        identifikace=identifikace,
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/recent-anomalies",
    response_model=VodomeryRecentAnomaliesResponse,
    summary="Get recent anomalies",
    description="Vrací seznam nedávných anomálií (outlierů) za zvolené období. "
    "Anomálie jsou detekovány pomocí ML modelu na základě odchylky od predikované spotřeby.",
)
def get_vodomery_recent_anomalies(
    start_date: date,
    end_date: date,
    identifikace: str | None = None,
    source: str = Query(default="VSE"),
    limit: int = Query(default=50, ge=1, le=1000),
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryRecentAnomaliesResponse:
    try:
        rows = load_recent_anomalies(
            current_user,
            source_filter=source,
            identifikace=identifikace,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return VodomeryRecentAnomaliesResponse(
        source_filter=source.upper(),
        identifikace=identifikace,
        start_date=start_date,
        end_date=end_date,
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/open-events",
    response_model=VodomeryOpenEventsResponse,
    summary="Get open events",
    description="Vrací seznam otevřených eventů (aktivních anomálií). "
    "Event je aktivní když anomálie trvá déle než nastavený práh.",
)
def get_vodomery_open_events(
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryOpenEventsResponse:
    rows = load_all_open_events(
        current_user,
        limit=limit,
    )
    return VodomeryOpenEventsResponse(
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/resolved-events",
    response_model=VodomeryResolvedEventsResponse,
    summary="Get resolved events",
    description="Vrací seznam vyřešených eventů za zvolené období. "
    "Event je vyřešen když spotřeba opět klesne pod práh anomálie.",
)
def get_vodomery_resolved_events(
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryResolvedEventsResponse:
    rows = load_recent_resolved_events(
        current_user,
        days=days,
        limit=limit,
    )
    return VodomeryResolvedEventsResponse(
        days=days,
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/event-history",
    response_model=VodomeryEventHistoryResponse,
    summary="Get event history for device",
    description="Vrací historii eventů pro vybraný vodoměr. "
    "Obsahuje: začátek, konec, typ, závažnost, notifikace.",
)
def get_vodomery_event_history(
    identifikace: str,
    limit: int = Query(default=20, ge=1, le=500),
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryEventHistoryResponse:
    try:
        rows = load_event_history(
            current_user,
            identifikace=identifikace,
            limit=limit,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return VodomeryEventHistoryResponse(
        identifikace=identifikace,
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/device-detail",
    response_model=VodomeryDeviceDetailResponse,
    summary="Get device detail",
    description="Vrací detailní informace o vybraném vodoměru: "
    "sériové číslo, pozice, objekt, poslední měření, aktivní alarmy.",
)
def get_vodomery_device_detail(
    identifikace: str,
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryDeviceDetailResponse:
    try:
        device = load_device_detail(
            current_user,
            identifikace=identifikace,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return VodomeryDeviceDetailResponse(
        identifikace=identifikace,
        found=device is not None,
        device=device,
    )


@router.get(
    "/branch-day-overview",
    response_model=VodomeryBranchOverviewResponse,
    summary="Get branch day overview",
    description="Vrací přehled spotřeby vody po větvích pro vybraný den. "
    "Užitečné pro sledování distribuce spotřeby v objektech.",
)
def get_vodomery_branch_day_overview(
    target_date: date,
    current_user: DashboardUserContext = Depends(get_current_vodomery_user),
) -> VodomeryBranchOverviewResponse:
    rows = load_branch_day_overview(
        current_user,
        target_date=target_date,
    )
    return VodomeryBranchOverviewResponse(
        target_date=target_date,
        total=len(rows),
        branches=rows,
    )


@router.get(
    "/billing-period",
    response_model=VodomeryBillingPeriodResponse,
    summary="Get billing allocation period",
    description="Vrací rozpočítání spotřeby fakturačního vodoměru na podružné vodoměry "
    "pro zadané období včetně přehledu aktivních přiřazení z historie větví. "
    "Vyžaduje admin oprávnění.",
)
def get_vodomery_billing_period(
    billing_ident: str,
    start_date: date,
    end_date: date,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> VodomeryBillingPeriodResponse:
    try:
        payload = load_branch_billing_period(
            current_user,
            billing_ident=billing_ident,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return VodomeryBillingPeriodResponse(**payload)


@router.get(
    "/outlier-reviews",
    response_model=VodomeryOutlierReviewListResponse,
    summary="Get outlier reviews",
    description="Vrací seznam outlierů k manuálnímu přezkoumání. "
    "Umožňuje adminovi označit outlier jako reálný ( únik ) nebo false positive. "
    "Vyžaduje admin oprávnění.",
)
def get_vodomery_outlier_reviews(
    review_status: str | None = Query(default="PENDING"),
    identifikace: str | None = Query(default=None),
    source: str = Query(default="VSE"),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> VodomeryOutlierReviewListResponse:
    try:
        rows = list_outlier_reviews_admin(
            current_user,
            review_status=review_status,
            identifikace=identifikace,
            source_filter=source,
            limit=limit,
        )
    except VodomeryAdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return VodomeryOutlierReviewListResponse(total=len(rows), rows=rows)


@router.patch(
    "/outlier-reviews/{review_id}",
    response_model=VodomeryOutlierReviewRow,
    summary="Update outlier review",
    description="Aktualizuje status outlier review (APPROVED/REJECTED) a poznámku. "
    "Vyžaduje admin oprávnění.",
)
def patch_vodomery_outlier_review(
    review_id: int,
    payload: VodomeryOutlierReviewUpdateRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> VodomeryOutlierReviewRow:
    try:
        row = update_outlier_review_admin(
            current_user,
            review_id=review_id,
            review_status=payload.review_status,
            review_note=payload.review_note,
        )
    except VodomeryAdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return VodomeryOutlierReviewRow(**row)


@router.get(
    "/expected-zero",
    response_model=VodomeryExpectedZeroListResponse,
    summary="Get expected zero devices",
    description="Vrací seznam vodoměrů s očekáváním nulové spotřeby. "
    "Tyto vodoměry jsou vyloučeny z detekce anomálií. "
    "Vyžaduje admin oprávnění.",
)
def get_vodomery_expected_zero(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> VodomeryExpectedZeroListResponse:
    rows = list_expected_zero_devices_admin(current_user)
    return VodomeryExpectedZeroListResponse(total=len(rows), rows=rows)


@router.put(
    "/expected-zero",
    response_model=VodomeryExpectedZeroListResponse,
    summary="Update expected zero devices",
    description="Nahradí seznam vodoměrů s očekáváním nulové spotřeby. "
    "Vyžaduje admin oprávnění.",
)
def update_vodomery_expected_zero(
    payload: VodomeryExpectedZeroUpdateRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> VodomeryExpectedZeroListResponse:
    rows = replace_expected_zero_devices_admin(
        current_user,
        identifikace_list=payload.identifikace_list,
    )
    return VodomeryExpectedZeroListResponse(total=len(rows), rows=rows)


@router.get(
    "/alert-rules",
    response_model=VodomeryAlertRulesResponse,
    summary="Get alert rules",
    description="Vrací seznam konfigurovaných alert pravidel pro vodoměry. "
    "Alert pravidla definují kdy a komu se zasílají upozornění na eventy. "
    "Vyžaduje admin oprávnění.",
)
def get_vodomery_alert_rules(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> VodomeryAlertRulesResponse:
    rows = list_alert_rules_admin(current_user)
    return VodomeryAlertRulesResponse(total=len(rows), rows=rows)


@router.post(
    "/alert-rules",
    response_model=VodomeryAlertRuleRow,
    status_code=status.HTTP_201_CREATED,
    summary="Create alert rule",
    description="Vytvoří nové alert pravidlo pro vodoměry. "
    "Definuje: filtr zařízení, typ eventu, minimální závažnost, dobu trvání, příjemce. "
    "Vyžaduje admin oprávnění.",
)
def create_vodomery_alert_rule(
    payload: VodomeryAlertRuleUpsertRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> VodomeryAlertRuleRow:
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
    except VodomeryAdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return VodomeryAlertRuleRow(**row)


@router.patch(
    "/alert-rules/{rule_id}",
    response_model=VodomeryAlertRuleRow,
    summary="Update alert rule",
    description="Aktualizuje existující alert pravidlo. "
    "Vyžaduje admin oprávnění.",
)
def update_vodomery_alert_rule(
    rule_id: int,
    payload: VodomeryAlertRuleUpsertRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> VodomeryAlertRuleRow:
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
    except (VodomeryAdminOperationError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return VodomeryAlertRuleRow(**row)


@router.delete(
    "/alert-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete alert rule",
    description="Smaže alert pravidlo. "
    "Vyžaduje admin oprávnění.",
)
def delete_vodomery_alert_rule(
    rule_id: int,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> Response:
    delete_alert_rule_admin(current_user, rule_id=rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
