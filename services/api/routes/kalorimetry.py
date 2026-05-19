from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.kalorimetry import (
    KalorimetryDeviceListResponse,
    KalorimetryOutlierReviewListResponse,
    KalorimetryOutlierReviewRow,
    KalorimetryOutlierReviewUpdateRequest,
)
from services.api.services.dashboard_auth import DashboardUserContext
from services.api.services.kalorimetry_admin import (
    KalorimetryAdminOperationError,
    list_devices_admin,
    list_outlier_reviews_admin,
    update_outlier_review_admin,
)


router = APIRouter(prefix="/api/v1/kalorimetry", tags=["kalorimetry"])


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
