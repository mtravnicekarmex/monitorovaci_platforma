from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from time import perf_counter
from typing import Callable, Sequence

from sqlalchemy import bindparam, insert, select, text

from app.time_utils import utc_now_naive
from core.db.connect import get_session_pg
from moduly.mereni.prediction import (
    ARCHIVE_SOURCE_WEEKLY_REBUILD,
    PredictionCandidateRegistry,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionForecastPeriodDefinition,
    PredictionPipelineRunner,
    PredictionPipelineSettings,
    PredictionCandidateSpec,
    PredictionCandidateResult,
    PredictionMetricSummary,
    PredictionSelectedModelDecision,
    PredictionSelectionFallbackReason,
    PredictionRebuildWindows,
    SELECTION_MODE_ACTIVE,
    build_prediction_rebuild_windows,
    build_rolling_weekly_folds,
    ensure_prediction_profile_snapshot_table,
    ensure_prediction_selected_model_snapshot_table,
    normalize_archive_source,
    persist_prediction_profile_snapshots,
    persist_selected_model_decisions,
)
from moduly.mereni.vodomery.database.model_validation import (
    ensure_vodomery_model_validation_tables,
    get_active_vodomery_model_version,
)
from moduly.mereni.vodomery.database.models import (
    VodomeryProfilesAnomaly,
    VodomeryModelSelectionCandidate,
    VodomeryModelSelectionDeviceCandidate,
    VodomeryModelSelectionRun,
    VodomeryModelValidationMetric,
    VodomeryModelValidationRun,
)
from moduly.mereni.vodomery.database.runtime_schema import drop_legacy_identifikace_fk


MODEL_VERSION_BASELINE = 1
MODEL_VERSION_LEARNING = 2
MODEL_VERSION_HIERARCHICAL = 3
MODEL_VERSION_SEASONAL_YEARLY = 4
MODEL_VERSION_LONG_RECENCY = 5
DEFAULT_MODEL_VERSION = MODEL_VERSION_BASELINE
MODEL_SELECTION_TRAINING_MONTHS = 3
MODEL_SELECTION_VALIDATION_MONTHS = 1
MODEL_SELECTION_COVERAGE_THRESHOLD = 0.85
MODEL_EVALUATION_VERSION_OFFSET = 1000
MODEL_ROLLING_BACKTEST_VERSION_OFFSET = 2000
MODEL_ROLLING_BACKTEST_FOLD_COUNT = 8
MODEL_ROLLING_BACKTEST_VALIDATION_DAYS = 7
MODEL_V3_RECENCY_HALF_LIFE_DAYS = 21.0
MODEL_V3_DOW_WEIGHT_TARGET = 4.0
MODEL_V3_WORKDAY_WEIGHT_TARGET = 10.0
MODEL_V3_SLOT_WEIGHT_TARGET = 14.0
MODEL_V4_TRAINING_WINDOW_MONTHS = 12
MODEL_V4_SEASON_WINDOW_DAYS = 45.0
MODEL_V4_SEASONAL_WEIGHT_TARGET = 4.0
MODEL_V4_DOW_WEIGHT_TARGET = 8.0
MODEL_V4_WORKDAY_WEIGHT_TARGET = 18.0
MODEL_V4_SLOT_WEIGHT_TARGET = 28.0
MODEL_V5_TRAINING_WINDOW_MONTHS = 12
MODEL_V5_RECENCY_HALF_LIFE_DAYS = 90.0
VODOMERY_MEDIUM_KEY = "vodomery"
VODOMERY_FORECAST_PERIOD_DEFINITION = PredictionForecastPeriodDefinition(
    cadence=PredictionForecastCadence.WEEKLY,
    period_count=1,
)
VODOMERY_PIPELINE_SETTINGS = PredictionPipelineSettings(
    medium_key=VODOMERY_MEDIUM_KEY,
    forecast_period_definition=VODOMERY_FORECAST_PERIOD_DEFINITION,
    default_training_window_months=MODEL_SELECTION_TRAINING_MONTHS,
    default_validation_window_months=MODEL_SELECTION_VALIDATION_MONTHS,
    candidate_coverage_threshold=MODEL_SELECTION_COVERAGE_THRESHOLD,
    rolling_backtest_fold_count=MODEL_ROLLING_BACKTEST_FOLD_COUNT,
    rolling_validation_period=PredictionForecastPeriodDefinition(
        cadence=PredictionForecastCadence.WEEKLY,
        period_count=1,
    ),
)

STRATEGY_DOW_SLOT_MEAN = "dow_slot_mean"
STRATEGY_WORKDAY_SLOT_MEAN = "workday_slot_mean"
STRATEGY_SLOT_MEAN = "slot_mean"
MODEL_V2_STRATEGIES: tuple[str, ...] = (
    STRATEGY_DOW_SLOT_MEAN,
    STRATEGY_WORKDAY_SLOT_MEAN,
    STRATEGY_SLOT_MEAN,
)
STRATEGY_PRIORITY = {
    STRATEGY_DOW_SLOT_MEAN: 0,
    STRATEGY_WORKDAY_SLOT_MEAN: 1,
    STRATEGY_SLOT_MEAN: 2,
}


@dataclass(frozen=True)
class CandidateModelDefinition:
    model_version: int
    model_name: str
    model_key: str = ""
    training_window_months: int = MODEL_SELECTION_TRAINING_MONTHS
    validation_window_months: int = MODEL_SELECTION_VALIDATION_MONTHS
    selection_enabled: bool = True

    def to_prediction_spec(self) -> PredictionCandidateSpec:
        return PredictionCandidateSpec(
            medium_key=VODOMERY_MEDIUM_KEY,
            model_version=self.model_version,
            model_key=self.model_key or f"model_{self.model_version}",
            model_name=self.model_name,
            training_window_months=self.training_window_months,
            validation_window_months=self.validation_window_months,
            selection_enabled=self.selection_enabled,
        )


@dataclass(frozen=True)
class RebuildWindows:
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    deploy_start: datetime
    deploy_end: datetime


@dataclass(frozen=True)
class ValidationAggregate:
    validation_total_count: int
    matched_validation_count: int
    coverage: float
    mae: float | None
    rmse: float | None
    bias: float | None
    wape: float | None = None
    abs_error_sum: float = 0.0
    squared_error_sum: float = 0.0
    error_sum: float = 0.0
    matched_actual_abs_sum: float = 0.0


@dataclass(frozen=True)
class DeviceModelPerformanceSummary:
    identifikace: str
    model_version: int
    model_name: str
    rolling_backtest_fold_count: int
    rolling_validation_total_count: int
    rolling_matched_validation_count: int
    rolling_coverage: float
    rolling_mae: float | None
    rolling_rmse: float | None
    rolling_bias: float | None
    rolling_wape: float | None
    model_key: str | None = None
    selection_enabled: bool = True
    best_for_identifier: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "identifikace": self.identifikace,
            "model_version": self.model_version,
            "model_key": self.model_key,
            "model_name": self.model_name,
            "selection_enabled": self.selection_enabled,
            "best_for_identifier": self.best_for_identifier,
            "rolling_backtest_fold_count": self.rolling_backtest_fold_count,
            "rolling_validation_total_count": self.rolling_validation_total_count,
            "rolling_matched_validation_count": self.rolling_matched_validation_count,
            "rolling_coverage": round(self.rolling_coverage, 6),
            "rolling_mae": None if self.rolling_mae is None else round(self.rolling_mae, 6),
            "rolling_rmse": None if self.rolling_rmse is None else round(self.rolling_rmse, 6),
            "rolling_bias": None if self.rolling_bias is None else round(self.rolling_bias, 6),
            "rolling_wape": None if self.rolling_wape is None else round(self.rolling_wape, 6),
        }


@dataclass(frozen=True)
class CandidateRollingBacktestResult:
    metrics: PredictionMetricSummary
    device_metrics: tuple[DeviceModelPerformanceSummary, ...] = ()


@dataclass(frozen=True)
class ValidationCandidate:
    identifikace: str
    strategy_key: str
    validation_total_count: int
    matched_validation_count: int
    coverage: float
    mae: float
    rmse: float
    bias: float
    abs_error_sum: float
    squared_error_sum: float
    error_sum: float


@dataclass(frozen=True)
class ModelPerformanceSummary:
    model_version: int
    model_name: str
    validation_total_count: int
    matched_validation_count: int
    coverage: float
    mae: float | None
    rmse: float | None
    bias: float | None
    profile_count: int
    model_key: str | None = None
    training_window_months: int | None = None
    validation_window_months: int | None = None
    selection_enabled: bool = True
    rolling_backtest_fold_count: int = 0
    rolling_validation_total_count: int | None = None
    rolling_matched_validation_count: int | None = None
    rolling_coverage: float | None = None
    rolling_mae: float | None = None
    rolling_rmse: float | None = None
    rolling_bias: float | None = None
    rolling_wape: float | None = None
    selected_device_count: int | None = None
    validation_candidate_count: int | None = None

    def to_prediction_candidate_result(self) -> PredictionCandidateResult:
        return PredictionCandidateResult(
            spec=PredictionCandidateSpec(
                medium_key=VODOMERY_MEDIUM_KEY,
                model_version=self.model_version,
                model_key=self.model_key or f"model_{self.model_version}",
                model_name=self.model_name,
                training_window_months=(
                    self.training_window_months
                    or VODOMERY_PIPELINE_SETTINGS.default_training_window_months
                ),
                validation_window_months=(
                    self.validation_window_months
                    or VODOMERY_PIPELINE_SETTINGS.default_validation_window_months
                ),
                selection_enabled=self.selection_enabled,
            ),
            metrics=PredictionMetricSummary(
                validation_total_count=self.validation_total_count,
                matched_validation_count=self.matched_validation_count,
                coverage=self.coverage,
                mae=self.mae,
                rmse=self.rmse,
                bias=self.bias,
            ),
            profile_count=self.profile_count,
            selected_device_count=self.selected_device_count,
            validation_candidate_count=self.validation_candidate_count,
        )

    def to_dict(self, *, selected: bool) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "model_key": self.model_key,
            "model_name": self.model_name,
            "training_window_months": self.training_window_months,
            "validation_window_months": self.validation_window_months,
            "selection_enabled": self.selection_enabled,
            "rolling_backtest_fold_count": self.rolling_backtest_fold_count,
            "rolling_validation_total_count": self.rolling_validation_total_count,
            "rolling_matched_validation_count": self.rolling_matched_validation_count,
            "rolling_coverage": None if self.rolling_coverage is None else round(self.rolling_coverage, 6),
            "rolling_mae": None if self.rolling_mae is None else round(self.rolling_mae, 6),
            "rolling_rmse": None if self.rolling_rmse is None else round(self.rolling_rmse, 6),
            "rolling_bias": None if self.rolling_bias is None else round(self.rolling_bias, 6),
            "rolling_wape": None if self.rolling_wape is None else round(self.rolling_wape, 6),
            "validation_total_count": self.validation_total_count,
            "matched_validation_count": self.matched_validation_count,
            "coverage": round(self.coverage, 6),
            "mae": None if self.mae is None else round(self.mae, 6),
            "rmse": None if self.rmse is None else round(self.rmse, 6),
            "bias": None if self.bias is None else round(self.bias, 6),
            "profile_count": self.profile_count,
            "selected_device_count": self.selected_device_count,
            "validation_candidate_count": self.validation_candidate_count,
            "selected": selected,
        }


@dataclass(frozen=True)
class VodomeryCandidateModelPlugin:
    definition: CandidateModelDefinition
    rebuild_fn: Callable[..., ModelPerformanceSummary]
    build_backtest_profiles_fn: Callable[..., None]

    @property
    def spec(self) -> PredictionCandidateSpec:
        return self.definition.to_prediction_spec()

    def rebuild_candidate(
        self,
        session,
        *,
        windows: RebuildWindows,
    ) -> ModelPerformanceSummary:
        return self.rebuild_fn(
            session,
            definition=self.definition,
            windows=windows,
        )

    def build_profiles_for_backtest(
        self,
        session,
        *,
        model_version: int,
        windows: RebuildWindows,
    ) -> None:
        self.build_backtest_profiles_fn(
            session,
            definition=self.definition,
            model_version=model_version,
            windows=windows,
        )


