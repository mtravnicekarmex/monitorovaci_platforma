from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from moduly.mereni.plynomery.database.outlier_reviews import (
    normalize_review_note,
    normalize_review_status,
)
from services.api.core.plynomery_alert_rule_validation import (
    normalize_alert_rule_email,
    normalize_alert_rule_event_type,
    normalize_alert_rule_identifikace,
    normalize_alert_rule_min_duration,
    normalize_alert_rule_name,
    normalize_alert_rule_note,
    normalize_alert_rule_send_on,
    normalize_alert_rule_severity,
)


class PlynomeryDeviceListResponse(BaseModel):
    total: int
    devices: list[str]


class PlynomeryMeasurementSeriesRow(BaseModel):
    date: datetime
    identifikace: str
    seriove_cislo: str | None = None
    zdroj: str
    objem: float
    delta: float | None = None
    platne: bool
    interval_minutes: int
    day_of_week: int
    slot: int
    synthetic: bool
    nocni_odber: bool
    gap_detected: bool
    reset_detected: bool
    source_date: datetime | None = None
    time_utc: datetime | None = None
    time_basis: str | None = None
    source_timezone: str | None = None
    source_utc_offset_minutes: int | None = None
    time_fold: int | None = None
    timestamp_position: str | None = None


class PlynomeryMeasurementSeriesResponse(BaseModel):
    identifikace: str
    start_date: date
    end_date: date
    total: int
    rows: list[PlynomeryMeasurementSeriesRow]


class PlynomeryPredictionProfileRow(BaseModel):
    interval_minutes: int
    day_of_week: int
    slot: int
    expected_mean: float
    expected_median: float | None = None
    expected_p10: float | None = None
    expected_p90: float | None = None
    expected_std: float | None = None
    sample_size: int | None = None
    model_version: int
    model_key: str | None = None
    profile_kind: str
    base_mean: float | None = None
    hdd_slope: float | None = None
    hdd_24h_mean: float | None = None
    selection_run_id: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class PlynomeryPredictionAvailabilityPeriod(BaseModel):
    prediction_available: bool
    availability_reason: str | None = None
    selection_run_id: int | None = None
    selected_model_version: int | None = None
    selected_model_name: str | None = None
    valid_from: datetime
    valid_to: datetime


class PlynomeryPredictionProfilesResponse(BaseModel):
    identifikace: str
    prediction_available: bool
    availability_status: str
    availability_reason: str | None = None
    selection_mode: str
    start_date: date | None = None
    end_date: date | None = None
    selection_run_id: int | None = None
    selected_model_version: int | None = None
    selected_model_name: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    total: int
    availability_periods: list[PlynomeryPredictionAvailabilityPeriod] = Field(
        default_factory=list
    )
    rows: list[PlynomeryPredictionProfileRow]


class PlynomeryPredictionSeriesRow(BaseModel):
    date: datetime
    ocekavana_spotreba: float
    interval_count: int
    candidate_interval_count: int
    prediction_complete: bool
    model_versions: list[int]
    profile_kinds: list[str]
    ocekavana_kumulovana_spotreba: float


class PlynomeryPredictionSeriesResponse(BaseModel):
    identifikace: str
    start_date: date
    end_date: date
    granularity: str
    prediction_available: bool
    availability_status: str
    availability_reason: str | None = None
    total: int
    rows: list[PlynomeryPredictionSeriesRow]


class PlynomeryAnomalyRow(BaseModel):
    date: datetime
    identifikace: str
    actual_value: float
    expected_mean: float
    z_score: float
    severity: str | None = None
    is_anomaly: bool


class PlynomeryRecentAnomaliesResponse(BaseModel):
    identifikace: str | None = None
    start_date: date
    end_date: date
    total: int
    rows: list[PlynomeryAnomalyRow]


class PlynomeryEventRow(BaseModel):
    identifikace: str
    event_type: str
    start_time: datetime
    end_time: datetime | None = None
    duration_minutes: int
    max_z_score: float
    avg_z_score: float
    severity: str


class PlynomeryOpenEventsResponse(BaseModel):
    total: int
    rows: list[PlynomeryEventRow]


class PlynomeryResolvedEventsResponse(BaseModel):
    days: int
    total: int
    rows: list[PlynomeryEventRow]


class PlynomeryExpectedZeroRow(BaseModel):
    identifikace: str
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime


class PlynomeryExpectedZeroListResponse(BaseModel):
    total: int
    rows: list[PlynomeryExpectedZeroRow]


class PlynomeryExpectedZeroUpdateRequest(BaseModel):
    identifikace_list: list[str]


class PlynomeryAlertRuleRow(BaseModel):
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


class PlynomeryAlertRulesResponse(BaseModel):
    total: int
    rows: list[PlynomeryAlertRuleRow]


class PlynomeryAlertRuleUpsertRequest(BaseModel):
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


class PlynomeryOutlierReviewRow(BaseModel):
    id: int
    identifikace: str
    date: datetime
    zdroj: str
    source_recid: int | None = None
    seriove_cislo: str
    interval_minutes: int
    detection_kind: str
    current_objem: float
    baseline_objem: float | None = None
    baseline_date: datetime | None = None
    candidate_delta: float
    threshold_delta: float | None = None
    sample_size: int | None = None
    median_delta: float | None = None
    p90_delta: float | None = None
    p99_delta: float | None = None
    std_delta: float | None = None
    review_status: str
    review_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class PlynomeryOutlierReviewListResponse(BaseModel):
    total: int
    rows: list[PlynomeryOutlierReviewRow]


class PlynomeryOutlierReviewUpdateRequest(BaseModel):
    review_status: str
    review_note: str | None = Field(default=None, max_length=4000)

    @field_validator("review_status")
    @classmethod
    def validate_review_status(cls, value: str) -> str:
        return normalize_review_status(value)

    @field_validator("review_note")
    @classmethod
    def validate_review_note(cls, value: str | None) -> str | None:
        return normalize_review_note(value)
