from __future__ import annotations

from fastapi import APIRouter, Response, status

from services.api.core.runtime_state import api_readiness


router = APIRouter(tags=["health"])


@router.get(
    "/health/live",
    summary="Liveness check",
    description="Základní liveness test pro Kubernetes/load balancer. Vrací OK pokud aplikace běží.",
)
def health_live() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/health/ready",
    summary="Readiness check",
    description="Readiness test kontrolující připravenost aplikace přijímat provoz. Vrací OK pokud je aplikace plně inicializována.",
)
def health_ready(response: Response) -> dict[str, str]:
    if not api_readiness.is_ready():
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ready"}
