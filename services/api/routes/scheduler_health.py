from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends

from core.scheduler.job_schedule import build_schedule_runs
from core.scheduler.metrics import get_metrics_store
from services.api.core.dependencies import get_current_admin_user
from services.api.schemas.admin import (
    SchedulerHealthResponse,
    SchedulerJobHealth,
    SchedulerScheduledRun,
)
from services.api.services.dashboard_auth import DashboardUserContext


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/scheduler", response_model=SchedulerHealthResponse)
def get_scheduler_health(
    current_user: DashboardUserContext = Depends(get_current_admin_user),
) -> SchedulerHealthResponse:
    del current_user

    metrics = get_metrics_store(refresh_from_disk=True)
    scheduler_running = metrics.is_scheduler_running()

    jobs = [
        SchedulerJobHealth(
            id=job_id,
            last_run=job_metrics.last_run,
            last_status=job_metrics.last_status,
            last_duration_seconds=job_metrics.last_duration_seconds,
            next_run=job_metrics.next_run,
            failure_rate_24h=metrics.get_failure_rate(job_id),
            avg_duration_24h=metrics.get_avg_duration(job_id),
        )
        for job_id, job_metrics in sorted(metrics.jobs.items())
    ]
    schedule = [
        SchedulerScheduledRun(
            job_id=run.job_id,
            job_label=run.job_label,
            description=run.description,
            scheduled_at=run.scheduled_at,
        )
        for run in build_schedule_runs(hours=24)
    ]

    total_failures = sum(job.failure_count_24h for job in metrics.jobs.values())
    total_runs = sum(
        job.success_count_24h + job.failure_count_24h for job in metrics.jobs.values()
    )

    if not scheduler_running:
        overall_status = "error"
    elif total_runs > 0 and total_failures > total_runs * 0.1:
        overall_status = "degraded"
    else:
        overall_status = "ok"

    return SchedulerHealthResponse(
        status=overall_status,
        scheduler_running=scheduler_running,
        jobs=jobs,
        schedule=schedule,
        checked_at=datetime.now(),
    )
