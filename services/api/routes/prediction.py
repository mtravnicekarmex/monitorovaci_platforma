from __future__ import annotations

from fastapi import APIRouter, Depends

from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.prediction import PredictionPerformanceResponse
from services.api.services.dashboard_auth import DashboardUserContext
from services.api.services.prediction_performance import collect_prediction_performance_report


router = APIRouter(prefix="/api/v1/prediction", tags=["prediction"])


@router.get(
    "/performance",
    response_model=PredictionPerformanceResponse,
    summary="Prediction model performance",
    description="Vraci admin-only souhrn kandidatu a per-identifier vyberu napric podporovanymi medii.",
)
def get_prediction_performance(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> PredictionPerformanceResponse:
    del current_user
    return collect_prediction_performance_report()