def _build_vodomery_pipeline_runner() -> PredictionPipelineRunner[VodomeryCandidateModelPlugin]:
    registry = PredictionCandidateRegistry(
        medium_key=VODOMERY_MEDIUM_KEY,
        plugins=(
            VodomeryCandidateModelPlugin(
                definition=CandidateModelDefinition(
                    model_version=MODEL_VERSION_BASELINE,
                    model_key="baseline_mad",
                    model_name="Model 1 - baseline MAD",
                ),
                rebuild_fn=_rebuild_model_1_candidate,
                build_backtest_profiles_fn=_build_model_1_profiles_for_backtest,
            ),
            VodomeryCandidateModelPlugin(
                definition=CandidateModelDefinition(
                    model_version=MODEL_VERSION_LEARNING,
                    model_key="adaptive_strategy",
                    model_name="Model 2 - adaptive strategy",
                ),
                rebuild_fn=_rebuild_model_2_candidate,
                build_backtest_profiles_fn=_build_model_2_profiles_for_backtest,
            ),
            VodomeryCandidateModelPlugin(
                definition=CandidateModelDefinition(
                    model_version=MODEL_VERSION_HIERARCHICAL,
                    model_key="recency_weighted_blend",
                    model_name="Model 3 - recency weighted blend",
                ),
                rebuild_fn=_rebuild_model_3_candidate,
                build_backtest_profiles_fn=_build_model_3_profiles_for_backtest,
            ),
            VodomeryCandidateModelPlugin(
                definition=CandidateModelDefinition(
                    model_version=MODEL_VERSION_SEASONAL_YEARLY,
                    model_key="seasonal_yearly_blend",
                    model_name="Model 4 - seasonal yearly blend",
                    training_window_months=MODEL_V4_TRAINING_WINDOW_MONTHS,
                    selection_enabled=False,
                ),
                rebuild_fn=_rebuild_model_4_candidate,
                build_backtest_profiles_fn=_build_model_4_profiles_for_backtest,
            ),
            VodomeryCandidateModelPlugin(
                definition=CandidateModelDefinition(
                    model_version=MODEL_VERSION_LONG_RECENCY,
                    model_key="recency_weighted_long_blend",
                    model_name="Model 5 - long recency weighted blend",
                    training_window_months=MODEL_V5_TRAINING_WINDOW_MONTHS,
                    selection_enabled=False,
                ),
                rebuild_fn=_rebuild_model_5_candidate,
                build_backtest_profiles_fn=_build_model_5_profiles_for_backtest,
            ),
        ),
    )
    return PredictionPipelineRunner(
        settings=VODOMERY_PIPELINE_SETTINGS,
        registry=registry,
    )


def get_candidate_model_plugins() -> tuple[VodomeryCandidateModelPlugin, ...]:
    return _build_vodomery_pipeline_runner().list_plugins()


def get_candidate_model_definitions(
    *,
    include_measured_only: bool = True,
) -> tuple[CandidateModelDefinition, ...]:
    return tuple(
        plugin.definition
        for plugin in _build_vodomery_pipeline_runner().list_plugins(
            include_non_selectable=include_measured_only,
        )
    )


def get_candidate_model_specs(
    *,
    include_measured_only: bool = True,
) -> tuple[PredictionCandidateSpec, ...]:
    return _build_vodomery_pipeline_runner().list_specs(
        include_non_selectable=include_measured_only,
    )


def get_candidate_model_versions(
    *,
    include_measured_only: bool = False,
) -> tuple[int, ...]:
    return _build_vodomery_pipeline_runner().list_model_versions(
        include_non_selectable=include_measured_only,
    )


def get_runtime_model_version(*, session=None, default: int = DEFAULT_MODEL_VERSION) -> int:
    return get_active_vodomery_model_version(session=session, default=default)


def build_rebuild_windows(
    reference_time: datetime | None = None,
    *,
    training_window_months: int = MODEL_SELECTION_TRAINING_MONTHS,
    validation_window_months: int = MODEL_SELECTION_VALIDATION_MONTHS,
) -> RebuildWindows:
    return _to_vodomery_rebuild_windows(
        build_prediction_rebuild_windows(
            reference_time=reference_time or utc_now_naive(),
            training_window_months=training_window_months,
            validation_window_months=validation_window_months,
        )
    )


def _to_vodomery_rebuild_windows(
    windows: PredictionRebuildWindows,
) -> RebuildWindows:
    return RebuildWindows(
        train_start=windows.train.start,
        train_end=windows.train.end,
        validation_start=windows.validation.start,
        validation_end=windows.validation.end,
        deploy_start=windows.deploy.start,
        deploy_end=windows.deploy.end,
    )


def build_model_2_rebuild_windows(
    reference_time: datetime | None = None,
    *,
    training_window_months: int = MODEL_SELECTION_TRAINING_MONTHS,
    validation_window_months: int = MODEL_SELECTION_VALIDATION_MONTHS,
) -> RebuildWindows:
    return build_rebuild_windows(
        reference_time=reference_time,
        training_window_months=training_window_months,
        validation_window_months=validation_window_months,
    )


def build_vodomery_weekly_forecast_period(
    reference_time: datetime | None = None,
) -> PredictionForecastPeriod:
    resolved_reference_time = reference_time or utc_now_naive()
    start = _floor_calendar_week_start(resolved_reference_time)
    end = start + timedelta(days=7)
    return PredictionForecastPeriod(
        start=start,
        end=end,
        cadence=PredictionForecastCadence.WEEKLY,
        label=f"{start:%Y-%m-%d} - {end:%Y-%m-%d}",
    )


def _floor_calendar_week_start(value: datetime) -> datetime:
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday())


def _subtract_months(value: datetime, months: int) -> datetime:
    month_index = value.month - months - 1
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def select_best_strategy(
    candidates: Sequence[ValidationCandidate],
    *,
    coverage_threshold: float = MODEL_SELECTION_COVERAGE_THRESHOLD,
) -> ValidationCandidate | None:
    eligible_candidates = [
        candidate
        for candidate in candidates
        if candidate.validation_total_count > 0 and candidate.matched_validation_count > 0
    ]
    if not eligible_candidates:
        return None

    return min(
        eligible_candidates,
        key=lambda candidate: (
            0 if candidate.coverage >= coverage_threshold else 1,
            candidate.mae,
            candidate.rmse,
            abs(candidate.bias),
            -candidate.matched_validation_count,
            STRATEGY_PRIORITY.get(candidate.strategy_key, 999),
        ),
    )


def select_best_model_summary(
    summaries: Sequence[ModelPerformanceSummary],
    *,
    coverage_threshold: float = MODEL_SELECTION_COVERAGE_THRESHOLD,
) -> ModelPerformanceSummary | None:
    summary_by_version = {summary.model_version: summary for summary in summaries}
    selected = _build_vodomery_pipeline_runner().select_best_candidate(
        (
            summary.to_prediction_candidate_result()
            for summary in summary_by_version.values()
        ),
        coverage_threshold=coverage_threshold,
    )
    if selected is None:
        return None
    return summary_by_version[selected.spec.model_version]


def rebuild_profiles(
    model_version: int | None = None,
    reference_time: datetime | None = None,
) -> dict[str, object]:
    rebuild_started_at = perf_counter()
    resolved_reference_time = reference_time or utc_now_naive()
    if model_version is not None:
        definition = _get_candidate_model_definition(model_version)
        if definition is None:
            raise ValueError(f"Neznama verze modelu: {model_version}")
        windows = _build_windows_for_definition(
            definition,
            reference_time=resolved_reference_time,
        )
        drop_legacy_identifikace_fk(VodomeryProfilesAnomaly.__tablename__)
        result = _rebuild_single_candidate_model(definition=definition, windows=windows)
        result["rebuild_duration_seconds"] = round(
            perf_counter() - rebuild_started_at,
            3,
        )
        return result

    ensure_vodomery_model_validation_tables()
    ensure_prediction_selected_model_snapshot_table()
    ensure_prediction_profile_snapshot_table()
    drop_legacy_identifikace_fk(VodomeryProfilesAnomaly.__tablename__)
    windows = build_rebuild_windows(reference_time=resolved_reference_time)
    forecast_period = build_vodomery_weekly_forecast_period(
        reference_time=resolved_reference_time,
    )
    session = get_session_pg()

    try:
        previous_active_model_version = get_runtime_model_version(
            session=session,
            default=DEFAULT_MODEL_VERSION,
        )
        summaries = []
        device_summaries: list[DeviceModelPerformanceSummary] = []
        for definition in get_candidate_model_definitions():
            candidate_windows = _build_windows_for_definition(
                definition,
                reference_time=resolved_reference_time,
            )
            summary = _rebuild_candidate_model(
                session,
                definition=definition,
                windows=candidate_windows,
            )
            rolling_result = _run_candidate_rolling_weekly_backtest_with_devices(
                session,
                definition=definition,
                reference_end=resolved_reference_time,
            )
            summaries.append(
                _summary_with_rolling_backtest(
                    summary,
                    fold_count=MODEL_ROLLING_BACKTEST_FOLD_COUNT,
                    metrics=rolling_result.metrics,
                )
            )
            device_summaries.extend(rolling_result.device_metrics)
        device_summaries = list(_mark_best_device_models(device_summaries))
        selected_summary = select_best_model_summary(summaries)
        if selected_summary is None:
            selected_summary = next(
                (
                    summary
                    for summary in summaries
                    if summary.model_version == previous_active_model_version
                ),
                summaries[0],
            )

        selection_run = _persist_selection_run(
            session,
            windows=windows,
            summaries=summaries,
            selected_summary=selected_summary,
            device_summaries=device_summaries,
        )
        selected_model_decisions = _build_selected_model_decisions(
            device_summaries=device_summaries,
            selected_summary=selected_summary,
            forecast_period=forecast_period,
            selection_run_id=int(selection_run.id),
            selection_mode=SELECTION_MODE_ACTIVE,
        )
        selected_model_snapshot_count = persist_selected_model_decisions(
            session,
            selected_model_decisions,
            selection_mode=SELECTION_MODE_ACTIVE,
        )
        prediction_profile_snapshot_rows = _build_selected_prediction_profile_snapshot_rows(
            session,
            selected_model_decisions,
            require_all_pairs=False,
        )
        prediction_profile_snapshot_count = persist_prediction_profile_snapshots(
            session,
            prediction_profile_snapshot_rows,
        )
        prediction_profile_snapshot_pair_count = _count_profile_snapshot_pairs(
            prediction_profile_snapshot_rows,
        )
        prediction_profile_snapshot_missing_pair_count = max(
            0,
            len(selected_model_decisions) - prediction_profile_snapshot_pair_count,
        )
        session.commit()
        rebuild_duration_seconds = perf_counter() - rebuild_started_at

        result = {
            "selection_run_id": int(selection_run.id),
            "active_model_version": selected_summary.model_version,
            "active_model_name": selected_summary.model_name,
            "previous_active_model_version": previous_active_model_version,
            "previous_active_model_name": _get_model_name(previous_active_model_version),
            "windows": {
                "train_start": windows.train_start,
                "train_end": windows.train_end,
                "validation_start": windows.validation_start,
                "validation_end": windows.validation_end,
                "deploy_start": windows.deploy_start,
                "deploy_end": windows.deploy_end,
            },
            "forecast_period": forecast_period.to_dict(),
            "candidates": [
                summary.to_dict(selected=summary.model_version == selected_summary.model_version)
                for summary in summaries
            ],
            "device_candidates": [
                summary.to_dict()
                for summary in device_summaries
            ],
            "selected_model_snapshot_mode": SELECTION_MODE_ACTIVE,
            "selected_model_snapshot_count": selected_model_snapshot_count,
            "prediction_profile_snapshot_source": ARCHIVE_SOURCE_WEEKLY_REBUILD,
            "prediction_profile_snapshot_count": prediction_profile_snapshot_count,
            "prediction_profile_snapshot_pair_count": prediction_profile_snapshot_pair_count,
            "prediction_profile_snapshot_missing_pair_count": (
                prediction_profile_snapshot_missing_pair_count
            ),
            "selected_model_snapshots": [
                decision.to_dict()
                for decision in selected_model_decisions
            ],
            "rebuild_duration_seconds": round(rebuild_duration_seconds, 3),
        }
        print(
            "Profiles rebuild complete "
            f"(selection_run_id={selection_run.id}, active_model_version={selected_summary.model_version})"
        )
        return result
    finally:
        session.close()


