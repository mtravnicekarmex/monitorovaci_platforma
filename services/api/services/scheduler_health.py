from __future__ import annotations

from datetime import datetime

from core.scheduler.job_schedule import build_schedule_runs, get_scheduler_job_specs
from core.scheduler.metrics import JobMetrics, get_metrics_store
from core.scheduler.scheduler import get_manual_run_specs
from services.api.schemas.admin import (
    SchedulerHealthResponse,
    SchedulerJobHealth,
    SchedulerScheduledRun,
)


def collect_scheduler_health() -> SchedulerHealthResponse:
    metrics = get_metrics_store(refresh_from_disk=True)
    scheduler_running = metrics.is_scheduler_running()
    job_specs_by_id = {job_spec.id: job_spec for job_spec in get_scheduler_job_specs()}
    manual_run_specs_by_id = get_manual_run_specs()
    all_job_ids = sorted(
        set(metrics.jobs) | set(job_specs_by_id) | set(manual_run_specs_by_id)
    )

    jobs = [
        SchedulerJobHealth(
            id=job_id,
            label=(
                job_specs_by_id[job_id].label
                if job_specs_by_id.get(job_id) is not None
                else (
                    None
                    if manual_run_specs_by_id.get(job_id) is None
                    else manual_run_specs_by_id[job_id].label
                )
            ),
            description=(
                job_specs_by_id[job_id].description
                if job_specs_by_id.get(job_id) is not None
                else (
                    None
                    if manual_run_specs_by_id.get(job_id) is None
                    else manual_run_specs_by_id[job_id].description
                )
            ),
            is_scheduled=job_id in job_specs_by_id,
            is_manual_runnable=job_id in manual_run_specs_by_id,
            last_run=(metrics.jobs.get(job_id) or JobMetrics()).last_run,
            last_status=(metrics.jobs.get(job_id) or JobMetrics()).last_status,
            last_duration_seconds=(
                metrics.jobs.get(job_id) or JobMetrics()
            ).last_duration_seconds,
            next_run=(metrics.jobs.get(job_id) or JobMetrics()).next_run,
            failure_rate_24h=(
                metrics.get_failure_rate(job_id) if job_id in metrics.jobs else 0.0
            ),
            avg_duration_24h=(
                metrics.get_avg_duration(job_id) if job_id in metrics.jobs else None
            ),
        )
        for job_id in all_job_ids
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
        job.success_count_24h + job.failure_count_24h
        for job in metrics.jobs.values()
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
        checked_at=datetime.now().astimezone(),
    )
