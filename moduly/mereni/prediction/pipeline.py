from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Generic, Iterable, TypeVar

from moduly.mereni.prediction.contracts import (
    PredictionCandidatePlugin,
    PredictionCandidateResult,
    PredictionCandidateSpec,
    PredictionForecastPeriod,
    PredictionForecastPeriodDefinition,
    PredictionRebuildWindows,
    PredictionTimeWindow,
)
from moduly.mereni.prediction.periods import (
    build_next_forecast_period,
    subtract_months,
)


@dataclass(frozen=True)
class PredictionPipelineSettings:
    medium_key: str
    forecast_period_definition: PredictionForecastPeriodDefinition
    default_training_window_months: int
    default_validation_window_months: int = 1
    candidate_coverage_threshold: float = 0.85
    rolling_backtest_fold_count: int = 0
    rolling_validation_period: PredictionForecastPeriodDefinition | None = None

    def __post_init__(self) -> None:
        if not self.medium_key:
            raise ValueError("Prediction pipeline settings need a medium key.")
        if self.default_training_window_months <= 0:
            raise ValueError("Default training window must be positive.")
        if self.default_validation_window_months <= 0:
            raise ValueError("Default validation window must be positive.")
        if not 0 <= self.candidate_coverage_threshold <= 1:
            raise ValueError("Candidate coverage threshold must be between 0 and 1.")
        if self.rolling_backtest_fold_count < 0:
            raise ValueError("Rolling backtest fold count must not be negative.")


PluginT = TypeVar("PluginT", bound=PredictionCandidatePlugin)


@dataclass(frozen=True)
class PredictionPipelineCandidateRun(Generic[PluginT]):
    plugin: PluginT
    spec: PredictionCandidateSpec
    windows: PredictionRebuildWindows


class PredictionCandidateRegistry(Generic[PluginT]):
    def __init__(
        self,
        *,
        medium_key: str,
        plugins: Iterable[PluginT],
    ) -> None:
        if not medium_key:
            raise ValueError("Prediction candidate registry needs a medium key.")
        self.medium_key = medium_key
        self._plugins = tuple(plugins)
        if not self._plugins:
            raise ValueError("Prediction candidate registry needs at least one plugin.")
        self._validate_plugins()

    def list_plugins(self, *, include_non_selectable: bool = True) -> tuple[PluginT, ...]:
        if include_non_selectable:
            return self._plugins
        return tuple(plugin for plugin in self._plugins if plugin.spec.selection_enabled)

    def list_specs(
        self,
        *,
        include_non_selectable: bool = True,
    ) -> tuple[PredictionCandidateSpec, ...]:
        return tuple(
            plugin.spec
            for plugin in self.list_plugins(include_non_selectable=include_non_selectable)
        )

    def list_model_versions(
        self,
        *,
        include_non_selectable: bool = True,
    ) -> tuple[int, ...]:
        return tuple(
            spec.model_version
            for spec in self.list_specs(include_non_selectable=include_non_selectable)
        )

    def get_by_model_version(self, model_version: int) -> PluginT | None:
        return next(
            (
                plugin
                for plugin in self._plugins
                if plugin.spec.model_version == model_version
            ),
            None,
        )

    def _validate_plugins(self) -> None:
        seen_versions: set[int] = set()
        seen_keys: set[str] = set()
        for plugin in self._plugins:
            spec = plugin.spec
            if spec.medium_key != self.medium_key:
                raise ValueError(
                    "Prediction candidate plugin medium key does not match registry."
                )
            if spec.model_version in seen_versions:
                raise ValueError(
                    f"Duplicate prediction model version: {spec.model_version}"
                )
            if spec.model_key in seen_keys:
                raise ValueError(f"Duplicate prediction model key: {spec.model_key}")
            seen_versions.add(spec.model_version)
            seen_keys.add(spec.model_key)


