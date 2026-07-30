from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from math import isfinite
from typing import Callable, Sequence

from sqlalchemy import select, text

from app.time_utils import prague_now_naive
from core.db.connect import ENGINE_PG, get_session_pg
from moduly.apps.meteo.meteo_sync import ensure_meteo_tables
from moduly.mereni.prediction import (
    PredictionCandidateRegistry,
    PredictionCandidateResult,
    PredictionCandidateSpec,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionForecastPeriodDefinition,
    PredictionMetricSummary,
    PredictionPipelineRunner,
    PredictionPipelineSettings,
    PredictionProfilePoint,
    PredictionSelectedModelDecision,
    PredictionSelectionFallbackReason,
    PredictionRebuildWindows,
    ARCHIVE_SOURCE_WEEKLY_REBUILD,
    SELECTION_MODE_ACTIVE,
    SELECTION_MODE_DRY_RUN,
    build_calendar_week_forecast_period,
    build_rolling_weekly_folds,
    build_prediction_rebuild_windows,
    ensure_prediction_profile_snapshot_table,
    ensure_prediction_selected_model_snapshot_table,
    normalize_archive_source,
    normalize_selection_mode,
    persist_prediction_profile_snapshots,
    persist_selected_model_decisions,
)
from moduly.mereni.plynomery.database.models import (
    PlynomeryModelSelectionCandidate,
    PlynomeryModelSelectionRun,
    PlynomeryProfilesAnomaly,
    PlynomeryWeatherModelProfile,
)


MODEL_VERSION_BASELINE = 1
MODEL_VERSION_WEATHER_ADJUSTED = 2
DEFAULT_MODEL_VERSION = MODEL_VERSION_BASELINE
MODEL_REBUILD_TRAINING_MONTHS = 3
MODEL_VALIDATION_MONTHS = 1
MODEL_SELECTION_COVERAGE_THRESHOLD = 0.85
MODEL_EVALUATION_VERSION_OFFSET = 1000
MODEL_ROLLING_BACKTEST_VERSION_OFFSET = 2000
MODEL_ROLLING_BACKTEST_FOLD_COUNT = 8
MODEL_ROLLING_BACKTEST_VALIDATION_DAYS = 7
MODEL_SELECTION_MIN_FOLD_COUNT = MODEL_ROLLING_BACKTEST_FOLD_COUNT
MIN_EXACT_HISTORY = 8
MIN_SLOT_HISTORY = 32
MIN_STD = 0.0001
MIN_HDD_VARIANCE = 0.0001
LOCAL_TIMEZONE_NAME = "Europe/Prague"
PLYNOMERY_MEDIUM_KEY = "plynomery"
PLYNOMERY_FORECAST_PERIOD_DEFINITION = PredictionForecastPeriodDefinition(
    cadence=PredictionForecastCadence.WEEKLY,
    period_count=1,
)
PLYNOMERY_PIPELINE_SETTINGS = PredictionPipelineSettings(
    medium_key=PLYNOMERY_MEDIUM_KEY,
    forecast_period_definition=PLYNOMERY_FORECAST_PERIOD_DEFINITION,
    default_training_window_months=MODEL_REBUILD_TRAINING_MONTHS,
    default_validation_window_months=MODEL_VALIDATION_MONTHS,
    candidate_coverage_threshold=MODEL_SELECTION_COVERAGE_THRESHOLD,
    rolling_backtest_fold_count=MODEL_ROLLING_BACKTEST_FOLD_COUNT,
    rolling_validation_period=PLYNOMERY_FORECAST_PERIOD_DEFINITION,
)


