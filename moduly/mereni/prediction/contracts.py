from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol, Sequence


class PredictionForecastCadence(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class PredictionSelectionFallbackReason(str, Enum):
    NONE = "none"
    GLOBAL_ACTIVE_MODEL = "global_active_model"
    NO_IDENTIFIER_METRICS = "no_identifier_metrics"
    NO_ELIGIBLE_CANDIDATE = "no_eligible_candidate"
    BELOW_COVERAGE_THRESHOLD = "below_coverage_threshold"
    BELOW_FOLD_COUNT_THRESHOLD = "below_fold_count_threshold"
    MISSING_PROFILE = "missing_profile"


@dataclass(frozen=True)
class PredictionTimeWindow:
    start: datetime
    end: datetime
    label: str | None = None

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("Prediction time window end must be after start.")


@dataclass(frozen=True)
class PredictionForecastPeriodDefinition:
    cadence: PredictionForecastCadence
    period_count: int = 1
    label: str | None = None

    def __post_init__(self) -> None:
        if self.period_count <= 0:
            raise ValueError("Prediction forecast period count must be positive.")
        object.__setattr__(
            self,
            "cadence",
            PredictionForecastCadence(self.cadence),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "cadence": self.cadence.value,
            "period_count": self.period_count,
            "label": self.label,
        }


@dataclass(frozen=True)
class PredictionForecastPeriod:
    start: datetime
    end: datetime
    cadence: PredictionForecastCadence
    label: str | None = None

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("Prediction forecast period end must be after start.")
        object.__setattr__(
            self,
            "cadence",
            PredictionForecastCadence(self.cadence),
        )

    def to_time_window(self) -> PredictionTimeWindow:
        return PredictionTimeWindow(
            start=self.start,
            end=self.end,
            label=self.label,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "start": self.start,
            "end": self.end,
            "cadence": self.cadence.value,
            "label": self.label,
        }


@dataclass(frozen=True)
class PredictionRebuildWindows:
    train: PredictionTimeWindow
    validation: PredictionTimeWindow
    deploy: PredictionTimeWindow


@dataclass(frozen=True)
class PredictionSelectionMetadata:
    medium_key: str
    selection_run_id: int
    selected_model_version: int
    selected_model_name: str
    train: PredictionTimeWindow
    validation: PredictionTimeWindow
    deploy: PredictionTimeWindow
    created_at: datetime


@dataclass(frozen=True)
class PredictionCandidateSpec:
    medium_key: str
    model_version: int
    model_key: str
    model_name: str
    training_window_months: int
    validation_window_months: int = 1
    selection_enabled: bool = True

    def __post_init__(self) -> None:
        if self.model_version <= 0:
            raise ValueError("Prediction model version must be positive.")
        if self.training_window_months <= 0:
            raise ValueError("Prediction training window must be positive.")
        if self.validation_window_months <= 0:
            raise ValueError("Prediction validation window must be positive.")


@dataclass(frozen=True)
class PredictionObservation:
    identifier: str
    timestamp: datetime
    actual_value: float
    interval_minutes: int
    day_of_week: int
    slot: int
    features: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PredictionProfilePoint:
    identifier: str
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
    features: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PredictionMetricSummary:
    validation_total_count: int
    matched_validation_count: int
    coverage: float
    mae: float | None
    rmse: float | None
    bias: float | None
    wape: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "validation_total_count": self.validation_total_count,
            "matched_validation_count": self.matched_validation_count,
            "coverage": round(self.coverage, 6),
            "mae": None if self.mae is None else round(self.mae, 6),
            "rmse": None if self.rmse is None else round(self.rmse, 6),
            "bias": None if self.bias is None else round(self.bias, 6),
            "wape": None if self.wape is None else round(self.wape, 6),
        }


