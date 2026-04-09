from __future__ import annotations

from datetime import date
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from services.api.core.vodomery_alert_rule_validation import (
    normalize_alert_rule_email,
    normalize_alert_rule_event_type,
    normalize_alert_rule_identifikace,
    normalize_alert_rule_min_duration,
    normalize_alert_rule_name,
    normalize_alert_rule_note,
    normalize_alert_rule_send_on,
    normalize_alert_rule_severity,
)


class VodomeryDeviceListResponse(BaseModel):
    source_filter: str
    total: int
    devices: list[str]


class VodomeryOverviewMetricsResponse(BaseModel):
    source_filter: str
    start_date: date
    end_date: date
    zarizeni: int
    mereni: int
    anomalie: int
    aktivni_eventy: int


class VodomeryMeasurementSeriesRow(BaseModel):
    date: datetime
    identifikace: str
    seriove_cislo: str
    zdroj: str
    objem: float
    delta: float | None = None
    interval_minutes: int
    day_of_week: int
    slot: int
    synthetic: bool
    nocni_odber: bool
    gap_detected: bool
    reset_detected: bool


class VodomeryMeasurementSeriesResponse(BaseModel):
    source_filter: str
    identifikace: str
    start_date: date
    end_date: date
    total: int
    rows: list[VodomeryMeasurementSeriesRow]


class VodomeryPredictionProfileRow(BaseModel):
    interval_minutes: int
    day_of_week: int
    slot: int
    expected_mean: float
    expected_median: float
    expected_p10: float
    expected_p90: float
    expected_std: float
    sample_size: int
    model_version: int


class VodomeryPredictionProfilesResponse(BaseModel):
    identifikace: str
    total: int
    rows: list[VodomeryPredictionProfileRow]


class VodomeryAnomalyRow(BaseModel):
    date: datetime
    identifikace: str
    actual_value: float
    expected_mean: float
    z_score: float
    severity: str | None = None
    is_anomaly: bool


class VodomeryRecentAnomaliesResponse(BaseModel):
    source_filter: str
    identifikace: str | None = None
    start_date: date
    end_date: date
    total: int
    rows: list[VodomeryAnomalyRow]


class VodomeryEventRow(BaseModel):
    identifikace: str
    event_type: str
    start_time: datetime
    end_time: datetime | None = None
    duration_minutes: int
    max_z_score: float
    avg_z_score: float
    severity: str


class VodomeryOpenEventsResponse(BaseModel):
    total: int
    rows: list[VodomeryEventRow]


class VodomeryResolvedEventsResponse(BaseModel):
    days: int
    total: int
    rows: list[VodomeryEventRow]


class VodomeryEventHistoryRow(BaseModel):
    event_type: str
    start_time: datetime
    end_time: datetime | None = None
    duration_minutes: int
    max_z_score: float
    avg_z_score: float
    severity: str
    is_active: bool
    resolved: bool


class VodomeryEventHistoryResponse(BaseModel):
    identifikace: str
    total: int
    rows: list[VodomeryEventHistoryRow]


class VodomeryDeviceDetail(BaseModel):
    identifikace: str
    seriove_cislo: str | None = None
    mbus: str | None = None
    objekt: str | None = None
    patro: str | None = None
    mistnost: str | None = None
    umisteni: str | None = None
    napaji: str | None = None
    koncovy_odberatel: str | None = None
    platnost_cejchu: datetime | None = None
    poznamka: str | None = None


class VodomeryDeviceDetailResponse(BaseModel):
    identifikace: str
    found: bool
    device: VodomeryDeviceDetail | None = None


class VodomeryExpectedZeroRow(BaseModel):
    identifikace: str
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime


class VodomeryExpectedZeroListResponse(BaseModel):
    total: int
    rows: list[VodomeryExpectedZeroRow]


class VodomeryExpectedZeroUpdateRequest(BaseModel):
    identifikace_list: list[str]


class VodomeryAlertRuleRow(BaseModel):
    id: int
    rule_name: str
    identifikace: str | None = None
    event_type: str | None = None
    severity_min: str
    min_duration_minutes: int
    send_on: str
    recipient_email: str
    enabled: bool
    note: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime


class VodomeryAlertRulesResponse(BaseModel):
    total: int
    rows: list[VodomeryAlertRuleRow]


class VodomeryAlertRuleUpsertRequest(BaseModel):
    rule_name: str = Field(min_length=1, max_length=150)
    recipient_email: str = Field(min_length=1, max_length=250)
    severity_min: str
    min_duration_minutes: int = Field(ge=0)
    send_on: str
    identifikace: str | None = Field(default=None, max_length=250)
    event_type: str | None = None
    enabled: bool = True
    note: str | None = None

    @field_validator("rule_name")
    @classmethod
    def validate_rule_name(cls, value: str) -> str:
        return normalize_alert_rule_name(value)

    @field_validator("recipient_email")
    @classmethod
    def validate_recipient_email(cls, value: str) -> str:
        return normalize_alert_rule_email(value)

    @field_validator("severity_min")
    @classmethod
    def validate_severity_min(cls, value: str) -> str:
        return normalize_alert_rule_severity(value)

    @field_validator("min_duration_minutes")
    @classmethod
    def validate_min_duration_minutes(cls, value: int) -> int:
        return normalize_alert_rule_min_duration(value)

    @field_validator("send_on")
    @classmethod
    def validate_send_on(cls, value: str) -> str:
        return normalize_alert_rule_send_on(value)

    @field_validator("identifikace")
    @classmethod
    def validate_identifikace(cls, value: str | None) -> str | None:
        return normalize_alert_rule_identifikace(value)

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, value: str | None) -> str | None:
        return normalize_alert_rule_event_type(value)

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str | None) -> str | None:
        return normalize_alert_rule_note(value)


class VodomeryBranchHourlyRow(BaseModel):
    date: datetime
    spotreba: float
    ocekavana_spotreba: float
    fakturacni_spotreba: float
    kumulovana_spotreba: float
    fakturacni_kumulovana_spotreba: float
    ocekavana_kumulovana_spotreba: float
    kumulovana_spotreba_graf: float | None = None
    fakturacni_kumulovana_spotreba_graf: float | None = None
    navazna_predikce: float | None = None
    denni_limit: float | None = None


class VodomeryBranchDeviceConsumptionRow(BaseModel):
    identifikace: str
    spotreba: float
    ocekavana_spotreba: float | None = None
    podil_procent: float | None = None
    odchylka_od_ocekavani_procent: float | None = None


class VodomeryBranchDeviceHourlyRow(BaseModel):
    date: datetime
    identifikace: str
    spotreba: float


class VodomeryBranchOverviewRow(BaseModel):
    key: str
    title: str
    billing_ident: str
    daily_limit: float | None = None
    active_devices: list[str]
    hourly_rows: list[VodomeryBranchHourlyRow]
    last_actual_timestamp: datetime | None = None
    actual_total: float
    device_consumption_rows: list[VodomeryBranchDeviceConsumptionRow]
    device_hourly_rows: list[VodomeryBranchDeviceHourlyRow]
    expected_total: float
    expected_end_of_day: float
    expected_vs_limit: float | None = None
    remaining_to_limit: float | None = None


class VodomeryBranchOverviewResponse(BaseModel):
    target_date: date
    total: int
    branches: list[VodomeryBranchOverviewRow]
