from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from moduly.mereni.kalorimetry.database.outlier_reviews import (
    normalize_review_note,
    normalize_review_status,
)


class KalorimetryDeviceListResponse(BaseModel):
    total: int
    devices: list[str]


class KalorimetryOutlierReviewRow(BaseModel):
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


class KalorimetryOutlierReviewListResponse(BaseModel):
    total: int
    rows: list[KalorimetryOutlierReviewRow]


class KalorimetryOutlierReviewUpdateRequest(BaseModel):
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