@dataclass(frozen=True)
class PredictionSelectedModelDecision:
    medium_key: str
    identifier: str
    forecast_period: PredictionForecastPeriod
    selection_run_id: int | None
    selected_model_version: int
    selected_model_key: str
    selected_model_name: str
    global_model_version: int
    global_model_key: str
    global_model_name: str
    fallback_reason: PredictionSelectionFallbackReason = (
        PredictionSelectionFallbackReason.NONE
    )
    metrics: PredictionMetricSummary | None = None
    created_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.medium_key:
            raise ValueError("Prediction selected model decision needs a medium key.")
        if not self.identifier:
            raise ValueError("Prediction selected model decision needs an identifier.")
        if self.selection_run_id is not None and self.selection_run_id <= 0:
            raise ValueError("Prediction selection run id must be positive.")
        if self.selected_model_version <= 0:
            raise ValueError("Prediction selected model version must be positive.")
        if self.global_model_version <= 0:
            raise ValueError("Prediction global model version must be positive.")
        if not self.selected_model_key:
            raise ValueError("Prediction selected model key must not be empty.")
        if not self.global_model_key:
            raise ValueError("Prediction global model key must not be empty.")

        fallback_reason = PredictionSelectionFallbackReason(self.fallback_reason)
        object.__setattr__(self, "fallback_reason", fallback_reason)

        if (
            self.uses_fallback
            and self.fallback_reason is not PredictionSelectionFallbackReason.MISSING_PROFILE
            and (
                self.selected_model_version != self.global_model_version
                or self.selected_model_key != self.global_model_key
            )
        ):
            raise ValueError(
                "Prediction fallback decisions must select the global model."
            )

    @property
    def uses_fallback(self) -> bool:
        return self.fallback_reason is not PredictionSelectionFallbackReason.NONE

    def to_dict(self) -> dict[str, object]:
        return {
            "medium_key": self.medium_key,
            "identifier": self.identifier,
            "forecast_period": self.forecast_period.to_dict(),
            "selection_run_id": self.selection_run_id,
            "selected_model_version": self.selected_model_version,
            "selected_model_key": self.selected_model_key,
            "selected_model_name": self.selected_model_name,
            "global_model_version": self.global_model_version,
            "global_model_key": self.global_model_key,
            "global_model_name": self.global_model_name,
            "fallback_reason": self.fallback_reason.value,
            "uses_fallback": self.uses_fallback,
            "metrics": None if self.metrics is None else self.metrics.to_dict(),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class CandidateProfileBuildResult:
    model_version: int
    profile_count: int
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PredictionCandidateResult:
    spec: PredictionCandidateSpec
    metrics: PredictionMetricSummary
    profile_count: int
    selected_device_count: int | None = None
    validation_candidate_count: int | None = None

    def to_dict(self, *, selected: bool) -> dict[str, object]:
        return {
            "model_version": self.spec.model_version,
            "model_key": self.spec.model_key,
            "model_name": self.spec.model_name,
            "selection_enabled": self.spec.selection_enabled,
            "profile_count": self.profile_count,
            "selected_device_count": self.selected_device_count,
            "validation_candidate_count": self.validation_candidate_count,
            "selected": selected,
            **self.metrics.to_dict(),
        }


class PredictionMediaAdapter(Protocol):
    medium_key: str

    def get_active_model_version(self) -> int:
        ...

    def load_observations(
        self,
        window: PredictionTimeWindow,
        *,
        identifiers: Sequence[str] | None = None,
    ) -> Sequence[PredictionObservation]:
        ...

    def replace_profiles(
        self,
        *,
        model_version: int,
        profiles: Iterable[PredictionProfilePoint],
    ) -> CandidateProfileBuildResult:
        ...

    def count_profiles(self, model_version: int) -> int:
        ...

    def load_selection_metadata(self) -> PredictionSelectionMetadata | None:
        ...


class PredictionCandidatePlugin(Protocol):
    spec: PredictionCandidateSpec


class CandidateModelPlugin(PredictionCandidatePlugin, Protocol):
    def build_profiles(
        self,
        adapter: PredictionMediaAdapter,
        windows: PredictionRebuildWindows,
    ) -> CandidateProfileBuildResult:
        ...
