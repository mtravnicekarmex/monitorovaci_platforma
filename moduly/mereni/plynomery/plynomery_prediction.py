from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import text

from app.time_utils import prague_now_naive
from core.db.connect import ENGINE_PG, get_session_pg
from moduly.apps.meteo.meteo_sync import ensure_meteo_tables
from moduly.mereni.plynomery.database.models import (
    PlynomeryModelSelectionCandidate,
    PlynomeryModelSelectionRun,
    PlynomeryProfilesAnomaly,
)


MODEL_VERSION_BASELINE = 1
MODEL_VERSION_WEATHER_ADJUSTED = 2
DEFAULT_MODEL_VERSION = MODEL_VERSION_BASELINE
MODEL_REBUILD_LOOKBACK_DAYS = 120
MODEL_VALIDATION_WINDOW_DAYS = 7
MODEL_SELECTION_COVERAGE_THRESHOLD = 0.85
MODEL_EVALUATION_VERSION_OFFSET = 1000
MIN_EXACT_HISTORY = 8
MIN_SLOT_HISTORY = 32
MIN_STD = 0.0001
MIN_HDD_VARIANCE = 0.0001
LOCAL_TIMEZONE_NAME = "Europe/Prague"


@dataclass(frozen=True)
class CandidateModelDefinition:
    model_version: int
    model_name: str


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

    def to_dict(self, *, selected: bool) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "model_name": self.model_name,
            "validation_total_count": self.validation_total_count,
            "matched_validation_count": self.matched_validation_count,
            "coverage": round(self.coverage, 6),
            "mae": None if self.mae is None else round(self.mae, 6),
            "rmse": None if self.rmse is None else round(self.rmse, 6),
            "bias": None if self.bias is None else round(self.bias, 6),
            "profile_count": self.profile_count,
            "selected": selected,
        }


CANDIDATE_MODELS: tuple[CandidateModelDefinition, ...] = (
    CandidateModelDefinition(
        model_version=MODEL_VERSION_BASELINE,
        model_name="Model 1 - exact/fallback baseline",
    ),
    CandidateModelDefinition(
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
        model_name="Model 2 - weather adjusted baseline",
    ),
)
MODEL_NAME_BY_VERSION = {
    definition.model_version: definition.model_name
    for definition in CANDIDATE_MODELS
}


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
                model_name VARCHAR(100) NOT NULL,
                validation_total_count INTEGER NOT NULL,
                matched_validation_count INTEGER NOT NULL,
                coverage DOUBLE PRECISION NOT NULL,
                mae DOUBLE PRECISION,
                rmse DOUBLE PRECISION,
                bias DOUBLE PRECISION,
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
    return CANDIDATE_MODELS


def get_candidate_model_versions() -> tuple[int, ...]:
    return tuple(definition.model_version for definition in get_candidate_model_definitions())


def get_runtime_model_version(*, session=None, default: int = DEFAULT_MODEL_VERSION) -> int:
    ensure_prediction_tables()
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
    lookback_days: int = MODEL_REBUILD_LOOKBACK_DAYS,
    validation_window_days: int = MODEL_VALIDATION_WINDOW_DAYS,
) -> RebuildWindows:
    deploy_end = reference_time or prague_now_naive()
    validation_end = deploy_end
    validation_start = validation_end - timedelta(days=validation_window_days)
    train_start = deploy_end - timedelta(days=lookback_days)
    train_end = validation_start
    deploy_start = deploy_end - timedelta(days=lookback_days)
    return RebuildWindows(
        train_start=train_start,
        train_end=train_end,
        validation_start=validation_start,
        validation_end=validation_end,
        deploy_start=deploy_start,
        deploy_end=deploy_end,
    )


