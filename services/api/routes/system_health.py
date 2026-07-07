from __future__ import annotations

from fastapi import APIRouter, Depends

from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.admin import SystemRuntimeHealthResponse
from services.api.services.dashboard_auth import DashboardUserContext
from services.api.services.system_health import collect_system_runtime_health


router = APIRouter(prefix="/health/system", tags=["health"])


@router.get(
    "/runtime",
    response_model=SystemRuntimeHealthResponse,
    summary="System runtime health",
    description=(
        "Vraci bezpecny admin prehled porestartoveho runtime stavu: boot time, "
        "startup scheduled task, ocekavane listenery a docasne porty."
    ),
)
def get_system_runtime_health(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> SystemRuntimeHealthResponse:
    del current_user
    return collect_system_runtime_health()
