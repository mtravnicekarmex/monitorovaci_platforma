from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.api.core.dependencies import get_current_manometry_user
from services.api.schemas.manometry import (
    ManometryDeviceDetailResponse,
    ManometryDeviceListResponse,
    ManometryMeasurementSeriesResponse,
)
from services.api.services.dashboard_auth import AuthorizationError, DashboardUserContext
from services.api.services.manometry import (
    list_accessible_devices,
    load_device_detail,
    load_measurement_series,
)


router = APIRouter(prefix="/api/v1/manometry", tags=["manometry"])


@router.get(
    "/devices",
    response_model=ManometryDeviceListResponse,
    summary="List manometry devices",
    description="Vrací seznam manometrů dostupných pro přihlášeného uživatele.",
)
def get_manometry_devices(
    limit: int = Query(default=500, ge=1, le=5000),
    current_user: DashboardUserContext = Depends(get_current_manometry_user),
) -> ManometryDeviceListResponse:
    devices = list_accessible_devices(current_user, limit=limit)
    return ManometryDeviceListResponse(total=len(devices), devices=devices)


@router.get(
    "/measurement-series",
    response_model=ManometryMeasurementSeriesResponse,
    summary="Get manometry measurement series",
    description="Vrací časovou řadu měření pro vybraný manometr.",
)
def get_manometry_measurement_series(
    identifikace: str,
    start_date: date,
    end_date: date,
    current_user: DashboardUserContext = Depends(get_current_manometry_user),
) -> ManometryMeasurementSeriesResponse:
    try:
        rows = load_measurement_series(
            current_user,
            identifikace=identifikace,
            start_date=start_date,
            end_date=end_date,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    return ManometryMeasurementSeriesResponse(
        identifikace=identifikace,
        start_date=start_date,
        end_date=end_date,
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/device-detail",
    response_model=ManometryDeviceDetailResponse,
    summary="Get manometry device detail",
    description="Vrací metadata a souhrnné statistiky vybraného manometru.",
)
def get_manometry_device_detail(
    identifikace: str,
    current_user: DashboardUserContext = Depends(get_current_manometry_user),
) -> ManometryDeviceDetailResponse:
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

    return ManometryDeviceDetailResponse(
        identifikace=identifikace,
        found=device is not None,
        device=device,
    )