@dataclass(frozen=True)
class PredictionPipelineRunner(Generic[PluginT]):
    settings: PredictionPipelineSettings
    registry: PredictionCandidateRegistry[PluginT]

    def __post_init__(self) -> None:
        if self.registry.medium_key != self.settings.medium_key:
            raise ValueError("Prediction pipeline registry medium key mismatch.")

    def list_plugins(self, *, include_non_selectable: bool = True) -> tuple[PluginT, ...]:
        return self.registry.list_plugins(include_non_selectable=include_non_selectable)

    def list_specs(
        self,
        *,
        include_non_selectable: bool = True,
    ) -> tuple[PredictionCandidateSpec, ...]:
        return self.registry.list_specs(include_non_selectable=include_non_selectable)

    def list_model_versions(
        self,
        *,
        include_non_selectable: bool = True,
    ) -> tuple[int, ...]:
        return self.registry.list_model_versions(
            include_non_selectable=include_non_selectable,
        )

    def get_plugin(self, model_version: int) -> PluginT | None:
        return self.registry.get_by_model_version(model_version)

    def build_rebuild_windows(
        self,
        *,
        reference_time: datetime,
        spec: PredictionCandidateSpec | None = None,
    ) -> PredictionRebuildWindows:
        return build_prediction_rebuild_windows(
            reference_time=reference_time,
            training_window_months=(
                spec.training_window_months
                if spec is not None
                else self.settings.default_training_window_months
            ),
            validation_window_months=(
                spec.validation_window_months
                if spec is not None
                else self.settings.default_validation_window_months
            ),
        )

    def build_candidate_runs(
        self,
        *,
        reference_time: datetime,
        include_non_selectable: bool = True,
    ) -> tuple[PredictionPipelineCandidateRun[PluginT], ...]:
        return tuple(
            PredictionPipelineCandidateRun(
                plugin=plugin,
                spec=plugin.spec,
                windows=self.build_rebuild_windows(
                    reference_time=reference_time,
                    spec=plugin.spec,
                ),
            )
            for plugin in self.list_plugins(
                include_non_selectable=include_non_selectable,
            )
        )

    def build_forecast_period(self, *, reference_time: datetime) -> PredictionForecastPeriod:
        return build_next_forecast_period(
            reference_time=reference_time,
            definition=self.settings.forecast_period_definition,
        )

    def select_best_candidate(
        self,
        candidates: Iterable[PredictionCandidateResult],
        *,
        coverage_threshold: float | None = None,
    ) -> PredictionCandidateResult | None:
        return select_best_prediction_candidate(
            candidates,
            coverage_threshold=(
                self.settings.candidate_coverage_threshold
                if coverage_threshold is None
                else coverage_threshold
            ),
        )


def build_prediction_rebuild_windows(
    *,
    reference_time: datetime,
    training_window_months: int,
    validation_window_months: int,
) -> PredictionRebuildWindows:
    if training_window_months <= 0:
        raise ValueError("Training window must be positive.")
    if validation_window_months <= 0:
        raise ValueError("Validation window must be positive.")

    validation_end = reference_time
    validation_start = subtract_months(validation_end, validation_window_months)
    train_end = validation_start
    train_start = subtract_months(train_end, training_window_months)
    return PredictionRebuildWindows(
        train=PredictionTimeWindow(start=train_start, end=train_end, label="train"),
        validation=PredictionTimeWindow(
            start=validation_start,
            end=validation_end,
            label="validation",
        ),
        deploy=PredictionTimeWindow(
            start=train_start,
            end=validation_end,
            label="deploy",
        ),
    )


def select_best_prediction_candidate(
    candidates: Iterable[PredictionCandidateResult],
    *,
    coverage_threshold: float = 0.85,
) -> PredictionCandidateResult | None:
    eligible_candidates = [
        candidate
        for candidate in candidates
        if candidate.spec.selection_enabled
        and candidate.metrics.validation_total_count > 0
        and candidate.metrics.matched_validation_count > 0
        and candidate.metrics.mae is not None
        and candidate.metrics.rmse is not None
        and candidate.metrics.bias is not None
    ]
    if not eligible_candidates:
        return None

    return min(
        eligible_candidates,
        key=lambda candidate: (
            0 if candidate.metrics.coverage >= coverage_threshold else 1,
            candidate.metrics.mae,
            candidate.metrics.rmse,
            abs(candidate.metrics.bias),
            -candidate.metrics.matched_validation_count,
            candidate.spec.model_version,
        ),
    )
