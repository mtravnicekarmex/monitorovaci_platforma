from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PredictionCandidateCatalogRecord(BaseModel):
    medium_key: str
    medium_label: str
    forecast_cadence: str
    model_version: int
    model_key: str
    model_name: str
    training_window_months: int
    validation_window_months: int
    selection_enabled: bool


class PredictionSelectionRunRecord(BaseModel):
    medium_key: str
    selection_run_id: int
    selected_model_version: int
    selected_model_name: str
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    deploy_start: datetime
    deploy_end: datetime
    created_at: datetime


class PredictionCandidatePerformanceRecord(BaseModel):
    medium_key: str
    medium_label: str
    selection_run_id: int
    model_version: int
    model_key: str
    model_name: str
    training_window_months: int | None = None
    validation_window_months: int | None = None
    selection_enabled: bool
    selected: bool
    validation_total_count: int = Field(ge=0)
    matched_validation_count: int = Field(ge=0)
    coverage: float = Field(ge=0)
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    wape: float | None = None
    rolling_backtest_fold_count: int = Field(default=0, ge=0)
    rolling_validation_total_count: int | None = Field(default=None, ge=0)
    rolling_matched_validation_count: int | None = Field(default=None, ge=0)
    rolling_coverage: float | None = Field(default=None, ge=0)
    rolling_mae: float | None = None
    rolling_rmse: float | None = None
    rolling_bias: float | None = None
    rolling_wape: float | None = None
    profile_count: int = Field(default=0, ge=0)
    created_at: datetime | None = None


class PredictionDistributionRecord(BaseModel):
    key: str
    label: str
    count: int = Field(ge=0)


class PredictionSnapshotSummary(BaseModel):
    medium_key: str
    selection_mode: str
    selection_run_id: int | None = None
    forecast_period_start: datetime
    forecast_period_end: datetime
    forecast_period_label: str | None = None
    forecast_cadence: str
    snapshot_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    selected_differs_from_global_count: int = Field(ge=0)
    latest_created_at: datetime | None = None
    model_distribution: list[PredictionDistributionRecord] = Field(default_factory=list)
    fallback_distribution: list[PredictionDistributionRecord] = Field(default_factory=list)


class PredictionIdentifierSelectionRecord(BaseModel):
    medium_key: str
    medium_label: str
    identifier: str
    selection_mode: str
    selection_run_id: int | None = None
    forecast_period_start: datetime
    forecast_period_end: datetime
    forecast_period_label: str | None = None
    selected_model_version: int
    selected_model_name: str
    global_model_version: int
    global_model_name: str
    uses_fallback: bool
    fallback_reason: str
    validation_total_count: int | None = Field(default=None, ge=0)
    matched_validation_count: int | None = Field(default=None, ge=0)
    coverage: float | None = Field(default=None, ge=0)
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    wape: float | None = None
    created_at: datetime | None = None


class PredictionMediumPerformance(BaseModel):
    medium_key: str
    medium_label: str
    forecast_cadence: str
    status: str
    detail: str
    candidate_catalog: list[PredictionCandidateCatalogRecord]
    latest_selection_run: PredictionSelectionRunRecord | None = None
    candidate_performance: list[PredictionCandidatePerformanceRecord] = Field(default_factory=list)
    snapshot_summary: PredictionSnapshotSummary | None = None
    worst_identifier_selections: list[PredictionIdentifierSelectionRecord] = Field(default_factory=list)


class PredictionPerformanceResponse(BaseModel):
    status: str
    checked_at: datetime
    media: list[PredictionMediumPerformance]
