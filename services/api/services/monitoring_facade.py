from __future__ import annotations

from services.api.schemas.admin import (
    SchedulerHealthResponse,
    SystemDatabaseHealthResponse,
    SystemProxyHealthResponse,
    SystemRuntimeHealthResponse,
    SystemSchedulerHealthResponse,
    SystemSmartFuelPassHealthResponse,
)
from services.api.schemas.monitoring import (
    MonitoringPostgresSchemaStatus,
    MonitoringPostgresStatus,
    MonitoringProxyHeaderStatus,
    MonitoringProxyRouteStatus,
    MonitoringRuntimeBoot,
    MonitoringRuntimeListener,
    MonitoringRuntimeStartupTask,
    MonitoringScheduledRun,
    MonitoringSchedulerHealthResponse,
    MonitoringSchedulerJob,
    MonitoringSmartFuelPassJobStatus,
    MonitoringSmartFuelPassTableStatus,
    MonitoringSystemDatabaseHealthResponse,
    MonitoringSystemProxyHealthResponse,
    MonitoringSystemRuntimeHealthResponse,
    MonitoringSystemSchedulerHealthResponse,
    MonitoringSystemSchedulerJob,
    MonitoringSystemSmartFuelPassHealthResponse,
)


def project_scheduler_health(
    source: SchedulerHealthResponse,
) -> MonitoringSchedulerHealthResponse:
    return MonitoringSchedulerHealthResponse(
        status=source.status,
        scheduler_running=source.scheduler_running,
        jobs=[
            MonitoringSchedulerJob(
                id=job.id,
                is_scheduled=job.is_scheduled,
                last_run=job.last_run,
                last_status=job.last_status,
                last_duration_seconds=job.last_duration_seconds,
                next_run=job.next_run,
                failure_rate_24h=job.failure_rate_24h,
                avg_duration_24h=job.avg_duration_24h,
            )
            for job in source.jobs
        ],
        schedule=[
            MonitoringScheduledRun(
                job_id=scheduled_run.job_id,
                scheduled_at=scheduled_run.scheduled_at,
            )
            for scheduled_run in source.schedule
        ],
        checked_at=source.checked_at,
    )


def project_system_scheduler_health(
    source: SystemSchedulerHealthResponse,
) -> MonitoringSystemSchedulerHealthResponse:
    return MonitoringSystemSchedulerHealthResponse(
        status=source.status,
        checked_at=source.checked_at,
        scheduler_running=source.scheduler_running,
        last_heartbeat=source.last_heartbeat,
        heartbeat_age_seconds=source.heartbeat_age_seconds,
        heartbeat_ttl_seconds=source.heartbeat_ttl_seconds,
        total_success_count_24h=source.total_success_count_24h,
        total_failure_count_24h=source.total_failure_count_24h,
        jobs=[
            MonitoringSystemSchedulerJob(
                job_id=job.job_id,
                status=job.status,
                last_status=job.last_status,
                last_run=job.last_run,
                next_run=job.next_run,
                success_count_24h=job.success_count_24h,
                failure_count_24h=job.failure_count_24h,
                last_duration_seconds=job.last_duration_seconds,
            )
            for job in source.jobs
        ],
    )


def _project_runtime_listener(source) -> MonitoringRuntimeListener:
    return MonitoringRuntimeListener(
        key=source.key,
        status=source.status,
        expected=source.expected,
        present=source.present,
        local_port=source.local_port,
    )


def project_system_runtime_health(
    source: SystemRuntimeHealthResponse,
) -> MonitoringSystemRuntimeHealthResponse:
    return MonitoringSystemRuntimeHealthResponse(
        status=source.status,
        checked_at=source.checked_at,
        boot=MonitoringRuntimeBoot(
            status=source.boot.status,
            boot_time=source.boot.boot_time,
        ),
        startup_task=MonitoringRuntimeStartupTask(
            task_name=source.startup_task.task_name,
            status=source.startup_task.status,
            last_run_time=source.startup_task.last_run_time,
            last_task_result=source.startup_task.last_task_result,
        ),
        expected_listeners=[
            _project_runtime_listener(listener)
            for listener in source.expected_listeners
        ],
        temporary_listeners=[
            _project_runtime_listener(listener)
            for listener in source.temporary_listeners
        ],
    )


def project_system_database_health(
    source: SystemDatabaseHealthResponse,
) -> MonitoringSystemDatabaseHealthResponse:
    return MonitoringSystemDatabaseHealthResponse(
        status=source.status,
        checked_at=source.checked_at,
        postgres=MonitoringPostgresStatus(
            status=source.postgres.status,
            connected=source.postgres.connected,
            latency_ms=source.postgres.latency_ms,
            transaction_read_only=source.postgres.transaction_read_only,
        ),
        expected_schemas=[
            MonitoringPostgresSchemaStatus(
                schema_name=schema.schema_name,
                status=schema.status,
                present=schema.present,
            )
            for schema in source.expected_schemas
        ],
    )


def project_system_proxy_health(
    source: SystemProxyHealthResponse,
) -> MonitoringSystemProxyHealthResponse:
    return MonitoringSystemProxyHealthResponse(
        status=source.status,
        checked_at=source.checked_at,
        routes=[
            MonitoringProxyRouteStatus(
                key=route.key,
                status=route.status,
                expected_status_code=route.expected_status_code,
                actual_status_code=route.actual_status_code,
            )
            for route in source.routes
        ],
        headers=[
            MonitoringProxyHeaderStatus(
                key=header.key,
                status=header.status,
                expected=header.expected,
                present=header.present,
            )
            for header in source.headers
        ],
    )


def _project_smartfuelpass_job(source) -> MonitoringSmartFuelPassJobStatus:
    return MonitoringSmartFuelPassJobStatus(
        job_id=source.job_id,
        status=source.status,
        last_status=source.last_status,
        last_run=source.last_run,
        success_count_24h=source.success_count_24h,
        failure_count_24h=source.failure_count_24h,
        last_duration_seconds=source.last_duration_seconds,
    )


def project_system_smartfuelpass_health(
    source: SystemSmartFuelPassHealthResponse,
) -> MonitoringSystemSmartFuelPassHealthResponse:
    return MonitoringSystemSmartFuelPassHealthResponse(
        status=source.status,
        checked_at=source.checked_at,
        table=MonitoringSmartFuelPassTableStatus(
            status=source.table.status,
            table_present=source.table.table_present,
            missing_ended_at_utc_count=source.table.missing_ended_at_utc_count,
            last_imported_at=source.table.last_imported_at,
            last_import_age_seconds=source.table.last_import_age_seconds,
        ),
        sync_job=_project_smartfuelpass_job(source.sync_job),
        weekly_report_job=_project_smartfuelpass_job(source.weekly_report_job),
    )