def _rebuild_single_candidate_model(
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> dict[str, object]:
    ensure_vodomery_model_validation_tables()
    session = get_session_pg()
    try:
        summary = _rebuild_candidate_model(session, definition=definition, windows=windows)
        session.commit()
        return {
            "model_version": summary.model_version,
            "model_name": summary.model_name,
            "profile_count": summary.profile_count,
            "validation_total_count": summary.validation_total_count,
            "matched_validation_count": summary.matched_validation_count,
            "coverage": summary.coverage,
            "mae": summary.mae,
            "rmse": summary.rmse,
            "bias": summary.bias,
        }
    finally:
        session.close()


def _build_windows_for_definition(
    definition: CandidateModelDefinition,
    *,
    reference_time: datetime,
) -> RebuildWindows:
    return _to_vodomery_rebuild_windows(
        _build_vodomery_pipeline_runner().build_rebuild_windows(
            reference_time=reference_time,
            spec=definition.to_prediction_spec(),
        )
    )


def _get_candidate_model_definition(model_version: int) -> CandidateModelDefinition | None:
    return next(
        (
            definition
            for definition in get_candidate_model_definitions()
            if definition.model_version == model_version
        ),
        None,
    )


def _get_candidate_model_plugin(model_version: int) -> VodomeryCandidateModelPlugin | None:
    return _build_vodomery_pipeline_runner().get_plugin(model_version)


def _get_model_name(model_version: int) -> str:
    plugin = _get_candidate_model_plugin(model_version)
    if plugin is None:
        return f"Model {model_version}"
    return plugin.spec.model_name


def _rebuild_candidate_model(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    plugin = _get_candidate_model_plugin(definition.model_version)
    if plugin is not None:
        return plugin.rebuild_candidate(session, windows=windows)
    raise ValueError(f"Neznama verze modelu: {definition.model_version}")


def _build_model_performance_summary(
    definition: CandidateModelDefinition,
    *,
    validation: ValidationAggregate,
    profile_count: int,
    selected_device_count: int | None = None,
    validation_candidate_count: int | None = None,
) -> ModelPerformanceSummary:
    return ModelPerformanceSummary(
        model_version=definition.model_version,
        model_name=definition.model_name,
        model_key=definition.model_key,
        training_window_months=definition.training_window_months,
        validation_window_months=definition.validation_window_months,
        selection_enabled=definition.selection_enabled,
        validation_total_count=validation.validation_total_count,
        matched_validation_count=validation.matched_validation_count,
        coverage=validation.coverage,
        mae=validation.mae,
        rmse=validation.rmse,
        bias=validation.bias,
        profile_count=profile_count,
        selected_device_count=selected_device_count,
        validation_candidate_count=validation_candidate_count,
    )


def _summary_with_rolling_backtest(
    summary: ModelPerformanceSummary,
    *,
    fold_count: int,
    metrics: PredictionMetricSummary,
) -> ModelPerformanceSummary:
    return replace(
        summary,
        rolling_backtest_fold_count=fold_count,
        rolling_validation_total_count=metrics.validation_total_count,
        rolling_matched_validation_count=metrics.matched_validation_count,
        rolling_coverage=metrics.coverage,
        rolling_mae=metrics.mae,
        rolling_rmse=metrics.rmse,
        rolling_bias=metrics.bias,
        rolling_wape=metrics.wape,
    )


def _run_candidate_rolling_weekly_backtest(
    session,
    *,
    definition: CandidateModelDefinition,
    reference_end: datetime,
    fold_count: int = MODEL_ROLLING_BACKTEST_FOLD_COUNT,
    validation_days: int = MODEL_ROLLING_BACKTEST_VALIDATION_DAYS,
) -> PredictionMetricSummary:
    folds = build_rolling_weekly_folds(
        reference_end=reference_end,
        fold_count=fold_count,
        training_window_months=definition.training_window_months,
        validation_days=validation_days,
    )
    fold_results: list[ValidationAggregate] = []
    for fold in folds:
        model_version = _build_rolling_backtest_model_version(
            definition.model_version,
            fold.fold_index,
        )
        windows = RebuildWindows(
            train_start=fold.train.start,
            train_end=fold.train.end,
            validation_start=fold.validation.start,
            validation_end=fold.validation.end,
            deploy_start=fold.train.start,
            deploy_end=fold.validation.end,
        )
        try:
            _build_candidate_profiles_for_backtest_fold(
                session,
                definition=definition,
                model_version=model_version,
                windows=windows,
            )
            fold_results.append(
                _evaluate_profiles_on_validation(
                    session,
                    model_version=model_version,
                    windows=windows,
                )
            )
        finally:
            _delete_profiles(session, model_version)

    return _combine_validation_aggregates(fold_results)


def _run_candidate_rolling_weekly_backtest_with_devices(
    session,
    *,
    definition: CandidateModelDefinition,
    reference_end: datetime,
    fold_count: int = MODEL_ROLLING_BACKTEST_FOLD_COUNT,
    validation_days: int = MODEL_ROLLING_BACKTEST_VALIDATION_DAYS,
) -> CandidateRollingBacktestResult:
    folds = build_rolling_weekly_folds(
        reference_end=reference_end,
        fold_count=fold_count,
        training_window_months=definition.training_window_months,
        validation_days=validation_days,
    )
    fold_results: list[ValidationAggregate] = []
    device_fold_results: dict[str, list[ValidationAggregate]] = defaultdict(list)
    for fold in folds:
        model_version = _build_rolling_backtest_model_version(
            definition.model_version,
            fold.fold_index,
        )
        windows = RebuildWindows(
            train_start=fold.train.start,
            train_end=fold.train.end,
            validation_start=fold.validation.start,
            validation_end=fold.validation.end,
            deploy_start=fold.train.start,
            deploy_end=fold.validation.end,
        )
        try:
            _build_candidate_profiles_for_backtest_fold(
                session,
                definition=definition,
                model_version=model_version,
                windows=windows,
            )
            fold_device_metrics = _evaluate_profiles_on_validation_by_identifikace(
                session,
                model_version=model_version,
                windows=windows,
            )
            fold_results.extend(fold_device_metrics.values())
            for identifikace, metrics in fold_device_metrics.items():
                device_fold_results[identifikace].append(metrics)
        finally:
            _delete_profiles(session, model_version)

    return CandidateRollingBacktestResult(
        metrics=_combine_validation_aggregates(fold_results),
        device_metrics=_combine_device_rolling_metrics(
            definition,
            fold_count=fold_count,
            device_fold_results=device_fold_results,
        ),
    )


def _build_rolling_backtest_model_version(model_version: int, fold_index: int) -> int:
    return MODEL_ROLLING_BACKTEST_VERSION_OFFSET + model_version * 100 + fold_index


def _build_model_1_profiles_for_backtest(
    session,
    *,
    definition: CandidateModelDefinition,
    model_version: int,
    windows: RebuildWindows,
) -> None:
    _build_v1_profiles(
        session,
        model_version=model_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
    )


def _build_model_2_profiles_for_backtest(
    session,
    *,
    definition: CandidateModelDefinition,
    model_version: int,
    windows: RebuildWindows,
) -> None:
    _, selected_by_ident = _select_model_2_strategies_for_windows(
        session,
        windows,
    )
    _replace_model_2_profiles(
        session,
        model_version=model_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
        selected_by_ident=selected_by_ident,
    )


def _build_model_3_profiles_for_backtest(
    session,
    *,
    definition: CandidateModelDefinition,
    model_version: int,
    windows: RebuildWindows,
) -> None:
    _build_model_3_profiles(
        session,
        model_version=model_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
        reference_end=windows.validation_start,
    )


def _build_model_4_profiles_for_backtest(
    session,
    *,
    definition: CandidateModelDefinition,
    model_version: int,
    windows: RebuildWindows,
) -> None:
    _build_model_4_profiles(
        session,
        model_version=model_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
        reference_end=windows.validation_start,
    )


def _build_model_5_profiles_for_backtest(
    session,
    *,
    definition: CandidateModelDefinition,
    model_version: int,
    windows: RebuildWindows,
) -> None:
    _build_model_3_profiles(
        session,
        model_version=model_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
        reference_end=windows.validation_start,
        half_life_days=MODEL_V5_RECENCY_HALF_LIFE_DAYS,
    )


def _build_candidate_profiles_for_backtest_fold(
    session,
    *,
    definition: CandidateModelDefinition,
    model_version: int,
    windows: RebuildWindows,
) -> None:
    plugin = _get_candidate_model_plugin(definition.model_version)
    if plugin is not None:
        plugin.build_profiles_for_backtest(
            session,
            model_version=model_version,
            windows=windows,
        )
        return

    raise ValueError(f"Neznama verze modelu: {definition.model_version}")


def _combine_validation_aggregates(
    aggregates: Sequence[ValidationAggregate],
) -> PredictionMetricSummary:
    validation_total_count = sum(item.validation_total_count for item in aggregates)
    matched_validation_count = sum(item.matched_validation_count for item in aggregates)
    if validation_total_count <= 0:
        return PredictionMetricSummary(
            validation_total_count=0,
            matched_validation_count=0,
            coverage=0.0,
            mae=None,
            rmse=None,
            bias=None,
            wape=None,
        )

    coverage = matched_validation_count / validation_total_count
    if matched_validation_count <= 0:
        return PredictionMetricSummary(
            validation_total_count=validation_total_count,
            matched_validation_count=0,
            coverage=coverage,
            mae=None,
            rmse=None,
            bias=None,
            wape=None,
        )

    abs_error_sum = sum(item.abs_error_sum for item in aggregates)
    squared_error_sum = sum(item.squared_error_sum for item in aggregates)
    error_sum = sum(item.error_sum for item in aggregates)
    matched_actual_abs_sum = sum(item.matched_actual_abs_sum for item in aggregates)
    return PredictionMetricSummary(
        validation_total_count=validation_total_count,
        matched_validation_count=matched_validation_count,
        coverage=coverage,
        mae=abs_error_sum / matched_validation_count,
        rmse=(squared_error_sum / matched_validation_count) ** 0.5,
        bias=error_sum / matched_validation_count,
        wape=(
            None
            if matched_actual_abs_sum <= 0
            else abs_error_sum / matched_actual_abs_sum
        ),
    )


def _combine_device_rolling_metrics(
    definition: CandidateModelDefinition,
    *,
    fold_count: int,
    device_fold_results: dict[str, list[ValidationAggregate]],
) -> tuple[DeviceModelPerformanceSummary, ...]:
    rows: list[DeviceModelPerformanceSummary] = []
    for identifikace, aggregates in sorted(device_fold_results.items()):
        metrics = _combine_validation_aggregates(aggregates)
        rows.append(
            DeviceModelPerformanceSummary(
                identifikace=identifikace,
                model_version=definition.model_version,
                model_key=definition.model_key,
                model_name=definition.model_name,
                selection_enabled=definition.selection_enabled,
                rolling_backtest_fold_count=fold_count,
                rolling_validation_total_count=metrics.validation_total_count,
                rolling_matched_validation_count=metrics.matched_validation_count,
                rolling_coverage=metrics.coverage,
                rolling_mae=metrics.mae,
                rolling_rmse=metrics.rmse,
                rolling_bias=metrics.bias,
                rolling_wape=metrics.wape,
            )
        )
    return tuple(rows)


def _mark_best_device_models(
    device_summaries: Sequence[DeviceModelPerformanceSummary],
    *,
    coverage_threshold: float = MODEL_SELECTION_COVERAGE_THRESHOLD,
) -> tuple[DeviceModelPerformanceSummary, ...]:
    best_by_identifikace = _select_best_device_model_by_identifikace(
        device_summaries,
        coverage_threshold=coverage_threshold,
    )
    return tuple(
        replace(
            summary,
            best_for_identifier=(
                best_by_identifikace.get(summary.identifikace) == summary
            ),
        )
        for summary in device_summaries
    )


def _select_best_device_model_by_identifikace(
    device_summaries: Sequence[DeviceModelPerformanceSummary],
    *,
    coverage_threshold: float = MODEL_SELECTION_COVERAGE_THRESHOLD,
) -> dict[str, DeviceModelPerformanceSummary]:
    summaries_by_identifikace: dict[str, list[DeviceModelPerformanceSummary]] = defaultdict(list)
    for summary in device_summaries:
        if (
            summary.rolling_validation_total_count > 0
            and summary.rolling_matched_validation_count > 0
            and summary.rolling_mae is not None
            and summary.rolling_rmse is not None
            and summary.rolling_bias is not None
        ):
            summaries_by_identifikace[summary.identifikace].append(summary)

    return {
        identifikace: min(
            summaries,
            key=lambda summary: (
                0 if summary.rolling_coverage >= coverage_threshold else 1,
                summary.rolling_mae,
                summary.rolling_rmse,
                abs(summary.rolling_bias),
                -summary.rolling_matched_validation_count,
                0 if summary.selection_enabled else 1,
                summary.model_version,
            ),
        )
        for identifikace, summaries in summaries_by_identifikace.items()
        if summaries
    }


def _build_selected_model_decisions(
    *,
    device_summaries: Sequence[DeviceModelPerformanceSummary],
    selected_summary: ModelPerformanceSummary,
    forecast_period: PredictionForecastPeriod,
    selection_run_id: int,
    selection_mode: str = SELECTION_MODE_ACTIVE,
    coverage_threshold: float = MODEL_SELECTION_COVERAGE_THRESHOLD,
) -> tuple[PredictionSelectedModelDecision, ...]:
    all_identifiers = sorted({summary.identifikace for summary in device_summaries})
    valid_by_identifier: dict[str, list[DeviceModelPerformanceSummary]] = defaultdict(list)
    best_overall_by_identifier: dict[str, DeviceModelPerformanceSummary] = {}

    for summary in device_summaries:
        if summary.best_for_identifier:
            best_overall_by_identifier[summary.identifikace] = summary
        if _device_summary_has_selection_metrics(summary):
            valid_by_identifier[summary.identifikace].append(summary)

    decisions: list[PredictionSelectedModelDecision] = []
    for identifikace in all_identifiers:
        valid_summaries = valid_by_identifier.get(identifikace, [])
        eligible_summaries = [
            summary
            for summary in valid_summaries
            if summary.selection_enabled
        ]
        threshold_summaries = [
            summary
            for summary in eligible_summaries
            if summary.rolling_coverage >= coverage_threshold
        ]

        if threshold_summaries:
            selected_device_summary = min(
                threshold_summaries,
                key=_device_summary_selection_key,
            )
            fallback_reason = PredictionSelectionFallbackReason.NONE
            selected_metrics = _device_summary_to_metric_summary(selected_device_summary)
            selected_model_version = selected_device_summary.model_version
            selected_model_key = _device_model_key(selected_device_summary)
            selected_model_name = selected_device_summary.model_name
        else:
            selected_device_summary = None
            fallback_reason = _resolve_device_selection_fallback_reason(
                valid_summaries=valid_summaries,
                eligible_summaries=eligible_summaries,
            )
            global_device_summary = _find_device_summary_for_model(
                valid_summaries,
                model_version=selected_summary.model_version,
            )
            selected_metrics = (
                None
                if global_device_summary is None
                else _device_summary_to_metric_summary(global_device_summary)
            )
            selected_model_version = selected_summary.model_version
            selected_model_key = _model_summary_key(selected_summary)
            selected_model_name = selected_summary.model_name

        best_overall = best_overall_by_identifier.get(identifikace)
        decisions.append(
            PredictionSelectedModelDecision(
                medium_key=VODOMERY_MEDIUM_KEY,
                identifier=identifikace,
                forecast_period=forecast_period,
                selection_run_id=selection_run_id,
                selected_model_version=selected_model_version,
                selected_model_key=selected_model_key,
                selected_model_name=selected_model_name,
                global_model_version=selected_summary.model_version,
                global_model_key=_model_summary_key(selected_summary),
                global_model_name=selected_summary.model_name,
                fallback_reason=fallback_reason,
                metrics=selected_metrics,
                metadata={
                    "selection_policy": "eligible_rolling_wape_min_coverage",
                    "selection_mode": selection_mode,
                    "coverage_threshold": coverage_threshold,
                    "best_overall_model_version": (
                        None if best_overall is None else best_overall.model_version
                    ),
                    "best_overall_model_key": (
                        None if best_overall is None else _device_model_key(best_overall)
                    ),
                    "best_overall_selection_enabled": (
                        None if best_overall is None else best_overall.selection_enabled
                    ),
                    "selected_from_device_metrics": selected_device_summary is not None,
                },
            )
        )

    return tuple(decisions)


def _persist_selected_prediction_profile_snapshots(
    session,
    decisions: Sequence[PredictionSelectedModelDecision],
    *,
    archive_source: str = ARCHIVE_SOURCE_WEEKLY_REBUILD,
    archive_version: int = 1,
    archive_run_id: str | None = None,
) -> int:
    rows = _build_selected_prediction_profile_snapshot_rows(
        session,
        decisions,
        archive_source=archive_source,
        archive_version=archive_version,
        archive_run_id=archive_run_id,
    )
    return persist_prediction_profile_snapshots(session, rows)


def _build_selected_prediction_profile_snapshot_rows(
    session,
    decisions: Sequence[PredictionSelectedModelDecision],
    *,
    archive_source: str = ARCHIVE_SOURCE_WEEKLY_REBUILD,
    archive_version: int = 1,
    archive_run_id: str | None = None,
    require_all_pairs: bool = True,
) -> tuple[dict[str, object], ...]:
    if not decisions:
        return ()
    if archive_version <= 0:
        raise ValueError("Prediction profile archive version must be positive.")

    normalized_archive_source = normalize_archive_source(archive_source)
    selected_pairs = {
        (decision.identifier, int(decision.selected_model_version)): decision
        for decision in decisions
    }
    identifiers = sorted({identifier for identifier, _ in selected_pairs})
    model_versions = sorted({model_version for _, model_version in selected_pairs})

    profiles = (
        session.execute(
            select(VodomeryProfilesAnomaly).where(
                VodomeryProfilesAnomaly.identifikace.in_(identifiers),
                VodomeryProfilesAnomaly.model_version.in_(model_versions),
            )
        )
        .scalars()
        .all()
    )

    rows: list[dict[str, object]] = []
    archived_pairs: set[tuple[str, int]] = set()
    for profile in profiles:
        pair = (profile.identifikace, int(profile.model_version))
        decision = selected_pairs.get(pair)
        if decision is None:
            continue

        archived_pairs.add(pair)
        forecast_period = decision.forecast_period
        rows.append(
            {
                "medium_key": decision.medium_key,
                "identifier": decision.identifier,
                "forecast_period_start": forecast_period.start,
                "forecast_period_end": forecast_period.end,
                "forecast_cadence": forecast_period.cadence.value,
                "forecast_period_label": forecast_period.label,
                "archive_source": normalized_archive_source,
                "archive_version": archive_version,
                "selection_mode": SELECTION_MODE_ACTIVE,
                "selection_run_id": decision.selection_run_id,
                "archive_run_id": archive_run_id,
                "model_version": decision.selected_model_version,
                "model_key": decision.selected_model_key,
                "model_name": decision.selected_model_name,
                "global_model_version": decision.global_model_version,
                "global_model_key": decision.global_model_key,
                "global_model_name": decision.global_model_name,
                "uses_fallback": decision.uses_fallback,
                "fallback_reason": decision.fallback_reason.value,
                "interval_minutes": int(profile.interval_minutes),
                "day_of_week": int(profile.day_of_week),
                "slot": int(profile.slot),
                "expected_mean": float(profile.mean),
                "expected_median": (
                    None if profile.median is None else float(profile.median)
                ),
                "expected_p10": None if profile.p10 is None else float(profile.p10),
                "expected_p90": None if profile.p90 is None else float(profile.p90),
                "expected_std": None if profile.std is None else float(profile.std),
                "sample_size": (
                    None if profile.sample_size is None else int(profile.sample_size)
                ),
                "source_profile_created_at": profile.created_at,
            }
        )

    missing_pair_count = len(set(selected_pairs) - archived_pairs)
    if missing_pair_count and require_all_pairs:
        raise RuntimeError(
            "Selected prediction profile archive is missing source profiles "
            f"for {missing_pair_count} identifier/model pairs."
        )

    return tuple(rows)


def _count_profile_snapshot_pairs(rows: Sequence[dict[str, object]]) -> int:
    return len(
        {
            (str(row["identifier"]), int(row["model_version"]))
            for row in rows
        }
    )


def _device_summary_has_selection_metrics(
    summary: DeviceModelPerformanceSummary,
) -> bool:
    return (
        summary.rolling_validation_total_count > 0
        and summary.rolling_matched_validation_count > 0
        and summary.rolling_mae is not None
        and summary.rolling_rmse is not None
        and summary.rolling_bias is not None
        and summary.rolling_wape is not None
    )


def _device_summary_selection_key(
    summary: DeviceModelPerformanceSummary,
) -> tuple[float, float, float, float, int, int]:
    return (
        float(summary.rolling_wape),
        float(summary.rolling_mae),
        float(summary.rolling_rmse),
        abs(float(summary.rolling_bias)),
        -summary.rolling_matched_validation_count,
        summary.model_version,
    )


def _resolve_device_selection_fallback_reason(
    *,
    valid_summaries: Sequence[DeviceModelPerformanceSummary],
    eligible_summaries: Sequence[DeviceModelPerformanceSummary],
) -> PredictionSelectionFallbackReason:
    if not valid_summaries:
        return PredictionSelectionFallbackReason.NO_IDENTIFIER_METRICS
    if not eligible_summaries:
        return PredictionSelectionFallbackReason.NO_ELIGIBLE_CANDIDATE
    return PredictionSelectionFallbackReason.BELOW_COVERAGE_THRESHOLD


def _find_device_summary_for_model(
    summaries: Sequence[DeviceModelPerformanceSummary],
    *,
    model_version: int,
) -> DeviceModelPerformanceSummary | None:
    for summary in summaries:
        if summary.model_version == model_version:
            return summary
    return None


def _device_summary_to_metric_summary(
    summary: DeviceModelPerformanceSummary,
) -> PredictionMetricSummary:
    return PredictionMetricSummary(
        validation_total_count=summary.rolling_validation_total_count,
        matched_validation_count=summary.rolling_matched_validation_count,
        coverage=summary.rolling_coverage,
        mae=summary.rolling_mae,
        rmse=summary.rolling_rmse,
        bias=summary.rolling_bias,
        wape=summary.rolling_wape,
    )


def _device_model_key(summary: DeviceModelPerformanceSummary) -> str:
    return summary.model_key or f"model_{summary.model_version}"


def _model_summary_key(summary: ModelPerformanceSummary) -> str:
    return summary.model_key or f"model_{summary.model_version}"


def _rebuild_model_1_candidate(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    evaluation_version = _build_evaluation_model_version(definition.model_version)
    _build_v1_profiles(
        session,
        model_version=evaluation_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
    )
    validation = _evaluate_profiles_on_validation(
        session,
        model_version=evaluation_version,
        windows=windows,
    )
    _delete_profiles(session, evaluation_version)

    _build_v1_profiles(
        session,
        model_version=definition.model_version,
        data_start=windows.deploy_start,
        data_end=windows.deploy_end,
    )
    profile_count = _count_profiles(session, definition.model_version)
    return _build_model_performance_summary(
        definition,
        validation=validation,
        profile_count=profile_count,
    )


def _rebuild_model_2_candidate(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    run, candidates, selected_by_ident = _prepare_model_2_strategy_selection(
        session,
        windows=windows,
    )
    evaluation_version = _build_evaluation_model_version(definition.model_version)
    _replace_model_2_profiles(
        session,
        model_version=evaluation_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
        selected_by_ident=selected_by_ident,
    )
    validation = _evaluate_profiles_on_validation(
        session,
        model_version=evaluation_version,
        windows=windows,
    )
    _delete_profiles(session, evaluation_version)

    _replace_model_2_profiles(
        session,
        model_version=definition.model_version,
        data_start=windows.deploy_start,
        data_end=windows.deploy_end,
        selected_by_ident=selected_by_ident,
    )
    profile_count = _count_profiles(session, definition.model_version)
    run.selected_device_count = len(selected_by_ident)
    run.inserted_profile_count = profile_count

    return _build_model_performance_summary(
        definition,
        validation=validation,
        profile_count=profile_count,
        selected_device_count=len(selected_by_ident),
        validation_candidate_count=len(candidates),
    )


def _rebuild_model_3_candidate(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    evaluation_version = _build_evaluation_model_version(definition.model_version)
    _build_model_3_profiles(
        session,
        model_version=evaluation_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
        reference_end=windows.validation_start,
    )
    validation = _evaluate_profiles_on_validation(
        session,
        model_version=evaluation_version,
        windows=windows,
    )
    _delete_profiles(session, evaluation_version)

    _build_model_3_profiles(
        session,
        model_version=definition.model_version,
        data_start=windows.deploy_start,
        data_end=windows.deploy_end,
        reference_end=windows.deploy_end,
    )
    profile_count = _count_profiles(session, definition.model_version)
    return _build_model_performance_summary(
        definition,
        validation=validation,
        profile_count=profile_count,
    )


def _rebuild_model_4_candidate(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    evaluation_version = _build_evaluation_model_version(definition.model_version)
    _build_model_4_profiles(
        session,
        model_version=evaluation_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
        reference_end=windows.validation_start,
    )
    validation = _evaluate_profiles_on_validation(
        session,
        model_version=evaluation_version,
        windows=windows,
    )
    _delete_profiles(session, evaluation_version)

    deploy_data_start = _subtract_months(
        windows.deploy_end,
        definition.training_window_months,
    )
    _build_model_4_profiles(
        session,
        model_version=definition.model_version,
        data_start=deploy_data_start,
        data_end=windows.deploy_end,
        reference_end=windows.deploy_end,
    )
    profile_count = _count_profiles(session, definition.model_version)
    return _build_model_performance_summary(
        definition,
        validation=validation,
        profile_count=profile_count,
    )


def _rebuild_model_5_candidate(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    evaluation_version = _build_evaluation_model_version(definition.model_version)
    _build_model_3_profiles(
        session,
        model_version=evaluation_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
        reference_end=windows.validation_start,
        half_life_days=MODEL_V5_RECENCY_HALF_LIFE_DAYS,
    )
    validation = _evaluate_profiles_on_validation(
        session,
        model_version=evaluation_version,
        windows=windows,
    )
    _delete_profiles(session, evaluation_version)

    deploy_data_start = _subtract_months(
        windows.deploy_end,
        definition.training_window_months,
    )
    _build_model_3_profiles(
        session,
        model_version=definition.model_version,
        data_start=deploy_data_start,
        data_end=windows.deploy_end,
        reference_end=windows.deploy_end,
        half_life_days=MODEL_V5_RECENCY_HALF_LIFE_DAYS,
    )
    profile_count = _count_profiles(session, definition.model_version)
    return _build_model_performance_summary(
        definition,
        validation=validation,
        profile_count=profile_count,
    )


def _persist_selection_run(
    session,
    *,
    windows: RebuildWindows,
    summaries: Sequence[ModelPerformanceSummary],
    selected_summary: ModelPerformanceSummary,
    device_summaries: Sequence[DeviceModelPerformanceSummary] = (),
) -> VodomeryModelSelectionRun:
    selection_run = VodomeryModelSelectionRun(
        train_start=windows.train_start,
        train_end=windows.train_end,
        validation_start=windows.validation_start,
        validation_end=windows.validation_end,
        deploy_start=windows.deploy_start,
        deploy_end=windows.deploy_end,
        selected_model_version=selected_summary.model_version,
        selected_model_name=selected_summary.model_name,
    )
    session.add(selection_run)
    session.flush()

    session.execute(
        insert(VodomeryModelSelectionCandidate),
        [
            {
                "selection_run_id": int(selection_run.id),
                "model_version": summary.model_version,
                "model_key": summary.model_key,
                "model_name": summary.model_name,
                "training_window_months": summary.training_window_months,
                "validation_window_months": summary.validation_window_months,
                "selection_enabled": summary.selection_enabled,
                "validation_total_count": summary.validation_total_count,
                "matched_validation_count": summary.matched_validation_count,
                "coverage": round(summary.coverage, 6),
                "mae": None if summary.mae is None else round(summary.mae, 6),
                "rmse": None if summary.rmse is None else round(summary.rmse, 6),
                "bias": None if summary.bias is None else round(summary.bias, 6),
                "rolling_backtest_fold_count": summary.rolling_backtest_fold_count,
                "rolling_validation_total_count": summary.rolling_validation_total_count,
                "rolling_matched_validation_count": summary.rolling_matched_validation_count,
                "rolling_coverage": (
                    None
                    if summary.rolling_coverage is None
                    else round(summary.rolling_coverage, 6)
                ),
                "rolling_mae": (
                    None
                    if summary.rolling_mae is None
                    else round(summary.rolling_mae, 6)
                ),
                "rolling_rmse": (
                    None
                    if summary.rolling_rmse is None
                    else round(summary.rolling_rmse, 6)
                ),
                "rolling_bias": (
                    None
                    if summary.rolling_bias is None
                    else round(summary.rolling_bias, 6)
                ),
                "rolling_wape": (
                    None
                    if summary.rolling_wape is None
                    else round(summary.rolling_wape, 6)
                ),
                "profile_count": summary.profile_count,
                "selected": summary.model_version == selected_summary.model_version,
            }
            for summary in summaries
        ],
    )
    if device_summaries:
        session.execute(
            insert(VodomeryModelSelectionDeviceCandidate),
            [
                {
                    "selection_run_id": int(selection_run.id),
                    "identifikace": summary.identifikace,
                    "model_version": summary.model_version,
                    "model_key": summary.model_key,
                    "model_name": summary.model_name,
                    "selection_enabled": summary.selection_enabled,
                    "rolling_backtest_fold_count": summary.rolling_backtest_fold_count,
                    "rolling_validation_total_count": summary.rolling_validation_total_count,
                    "rolling_matched_validation_count": summary.rolling_matched_validation_count,
                    "rolling_coverage": round(summary.rolling_coverage, 6),
                    "rolling_mae": (
                        None
                        if summary.rolling_mae is None
                        else round(summary.rolling_mae, 6)
                    ),
                    "rolling_rmse": (
                        None
                        if summary.rolling_rmse is None
                        else round(summary.rolling_rmse, 6)
                    ),
                    "rolling_bias": (
                        None
                        if summary.rolling_bias is None
                        else round(summary.rolling_bias, 6)
                    ),
                    "rolling_wape": (
                        None
                        if summary.rolling_wape is None
                        else round(summary.rolling_wape, 6)
                    ),
                    "best_for_identifier": summary.best_for_identifier,
                }
                for summary in device_summaries
            ],
        )
    return selection_run


def _prepare_model_2_strategy_selection(
    session,
    *,
    windows: RebuildWindows,
) -> tuple[VodomeryModelValidationRun, list[ValidationCandidate], dict[str, ValidationCandidate]]:
    run = VodomeryModelValidationRun(
        model_version=MODEL_VERSION_LEARNING,
        train_start=windows.train_start,
        train_end=windows.train_end,
        validation_start=windows.validation_start,
        validation_end=windows.validation_end,
        deploy_start=windows.deploy_start,
        deploy_end=windows.deploy_end,
    )
    session.add(run)
    session.flush()

    candidates, selected_by_ident = _select_model_2_strategies_for_windows(
        session,
        windows,
    )
    _persist_validation_metrics(
        session,
        run_id=int(run.id),
        model_version=MODEL_VERSION_LEARNING,
        candidates=candidates,
        selected_by_ident=selected_by_ident,
    )
    return run, candidates, selected_by_ident


def _select_model_2_strategies_for_windows(
    session,
    windows: RebuildWindows,
) -> tuple[list[ValidationCandidate], dict[str, ValidationCandidate]]:
    candidates = _load_model_2_candidate_metrics(session, windows)
    selected_by_ident: dict[str, ValidationCandidate] = {}
    candidates_by_ident: dict[str, list[ValidationCandidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_ident[candidate.identifikace].append(candidate)

    for identifikace, ident_candidates in candidates_by_ident.items():
        best_candidate = select_best_strategy(ident_candidates)
        if best_candidate is not None:
            selected_by_ident[identifikace] = best_candidate

    return candidates, selected_by_ident


def _build_evaluation_model_version(model_version: int) -> int:
    return MODEL_EVALUATION_VERSION_OFFSET + model_version


def _delete_profiles(session, model_version: int) -> None:
    session.execute(
        text(
            """
            DELETE FROM monitoring.vodomery_anomaly_profiles
            WHERE model_version = :model_version
            """
        ),
        {"model_version": model_version},
    )


def _count_profiles(session, model_version: int) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM monitoring.vodomery_anomaly_profiles
                WHERE model_version = :model_version
                """
            ),
            {"model_version": model_version},
        ).scalar_one()
    )


def _build_v1_profiles(
    session,
    *,
    model_version: int,
    data_start: datetime | None,
    data_end: datetime | None,
) -> None:
    _delete_profiles(session, model_version)
    session.execute(
        text(
            """
            WITH base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    delta
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND (:data_start IS NULL OR date >= :data_start)
                    AND (:data_end IS NULL OR date < :data_end)
            ),
            stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    COUNT(*) AS sample_size
                FROM base
                GROUP BY identifikace, interval_minutes, day_of_week, slot
            ),
            mad AS (
                SELECT
                    b.identifikace,
                    b.interval_minutes,
                    b.day_of_week,
                    b.slot,
                    percentile_cont(0.5)
                        WITHIN GROUP (ORDER BY abs(b.delta - s.median))
                        AS mad
                FROM base b
                JOIN stats s USING (identifikace, interval_minutes, day_of_week, slot)
                GROUP BY b.identifikace, b.interval_minutes, b.day_of_week, b.slot
            )
            INSERT INTO monitoring.vodomery_anomaly_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                median,
                mean,
                p10,
                p90,
                std,
                model_version,
                sample_size
            )
            SELECT
                s.identifikace,
                s.interval_minutes,
                s.day_of_week,
                s.slot,
                s.median,
                s.mean,
                s.p10,
                s.p90,
                GREATEST(1.4826 * COALESCE(m.mad, 0.0), 0.0001) AS std,
                :model_version,
                s.sample_size
            FROM stats s
            LEFT JOIN mad m
                USING (identifikace, interval_minutes, day_of_week, slot)
            """
        ),
        {
            "model_version": model_version,
            "data_start": data_start,
            "data_end": data_end,
        },
    )


def _build_model_3_profiles(
    session,
    *,
    model_version: int,
    data_start: datetime,
    data_end: datetime,
    reference_end: datetime,
    half_life_days: float = MODEL_V3_RECENCY_HALF_LIFE_DAYS,
    dow_weight_target: float = MODEL_V3_DOW_WEIGHT_TARGET,
    workday_weight_target: float = MODEL_V3_WORKDAY_WEIGHT_TARGET,
    slot_weight_target: float = MODEL_V3_SLOT_WEIGHT_TARGET,
) -> None:
    # Blend specific and broader profiles based on recent effective sample size
    # so sparse slots keep coverage without hard-switching the whole device.
    _delete_profiles(session, model_version)
    session.execute(
        text(
            """
            WITH base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    CASE WHEN day_of_week BETWEEN 0 AND 4 THEN TRUE ELSE FALSE END AS is_workday,
                    delta,
                    GREATEST(
                        EXTRACT(EPOCH FROM (:reference_end - date)) / 86400.0,
                        0.0
                    ) AS age_days
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :data_start
                    AND date < :data_end
            ),
            weighted_base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    is_workday,
                    delta,
                    EXP(-LN(2.0) * age_days / :half_life_days) AS recency_weight
                FROM base
            ),
            interval_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    SUM(recency_weight * delta) / NULLIF(SUM(recency_weight), 0.0) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size,
                    COALESCE(SUM(recency_weight), 0.0) AS weighted_sample_size
                FROM weighted_base
                GROUP BY identifikace, interval_minutes
            ),
            slot_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    SUM(recency_weight * delta) / NULLIF(SUM(recency_weight), 0.0) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size,
                    COALESCE(SUM(recency_weight), 0.0) AS weighted_sample_size
                FROM weighted_base
                GROUP BY identifikace, interval_minutes, slot
            ),
            workday_slot_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    is_workday,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    SUM(recency_weight * delta) / NULLIF(SUM(recency_weight), 0.0) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size,
                    COALESCE(SUM(recency_weight), 0.0) AS weighted_sample_size
                FROM weighted_base
                GROUP BY identifikace, interval_minutes, is_workday, slot
            ),
            dow_slot_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    SUM(recency_weight * delta) / NULLIF(SUM(recency_weight), 0.0) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size,
                    COALESCE(SUM(recency_weight), 0.0) AS weighted_sample_size
                FROM weighted_base
                GROUP BY identifikace, interval_minutes, day_of_week, slot
            ),
            slots AS (
                SELECT
                    interval_stats.identifikace,
                    interval_stats.interval_minutes,
                    generated_slots.slot
                FROM interval_stats
                CROSS JOIN LATERAL generate_series(
                    0,
                    GREATEST(
                        COALESCE(
                            CAST(FLOOR(1440.0 / NULLIF(interval_stats.interval_minutes, 0)) AS integer),
                            1
                        ) - 1,
                        0
                    )
                ) AS generated_slots(slot)
            ),
            days(day_of_week, is_workday) AS (
                VALUES
                    (0, TRUE),
                    (1, TRUE),
                    (2, TRUE),
                    (3, TRUE),
                    (4, TRUE),
                    (5, FALSE),
                    (6, FALSE)
            ),
            grid AS (
                SELECT
                    slots.identifikace,
                    slots.interval_minutes,
                    days.day_of_week,
                    days.is_workday,
                    slots.slot
                FROM slots
                CROSS JOIN days
            ),
            blended AS (
                SELECT
                    grid.identifikace,
                    grid.interval_minutes,
                    grid.day_of_week,
                    grid.slot,
                    interval_stats.median AS interval_median,
                    interval_stats.mean AS interval_mean,
                    interval_stats.p10 AS interval_p10,
                    interval_stats.p90 AS interval_p90,
                    interval_stats.std AS interval_std,
                    interval_stats.sample_size AS interval_sample_size,
                    slot_stats.median AS slot_median,
                    slot_stats.mean AS slot_mean,
                    slot_stats.p10 AS slot_p10,
                    slot_stats.p90 AS slot_p90,
                    slot_stats.std AS slot_std,
                    slot_stats.sample_size AS slot_sample_size,
                    workday_slot_stats.median AS workday_median,
                    workday_slot_stats.mean AS workday_mean,
                    workday_slot_stats.p10 AS workday_p10,
                    workday_slot_stats.p90 AS workday_p90,
                    workday_slot_stats.std AS workday_std,
                    workday_slot_stats.sample_size AS workday_sample_size,
                    dow_slot_stats.median AS dow_median,
                    dow_slot_stats.mean AS dow_mean,
                    dow_slot_stats.p10 AS dow_p10,
                    dow_slot_stats.p90 AS dow_p90,
                    dow_slot_stats.std AS dow_std,
                    dow_slot_stats.sample_size AS dow_sample_size,
                    LEAST(
                        COALESCE(slot_stats.weighted_sample_size, 0.0) / :slot_weight_target,
                        1.0
                    ) AS slot_trust,
                    LEAST(
                        COALESCE(workday_slot_stats.weighted_sample_size, 0.0) / :workday_weight_target,
                        1.0
                    ) AS workday_trust,
                    LEAST(
                        COALESCE(dow_slot_stats.weighted_sample_size, 0.0) / :dow_weight_target,
                        1.0
                    ) AS dow_trust
                FROM grid
                JOIN interval_stats
                    ON interval_stats.identifikace = grid.identifikace
                    AND interval_stats.interval_minutes = grid.interval_minutes
                LEFT JOIN slot_stats
                    ON slot_stats.identifikace = grid.identifikace
                    AND slot_stats.interval_minutes = grid.interval_minutes
                    AND slot_stats.slot = grid.slot
                LEFT JOIN workday_slot_stats
                    ON workday_slot_stats.identifikace = grid.identifikace
                    AND workday_slot_stats.interval_minutes = grid.interval_minutes
                    AND workday_slot_stats.is_workday = grid.is_workday
                    AND workday_slot_stats.slot = grid.slot
                LEFT JOIN dow_slot_stats
                    ON dow_slot_stats.identifikace = grid.identifikace
                    AND dow_slot_stats.interval_minutes = grid.interval_minutes
                    AND dow_slot_stats.day_of_week = grid.day_of_week
                    AND dow_slot_stats.slot = grid.slot
            ),
            profiles AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    dow_trust * COALESCE(dow_median, workday_median, slot_median, interval_median)
                        + (1.0 - dow_trust) * (
                            workday_trust * COALESCE(workday_median, slot_median, interval_median)
                            + (1.0 - workday_trust) * (
                                slot_trust * COALESCE(slot_median, interval_median)
                                + (1.0 - slot_trust) * interval_median
                            )
                        ) AS median,
                    dow_trust * COALESCE(dow_mean, workday_mean, slot_mean, interval_mean)
                        + (1.0 - dow_trust) * (
                            workday_trust * COALESCE(workday_mean, slot_mean, interval_mean)
                            + (1.0 - workday_trust) * (
                                slot_trust * COALESCE(slot_mean, interval_mean)
                                + (1.0 - slot_trust) * interval_mean
                            )
                        ) AS mean,
                    dow_trust * COALESCE(dow_p10, workday_p10, slot_p10, interval_p10)
                        + (1.0 - dow_trust) * (
                            workday_trust * COALESCE(workday_p10, slot_p10, interval_p10)
                            + (1.0 - workday_trust) * (
                                slot_trust * COALESCE(slot_p10, interval_p10)
                                + (1.0 - slot_trust) * interval_p10
                            )
                        ) AS p10,
                    dow_trust * COALESCE(dow_p90, workday_p90, slot_p90, interval_p90)
                        + (1.0 - dow_trust) * (
                            workday_trust * COALESCE(workday_p90, slot_p90, interval_p90)
                            + (1.0 - workday_trust) * (
                                slot_trust * COALESCE(slot_p90, interval_p90)
                                + (1.0 - slot_trust) * interval_p90
                            )
                        ) AS p90,
                    dow_trust * COALESCE(dow_std, workday_std, slot_std, interval_std)
                        + (1.0 - dow_trust) * (
                            workday_trust * COALESCE(workday_std, slot_std, interval_std)
                            + (1.0 - workday_trust) * (
                                slot_trust * COALESCE(slot_std, interval_std)
                                + (1.0 - slot_trust) * interval_std
                            )
                        ) AS std,
                    GREATEST(
                        COALESCE(dow_sample_size, 0),
                        COALESCE(workday_sample_size, 0),
                        COALESCE(slot_sample_size, 0),
                        interval_sample_size
                    ) AS sample_size
                FROM blended
            )
            INSERT INTO monitoring.vodomery_anomaly_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                median,
                mean,
                p10,
                p90,
                std,
                model_version,
                sample_size
            )
            SELECT
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                median,
                mean,
                LEAST(p10, p90) AS p10,
                GREATEST(p10, p90) AS p90,
                GREATEST(std, 0.0001) AS std,
                :model_version,
                GREATEST(sample_size, 1) AS sample_size
            FROM profiles
            """
        ),
        {
            "model_version": model_version,
            "data_start": data_start,
            "data_end": data_end,
            "reference_end": reference_end,
            "half_life_days": half_life_days,
            "dow_weight_target": dow_weight_target,
            "workday_weight_target": workday_weight_target,
            "slot_weight_target": slot_weight_target,
        },
    )


def _build_model_4_profiles(
    session,
    *,
    model_version: int,
    data_start: datetime,
    data_end: datetime,
    reference_end: datetime,
) -> None:
    _delete_profiles(session, model_version)
    session.execute(
        text(
            """
            WITH base_raw AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    CASE WHEN day_of_week BETWEEN 0 AND 4 THEN TRUE ELSE FALSE END AS is_workday,
                    delta,
                    EXTRACT(DOY FROM date)::integer AS observation_doy,
                    EXTRACT(DOY FROM :reference_end)::integer AS reference_doy
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :data_start
                    AND date < :data_end
            ),
            base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    is_workday,
                    delta,
                    LEAST(
                        ABS(observation_doy - reference_doy),
                        366 - ABS(observation_doy - reference_doy)
                    )::double precision AS season_distance_days
                FROM base_raw
            ),
            interval_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size
                FROM base
                GROUP BY identifikace, interval_minutes
            ),
            slot_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size
                FROM base
                GROUP BY identifikace, interval_minutes, slot
            ),
            workday_slot_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    is_workday,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size
                FROM base
                GROUP BY identifikace, interval_minutes, is_workday, slot
            ),
            dow_slot_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size
                FROM base
                GROUP BY identifikace, interval_minutes, day_of_week, slot
            ),
            seasonal_dow_slot_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size
                FROM base
                WHERE season_distance_days <= :season_window_days
                GROUP BY identifikace, interval_minutes, day_of_week, slot
            ),
            slots AS (
                SELECT
                    interval_stats.identifikace,
                    interval_stats.interval_minutes,
                    generated_slots.slot
                FROM interval_stats
                CROSS JOIN LATERAL generate_series(
                    0,
                    GREATEST(
                        COALESCE(
                            CAST(FLOOR(1440.0 / NULLIF(interval_stats.interval_minutes, 0)) AS integer),
                            1
                        ) - 1,
                        0
                    )
                ) AS generated_slots(slot)
            ),
            days(day_of_week, is_workday) AS (
                VALUES
                    (0, TRUE),
                    (1, TRUE),
                    (2, TRUE),
                    (3, TRUE),
                    (4, TRUE),
                    (5, FALSE),
                    (6, FALSE)
            ),
            grid AS (
                SELECT
                    slots.identifikace,
                    slots.interval_minutes,
                    days.day_of_week,
                    days.is_workday,
                    slots.slot
                FROM slots
                CROSS JOIN days
            ),
            blended AS (
                SELECT
                    grid.identifikace,
                    grid.interval_minutes,
                    grid.day_of_week,
                    grid.slot,
                    interval_stats.median AS interval_median,
                    interval_stats.mean AS interval_mean,
                    interval_stats.p10 AS interval_p10,
                    interval_stats.p90 AS interval_p90,
                    interval_stats.std AS interval_std,
                    interval_stats.sample_size AS interval_sample_size,
                    slot_stats.median AS slot_median,
                    slot_stats.mean AS slot_mean,
                    slot_stats.p10 AS slot_p10,
                    slot_stats.p90 AS slot_p90,
                    slot_stats.std AS slot_std,
                    slot_stats.sample_size AS slot_sample_size,
                    workday_slot_stats.median AS workday_median,
                    workday_slot_stats.mean AS workday_mean,
                    workday_slot_stats.p10 AS workday_p10,
                    workday_slot_stats.p90 AS workday_p90,
                    workday_slot_stats.std AS workday_std,
                    workday_slot_stats.sample_size AS workday_sample_size,
                    dow_slot_stats.median AS dow_median,
                    dow_slot_stats.mean AS dow_mean,
                    dow_slot_stats.p10 AS dow_p10,
                    dow_slot_stats.p90 AS dow_p90,
                    dow_slot_stats.std AS dow_std,
                    dow_slot_stats.sample_size AS dow_sample_size,
                    seasonal_dow_slot_stats.median AS seasonal_median,
                    seasonal_dow_slot_stats.mean AS seasonal_mean,
                    seasonal_dow_slot_stats.p10 AS seasonal_p10,
                    seasonal_dow_slot_stats.p90 AS seasonal_p90,
                    seasonal_dow_slot_stats.std AS seasonal_std,
                    seasonal_dow_slot_stats.sample_size AS seasonal_sample_size,
                    LEAST(
                        COALESCE(slot_stats.sample_size, 0)::double precision / :slot_weight_target,
                        1.0
                    ) AS slot_trust,
                    LEAST(
                        COALESCE(workday_slot_stats.sample_size, 0)::double precision / :workday_weight_target,
                        1.0
                    ) AS workday_trust,
                    LEAST(
                        COALESCE(dow_slot_stats.sample_size, 0)::double precision / :dow_weight_target,
                        1.0
                    ) AS dow_trust,
                    LEAST(
                        COALESCE(seasonal_dow_slot_stats.sample_size, 0)::double precision / :seasonal_weight_target,
                        1.0
                    ) AS seasonal_trust
                FROM grid
                JOIN interval_stats
                    ON interval_stats.identifikace = grid.identifikace
                    AND interval_stats.interval_minutes = grid.interval_minutes
                LEFT JOIN slot_stats
                    ON slot_stats.identifikace = grid.identifikace
                    AND slot_stats.interval_minutes = grid.interval_minutes
                    AND slot_stats.slot = grid.slot
                LEFT JOIN workday_slot_stats
                    ON workday_slot_stats.identifikace = grid.identifikace
                    AND workday_slot_stats.interval_minutes = grid.interval_minutes
                    AND workday_slot_stats.is_workday = grid.is_workday
                    AND workday_slot_stats.slot = grid.slot
                LEFT JOIN dow_slot_stats
                    ON dow_slot_stats.identifikace = grid.identifikace
                    AND dow_slot_stats.interval_minutes = grid.interval_minutes
                    AND dow_slot_stats.day_of_week = grid.day_of_week
                    AND dow_slot_stats.slot = grid.slot
                LEFT JOIN seasonal_dow_slot_stats
                    ON seasonal_dow_slot_stats.identifikace = grid.identifikace
                    AND seasonal_dow_slot_stats.interval_minutes = grid.interval_minutes
                    AND seasonal_dow_slot_stats.day_of_week = grid.day_of_week
                    AND seasonal_dow_slot_stats.slot = grid.slot
            ),
            profiles AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    seasonal_trust * COALESCE(seasonal_median, dow_median, workday_median, slot_median, interval_median)
                        + (1.0 - seasonal_trust) * (
                            dow_trust * COALESCE(dow_median, workday_median, slot_median, interval_median)
                            + (1.0 - dow_trust) * (
                                workday_trust * COALESCE(workday_median, slot_median, interval_median)
                                + (1.0 - workday_trust) * (
                                    slot_trust * COALESCE(slot_median, interval_median)
                                    + (1.0 - slot_trust) * interval_median
                                )
                            )
                        ) AS median,
                    seasonal_trust * COALESCE(seasonal_mean, dow_mean, workday_mean, slot_mean, interval_mean)
                        + (1.0 - seasonal_trust) * (
                            dow_trust * COALESCE(dow_mean, workday_mean, slot_mean, interval_mean)
                            + (1.0 - dow_trust) * (
                                workday_trust * COALESCE(workday_mean, slot_mean, interval_mean)
                                + (1.0 - workday_trust) * (
                                    slot_trust * COALESCE(slot_mean, interval_mean)
                                    + (1.0 - slot_trust) * interval_mean
                                )
                            )
                        ) AS mean,
                    seasonal_trust * COALESCE(seasonal_p10, dow_p10, workday_p10, slot_p10, interval_p10)
                        + (1.0 - seasonal_trust) * (
                            dow_trust * COALESCE(dow_p10, workday_p10, slot_p10, interval_p10)
                            + (1.0 - dow_trust) * (
                                workday_trust * COALESCE(workday_p10, slot_p10, interval_p10)
                                + (1.0 - workday_trust) * (
                                    slot_trust * COALESCE(slot_p10, interval_p10)
                                    + (1.0 - slot_trust) * interval_p10
                                )
                            )
                        ) AS p10,
                    seasonal_trust * COALESCE(seasonal_p90, dow_p90, workday_p90, slot_p90, interval_p90)
                        + (1.0 - seasonal_trust) * (
                            dow_trust * COALESCE(dow_p90, workday_p90, slot_p90, interval_p90)
                            + (1.0 - dow_trust) * (
                                workday_trust * COALESCE(workday_p90, slot_p90, interval_p90)
                                + (1.0 - workday_trust) * (
                                    slot_trust * COALESCE(slot_p90, interval_p90)
                                    + (1.0 - slot_trust) * interval_p90
                                )
                            )
                        ) AS p90,
                    seasonal_trust * COALESCE(seasonal_std, dow_std, workday_std, slot_std, interval_std)
                        + (1.0 - seasonal_trust) * (
                            dow_trust * COALESCE(dow_std, workday_std, slot_std, interval_std)
                            + (1.0 - dow_trust) * (
                                workday_trust * COALESCE(workday_std, slot_std, interval_std)
                                + (1.0 - workday_trust) * (
                                    slot_trust * COALESCE(slot_std, interval_std)
                                    + (1.0 - slot_trust) * interval_std
                                )
                            )
                        ) AS std,
                    GREATEST(
                        COALESCE(seasonal_sample_size, 0),
                        COALESCE(dow_sample_size, 0),
                        COALESCE(workday_sample_size, 0),
                        COALESCE(slot_sample_size, 0),
                        interval_sample_size
                    ) AS sample_size
                FROM blended
            )
            INSERT INTO monitoring.vodomery_anomaly_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                median,
                mean,
                p10,
                p90,
                std,
                model_version,
                sample_size
            )
            SELECT
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                median,
                mean,
                LEAST(p10, p90) AS p10,
                GREATEST(p10, p90) AS p90,
                GREATEST(std, 0.0001) AS std,
                :model_version,
                GREATEST(sample_size, 1) AS sample_size
            FROM profiles
            """
        ),
        {
            "model_version": model_version,
            "data_start": data_start,
            "data_end": data_end,
            "reference_end": reference_end,
            "season_window_days": MODEL_V4_SEASON_WINDOW_DAYS,
            "seasonal_weight_target": MODEL_V4_SEASONAL_WEIGHT_TARGET,
            "dow_weight_target": MODEL_V4_DOW_WEIGHT_TARGET,
            "workday_weight_target": MODEL_V4_WORKDAY_WEIGHT_TARGET,
            "slot_weight_target": MODEL_V4_SLOT_WEIGHT_TARGET,
        },
    )


def _evaluate_profiles_on_validation(
    session,
    *,
    model_version: int,
    windows: RebuildWindows,
) -> ValidationAggregate:
    row = session.execute(
        text(
            """
            WITH validation_base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    delta
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :validation_start
                    AND date < :validation_end
            ),
            joined AS (
                SELECT
                    v.delta AS actual_value,
                    p.id AS profile_id,
                    p.mean AS predicted_mean
                FROM validation_base v
                LEFT JOIN monitoring.vodomery_anomaly_profiles p
                    ON p.model_version = :model_version
                    AND p.identifikace = v.identifikace
                    AND p.interval_minutes = v.interval_minutes
                    AND p.day_of_week = v.day_of_week
                    AND p.slot = v.slot
            )
            SELECT
                (SELECT COUNT(*) FROM validation_base) AS validation_total_count,
                COUNT(profile_id) AS matched_validation_count,
                COALESCE(SUM(ABS(actual_value - predicted_mean)), 0.0) AS abs_error_sum,
                COALESCE(SUM(POWER(actual_value - predicted_mean, 2)), 0.0) AS squared_error_sum,
                COALESCE(SUM(actual_value - predicted_mean), 0.0) AS error_sum,
                COALESCE(
                    SUM(
                        CASE
                            WHEN profile_id IS NOT NULL THEN ABS(actual_value)
                            ELSE 0.0
                        END
                    ),
                    0.0
                ) AS matched_actual_abs_sum
            FROM joined
            """
        ),
        {
            "model_version": model_version,
            "validation_start": windows.validation_start,
            "validation_end": windows.validation_end,
        },
    ).mappings().one()

    validation_total_count = int(row["validation_total_count"] or 0)
    matched_validation_count = int(row["matched_validation_count"] or 0)
    abs_error_sum = float(row["abs_error_sum"] or 0.0)
    squared_error_sum = float(row["squared_error_sum"] or 0.0)
    error_sum = float(row["error_sum"] or 0.0)
    matched_actual_abs_sum = float(row["matched_actual_abs_sum"] or 0.0)
    if validation_total_count <= 0:
        return ValidationAggregate(
            validation_total_count=0,
            matched_validation_count=0,
            coverage=0.0,
            mae=None,
            rmse=None,
            bias=None,
            wape=None,
        )

    coverage = matched_validation_count / validation_total_count
    if matched_validation_count <= 0:
        return ValidationAggregate(
            validation_total_count=validation_total_count,
            matched_validation_count=0,
            coverage=coverage,
            mae=None,
            rmse=None,
            bias=None,
            wape=None,
            abs_error_sum=abs_error_sum,
            squared_error_sum=squared_error_sum,
            error_sum=error_sum,
            matched_actual_abs_sum=matched_actual_abs_sum,
        )

    return ValidationAggregate(
        validation_total_count=validation_total_count,
        matched_validation_count=matched_validation_count,
        coverage=coverage,
        mae=abs_error_sum / matched_validation_count,
        rmse=(squared_error_sum / matched_validation_count) ** 0.5,
        bias=error_sum / matched_validation_count,
        wape=(
            None
            if matched_actual_abs_sum <= 0
            else abs_error_sum / matched_actual_abs_sum
        ),
        abs_error_sum=abs_error_sum,
        squared_error_sum=squared_error_sum,
        error_sum=error_sum,
        matched_actual_abs_sum=matched_actual_abs_sum,
    )


def _evaluate_profiles_on_validation_by_identifikace(
    session,
    *,
    model_version: int,
    windows: RebuildWindows,
) -> dict[str, ValidationAggregate]:
    rows = session.execute(
        text(
            """
            WITH validation_base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    delta
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :validation_start
                    AND date < :validation_end
            ),
            joined AS (
                SELECT
                    v.identifikace,
                    v.delta AS actual_value,
                    p.id AS profile_id,
                    p.mean AS predicted_mean
                FROM validation_base v
                LEFT JOIN monitoring.vodomery_anomaly_profiles p
                    ON p.model_version = :model_version
                    AND p.identifikace = v.identifikace
                    AND p.interval_minutes = v.interval_minutes
                    AND p.day_of_week = v.day_of_week
                    AND p.slot = v.slot
            )
            SELECT
                identifikace,
                COUNT(*) AS validation_total_count,
                COUNT(profile_id) AS matched_validation_count,
                COALESCE(SUM(ABS(actual_value - predicted_mean)), 0.0) AS abs_error_sum,
                COALESCE(SUM(POWER(actual_value - predicted_mean, 2)), 0.0) AS squared_error_sum,
                COALESCE(SUM(actual_value - predicted_mean), 0.0) AS error_sum,
                COALESCE(
                    SUM(
                        CASE
                            WHEN profile_id IS NOT NULL THEN ABS(actual_value)
                            ELSE 0.0
                        END
                    ),
                    0.0
                ) AS matched_actual_abs_sum
            FROM joined
            GROUP BY identifikace
            ORDER BY identifikace
            """
        ),
        {
            "model_version": model_version,
            "validation_start": windows.validation_start,
            "validation_end": windows.validation_end,
        },
    ).mappings().all()

    return {
        str(row["identifikace"]): _build_validation_aggregate_from_sums(row)
        for row in rows
    }


def _build_validation_aggregate_from_sums(row) -> ValidationAggregate:
    validation_total_count = int(row["validation_total_count"] or 0)
    matched_validation_count = int(row["matched_validation_count"] or 0)
    abs_error_sum = float(row["abs_error_sum"] or 0.0)
    squared_error_sum = float(row["squared_error_sum"] or 0.0)
    error_sum = float(row["error_sum"] or 0.0)
    matched_actual_abs_sum = float(row["matched_actual_abs_sum"] or 0.0)
    if validation_total_count <= 0:
        return ValidationAggregate(
            validation_total_count=0,
            matched_validation_count=0,
            coverage=0.0,
            mae=None,
            rmse=None,
            bias=None,
            wape=None,
        )

    coverage = matched_validation_count / validation_total_count
    if matched_validation_count <= 0:
        return ValidationAggregate(
            validation_total_count=validation_total_count,
            matched_validation_count=0,
            coverage=coverage,
            mae=None,
            rmse=None,
            bias=None,
            wape=None,
            abs_error_sum=abs_error_sum,
            squared_error_sum=squared_error_sum,
            error_sum=error_sum,
            matched_actual_abs_sum=matched_actual_abs_sum,
        )

    return ValidationAggregate(
        validation_total_count=validation_total_count,
        matched_validation_count=matched_validation_count,
        coverage=coverage,
        mae=abs_error_sum / matched_validation_count,
        rmse=(squared_error_sum / matched_validation_count) ** 0.5,
        bias=error_sum / matched_validation_count,
        wape=(
            None
            if matched_actual_abs_sum <= 0
            else abs_error_sum / matched_actual_abs_sum
        ),
        abs_error_sum=abs_error_sum,
        squared_error_sum=squared_error_sum,
        error_sum=error_sum,
        matched_actual_abs_sum=matched_actual_abs_sum,
    )


def _load_model_2_candidate_metrics(session, windows: RebuildWindows) -> list[ValidationCandidate]:
    rows = session.execute(
        text(
            """
            WITH train_base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    delta
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :train_start
                    AND date < :train_end
            ),
            validation_base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    delta
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :validation_start
                    AND date < :validation_end
            ),
            validation_totals AS (
                SELECT
                    identifikace,
                    COUNT(*) AS validation_total_count
                FROM validation_base
                GROUP BY identifikace
            ),
            train_dow_slot AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    AVG(delta) AS predicted_mean
                FROM train_base
                GROUP BY identifikace, interval_minutes, day_of_week, slot
            ),
            train_workday_slot AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    CASE WHEN day_of_week BETWEEN 0 AND 4 THEN TRUE ELSE FALSE END AS is_workday,
                    slot,
                    AVG(delta) AS predicted_mean
                FROM train_base
                GROUP BY identifikace, interval_minutes, is_workday, slot
            ),
            train_slot AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    slot,
                    AVG(delta) AS predicted_mean
                FROM train_base
                GROUP BY identifikace, interval_minutes, slot
            ),
            candidate_predictions AS (
                SELECT
                    v.identifikace,
                    'dow_slot_mean' AS strategy_key,
                    v.delta AS actual_value,
                    p.predicted_mean
                FROM validation_base v
                JOIN train_dow_slot p
                    ON p.identifikace = v.identifikace
                    AND p.interval_minutes = v.interval_minutes
                    AND p.day_of_week = v.day_of_week
                    AND p.slot = v.slot

                UNION ALL

                SELECT
                    v.identifikace,
                    'workday_slot_mean' AS strategy_key,
                    v.delta AS actual_value,
                    p.predicted_mean
                FROM validation_base v
                JOIN train_workday_slot p
                    ON p.identifikace = v.identifikace
                    AND p.interval_minutes = v.interval_minutes
                    AND p.is_workday = CASE WHEN v.day_of_week BETWEEN 0 AND 4 THEN TRUE ELSE FALSE END
                    AND p.slot = v.slot

                UNION ALL

                SELECT
                    v.identifikace,
                    'slot_mean' AS strategy_key,
                    v.delta AS actual_value,
                    p.predicted_mean
                FROM validation_base v
                JOIN train_slot p
                    ON p.identifikace = v.identifikace
                    AND p.interval_minutes = v.interval_minutes
                    AND p.slot = v.slot
            ),
            candidate_metrics AS (
                SELECT
                    identifikace,
                    strategy_key,
                    COUNT(*) AS matched_validation_count,
                    AVG(ABS(actual_value - predicted_mean)) AS mae,
                    SQRT(AVG(POWER(actual_value - predicted_mean, 2))) AS rmse,
                    AVG(actual_value - predicted_mean) AS bias,
                    SUM(ABS(actual_value - predicted_mean)) AS abs_error_sum,
                    SUM(POWER(actual_value - predicted_mean, 2)) AS squared_error_sum,
                    SUM(actual_value - predicted_mean) AS error_sum
                FROM candidate_predictions
                GROUP BY identifikace, strategy_key
            )
            SELECT
                metric.identifikace,
                metric.strategy_key,
                totals.validation_total_count,
                metric.matched_validation_count,
                COALESCE(
                    metric.matched_validation_count::double precision
                    / NULLIF(totals.validation_total_count, 0),
                    0.0
                ) AS coverage,
                metric.mae,
                metric.rmse,
                metric.bias,
                metric.abs_error_sum,
                metric.squared_error_sum,
                metric.error_sum
            FROM candidate_metrics metric
            JOIN validation_totals totals
                ON totals.identifikace = metric.identifikace
            ORDER BY metric.identifikace, metric.strategy_key
            """
        ),
        {
            "train_start": windows.train_start,
            "train_end": windows.train_end,
            "validation_start": windows.validation_start,
            "validation_end": windows.validation_end,
        },
    ).mappings().all()

    return [
        ValidationCandidate(
            identifikace=str(row["identifikace"]),
            strategy_key=str(row["strategy_key"]),
            validation_total_count=int(row["validation_total_count"]),
            matched_validation_count=int(row["matched_validation_count"]),
            coverage=float(row["coverage"]),
            mae=float(row["mae"]),
            rmse=float(row["rmse"]),
            bias=float(row["bias"]),
            abs_error_sum=float(row["abs_error_sum"]),
            squared_error_sum=float(row["squared_error_sum"]),
            error_sum=float(row["error_sum"]),
        )
        for row in rows
    ]


def _persist_validation_metrics(
    session,
    *,
    run_id: int,
    model_version: int,
    candidates: Sequence[ValidationCandidate],
    selected_by_ident: dict[str, ValidationCandidate],
) -> None:
    if not candidates:
        return

    selected_keys = {
        (candidate.identifikace, candidate.strategy_key)
        for candidate in selected_by_ident.values()
    }
    session.execute(
        insert(VodomeryModelValidationMetric),
        [
            {
                "run_id": run_id,
                "model_version": model_version,
                "identifikace": candidate.identifikace,
                "strategy_key": candidate.strategy_key,
                "validation_total_count": candidate.validation_total_count,
                "matched_validation_count": candidate.matched_validation_count,
                "coverage": round(candidate.coverage, 6),
                "mae": round(candidate.mae, 6),
                "rmse": round(candidate.rmse, 6),
                "bias": round(candidate.bias, 6),
                "selected": (candidate.identifikace, candidate.strategy_key) in selected_keys,
            }
            for candidate in candidates
        ],
    )


def _replace_model_2_profiles(
    session,
    *,
    model_version: int,
    data_start: datetime,
    data_end: datetime,
    selected_by_ident: dict[str, ValidationCandidate],
) -> None:
    _delete_profiles(session, model_version)
    identifiers_by_strategy: dict[str, list[str]] = defaultdict(list)
    for identifikace, candidate in selected_by_ident.items():
        identifiers_by_strategy[candidate.strategy_key].append(identifikace)

    for strategy_key in MODEL_V2_STRATEGIES:
        identifiers = identifiers_by_strategy.get(strategy_key, [])
        if not identifiers:
            continue
        _insert_profiles_for_strategy(
            session,
            strategy_key=strategy_key,
            identifiers=identifiers,
            data_start=data_start,
            data_end=data_end,
            model_version=model_version,
        )


def _insert_profiles_for_strategy(
    session,
    *,
    strategy_key: str,
    identifiers: Sequence[str],
    data_start: datetime,
    data_end: datetime,
    model_version: int,
) -> None:
    if not identifiers:
        return

    if strategy_key == STRATEGY_DOW_SLOT_MEAN:
        statement = text(
            """
            WITH profile_base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    delta
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :data_start
                    AND date < :data_end
                    AND identifikace IN :identifiers
            )
            INSERT INTO monitoring.vodomery_anomaly_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                median,
                mean,
                p10,
                p90,
                std,
                model_version,
                sample_size
            )
            SELECT
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                AVG(delta) AS mean,
                percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                :model_version,
                COUNT(*) AS sample_size
            FROM profile_base
            GROUP BY identifikace, interval_minutes, day_of_week, slot
            """
        ).bindparams(bindparam("identifiers", expanding=True))
    elif strategy_key == STRATEGY_WORKDAY_SLOT_MEAN:
        statement = text(
            """
            WITH profile_base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    delta
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :data_start
                    AND date < :data_end
                    AND identifikace IN :identifiers
            ),
            stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    CASE WHEN day_of_week BETWEEN 0 AND 4 THEN TRUE ELSE FALSE END AS is_workday,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size
                FROM profile_base
                GROUP BY identifikace, interval_minutes, is_workday, slot
            ),
            days(day_of_week, is_workday) AS (
                VALUES
                    (0, TRUE),
                    (1, TRUE),
                    (2, TRUE),
                    (3, TRUE),
                    (4, TRUE),
                    (5, FALSE),
                    (6, FALSE)
            )
            INSERT INTO monitoring.vodomery_anomaly_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                median,
                mean,
                p10,
                p90,
                std,
                model_version,
                sample_size
            )
            SELECT
                stats.identifikace,
                stats.interval_minutes,
                days.day_of_week,
                stats.slot,
                stats.median,
                stats.mean,
                stats.p10,
                stats.p90,
                stats.std,
                :model_version,
                stats.sample_size
            FROM stats
            JOIN days
                ON days.is_workday = stats.is_workday
            """
        ).bindparams(bindparam("identifiers", expanding=True))
    elif strategy_key == STRATEGY_SLOT_MEAN:
        statement = text(
            """
            WITH profile_base AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    slot,
                    delta
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :data_start
                    AND date < :data_end
                    AND identifikace IN :identifiers
            ),
            stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    slot,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), 0.0001) AS std,
                    COUNT(*) AS sample_size
                FROM profile_base
                GROUP BY identifikace, interval_minutes, slot
            ),
            days(day_of_week) AS (
                VALUES
                    (0),
                    (1),
                    (2),
                    (3),
                    (4),
                    (5),
                    (6)
            )
            INSERT INTO monitoring.vodomery_anomaly_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                median,
                mean,
                p10,
                p90,
                std,
                model_version,
                sample_size
            )
            SELECT
                stats.identifikace,
                stats.interval_minutes,
                days.day_of_week,
                stats.slot,
                stats.median,
                stats.mean,
                stats.p10,
                stats.p90,
                stats.std,
                :model_version,
                stats.sample_size
            FROM stats
            CROSS JOIN days
            """
        ).bindparams(bindparam("identifiers", expanding=True))
    else:
        raise ValueError(f"Neznama strategie profilu: {strategy_key}")

    session.execute(
        statement,
        {
            "data_start": data_start,
            "data_end": data_end,
            "model_version": model_version,
            "identifiers": list(identifiers),
        },
    )