@dataclass(frozen=True)
class CandidateModelDefinition:
    model_version: int
    model_name: str
    model_key: str = ""
    training_window_months: int = MODEL_REBUILD_TRAINING_MONTHS
    validation_window_months: int = MODEL_VALIDATION_MONTHS
    selection_enabled: bool = True

    def to_prediction_spec(self) -> PredictionCandidateSpec:
        return PredictionCandidateSpec(
            medium_key=PLYNOMERY_MEDIUM_KEY,
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

    def to_dict(self) -> dict[str, object]:
        return {
            "identifikace": self.identifikace,
            "model_version": self.model_version,
            "model_key": self.model_key,
            "model_name": self.model_name,
            "selection_enabled": self.selection_enabled,
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


DeployableProfileCatalog = dict[
    tuple[str, int],
    tuple[PredictionProfilePoint, ...],
]


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

    def to_prediction_candidate_result(self) -> PredictionCandidateResult:
        return PredictionCandidateResult(
            spec=PredictionCandidateSpec(
                medium_key=PLYNOMERY_MEDIUM_KEY,
                model_version=self.model_version,
                model_key=self.model_key or f"model_{self.model_version}",
                model_name=self.model_name,
                training_window_months=(
                    self.training_window_months
                    or PLYNOMERY_PIPELINE_SETTINGS.default_training_window_months
                ),
                validation_window_months=(
                    self.validation_window_months
                    or PLYNOMERY_PIPELINE_SETTINGS.default_validation_window_months
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
        )

    def to_dict(self, *, selected: bool) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "model_name": self.model_name,
            "model_key": self.model_key,
            "selection_enabled": self.selection_enabled,
            "rolling_backtest_fold_count": self.rolling_backtest_fold_count,
            "rolling_validation_total_count": self.rolling_validation_total_count,
            "rolling_matched_validation_count": self.rolling_matched_validation_count,
            "rolling_coverage": self.rolling_coverage,
            "rolling_mae": self.rolling_mae,
            "rolling_rmse": self.rolling_rmse,
            "rolling_bias": self.rolling_bias,
            "rolling_wape": self.rolling_wape,
            "validation_total_count": self.validation_total_count,
            "matched_validation_count": self.matched_validation_count,
            "coverage": round(self.coverage, 6),
            "mae": None if self.mae is None else round(self.mae, 6),
            "rmse": None if self.rmse is None else round(self.rmse, 6),
            "bias": None if self.bias is None else round(self.bias, 6),
            "profile_count": self.profile_count,
            "selected": selected,
        }


@dataclass(frozen=True)
class PlynomeryCandidateModelPlugin:
    definition: CandidateModelDefinition
    rebuild_fn: Callable[..., ModelPerformanceSummary]

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


def _build_plynomery_pipeline_runner() -> PredictionPipelineRunner[PlynomeryCandidateModelPlugin]:
    registry = PredictionCandidateRegistry(
        medium_key=PLYNOMERY_MEDIUM_KEY,
        plugins=(
            PlynomeryCandidateModelPlugin(
                definition=CandidateModelDefinition(
                    model_version=MODEL_VERSION_BASELINE,
                    model_key="exact_fallback_baseline",
                    model_name="Model 1 - exact/fallback baseline",
                ),
                rebuild_fn=_rebuild_baseline_candidate,
            ),
            PlynomeryCandidateModelPlugin(
                definition=CandidateModelDefinition(
                    model_version=MODEL_VERSION_WEATHER_ADJUSTED,
                    model_key="weather_adjusted_baseline",
                    model_name="Model 2 - weather adjusted baseline",
                ),
                rebuild_fn=_rebuild_weather_adjusted_candidate,
            ),
        ),
    )
    return PredictionPipelineRunner(
        settings=PLYNOMERY_PIPELINE_SETTINGS,
        registry=registry,
    )


def ensure_prediction_tables() -> None:
    ensure_meteo_tables()
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        PlynomeryProfilesAnomaly.__table__.create(bind=conn, checkfirst=True)
        _ensure_weather_model_profile_table(conn)
        _ensure_model_selection_tables(conn)


def _ensure_weather_model_profile_table(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS monitoring.plynomery_weather_model_profiles (
                id SERIAL PRIMARY KEY,
                identifikace VARCHAR(250) NOT NULL,
                interval_minutes INTEGER NOT NULL,
                day_of_week INTEGER NOT NULL,
                slot INTEGER NOT NULL,
                base_mean DOUBLE PRECISION NOT NULL,
                hdd_slope DOUBLE PRECISION NOT NULL,
                hdd_24h_mean DOUBLE PRECISION NOT NULL,
                residual_mean DOUBLE PRECISION NOT NULL,
                residual_median DOUBLE PRECISION NOT NULL,
                residual_p10 DOUBLE PRECISION NOT NULL,
                residual_p90 DOUBLE PRECISION NOT NULL,
                residual_std DOUBLE PRECISION NOT NULL,
                model_version INTEGER NOT NULL,
                sample_size INTEGER NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_plynomery_weather_profile_key
            ON monitoring.plynomery_weather_model_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                model_version
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_plynomery_weather_profile_lookup
            ON monitoring.plynomery_weather_model_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot
            )
            """
        )
    )


def _ensure_model_selection_tables(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS monitoring.plynomery_model_selection_runs (
                id SERIAL PRIMARY KEY,
                train_start TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                train_end TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                validation_start TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                validation_end TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                deploy_start TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                deploy_end TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                selected_model_version INTEGER NOT NULL,
                selected_model_name VARCHAR(100) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_plynomery_model_selection_runs_created
            ON monitoring.plynomery_model_selection_runs (created_at)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS monitoring.plynomery_model_selection_candidates (
                id SERIAL PRIMARY KEY,
                selection_run_id INTEGER NOT NULL REFERENCES monitoring.plynomery_model_selection_runs(id) ON DELETE CASCADE,
                model_version INTEGER NOT NULL,
                model_key VARCHAR(80),
                model_name VARCHAR(100) NOT NULL,
                training_window_months INTEGER,
                validation_window_months INTEGER,
                selection_enabled BOOLEAN NOT NULL DEFAULT true,
                validation_total_count INTEGER NOT NULL,
                matched_validation_count INTEGER NOT NULL,
                coverage DOUBLE PRECISION NOT NULL,
                mae DOUBLE PRECISION,
                rmse DOUBLE PRECISION,
                bias DOUBLE PRECISION,
                rolling_backtest_fold_count INTEGER NOT NULL DEFAULT 0,
                rolling_validation_total_count INTEGER,
                rolling_matched_validation_count INTEGER,
                rolling_coverage DOUBLE PRECISION,
                rolling_mae DOUBLE PRECISION,
                rolling_rmse DOUBLE PRECISION,
                rolling_bias DOUBLE PRECISION,
                rolling_wape DOUBLE PRECISION,
                profile_count INTEGER NOT NULL DEFAULT 0,
                selected BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        text(
            """
            ALTER TABLE monitoring.plynomery_model_selection_candidates
                ADD COLUMN IF NOT EXISTS model_key VARCHAR(80),
                ADD COLUMN IF NOT EXISTS training_window_months INTEGER,
                ADD COLUMN IF NOT EXISTS validation_window_months INTEGER,
                ADD COLUMN IF NOT EXISTS selection_enabled BOOLEAN NOT NULL DEFAULT true,
                ADD COLUMN IF NOT EXISTS rolling_backtest_fold_count INTEGER NOT NULL DEFAULT 0,
                ADD COLUMN IF NOT EXISTS rolling_validation_total_count INTEGER,
                ADD COLUMN IF NOT EXISTS rolling_matched_validation_count INTEGER,
                ADD COLUMN IF NOT EXISTS rolling_coverage DOUBLE PRECISION,
                ADD COLUMN IF NOT EXISTS rolling_mae DOUBLE PRECISION,
                ADD COLUMN IF NOT EXISTS rolling_rmse DOUBLE PRECISION,
                ADD COLUMN IF NOT EXISTS rolling_bias DOUBLE PRECISION,
                ADD COLUMN IF NOT EXISTS rolling_wape DOUBLE PRECISION
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_plynomery_model_selection_candidate_run_version
            ON monitoring.plynomery_model_selection_candidates (selection_run_id, model_version)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_plynomery_model_selection_candidates_run
            ON monitoring.plynomery_model_selection_candidates (selection_run_id)
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_plynomery_model_selection_candidates_selected
            ON monitoring.plynomery_model_selection_candidates (selected)
            """
        )
    )


def get_candidate_model_definitions() -> tuple[CandidateModelDefinition, ...]:
    return tuple(
        plugin.definition
        for plugin in _build_plynomery_pipeline_runner().list_plugins()
    )


def get_candidate_model_versions() -> tuple[int, ...]:
    return _build_plynomery_pipeline_runner().list_model_versions()


def get_candidate_model_specs() -> tuple[PredictionCandidateSpec, ...]:
    return _build_plynomery_pipeline_runner().list_specs()


def get_runtime_model_version(*, session=None, default: int = DEFAULT_MODEL_VERSION) -> int:
    ensure_prediction_tables()
    ensure_prediction_selected_model_snapshot_table()
    ensure_prediction_profile_snapshot_table()
    owns_connection = session is None
    db_session = session
    if db_session is None:
        db_session = ENGINE_PG.connect()

    try:
        selected_model_version = db_session.execute(
            text(
                """
                SELECT selected_model_version
                FROM monitoring.plynomery_model_selection_runs
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            )
        ).scalar_one_or_none()
        if selected_model_version is None:
            return default
        return int(selected_model_version)
    finally:
        if owns_connection:
            db_session.close()


def build_rebuild_windows(
    reference_time: datetime | None = None,
    *,
    training_window_months: int = MODEL_REBUILD_TRAINING_MONTHS,
    validation_window_months: int = MODEL_VALIDATION_MONTHS,
) -> RebuildWindows:
    return _to_plynomery_rebuild_windows(
        build_prediction_rebuild_windows(
            reference_time=reference_time or prague_now_naive(),
            training_window_months=training_window_months,
            validation_window_months=validation_window_months,
        )
    )


def build_plynomery_weekly_forecast_period(
    reference_time: datetime | None = None,
) -> PredictionForecastPeriod:
    resolved_reference_time = reference_time or prague_now_naive()
    return build_calendar_week_forecast_period(
        reference_time=resolved_reference_time,
        period_count=PLYNOMERY_FORECAST_PERIOD_DEFINITION.period_count,
    )


def _to_plynomery_rebuild_windows(
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


def _build_windows_for_definition(
    definition: CandidateModelDefinition,
    *,
    reference_time: datetime,
) -> RebuildWindows:
    return _to_plynomery_rebuild_windows(
        _build_plynomery_pipeline_runner().build_rebuild_windows(
            reference_time=reference_time,
            spec=definition.to_prediction_spec(),
        )
    )


def select_best_model_summary(
    summaries: Sequence[ModelPerformanceSummary],
    *,
    coverage_threshold: float = MODEL_SELECTION_COVERAGE_THRESHOLD,
) -> ModelPerformanceSummary | None:
    summary_by_version = {summary.model_version: summary for summary in summaries}
    selected = _build_plynomery_pipeline_runner().select_best_candidate(
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
    *,
    selection_mode: str = SELECTION_MODE_ACTIVE,
) -> dict[str, object]:
    resolved_reference_time = reference_time or prague_now_naive()
    normalized_selection_mode = normalize_selection_mode(selection_mode)
    if model_version is not None and model_version not in get_candidate_model_versions():
        raise ValueError(f"Neznama verze modelu: {model_version}")

    ensure_prediction_tables()

    if model_version is not None:
        definition = _get_candidate_model_definition(model_version)
        if definition is None:
            raise ValueError(f"Neznama verze modelu: {model_version}")
        windows = _build_windows_for_definition(
            definition,
            reference_time=resolved_reference_time,
        )
        session = get_session_pg()
        try:
            summary = _rebuild_candidate_model(
                session,
                definition=definition,
                windows=windows,
            )
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

    windows = build_rebuild_windows(reference_time=resolved_reference_time)
    session = get_session_pg()
    try:
        previous_active_model_version = get_runtime_model_version(
            session=session,
            default=DEFAULT_MODEL_VERSION,
        )
        summaries = []
        device_summaries: list[DeviceModelPerformanceSummary] = []
        forecast_period = build_plynomery_weekly_forecast_period(
            resolved_reference_time
        )
        rolling_reference_end = forecast_period.start
        for definition in get_candidate_model_definitions():
            candidate_windows = _build_windows_for_definition(
                definition,
                reference_time=resolved_reference_time,
            )
            rolling_result = _run_candidate_rolling_weekly_backtest_with_devices(
                session,
                definition=definition,
                reference_end=rolling_reference_end,
            )
            summaries.append(
                _summary_with_rolling_backtest(
                    _rebuild_candidate_model(
                        session,
                        definition=definition,
                        windows=candidate_windows,
                    ),
                    fold_count=MODEL_ROLLING_BACKTEST_FOLD_COUNT,
                    metrics=rolling_result.metrics,
                )
            )
            device_summaries.extend(rolling_result.device_metrics)
        deployable_profile_catalog = _load_deployable_profile_catalog(
            session,
            device_summaries,
        )
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
        )
        dry_run_decisions = _build_dry_run_selected_model_decisions(
            device_summaries=device_summaries,
            selected_summary=selected_summary,
            forecast_period=forecast_period,
            selection_run_id=int(selection_run.id),
            deployable_profile_catalog=deployable_profile_catalog,
            selection_mode=normalized_selection_mode,
        )
        archive_run_id = f"plynomery-selection-{int(selection_run.id)}"
        dry_run_profile_snapshot_rows = _build_dry_run_profile_snapshot_rows(
            dry_run_decisions,
            deployable_profile_catalog=deployable_profile_catalog,
            windows=windows,
            archive_run_id=archive_run_id,
            selection_mode=normalized_selection_mode,
        )
        dry_run_selected_model_snapshot_count = persist_selected_model_decisions(
            session,
            dry_run_decisions,
            selection_mode=normalized_selection_mode,
        )
        dry_run_profile_snapshot_count = persist_prediction_profile_snapshots(
            session,
            dry_run_profile_snapshot_rows,
        )
        session.commit()

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
            "candidates": [
                summary.to_dict(selected=summary.model_version == selected_summary.model_version)
                for summary in summaries
            ],
            "per_identifier_candidates": [
                summary.to_dict()
                for summary in device_summaries
            ],
            "deployable_profile_pair_count": len(deployable_profile_catalog),
            "deployable_profile_count": sum(
                len(points)
                for points in deployable_profile_catalog.values()
            ),
            "forecast_period": forecast_period.to_dict(),
            "selection_mode": normalized_selection_mode,
            "selected_models": [
                decision.to_dict()
                for decision in dry_run_decisions
            ],
            "dry_run_selected_models": [
                decision.to_dict()
                for decision in dry_run_decisions
            ],
            "dry_run_fallback_count": sum(
                1 for decision in dry_run_decisions if decision.uses_fallback
            ),
            "dry_run_unavailable_count": sum(
                1
                for decision in dry_run_decisions
                if decision.metadata.get("prediction_available") is False
            ),
            "dry_run_selected_model_snapshot_count": (
                dry_run_selected_model_snapshot_count
            ),
            "dry_run_profile_snapshot_count": dry_run_profile_snapshot_count,
            "dry_run_profile_snapshot_pair_count": _count_profile_snapshot_pairs(
                dry_run_profile_snapshot_rows
            ),
            "dry_run_profile_snapshot_source": ARCHIVE_SOURCE_WEEKLY_REBUILD,
            "dry_run_profile_snapshot_archive_run_id": archive_run_id,
            "dry_run_winner_counts": dict(
                sorted(
                    {
                        model_version: sum(
                            1
                            for decision in dry_run_decisions
                            if decision.selected_model_version == model_version
                            and decision.metadata.get("prediction_available")
                            is not False
                        )
                        for model_version in {
                            decision.selected_model_version
                            for decision in dry_run_decisions
                            if decision.metadata.get("prediction_available")
                            is not False
                        }
                    }.items()
                )
            ),
        }
        result.update(
            {
                "fallback_count": result["dry_run_fallback_count"],
                "unavailable_count": result["dry_run_unavailable_count"],
                "selected_model_snapshot_count": result[
                    "dry_run_selected_model_snapshot_count"
                ],
                "profile_snapshot_count": result[
                    "dry_run_profile_snapshot_count"
                ],
                "profile_snapshot_pair_count": result[
                    "dry_run_profile_snapshot_pair_count"
                ],
                "winner_counts": result["dry_run_winner_counts"],
            }
        )
        print(
            "Plynomery profiles rebuild complete "
            f"(selection_run_id={selection_run.id}, active_model_version={selected_summary.model_version})"
        )
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


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


def _get_candidate_model_definition(
    model_version: int,
) -> CandidateModelDefinition | None:
    return next(
        (
            definition
            for definition in get_candidate_model_definitions()
            if definition.model_version == model_version
        ),
        None,
    )


def _get_candidate_model_plugin(
    model_version: int,
) -> PlynomeryCandidateModelPlugin | None:
    return _build_plynomery_pipeline_runner().get_plugin(model_version)


def _get_model_name(model_version: int) -> str:
    plugin = _get_candidate_model_plugin(model_version)
    if plugin is None:
        return f"Model {model_version}"
    return plugin.spec.model_name


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
            if definition.model_version == MODEL_VERSION_WEATHER_ADJUSTED:
                _replace_weather_profiles(
                    session,
                    model_version=model_version,
                    data_start=windows.train_start,
                    data_end=windows.train_end,
                )
                fold_device_metrics = _evaluate_weather_profiles_on_validation_by_identifikace(
                    session,
                    model_version=model_version,
                    windows=windows,
                )
            else:
                _replace_profiles(
                    session,
                    model_version=model_version,
                    data_start=windows.train_start,
                    data_end=windows.train_end,
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
            if definition.model_version == MODEL_VERSION_WEATHER_ADJUSTED:
                _delete_weather_profiles(session, model_version)
            else:
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


def _rebuild_baseline_candidate(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    model_version = definition.model_version
    evaluation_version = _build_evaluation_model_version(model_version)
    _replace_profiles(
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

    _replace_profiles(
        session,
        model_version=model_version,
        data_start=windows.deploy_start,
        data_end=windows.deploy_end,
    )
    profile_count = _count_profiles(session, model_version)
    return ModelPerformanceSummary(
        model_version=model_version,
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
    )


def _rebuild_weather_adjusted_candidate(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    model_version = definition.model_version
    evaluation_version = _build_evaluation_model_version(model_version)
    _replace_weather_profiles(
        session,
        model_version=evaluation_version,
        data_start=windows.train_start,
        data_end=windows.train_end,
    )
    validation = _evaluate_weather_profiles_on_validation(
        session,
        model_version=evaluation_version,
        windows=windows,
    )
    _delete_weather_profiles(session, evaluation_version)

    _replace_weather_profiles(
        session,
        model_version=model_version,
        data_start=windows.deploy_start,
        data_end=windows.deploy_end,
    )
    profile_count = _count_weather_profiles(session, model_version)
    return ModelPerformanceSummary(
        model_version=model_version,
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
    )


def _persist_selection_run(
    session,
    *,
    windows: RebuildWindows,
    summaries: Sequence[ModelPerformanceSummary],
    selected_summary: ModelPerformanceSummary,
) -> PlynomeryModelSelectionRun:
    selection_run = PlynomeryModelSelectionRun(
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

    for summary in summaries:
        session.add(
            PlynomeryModelSelectionCandidate(
                selection_run_id=selection_run.id,
                model_version=summary.model_version,
                model_key=summary.model_key,
                model_name=summary.model_name,
                training_window_months=summary.training_window_months,
                validation_window_months=summary.validation_window_months,
                selection_enabled=summary.selection_enabled,
                validation_total_count=summary.validation_total_count,
                matched_validation_count=summary.matched_validation_count,
                coverage=summary.coverage,
                mae=summary.mae,
                rmse=summary.rmse,
                bias=summary.bias,
                rolling_backtest_fold_count=summary.rolling_backtest_fold_count,
                rolling_validation_total_count=summary.rolling_validation_total_count,
                rolling_matched_validation_count=summary.rolling_matched_validation_count,
                rolling_coverage=summary.rolling_coverage,
                rolling_mae=summary.rolling_mae,
                rolling_rmse=summary.rolling_rmse,
                rolling_bias=summary.rolling_bias,
                rolling_wape=summary.rolling_wape,
                profile_count=summary.profile_count,
                selected=summary.model_version == selected_summary.model_version,
            )
        )

    return selection_run


def _build_evaluation_model_version(model_version: int) -> int:
    return MODEL_EVALUATION_VERSION_OFFSET + model_version


def _delete_profiles(session, model_version: int) -> None:
    session.execute(
        text(
            """
            DELETE FROM monitoring.plynomery_anomaly_profiles
            WHERE model_version = :model_version
            """
        ),
        {"model_version": model_version},
    )


def _delete_weather_profiles(session, model_version: int) -> None:
    session.execute(
        text(
            """
            DELETE FROM monitoring.plynomery_weather_model_profiles
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
                FROM monitoring.plynomery_anomaly_profiles
                WHERE model_version = :model_version
                """
            ),
            {"model_version": model_version},
        ).scalar_one()
    )


def _count_weather_profiles(session, model_version: int) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM monitoring.plynomery_weather_model_profiles
                WHERE model_version = :model_version
                """
            ),
            {"model_version": model_version},
        ).scalar_one()
    )


def _replace_profiles(
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
                FROM monitoring."Mereni_plynomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND (:data_start IS NULL OR date >= :data_start)
                    AND (:data_end IS NULL OR date < :data_end)
            ),
            exact_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    COUNT(*) AS sample_size,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), :min_std) AS std
                FROM base
                GROUP BY identifikace, interval_minutes, day_of_week, slot
            ),
            slot_stats AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    slot,
                    COUNT(*) AS sample_size,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                    AVG(delta) AS mean,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                    GREATEST(COALESCE(stddev_samp(delta), 0.0), :min_std) AS std
                FROM base
                GROUP BY identifikace, interval_minutes, slot
            ),
            exact_profiles AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    median,
                    mean,
                    p10,
                    p90,
                    std,
                    sample_size
                FROM exact_stats
                WHERE sample_size >= :min_exact_history
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
            ),
            fallback_profiles AS (
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
                    stats.sample_size
                FROM slot_stats stats
                CROSS JOIN days
                WHERE
                    stats.sample_size >= :min_slot_history
                    AND NOT EXISTS (
                        SELECT 1
                        FROM exact_profiles exact
                        WHERE
                            exact.identifikace = stats.identifikace
                            AND exact.interval_minutes = stats.interval_minutes
                            AND exact.day_of_week = days.day_of_week
                            AND exact.slot = stats.slot
                    )
            )
            INSERT INTO monitoring.plynomery_anomaly_profiles (
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
                profiles.identifikace,
                profiles.interval_minutes,
                profiles.day_of_week,
                profiles.slot,
                profiles.median,
                profiles.mean,
                profiles.p10,
                profiles.p90,
                profiles.std,
                :model_version,
                profiles.sample_size
            FROM (
                SELECT * FROM exact_profiles
                UNION ALL
                SELECT * FROM fallback_profiles
            ) profiles
            """
        ),
        {
            "model_version": model_version,
            "data_start": data_start,
            "data_end": data_end,
            "min_exact_history": MIN_EXACT_HISTORY,
            "min_slot_history": MIN_SLOT_HISTORY,
            "min_std": MIN_STD,
        },
    )


def _replace_weather_profiles(
    session,
    *,
    model_version: int,
    data_start: datetime | None,
    data_end: datetime | None,
) -> None:
    _delete_weather_profiles(session, model_version)
    session.execute(
        text(
            f"""
            WITH meteo_features AS (
                SELECT
                    datetime_hour,
                    AVG(heating_degree_hours::double precision) OVER (
                        ORDER BY datetime_hour
                        ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
                    ) AS hdd_24h
                FROM monitoring.meteo_hourly
            ),
            base AS (
                SELECT
                    m.identifikace,
                    m.interval_minutes,
                    m.day_of_week,
                    m.slot,
                    m.delta::double precision AS delta,
                    mf.hdd_24h
                FROM monitoring."Mereni_plynomery_vse" m
                JOIN meteo_features mf
                    ON mf.datetime_hour = date_trunc(
                        'hour',
                        (m.date AT TIME ZONE '{LOCAL_TIMEZONE_NAME}') AT TIME ZONE 'UTC'
                    )
                WHERE
                    m.synthetic = FALSE
                    AND m.platne = TRUE
                    AND m.reset_detected = FALSE
                    AND m.delta IS NOT NULL
                    AND (:data_start IS NULL OR m.date >= :data_start)
                    AND (:data_end IS NULL OR m.date < :data_end)
            ),
            exact_fit AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    COUNT(*) AS sample_size,
                    AVG(delta) AS avg_delta,
                    AVG(hdd_24h) AS avg_hdd_24h,
                    CASE
                        WHEN COUNT(*) >= :min_exact_history
                            AND COALESCE(REGR_SXX(delta, hdd_24h), 0.0) >= :min_hdd_variance
                        THEN GREATEST(COALESCE(REGR_SLOPE(delta, hdd_24h), 0.0), 0.0)
                        ELSE 0.0
                    END AS hdd_slope
                FROM base
                GROUP BY identifikace, interval_minutes, day_of_week, slot
            ),
            exact_residuals AS (
                SELECT
                    b.identifikace,
                    b.interval_minutes,
                    b.day_of_week,
                    b.slot,
                    f.sample_size,
                    (f.avg_delta - f.hdd_slope * f.avg_hdd_24h) AS base_mean,
                    f.hdd_slope,
                    f.avg_hdd_24h,
                    b.delta - (
                        (f.avg_delta - f.hdd_slope * f.avg_hdd_24h)
                        + f.hdd_slope * b.hdd_24h
                    ) AS residual
                FROM base b
                JOIN exact_fit f
                    USING (identifikace, interval_minutes, day_of_week, slot)
                WHERE f.sample_size >= :min_exact_history
            ),
            exact_profiles AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    day_of_week,
                    slot,
                    MAX(base_mean) AS base_mean,
                    MAX(hdd_slope) AS hdd_slope,
                    MAX(avg_hdd_24h) AS hdd_24h_mean,
                    AVG(residual) AS residual_mean,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY residual) AS residual_median,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY residual) AS residual_p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY residual) AS residual_p90,
                    GREATEST(COALESCE(stddev_samp(residual), 0.0), :min_std) AS residual_std,
                    MAX(sample_size)::integer AS sample_size
                FROM exact_residuals
                GROUP BY identifikace, interval_minutes, day_of_week, slot
            ),
            slot_fit AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    slot,
                    COUNT(*) AS sample_size,
                    AVG(delta) AS avg_delta,
                    AVG(hdd_24h) AS avg_hdd_24h,
                    CASE
                        WHEN COUNT(*) >= :min_slot_history
                            AND COALESCE(REGR_SXX(delta, hdd_24h), 0.0) >= :min_hdd_variance
                        THEN GREATEST(COALESCE(REGR_SLOPE(delta, hdd_24h), 0.0), 0.0)
                        ELSE 0.0
                    END AS hdd_slope
                FROM base
                GROUP BY identifikace, interval_minutes, slot
            ),
            slot_residuals AS (
                SELECT
                    b.identifikace,
                    b.interval_minutes,
                    b.slot,
                    f.sample_size,
                    (f.avg_delta - f.hdd_slope * f.avg_hdd_24h) AS base_mean,
                    f.hdd_slope,
                    f.avg_hdd_24h,
                    b.delta - (
                        (f.avg_delta - f.hdd_slope * f.avg_hdd_24h)
                        + f.hdd_slope * b.hdd_24h
                    ) AS residual
                FROM base b
                JOIN slot_fit f
                    USING (identifikace, interval_minutes, slot)
                WHERE f.sample_size >= :min_slot_history
            ),
            slot_profiles AS (
                SELECT
                    identifikace,
                    interval_minutes,
                    slot,
                    MAX(base_mean) AS base_mean,
                    MAX(hdd_slope) AS hdd_slope,
                    MAX(avg_hdd_24h) AS hdd_24h_mean,
                    AVG(residual) AS residual_mean,
                    percentile_cont(0.5) WITHIN GROUP (ORDER BY residual) AS residual_median,
                    percentile_cont(0.1) WITHIN GROUP (ORDER BY residual) AS residual_p10,
                    percentile_cont(0.9) WITHIN GROUP (ORDER BY residual) AS residual_p90,
                    GREATEST(COALESCE(stddev_samp(residual), 0.0), :min_std) AS residual_std,
                    MAX(sample_size)::integer AS sample_size
                FROM slot_residuals
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
            ),
            fallback_profiles AS (
                SELECT
                    stats.identifikace,
                    stats.interval_minutes,
                    days.day_of_week,
                    stats.slot,
                    stats.base_mean,
                    stats.hdd_slope,
                    stats.hdd_24h_mean,
                    stats.residual_mean,
                    stats.residual_median,
                    stats.residual_p10,
                    stats.residual_p90,
                    stats.residual_std,
                    stats.sample_size
                FROM slot_profiles stats
                CROSS JOIN days
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM exact_profiles exact
                    WHERE
                        exact.identifikace = stats.identifikace
                        AND exact.interval_minutes = stats.interval_minutes
                        AND exact.day_of_week = days.day_of_week
                        AND exact.slot = stats.slot
                )
            )
            INSERT INTO monitoring.plynomery_weather_model_profiles (
                identifikace,
                interval_minutes,
                day_of_week,
                slot,
                base_mean,
                hdd_slope,
                hdd_24h_mean,
                residual_mean,
                residual_median,
                residual_p10,
                residual_p90,
                residual_std,
                model_version,
                sample_size
            )
            SELECT
                profiles.identifikace,
                profiles.interval_minutes,
                profiles.day_of_week,
                profiles.slot,
                profiles.base_mean,
                profiles.hdd_slope,
                profiles.hdd_24h_mean,
                profiles.residual_mean,
                profiles.residual_median,
                profiles.residual_p10,
                profiles.residual_p90,
                profiles.residual_std,
                :model_version,
                profiles.sample_size
            FROM (
                SELECT * FROM exact_profiles
                UNION ALL
                SELECT * FROM fallback_profiles
            ) profiles
            """
        ),
        {
            "model_version": model_version,
            "data_start": data_start,
            "data_end": data_end,
            "min_exact_history": MIN_EXACT_HISTORY,
            "min_slot_history": MIN_SLOT_HISTORY,
            "min_std": MIN_STD,
            "min_hdd_variance": MIN_HDD_VARIANCE,
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
                FROM monitoring."Mereni_plynomery_vse"
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
                LEFT JOIN monitoring.plynomery_anomaly_profiles p
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
                COALESCE(SUM(actual_value - predicted_mean), 0.0) AS error_sum
            FROM joined
            """
        ),
        {
            "model_version": model_version,
            "validation_start": windows.validation_start,
            "validation_end": windows.validation_end,
        },
    ).mappings().one()

    return _build_validation_aggregate(row)


def _evaluate_weather_profiles_on_validation(
    session,
    *,
    model_version: int,
    windows: RebuildWindows,
) -> ValidationAggregate:
    row = session.execute(
        text(
            f"""
            WITH meteo_features AS (
                SELECT
                    datetime_hour,
                    AVG(heating_degree_hours::double precision) OVER (
                        ORDER BY datetime_hour
                        ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
                    ) AS hdd_24h
                FROM monitoring.meteo_hourly
            ),
            validation_base AS (
                SELECT
                    m.identifikace,
                    m.interval_minutes,
                    m.day_of_week,
                    m.slot,
                    m.delta::double precision AS delta,
                    mf.hdd_24h
                FROM monitoring."Mereni_plynomery_vse" m
                LEFT JOIN meteo_features mf
                    ON mf.datetime_hour = date_trunc(
                        'hour',
                        (m.date AT TIME ZONE '{LOCAL_TIMEZONE_NAME}') AT TIME ZONE 'UTC'
                    )
                WHERE
                    m.synthetic = FALSE
                    AND m.platne = TRUE
                    AND m.reset_detected = FALSE
                    AND m.delta IS NOT NULL
                    AND m.date >= :validation_start
                    AND m.date < :validation_end
            ),
            joined AS (
                SELECT
                    v.delta AS actual_value,
                    CASE
                        WHEN p.id IS NOT NULL AND v.hdd_24h IS NOT NULL
                        THEN p.base_mean + p.hdd_slope * v.hdd_24h
                        ELSE NULL
                    END AS predicted_mean
                FROM validation_base v
                LEFT JOIN monitoring.plynomery_weather_model_profiles p
                    ON p.model_version = :model_version
                    AND p.identifikace = v.identifikace
                    AND p.interval_minutes = v.interval_minutes
                    AND p.day_of_week = v.day_of_week
                    AND p.slot = v.slot
            )
            SELECT
                (SELECT COUNT(*) FROM validation_base) AS validation_total_count,
                COUNT(predicted_mean) AS matched_validation_count,
                COALESCE(SUM(ABS(actual_value - predicted_mean)), 0.0) AS abs_error_sum,
                COALESCE(SUM(POWER(actual_value - predicted_mean, 2)), 0.0) AS squared_error_sum,
                COALESCE(SUM(actual_value - predicted_mean), 0.0) AS error_sum
            FROM joined
            """
        ),
        {
            "model_version": model_version,
            "validation_start": windows.validation_start,
            "validation_end": windows.validation_end,
        },
    ).mappings().one()

    return _build_validation_aggregate(row)


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
                SELECT identifikace, interval_minutes, day_of_week, slot, delta
                FROM monitoring."Mereni_plynomery_vse"
                WHERE synthetic = FALSE
                  AND platne = TRUE
                  AND reset_detected = FALSE
                  AND delta IS NOT NULL
                  AND date >= :validation_start
                  AND date < :validation_end
            ),
            joined AS (
                SELECT v.identifikace, v.delta AS actual_value,
                       p.id AS profile_id, p.mean AS predicted_mean
                FROM validation_base v
                LEFT JOIN monitoring.plynomery_anomaly_profiles p
                  ON p.model_version = :model_version
                 AND p.identifikace = v.identifikace
                 AND p.interval_minutes = v.interval_minutes
                 AND p.day_of_week = v.day_of_week
                 AND p.slot = v.slot
            )
            SELECT identifikace,
                   COUNT(*) AS validation_total_count,
                   COUNT(profile_id) AS matched_validation_count,
                   COALESCE(SUM(ABS(actual_value - predicted_mean)), 0.0) AS abs_error_sum,
                   COALESCE(SUM(POWER(actual_value - predicted_mean, 2)), 0.0) AS squared_error_sum,
                   COALESCE(SUM(actual_value - predicted_mean), 0.0) AS error_sum,
                   COALESCE(SUM(CASE WHEN profile_id IS NOT NULL
                                     THEN ABS(actual_value) ELSE 0.0 END), 0.0)
                       AS matched_actual_abs_sum
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
        str(row["identifikace"]): _build_validation_aggregate(row)
        for row in rows
    }


def _evaluate_weather_profiles_on_validation_by_identifikace(
    session,
    *,
    model_version: int,
    windows: RebuildWindows,
) -> dict[str, ValidationAggregate]:
    rows = session.execute(
        text(
            f"""
            WITH meteo_features AS (
                SELECT datetime_hour,
                       AVG(heating_degree_hours::double precision) OVER (
                           ORDER BY datetime_hour
                           ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
                       ) AS hdd_24h
                FROM monitoring.meteo_hourly
            ),
            validation_base AS (
                SELECT m.identifikace, m.interval_minutes, m.day_of_week, m.slot,
                       m.delta::double precision AS delta, mf.hdd_24h
                FROM monitoring."Mereni_plynomery_vse" m
                LEFT JOIN meteo_features mf
                  ON mf.datetime_hour = date_trunc(
                      'hour',
                      (m.date AT TIME ZONE '{LOCAL_TIMEZONE_NAME}') AT TIME ZONE 'UTC'
                  )
                WHERE m.synthetic = FALSE
                  AND m.platne = TRUE
                  AND m.reset_detected = FALSE
                  AND m.delta IS NOT NULL
                  AND m.date >= :validation_start
                  AND m.date < :validation_end
            ),
            joined AS (
                SELECT v.identifikace, v.delta AS actual_value,
                       CASE WHEN p.id IS NOT NULL AND v.hdd_24h IS NOT NULL
                            THEN p.base_mean + p.hdd_slope * v.hdd_24h
                            ELSE NULL END AS predicted_mean
                FROM validation_base v
                LEFT JOIN monitoring.plynomery_weather_model_profiles p
                  ON p.model_version = :model_version
                 AND p.identifikace = v.identifikace
                 AND p.interval_minutes = v.interval_minutes
                 AND p.day_of_week = v.day_of_week
                 AND p.slot = v.slot
            )
            SELECT identifikace,
                   COUNT(*) AS validation_total_count,
                   COUNT(predicted_mean) AS matched_validation_count,
                   COALESCE(SUM(ABS(actual_value - predicted_mean)), 0.0) AS abs_error_sum,
                   COALESCE(SUM(POWER(actual_value - predicted_mean, 2)), 0.0) AS squared_error_sum,
                   COALESCE(SUM(actual_value - predicted_mean), 0.0) AS error_sum,
                   COALESCE(SUM(CASE WHEN predicted_mean IS NOT NULL
                                     THEN ABS(actual_value) ELSE 0.0 END), 0.0)
                       AS matched_actual_abs_sum
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
        str(row["identifikace"]): _build_validation_aggregate(row)
        for row in rows
    }


def _build_validation_aggregate(row) -> ValidationAggregate:
    validation_total_count = int(row["validation_total_count"] or 0)
    matched_validation_count = int(row["matched_validation_count"] or 0)
    abs_error_sum = float(row["abs_error_sum"] or 0.0)
    squared_error_sum = float(row["squared_error_sum"] or 0.0)
    error_sum = float(row["error_sum"] or 0.0)
    matched_actual_abs_sum = float(
        row.get("matched_actual_abs_sum", 0.0) or 0.0
    )
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


def _combine_validation_aggregates(
    aggregates: Sequence[ValidationAggregate],
) -> PredictionMetricSummary:
    validation_total_count = sum(item.validation_total_count for item in aggregates)
    matched_validation_count = sum(item.matched_validation_count for item in aggregates)
    coverage = (
        0.0
        if validation_total_count <= 0
        else matched_validation_count / validation_total_count
    )
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
    rows = []
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


def _build_dry_run_selected_model_decisions(
    *,
    device_summaries: Sequence[DeviceModelPerformanceSummary],
    selected_summary: ModelPerformanceSummary,
    forecast_period: PredictionForecastPeriod,
    selection_run_id: int,
    deployable_profile_catalog: DeployableProfileCatalog,
    coverage_threshold: float = MODEL_SELECTION_COVERAGE_THRESHOLD,
    minimum_fold_count: int = MODEL_SELECTION_MIN_FOLD_COUNT,
    selection_mode: str = SELECTION_MODE_DRY_RUN,
) -> tuple[PredictionSelectedModelDecision, ...]:
    normalized_selection_mode = normalize_selection_mode(selection_mode)
    summaries_by_identifier: dict[str, list[DeviceModelPerformanceSummary]] = defaultdict(list)
    for summary in device_summaries:
        summaries_by_identifier[summary.identifikace].append(summary)

    decisions = []
    for identifier, summaries in sorted(summaries_by_identifier.items()):
        fallback_metric_summaries = [
            summary for summary in summaries
            if _device_summary_has_fallback_metrics(summary)
        ]
        selection_metric_summaries = [
            summary for summary in fallback_metric_summaries
            if summary.rolling_wape is not None
        ]
        eligible_summaries = [
            summary for summary in selection_metric_summaries
            if summary.selection_enabled
        ]
        folded_summaries = [
            summary for summary in eligible_summaries
            if summary.rolling_backtest_fold_count >= minimum_fold_count
        ]
        threshold_summaries = [
            summary for summary in folded_summaries
            if summary.rolling_coverage >= coverage_threshold
        ]
        deployable_threshold_summaries = [
            summary for summary in threshold_summaries
            if (identifier, summary.model_version) in deployable_profile_catalog
        ]

        selected_device_summary = None
        if deployable_threshold_summaries:
            selected_device_summary = min(
                deployable_threshold_summaries,
                key=_device_summary_selection_key,
            )
            metric_winner = min(
                threshold_summaries,
                key=_device_summary_selection_key,
            )
            fallback_reason = (
                PredictionSelectionFallbackReason.MISSING_PROFILE
                if selected_device_summary is not metric_winner
                else PredictionSelectionFallbackReason.NONE
            )
        else:
            global_device_summary = _find_device_summary_for_model(
                fallback_metric_summaries,
                model_version=selected_summary.model_version,
            )
            global_pair = (identifier, selected_summary.model_version)
            if global_pair in deployable_profile_catalog:
                fallback_reason = (
                    PredictionSelectionFallbackReason.MISSING_PROFILE
                    if threshold_summaries
                    else _resolve_device_selection_fallback_reason(
                        selection_metric_summaries=selection_metric_summaries,
                        eligible_summaries=eligible_summaries,
                        folded_summaries=folded_summaries,
                    )
                )
            else:
                deployable_summaries = [
                    summary for summary in eligible_summaries
                    if (identifier, summary.model_version)
                    in deployable_profile_catalog
                ]
                if not deployable_summaries:
                    fallback_reason = (
                        PredictionSelectionFallbackReason.INSUFFICIENT_HISTORY
                    )
                else:
                    selected_device_summary = min(
                        deployable_summaries,
                        key=_device_summary_selection_key,
                    )
                    fallback_reason = (
                        PredictionSelectionFallbackReason.MISSING_PROFILE
                    )

        selected = selected_device_summary or _find_device_summary_for_model(
            fallback_metric_summaries,
            model_version=selected_summary.model_version,
        )
        if selected_device_summary is None:
            selected_model_version = selected_summary.model_version
            selected_model_key = _model_summary_key(selected_summary)
            selected_model_name = selected_summary.model_name
        else:
            selected_model_version = selected.model_version
            selected_model_key = _device_model_key(selected)
            selected_model_name = selected.model_name

        decisions.append(
            PredictionSelectedModelDecision(
                medium_key=PLYNOMERY_MEDIUM_KEY,
                identifier=identifier,
                forecast_period=forecast_period,
                selection_run_id=selection_run_id,
                selected_model_version=selected_model_version,
                selected_model_key=selected_model_key,
                selected_model_name=selected_model_name,
                global_model_version=selected_summary.model_version,
                global_model_key=_model_summary_key(selected_summary),
                global_model_name=selected_summary.model_name,
                fallback_reason=fallback_reason,
                metrics=(
                    None
                    if selected is None
                    else _device_summary_to_metric_summary(selected)
                ),
                metadata={
                    "selection_mode": normalized_selection_mode,
                    "selection_policy": "eligible_rolling_wape_min_coverage",
                    "coverage_threshold": coverage_threshold,
                    "minimum_fold_count": minimum_fold_count,
                    "prediction_available": (
                        fallback_reason
                        is not PredictionSelectionFallbackReason.INSUFFICIENT_HISTORY
                    ),
                    "availability_reason": (
                        None
                        if fallback_reason
                        is not PredictionSelectionFallbackReason.INSUFFICIENT_HISTORY
                        else PredictionSelectionFallbackReason.INSUFFICIENT_HISTORY.value
                    ),
                    "deployable_profile_required": (
                        fallback_reason
                        is not PredictionSelectionFallbackReason.INSUFFICIENT_HISTORY
                    ),
                    "metric_winner_missing_profile": (
                        fallback_reason
                        is PredictionSelectionFallbackReason.MISSING_PROFILE
                    ),
                },
            )
        )
    return tuple(decisions)


def _device_summary_has_fallback_metrics(
    summary: DeviceModelPerformanceSummary,
) -> bool:
    return (
        summary.rolling_validation_total_count > 0
        and summary.rolling_matched_validation_count > 0
        and summary.rolling_mae is not None
        and summary.rolling_rmse is not None
        and summary.rolling_bias is not None
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
    selection_metric_summaries: Sequence[DeviceModelPerformanceSummary],
    eligible_summaries: Sequence[DeviceModelPerformanceSummary],
    folded_summaries: Sequence[DeviceModelPerformanceSummary],
) -> PredictionSelectionFallbackReason:
    if not selection_metric_summaries:
        return PredictionSelectionFallbackReason.NO_IDENTIFIER_METRICS
    if not eligible_summaries:
        return PredictionSelectionFallbackReason.NO_ELIGIBLE_CANDIDATE
    if not folded_summaries:
        return PredictionSelectionFallbackReason.BELOW_FOLD_COUNT_THRESHOLD
    return PredictionSelectionFallbackReason.BELOW_COVERAGE_THRESHOLD


def _find_device_summary_for_model(
    summaries: Sequence[DeviceModelPerformanceSummary],
    *,
    model_version: int,
) -> DeviceModelPerformanceSummary | None:
    return next(
        (
            summary for summary in summaries
            if summary.model_version == model_version
        ),
        None,
    )


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


def _build_dry_run_profile_snapshot_rows(
    decisions: Sequence[PredictionSelectedModelDecision],
    *,
    deployable_profile_catalog: DeployableProfileCatalog,
    windows: RebuildWindows,
    archive_source: str = ARCHIVE_SOURCE_WEEKLY_REBUILD,
    archive_version: int = 1,
    archive_run_id: str | None = None,
    selection_mode: str = SELECTION_MODE_DRY_RUN,
) -> tuple[dict[str, object], ...]:
    if archive_version <= 0:
        raise ValueError("Prediction profile archive version must be positive.")
    normalized_archive_source = normalize_archive_source(archive_source)
    normalized_selection_mode = normalize_selection_mode(selection_mode)
    rows = []
    archived_pairs = set()
    for decision in decisions:
        if decision.metadata.get("prediction_available") is False:
            continue
        pair = (decision.identifier, int(decision.selected_model_version))
        points = deployable_profile_catalog.get(pair, ())
        if not points:
            continue
        archived_pairs.add(pair)
        for point in points:
            rows.append(
                {
                    "medium_key": decision.medium_key,
                    "identifier": decision.identifier,
                    "forecast_period_start": decision.forecast_period.start,
                    "forecast_period_end": decision.forecast_period.end,
                    "forecast_cadence": decision.forecast_period.cadence.value,
                    "forecast_period_label": decision.forecast_period.label,
                    "archive_source": normalized_archive_source,
                    "archive_version": archive_version,
                    "selection_mode": normalized_selection_mode,
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
                    "interval_minutes": point.interval_minutes,
                    "day_of_week": point.day_of_week,
                    "slot": point.slot,
                    "expected_mean": point.expected_mean,
                    "expected_median": point.expected_median,
                    "expected_p10": point.expected_p10,
                    "expected_p90": point.expected_p90,
                    "expected_std": point.expected_std,
                    "sample_size": point.sample_size,
                    "source_profile_created_at": None,
                    "training_window_start": windows.train_start,
                    "training_window_end": windows.train_end,
                    "validation_window_start": windows.validation_start,
                    "validation_window_end": windows.validation_end,
                    "metadata_json": json.dumps(
                        dict(point.features),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                }
            )

    selected_pairs = {
        (decision.identifier, int(decision.selected_model_version))
        for decision in decisions
        if decision.metadata.get("prediction_available") is not False
    }
    missing_pair_count = len(selected_pairs - archived_pairs)
    if missing_pair_count:
        raise RuntimeError(
            "Dry-run plynomery profile archive is missing deployable profiles "
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


def _load_deployable_profile_catalog(
    session,
    device_summaries: Sequence[DeviceModelPerformanceSummary],
) -> DeployableProfileCatalog:
    identifiers = sorted({summary.identifikace for summary in device_summaries})
    model_versions = sorted({summary.model_version for summary in device_summaries})
    if not identifiers or not model_versions:
        return {}

    profiles_by_pair: dict[tuple[str, int], list[PredictionProfilePoint]] = defaultdict(list)
    if MODEL_VERSION_BASELINE in model_versions:
        profiles = (
            session.execute(
                select(PlynomeryProfilesAnomaly).where(
                    PlynomeryProfilesAnomaly.identifikace.in_(identifiers),
                    PlynomeryProfilesAnomaly.model_version == MODEL_VERSION_BASELINE,
                )
            )
            .scalars()
            .all()
        )
        for profile in profiles:
            point = _static_profile_to_prediction_point(profile)
            profiles_by_pair[(point.identifier, point.model_version)].append(point)

    if MODEL_VERSION_WEATHER_ADJUSTED in model_versions:
        profiles = (
            session.execute(
                select(PlynomeryWeatherModelProfile).where(
                    PlynomeryWeatherModelProfile.identifikace.in_(identifiers),
                    PlynomeryWeatherModelProfile.model_version
                    == MODEL_VERSION_WEATHER_ADJUSTED,
                )
            )
            .scalars()
            .all()
        )
        for profile in profiles:
            point = _weather_profile_to_prediction_point(profile)
            profiles_by_pair[(point.identifier, point.model_version)].append(point)

    unsupported_versions = set(model_versions) - {
        MODEL_VERSION_BASELINE,
        MODEL_VERSION_WEATHER_ADJUSTED,
    }
    if unsupported_versions:
        raise ValueError(
            "Unsupported plynomery deployable profile model versions: "
            f"{sorted(unsupported_versions)}"
        )

    return {
        pair: tuple(
            sorted(
                points,
                key=lambda point: (
                    point.interval_minutes,
                    point.day_of_week,
                    point.slot,
                ),
            )
        )
        for pair, points in sorted(profiles_by_pair.items())
        if points
    }


def _static_profile_to_prediction_point(profile) -> PredictionProfilePoint:
    point = PredictionProfilePoint(
        identifier=str(profile.identifikace),
        interval_minutes=int(profile.interval_minutes),
        day_of_week=int(profile.day_of_week),
        slot=int(profile.slot),
        expected_mean=float(profile.mean),
        expected_median=float(profile.median),
        expected_p10=float(profile.p10),
        expected_p90=float(profile.p90),
        expected_std=float(profile.std),
        sample_size=int(profile.sample_size),
        model_version=int(profile.model_version),
        features={"profile_kind": "static"},
    )
    _validate_deployable_profile_point(point)
    return point


def _weather_profile_to_prediction_point(profile) -> PredictionProfilePoint:
    base_mean = float(profile.base_mean)
    hdd_slope = float(profile.hdd_slope)
    hdd_24h_mean = float(profile.hdd_24h_mean)
    reference_mean = base_mean + hdd_slope * hdd_24h_mean
    point = PredictionProfilePoint(
        identifier=str(profile.identifikace),
        interval_minutes=int(profile.interval_minutes),
        day_of_week=int(profile.day_of_week),
        slot=int(profile.slot),
        expected_mean=reference_mean,
        expected_median=reference_mean + float(profile.residual_median),
        expected_p10=reference_mean + float(profile.residual_p10),
        expected_p90=reference_mean + float(profile.residual_p90),
        expected_std=float(profile.residual_std),
        sample_size=int(profile.sample_size),
        model_version=int(profile.model_version),
        features={
            "profile_kind": "weather_adjusted",
            "base_mean": base_mean,
            "hdd_slope": hdd_slope,
            "hdd_24h_mean": hdd_24h_mean,
            "residual_mean": float(profile.residual_mean),
            "residual_median": float(profile.residual_median),
            "residual_p10": float(profile.residual_p10),
            "residual_p90": float(profile.residual_p90),
            "residual_std": float(profile.residual_std),
        },
    )
    _validate_deployable_profile_point(point)
    return point


def _validate_deployable_profile_point(point: PredictionProfilePoint) -> None:
    numeric_values = (
        point.expected_mean,
        point.expected_median,
        point.expected_p10,
        point.expected_p90,
        point.expected_std,
        *(
            value
            for key, value in point.features.items()
            if key != "profile_kind"
        ),
    )
    if (
        not point.identifier
        or point.interval_minutes <= 0
        or not 0 <= point.day_of_week <= 6
        or point.slot < 0
        or point.sample_size <= 0
        or point.model_version <= 0
        or any(not isfinite(float(value)) for value in numeric_values)
        or point.expected_std <= 0
        or point.expected_p10 > point.expected_p90
    ):
        raise RuntimeError(
            "Unusable deployable plynomery profile "
            f"for model {point.model_version}."
        )
