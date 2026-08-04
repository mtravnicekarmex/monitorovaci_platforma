from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from services.api.core.monitoring_auth import require_monitoring_agent
from services.api.core.runtime_state import api_readiness
from services.api.schemas.admin import SystemSchedulerHealthResponse
from services.api.services.system_health import collect_system_scheduler_health


router = APIRouter(
    prefix="/api/v1/monitoring/health",
    tags=["monitoring"],
    dependencies=[Depends(require_monitoring_agent)],
)


@router.get("/live", summary="Monitoring facade liveness")
def get_monitoring_liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Monitoring facade readiness")
def get_monitoring_readiness(response: Response) -> dict[str, str]:
    if not api_readiness.is_ready():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ready"}


@router.get(
    "/system/scheduler",
    response_model=SystemSchedulerHealthResponse,
    summary="Monitoring facade scheduler health",
)
def get_monitoring_scheduler_health() -> SystemSchedulerHealthResponse:
    return collect_system_scheduler_health()
