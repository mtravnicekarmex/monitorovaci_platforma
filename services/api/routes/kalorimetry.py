from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.api.core.dependencies import (
    get_current_admin_user,
    get_current_kalorimetry_user,
)
from services.api.schemas.kalorimetry import (
    KalorimetryDeviceListResponse,
    KalorimetryMeasurementSeriesResponse,
    KalorimetryOutlierReviewListResponse,
    KalorimetryOutlierReviewRow,
    KalorimetryOutlierReviewUpdateRequest,
    KalorimetryPredictionProfilesResponse,
    KalorimetryPredictionSeriesResponse,
)
from services.api.services.dashboard_auth import (
    AuthorizationError,
    DashboardUserContext,
)
from services.api.services.kalorimetry import (
    load_measurement_series,
    load_prediction_profiles,
    load_prediction_series,
)
from services.api.services.kalorimetry_admin import (
    KalorimetryAdminOperationError,
    list_devices_admin,
    list_outlier_reviews_admin,
    update_outlier_review_admin,
)


router = APIRouter(prefix="/api/v1/kalorimetry", tags=["kalorimetry"])


@router.get(
    "/measurement-series",
    response_model=KalorimetryMeasurementSeriesResponse,
    summary="Get kalorimetry measurement series",
)
def get_kalorimetry_measurement_series(
    identifikace: str,
    start_date: date,
    end_date: date,
    current_user: DashboardUserContext = Depends(
        get_current_kalorimetry_user
    ),
) -> KalorimetryMeasurementSeriesResponse:
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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return KalorimetryMeasurementSeriesResponse(
        identifikace=identifikace,
        start_date=start_date,
        end_date=end_date,
        total=len(rows),
        rows=rows,
    )


@router.get(
    "/prediction-profiles",
    response_model=KalorimetryPredictionProfilesResponse,
    summary="Get period-valid kalorimetry prediction profiles",
)
def get_kalorimetry_prediction_profiles(
    identifikace: str,
    start_date: date | None = None,
    end_date: date | None = None,
    current_user: DashboardUserContext = Depends(
        get_current_kalorimetry_user
    ),
) -> KalorimetryPredictionProfilesResponse:
    try:
        result = load_prediction_profiles(
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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return KalorimetryPredictionProfilesResponse(
        **{**result, "identifikace": identifikace},
        total=len(result["rows"]),
    )


@router.get(
    "/prediction-series",
    response_model=KalorimetryPredictionSeriesResponse,
    summary="Get period-valid kalorimetry prediction series",
)
def get_kalorimetry_prediction_series(
    identifikace: str,
    start_date: date,
    end_date: date,
    granularity: str = Query(pattern="^(hourly|daily|monthly)$"),
    current_user: DashboardUserContext = Depends(
        get_current_kalorimetry_user
    ),
) -> KalorimetryPredictionSeriesResponse:
    try:
        result = load_prediction_series(
            current_user,
            identifikace=identifikace,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
        )
    except AuthorizationError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return KalorimetryPredictionSeriesResponse(
        **{**result, "identifikace": identifikace},
        total=len(result["rows"]),
    )


@router.get(
    "/devices",
    response_model=KalorimetryDeviceListResponse,
    summary="List kalorimetry devices",
    description="Vraci seznam kalorimetru pro admin review outlieru.",
)
def get_kalorimetry_devices(
    limit: int = Query(default=5000, ge=1, le=5000),
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> KalorimetryDeviceListResponse:
    devices = list_devices_admin(current_user, limit=limit)
    return KalorimetryDeviceListResponse(
        total=len(devices),
        devices=devices,
    )


@router.get(
    "/outlier-reviews",
    response_model=KalorimetryOutlierReviewListResponse,
    summary="Get kalorimetry outlier reviews",
    description="Vraci seznam kalorimetrickych outlieru k manualnimu prezkoumani. Vyuziva admin opravneni.",
)
def get_kalorimetry_outlier_reviews(
    review_status: str | None = Query(default="PENDING"),
    identifikace: str | None = Query(default=None),
    source: str = Query(default="VSE"),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> KalorimetryOutlierReviewListResponse:
    try:
        rows = list_outlier_reviews_admin(
            current_user,
            review_status=review_status,
            identifikace=identifikace,
            source_filter=source,
            limit=limit,
        )
    except KalorimetryAdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return KalorimetryOutlierReviewListResponse(total=len(rows), rows=rows)


@router.patch(
    "/outlier-reviews/{review_id}",
    response_model=KalorimetryOutlierReviewRow,
    summary="Update kalorimetry outlier review",
    description="Aktualizuje status kalorimetrickeho outlier review a poznamku. Vyuziva admin opravneni.",
)
def patch_kalorimetry_outlier_review(
    review_id: int,
    payload: KalorimetryOutlierReviewUpdateRequest,
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> KalorimetryOutlierReviewRow:
    try:
        row = update_outlier_review_admin(
            current_user,
            review_id=review_id,
            review_status=payload.review_status,
            review_note=payload.review_note,
        )
    except KalorimetryAdminOperationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return KalorimetryOutlierReviewRow(**row)
