from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from services.api.core.monitoring_auth import require_monitoring_agent
from services.api.core.runtime_state import api_readiness
from services.api.schemas.monitoring import (
    MonitoringDatabaseAvailabilityLocalAgentResponse,
    MonitoringSchedulerHealthResponse,
    MonitoringSchedulerMetricsLocalAgentResponse,
    MonitoringSystemDatabaseHealthResponse,
    MonitoringSystemProxyHealthResponse,
    MonitoringSystemRuntimeHealthResponse,
    MonitoringSystemSchedulerHealthResponse,
    MonitoringSystemSmartFuelPassHealthResponse,
)
from services.api.services.monitoring_facade import (
    project_database_availability_local_agent,
    project_scheduler_health,
    project_scheduler_metrics_local_agent,
    project_system_database_health,
    project_system_proxy_health,
    project_system_runtime_health,
    project_system_scheduler_health,
    project_system_smartfuelpass_health,
)
from services.api.services.scheduler_health import collect_scheduler_health
from services.api.services.system_health import (
    collect_system_database_health,
    collect_system_proxy_health,
    collect_system_runtime_health,
    collect_system_scheduler_health,
    collect_system_smartfuelpass_health,
)
from local_monitoring_agents.database_availability import (
    load_database_availability_local_agent_facade_snapshot,
)
from local_monitoring_agents.scheduler_metrics import (
    load_scheduler_metrics_local_agent_facade_snapshot,
)


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
    response_model=MonitoringSystemSchedulerHealthResponse,
    summary="Monitoring facade scheduler health",
)
def get_monitoring_scheduler_health() -> MonitoringSystemSchedulerHealthResponse:
    return project_system_scheduler_health(collect_system_scheduler_health())


@router.get(
    "/scheduler",
    response_model=MonitoringSchedulerHealthResponse,
    summary="Monitoring facade detailed scheduler health",
)
def get_monitoring_detailed_scheduler_health() -> MonitoringSchedulerHealthResponse:
    return project_scheduler_health(collect_scheduler_health())


@router.get(
    "/system/runtime",
    response_model=MonitoringSystemRuntimeHealthResponse,
    summary="Monitoring facade system runtime health",
)
def get_monitoring_runtime_health() -> MonitoringSystemRuntimeHealthResponse:
    return project_system_runtime_health(collect_system_runtime_health())


@router.get(
    "/system/database",
    response_model=MonitoringSystemDatabaseHealthResponse,
    summary="Monitoring facade system database health",
)
def get_monitoring_database_health() -> MonitoringSystemDatabaseHealthResponse:
    return project_system_database_health(collect_system_database_health())


@router.get(
    "/system/proxy",
    response_model=MonitoringSystemProxyHealthResponse,
    summary="Monitoring facade system proxy health",
)
def get_monitoring_proxy_health() -> MonitoringSystemProxyHealthResponse:
    return project_system_proxy_health(collect_system_proxy_health())


@router.get(
    "/system/smartfuelpass",
    response_model=MonitoringSystemSmartFuelPassHealthResponse,
    summary="Monitoring facade SmartFuelPass health",
)
def get_monitoring_smartfuelpass_health(
) -> MonitoringSystemSmartFuelPassHealthResponse:
    return project_system_smartfuelpass_health(
        collect_system_smartfuelpass_health()
    )


@router.get(
    "/local-agents/database-availability",
    response_model=MonitoringDatabaseAvailabilityLocalAgentResponse,
    summary="Monitoring facade local database availability agent aggregate",
)
def get_monitoring_database_availability_local_agent(
) -> MonitoringDatabaseAvailabilityLocalAgentResponse:
    return project_database_availability_local_agent(
        load_database_availability_local_agent_facade_snapshot()
    )


@router.get(
    "/local-agents/scheduler-metrics",
    response_model=MonitoringSchedulerMetricsLocalAgentResponse,
    summary="Monitoring facade local scheduler metrics agent aggregate",
)
def get_monitoring_scheduler_metrics_local_agent(
) -> MonitoringSchedulerMetricsLocalAgentResponse:
    return project_scheduler_metrics_local_agent(
        load_scheduler_metrics_local_agent_facade_snapshot()
    )