def select_best_model_summary(
    summaries: Sequence[ModelPerformanceSummary],
    *,
    coverage_threshold: float = MODEL_SELECTION_COVERAGE_THRESHOLD,
) -> ModelPerformanceSummary | None:
    eligible_summaries = [
        summary
        for summary in summaries
        if summary.validation_total_count > 0
        and summary.matched_validation_count > 0
        and summary.mae is not None
        and summary.rmse is not None
        and summary.bias is not None
    ]
    if not eligible_summaries:
        return None

    return min(
        eligible_summaries,
        key=lambda summary: (
            0 if summary.coverage >= coverage_threshold else 1,
            summary.mae,
            summary.rmse,
            abs(summary.bias),
            -summary.matched_validation_count,
            summary.model_version,
        ),
    )


def rebuild_profiles(
    model_version: int | None = None,
    reference_time: datetime | None = None,
) -> dict[str, object]:
    if model_version is not None and model_version not in get_candidate_model_versions():
        raise ValueError(f"Neznama verze modelu: {model_version}")

    ensure_prediction_tables()
    windows = build_rebuild_windows(reference_time=reference_time)

    if model_version is not None:
        definition = MODEL_NAME_BY_VERSION[model_version]
        session = get_session_pg()
        try:
            summary = _rebuild_candidate_model(
                session,
                definition=CandidateModelDefinition(model_version, definition),
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

    session = get_session_pg()
    try:
        previous_active_model_version = get_runtime_model_version(
            session=session,
            default=DEFAULT_MODEL_VERSION,
        )
        summaries = [
            _rebuild_candidate_model(
                session,
                definition=definition,
                windows=windows,
            )
            for definition in get_candidate_model_definitions()
        ]
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
        session.commit()

        result = {
            "selection_run_id": int(selection_run.id),
            "active_model_version": selected_summary.model_version,
            "active_model_name": selected_summary.model_name,
            "previous_active_model_version": previous_active_model_version,
            "previous_active_model_name": MODEL_NAME_BY_VERSION.get(
                previous_active_model_version,
                f"Model {previous_active_model_version}",
            ),
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
        }
        print(
            "Plynomery profiles rebuild complete "
            f"(selection_run_id={selection_run.id}, active_model_version={selected_summary.model_version})"
        )
        return result
    finally:
        session.close()


def _rebuild_candidate_model(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    if definition.model_version == MODEL_VERSION_BASELINE:
        return _rebuild_baseline_candidate(
            session,
            model_version=definition.model_version,
            windows=windows,
        )
    if definition.model_version == MODEL_VERSION_WEATHER_ADJUSTED:
        return _rebuild_weather_adjusted_candidate(
            session,
            model_version=definition.model_version,
            windows=windows,
        )
    raise ValueError(f"Neznama verze modelu: {definition.model_version}")


def _rebuild_baseline_candidate(
    session,
    *,
    model_version: int,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
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
        model_name=MODEL_NAME_BY_VERSION[model_version],
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
    model_version: int,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
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
        model_name=MODEL_NAME_BY_VERSION[model_version],
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
                model_name=summary.model_name,
                validation_total_count=summary.validation_total_count,
                matched_validation_count=summary.matched_validation_count,
                coverage=summary.coverage,
                mae=summary.mae,
                rmse=summary.rmse,
                bias=summary.bias,
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


def _build_validation_aggregate(row) -> ValidationAggregate:
    validation_total_count = int(row["validation_total_count"] or 0)
    matched_validation_count = int(row["matched_validation_count"] or 0)
    if validation_total_count <= 0:
        return ValidationAggregate(
            validation_total_count=0,
            matched_validation_count=0,
            coverage=0.0,
            mae=None,
            rmse=None,
            bias=None,
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
        )

    abs_error_sum = float(row["abs_error_sum"] or 0.0)
    squared_error_sum = float(row["squared_error_sum"] or 0.0)
    error_sum = float(row["error_sum"] or 0.0)
    return ValidationAggregate(
        validation_total_count=validation_total_count,
        matched_validation_count=matched_validation_count,
        coverage=coverage,
        mae=abs_error_sum / matched_validation_count,
        rmse=(squared_error_sum / matched_validation_count) ** 0.5,
        bias=error_sum / matched_validation_count,
    )
