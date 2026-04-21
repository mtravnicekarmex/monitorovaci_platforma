from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

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
