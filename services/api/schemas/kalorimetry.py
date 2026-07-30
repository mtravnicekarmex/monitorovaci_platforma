from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from moduly.mereni.kalorimetry.database.outlier_reviews import (
    normalize_review_note,
    normalize_review_status,
)


class KalorimetryDeviceListResponse(BaseModel):
    total: int
    devices: list[str]


class KalorimetryMeasurementSeriesRow(BaseModel):
    date: datetime
    identifikace: str
    seriove_cislo: str | None = None
    zdroj: str
    spotreba_energie: float
    objem: float | None = None
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


class KalorimetryMeasurementSeriesResponse(BaseModel):
    identifikace: str
    start_date: date
    end_date: date
    total: int
    rows: list[KalorimetryMeasurementSeriesRow]


class KalorimetryPredictionProfileRow(BaseModel):
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
    selection_run_id: int | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None


class KalorimetryPredictionAvailabilityPeriod(BaseModel):
    prediction_available: bool
    availability_reason: str | None = None
    selection_run_id: int | None = None
    selected_model_version: int | None = None
    selected_model_name: str | None = None
    valid_from: datetime
    valid_to: datetime


class KalorimetryPredictionProfilesResponse(BaseModel):
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
    availability_periods: list[
        KalorimetryPredictionAvailabilityPeriod
    ] = Field(default_factory=list)
    rows: list[KalorimetryPredictionProfileRow]


class KalorimetryPredictionSeriesRow(BaseModel):
    date: datetime
    ocekavana_spotreba: float
    interval_count: int
    candidate_interval_count: int
    prediction_complete: bool
    model_versions: list[int]
    profile_kinds: list[str]
    ocekavana_kumulovana_spotreba: float


class KalorimetryPredictionSeriesResponse(BaseModel):
    identifikace: str
    start_date: date
    end_date: date
    granularity: str
    prediction_available: bool
    availability_status: str
    availability_reason: str | None = None
    total: int
    rows: list[KalorimetryPredictionSeriesRow]


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
