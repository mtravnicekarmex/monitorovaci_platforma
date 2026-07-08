from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class AdminDeviceOptionsResponse(BaseModel):
    total: int
    devices: list[str]


class AdminUserRecord(BaseModel):
    username: str
    email: str | None = None
    available_sections: list[str]
    available_pages: list[str]
    device_ids: list[str]
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class AdminUsersResponse(BaseModel):
    total: int
    users: list[AdminUserRecord]


class AdminUserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)
    email: str | None = Field(default=None, max_length=250)
    available_sections: list[str] = Field(default_factory=list)
    available_pages: list[str] = Field(default_factory=list)
    device_ids: list[str] = Field(default_factory=list)
    is_active: bool = True
    is_admin: bool = False


class AdminUserUpdateRequest(BaseModel):
    password: str | None = Field(default=None, min_length=1, max_length=1024)
    email: str | None = Field(default=None, max_length=250)
    available_sections: list[str] | None = None
    available_pages: list[str] | None = None
    device_ids: list[str] | None = None
    is_active: bool | None = None
    is_admin: bool | None = None


class AdminMapLayerRecord(BaseModel):
    layer_id: str
    title: str
    layer_kind: str
    source_schema: str
    source_table: str
    geometry_column: str
    identifier_column: str
    source_srid: int
    target_srid: int
    property_columns: list[str]
    property_aliases: dict[str, Any]
    filter_columns: list[str]
    popup_columns: list[str]
    style: dict[str, Any]
    device_section_key: str | None = None
    restrict_to_allowed_devices: bool
    map_enabled: bool
    default_visible: bool
    show_photo: bool
    is_active: bool
    draw_order: int
    created_at: datetime
    updated_at: datetime


class AdminMapLayersResponse(BaseModel):
    total: int
    layers: list[AdminMapLayerRecord]


class AdminMapLayerCreateRequest(BaseModel):
    layer_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1, max_length=250)
    layer_kind: str = Field(default="context", pattern="^(context|device)$")
    source_schema: str = Field(default="evidence", min_length=1, max_length=100)
    source_table: str = Field(min_length=1, max_length=250)
    geometry_column: str = Field(default="geom", min_length=1, max_length=100)
    identifier_column: str = Field(min_length=1, max_length=100)
    source_srid: int = 3857
    target_srid: int = 4326
    property_columns: list[str] = Field(default_factory=list)
    property_aliases: dict[str, Any] = Field(default_factory=dict)
    filter_columns: list[str] = Field(default_factory=list)
    popup_columns: list[str] = Field(default_factory=list)
    style: dict[str, Any] = Field(default_factory=dict)
    device_section_key: str | None = Field(default=None, max_length=100)
    restrict_to_allowed_devices: bool = False
    map_enabled: bool = True
    default_visible: bool = True
    show_photo: bool = False
    is_active: bool = True
    draw_order: int = 100


class AdminMapLayerUpdateRequest(AdminMapLayerCreateRequest):
    layer_id: str | None = Field(default=None, max_length=100, exclude=True)


class AdminRevizeMutationRequest(BaseModel):
    budova: str = Field(min_length=1, max_length=50)
    datum: date
    delka_platnosti: int = Field(ge=1, le=99)
    typ_zarizeni: str = Field(min_length=1, max_length=100)
    nazev_revize: str | None = Field(default=None, max_length=255)
    dodavatel: str | None = Field(default=None, max_length=200)
    servisni_smlouva: str | None = Field(default=None, max_length=500)
    soubor: str | None = Field(default=None, max_length=500)
    poznamka: str | None = None
    linked_device_ids: list[int] = Field(default_factory=list)


class AdminRevizeMutationResponse(BaseModel):
    id: int


class AdminDeviceMutationRequest(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)


class AdminDeviceUpdateRequest(AdminDeviceMutationRequest):
    primary_key_value: Any


class SchedulerJobHealth(BaseModel):
    id: str
    label: str | None = None
    description: str | None = None
    is_scheduled: bool = False
    is_manual_runnable: bool = False
    last_run: datetime | None = None
    last_status: str
    last_duration_seconds: float | None = None
    next_run: datetime | None = None
    failure_rate_24h: float = Field(ge=0.0, le=1.0)
    avg_duration_24h: float | None = None


class SchedulerScheduledRun(BaseModel):
    job_id: str
    job_label: str
    description: str
    scheduled_at: datetime


class SchedulerHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    scheduler_running: bool
    jobs: list[SchedulerJobHealth]
    schedule: list[SchedulerScheduledRun] = Field(default_factory=list)
    checked_at: datetime


class SchedulerJobRunResponse(BaseModel):
    job_id: str
    job_label: str
    status: str = Field(..., pattern="^(started|busy)$")
    detail: str
    requested_at: datetime


