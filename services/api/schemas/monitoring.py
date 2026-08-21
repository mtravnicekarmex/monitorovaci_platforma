from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MonitoringSchedulerJob(BaseModel):
    id: str
    is_scheduled: bool
    last_run: datetime | None = None
    last_status: str
    last_duration_seconds: float | None = Field(default=None, ge=0)
    next_run: datetime | None = None
    failure_rate_24h: float = Field(ge=0.0, le=1.0)
    avg_duration_24h: float | None = Field(default=None, ge=0)


class MonitoringScheduledRun(BaseModel):
    job_id: str
    scheduled_at: datetime


class MonitoringSchedulerHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    scheduler_running: bool
    jobs: list[MonitoringSchedulerJob]
    schedule: list[MonitoringScheduledRun]
    checked_at: datetime


class MonitoringSystemSchedulerJob(BaseModel):
    job_id: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    last_status: str
    last_run: datetime | None = None
    next_run: datetime | None = None
    success_count_24h: int = Field(ge=0)
    failure_count_24h: int = Field(ge=0)
    last_duration_seconds: float | None = Field(default=None, ge=0)


class MonitoringSystemSchedulerHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    scheduler_running: bool
    last_heartbeat: datetime | None = None
    heartbeat_age_seconds: float | None = Field(default=None, ge=0)
    heartbeat_ttl_seconds: int = Field(ge=1)
    total_success_count_24h: int = Field(ge=0)
    total_failure_count_24h: int = Field(ge=0)
    jobs: list[MonitoringSystemSchedulerJob]


class MonitoringRuntimeBoot(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    boot_time: datetime | None = None


class MonitoringRuntimeStartupTask(BaseModel):
    task_name: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    last_run_time: datetime | None = None
    last_task_result: int | None = None


class MonitoringRuntimeListener(BaseModel):
    key: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    expected: bool
    present: bool
    local_port: int = Field(ge=1, le=65535)


class MonitoringSystemRuntimeHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    boot: MonitoringRuntimeBoot
    startup_task: MonitoringRuntimeStartupTask
    expected_listeners: list[MonitoringRuntimeListener]
    temporary_listeners: list[MonitoringRuntimeListener]


class MonitoringPostgresStatus(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    connected: bool
    latency_ms: float | None = Field(default=None, ge=0)
    transaction_read_only: bool | None = None


class MonitoringPostgresSchemaStatus(BaseModel):
    schema_name: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    present: bool


class MonitoringSystemDatabaseHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    postgres: MonitoringPostgresStatus
    expected_schemas: list[MonitoringPostgresSchemaStatus]


class MonitoringProxyRouteStatus(BaseModel):
    key: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    expected_status_code: int = Field(ge=100, le=599)
    actual_status_code: int | None = Field(default=None, ge=100, le=599)


class MonitoringProxyHeaderStatus(BaseModel):
    key: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    expected: str = Field(..., pattern="^(present|absent)$")
    present: bool


class MonitoringSystemProxyHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    routes: list[MonitoringProxyRouteStatus]
    headers: list[MonitoringProxyHeaderStatus]


class MonitoringSmartFuelPassTableStatus(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    table_present: bool
    missing_ended_at_utc_count: int = Field(ge=0)
    last_imported_at: datetime | None = None
    last_import_age_seconds: float | None = Field(default=None, ge=0)


class MonitoringSmartFuelPassJobStatus(BaseModel):
    job_id: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    last_status: str
    last_run: datetime | None = None
    success_count_24h: int = Field(ge=0)
    failure_count_24h: int = Field(ge=0)
    last_duration_seconds: float | None = Field(default=None, ge=0)


class MonitoringSystemSmartFuelPassHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    table: MonitoringSmartFuelPassTableStatus
    sync_job: MonitoringSmartFuelPassJobStatus
    weekly_report_job: MonitoringSmartFuelPassJobStatus


class MonitoringDatabaseAvailabilityLocalAgentService(BaseModel):
    service_key: str
    status: str = Field(..., pattern="^(ok|degraded)$")
    available: bool
    failed_check_count: int = Field(ge=0)
    last_checked_at: datetime | None = None
    last_checked_age_seconds: float | None = Field(default=None, ge=0)
    outage_age_seconds: float | None = Field(default=None, ge=0)


class MonitoringDatabaseAvailabilityLocalAgentResponse(BaseModel):
    contract_version: int = Field(ge=1)
    agent_key: str
    mode: str = Field(..., pattern="^local_agent$")
    status: str = Field(..., pattern="^(ok|degraded|error|unavailable)$")
    checked_at: datetime
    state_updated_at: datetime | None = None
    state_age_seconds: float | None = Field(default=None, ge=0)
    stale_after_seconds: float = Field(gt=0)
    service_count: int = Field(ge=0)
    unavailable_service_count: int = Field(ge=0)
    stale_service_count: int = Field(ge=0)
    pending_event_count: int = Field(ge=0)
    delivered_event_count_24h: int = Field(ge=0)
    recent_transition_count: int = Field(ge=0)
    services: list[MonitoringDatabaseAvailabilityLocalAgentService]
    evidence_gaps: list[str]


class MonitoringSchedulerMetricsLocalAgentJob(BaseModel):
    job_id: str
    status: str = Field(..., pattern="^(ok|degraded|error|unknown)$")
    last_status_class: str = Field(
        ...,
        pattern="^(success|error|skipped|unknown|other)$",
    )
    last_run_at: datetime | None = None
    last_run_age_seconds: float | None = Field(default=None, ge=0)
    next_run_at: datetime | None = None
    success_count_24h: int = Field(ge=0)
    failure_count_24h: int = Field(ge=0)
    failure_rate_24h: float = Field(ge=0.0, le=1.0)


class MonitoringSchedulerMetricsLocalAgentResponse(BaseModel):
    contract_version: int = Field(ge=1)
    agent_key: str
    mode: str = Field(..., pattern="^local_agent$")
    status: str = Field(..., pattern="^(ok|degraded|error|unavailable)$")
    checked_at: datetime
    state_updated_at: datetime | None = None
    state_age_seconds: float | None = Field(default=None, ge=0)
    scheduler_running: bool
    heartbeat_at: datetime | None = None
    heartbeat_age_seconds: float | None = Field(default=None, ge=0)
    heartbeat_ttl_seconds: int = Field(ge=1)
    job_count: int = Field(ge=0)
    success_count_24h: int = Field(ge=0)
    failure_count_24h: int = Field(ge=0)
    error_job_count: int = Field(ge=0)
    degraded_job_count: int = Field(ge=0)
    jobs: list[MonitoringSchedulerMetricsLocalAgentJob]
    evidence_gaps: list[str]
