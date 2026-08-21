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
    MonitoringDatabaseAvailabilityLocalAgentResponse,
    MonitoringDatabaseAvailabilityLocalAgentService,
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
    MonitoringSchedulerMetricsLocalAgentJob,
    MonitoringSchedulerMetricsLocalAgentResponse,
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


def project_database_availability_local_agent(
    source,
) -> MonitoringDatabaseAvailabilityLocalAgentResponse:
    return MonitoringDatabaseAvailabilityLocalAgentResponse(
        contract_version=source.contract_version,
        agent_key=source.agent_key,
        mode=source.mode,
        status=source.status,
        checked_at=source.checked_at,
        state_updated_at=source.state_updated_at,
        state_age_seconds=source.state_age_seconds,
        stale_after_seconds=source.stale_after_seconds,
        service_count=source.service_count,
        unavailable_service_count=source.unavailable_service_count,
        stale_service_count=source.stale_service_count,
        pending_event_count=source.pending_event_count,
        delivered_event_count_24h=source.delivered_event_count_24h,
        recent_transition_count=source.recent_transition_count,
        services=[
            MonitoringDatabaseAvailabilityLocalAgentService(
                service_key=service.service_key,
                status=service.status,
                available=service.available,
                failed_check_count=service.failed_check_count,
                last_checked_at=service.last_checked_at,
                last_checked_age_seconds=service.last_checked_age_seconds,
                outage_age_seconds=service.outage_age_seconds,
            )
            for service in source.services
        ],
        evidence_gaps=list(source.evidence_gaps),
    )


def project_scheduler_metrics_local_agent(
    source,
) -> MonitoringSchedulerMetricsLocalAgentResponse:
    return MonitoringSchedulerMetricsLocalAgentResponse(
        contract_version=source.contract_version,
        agent_key=source.agent_key,
        mode=source.mode,
        status=source.status,
        checked_at=source.checked_at,
        state_updated_at=source.state_updated_at,
        state_age_seconds=source.state_age_seconds,
        scheduler_running=source.scheduler_running,
        heartbeat_at=source.heartbeat_at,
        heartbeat_age_seconds=source.heartbeat_age_seconds,
        heartbeat_ttl_seconds=source.heartbeat_ttl_seconds,
        job_count=source.job_count,
        success_count_24h=source.success_count_24h,
        failure_count_24h=source.failure_count_24h,
        error_job_count=source.error_job_count,
        degraded_job_count=source.degraded_job_count,
        jobs=[
            MonitoringSchedulerMetricsLocalAgentJob(
                job_id=job.job_id,
                status=job.status,
                last_status_class=job.last_status_class,
                last_run_at=job.last_run_at,
                last_run_age_seconds=job.last_run_age_seconds,
                next_run_at=job.next_run_at,
                success_count_24h=job.success_count_24h,
                failure_count_24h=job.failure_count_24h,
                failure_rate_24h=job.failure_rate_24h,
            )
            for job in source.jobs
        ],
        evidence_gaps=list(source.evidence_gaps),
    )