class SchedulerLogResponse(BaseModel):
    path: str
    exists: bool
    max_lines: int = Field(ge=1)
    lines_returned: int = Field(ge=0)
    content: str
    updated_at: datetime | None = None


class SystemRuntimeBootStatus(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    boot_time: datetime | None = None
    detail: str


class SystemRuntimeStartupTaskStatus(BaseModel):
    task_name: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    last_run_time: datetime | None = None
    next_run_time: datetime | None = None
    last_task_result: int | None = None
    detail: str


class SystemRuntimeListenerStatus(BaseModel):
    key: str
    label: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    expected: bool
    present: bool
    local_address: str | None = None
    local_port: int = Field(ge=1, le=65535)
    process_ids: list[int] = Field(default_factory=list)
    detail: str


class SystemRuntimeHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    boot: SystemRuntimeBootStatus
    startup_task: SystemRuntimeStartupTaskStatus
    expected_listeners: list[SystemRuntimeListenerStatus]
    temporary_listeners: list[SystemRuntimeListenerStatus]


class SystemProxyRouteStatus(BaseModel):
    key: str
    label: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    method: str
    scheme: str
    host: str
    path: str
    expected_status_code: int = Field(ge=100, le=599)
    actual_status_code: int | None = Field(default=None, ge=100, le=599)
    expected_content_type_prefix: str | None = None
    actual_content_type: str | None = None
    expected_location: str | None = None
    actual_location: str | None = None
    detail: str


class SystemProxyHeaderStatus(BaseModel):
    key: str
    header_name: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    expected: str = Field(..., pattern="^(present|absent)$")
    present: bool
    detail: str


class SystemProxyHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    public_host: str
    routes: list[SystemProxyRouteStatus]
    headers: list[SystemProxyHeaderStatus]


class SystemSchedulerJobStatus(BaseModel):
    job_id: str
    label: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    last_status: str
    last_run: datetime | None = None
    next_run: datetime | None = None
    success_count_24h: int = Field(ge=0)
    failure_count_24h: int = Field(ge=0)
    last_duration_seconds: float | None = None
    detail: str


class SystemSchedulerHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    scheduler_running: bool
    last_heartbeat: datetime | None = None
    heartbeat_age_seconds: float | None = Field(default=None, ge=0)
    heartbeat_ttl_seconds: int = Field(ge=1)
    total_success_count_24h: int = Field(ge=0)
    total_failure_count_24h: int = Field(ge=0)
    jobs: list[SystemSchedulerJobStatus]


class SystemPostgresConnectionStatus(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    connected: bool
    latency_ms: float | None = Field(default=None, ge=0)
    server_time: datetime | None = None
    server_timezone: str | None = None
    server_version: str | None = None
    transaction_read_only: bool | None = None
    detail: str


class SystemPostgresSchemaStatus(BaseModel):
    schema_name: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    present: bool
    table_count: int | None = Field(default=None, ge=0)
    detail: str


class SystemDatabaseHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    postgres: SystemPostgresConnectionStatus
    expected_schemas: list[SystemPostgresSchemaStatus]


class SystemSmartFuelPassTableStatus(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    table_present: bool
    total_session_count: int = Field(ge=0)
    sessions_with_utc_count: int = Field(ge=0)
    missing_ended_at_utc_count: int = Field(ge=0)
    first_session_at: datetime | None = None
    last_session_at: datetime | None = None
    last_imported_at: datetime | None = None
    last_import_age_seconds: float | None = Field(default=None, ge=0)
    total_amount: float = Field(ge=0)
    location_count: int = Field(ge=0)
    connector_count: int = Field(ge=0)
    detail: str


class SystemSmartFuelPassJobMetricStatus(BaseModel):
    job_id: str
    label: str
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    last_status: str
    last_run: datetime | None = None
    success_count_24h: int = Field(ge=0)
    failure_count_24h: int = Field(ge=0)
    last_duration_seconds: float | None = None
    detail: str


class SystemSmartFuelPassPeriodSummary(BaseModel):
    key: str
    label: str
    start: datetime | None = None
    end: datetime | None = None
    session_count: int = Field(ge=0)
    total_amount: float = Field(ge=0)
    location_count: int = Field(ge=0)
    connector_count: int = Field(ge=0)
    first_session_at: datetime | None = None
    last_session_at: datetime | None = None


class SystemSmartFuelPassHealthResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|degraded|error)$")
    checked_at: datetime
    source: str
    period_basis: str
    table: SystemSmartFuelPassTableStatus
    sync_job: SystemSmartFuelPassJobMetricStatus
    weekly_report_job: SystemSmartFuelPassJobMetricStatus
    report_periods: list[SystemSmartFuelPassPeriodSummary]
