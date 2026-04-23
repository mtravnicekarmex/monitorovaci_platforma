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
