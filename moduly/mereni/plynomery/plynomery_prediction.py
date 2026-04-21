from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG, get_session_pg
from moduly.mereni.plynomery.database.models import PlynomeryProfilesAnomaly


MODEL_VERSION_BASELINE = 1
DEFAULT_MODEL_VERSION = MODEL_VERSION_BASELINE
MODEL_REBUILD_LOOKBACK_DAYS = 120
MODEL_VALIDATION_WINDOW_DAYS = 7
MODEL_EVALUATION_VERSION_OFFSET = 1000
MIN_EXACT_HISTORY = 8
MIN_SLOT_HISTORY = 32
MIN_STD = 0.0001


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
)
MODEL_NAME_BY_VERSION = {
    definition.model_version: definition.model_name
    for definition in CANDIDATE_MODELS
}


def ensure_prediction_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        PlynomeryProfilesAnomaly.__table__.create(bind=conn, checkfirst=True)


def get_candidate_model_definitions() -> tuple[CandidateModelDefinition, ...]:
    return CANDIDATE_MODELS


def get_candidate_model_versions() -> tuple[int, ...]:
    return tuple(definition.model_version for definition in get_candidate_model_definitions())


def get_runtime_model_version(*, session=None, default: int = DEFAULT_MODEL_VERSION) -> int:
    return MODEL_VERSION_BASELINE


def build_rebuild_windows(
    reference_time: datetime | None = None,
    *,
    lookback_days: int = MODEL_REBUILD_LOOKBACK_DAYS,
    validation_window_days: int = MODEL_VALIDATION_WINDOW_DAYS,
) -> RebuildWindows:
    deploy_end = reference_time or utc_now_naive()
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


def rebuild_profiles(
    model_version: int | None = None,
    reference_time: datetime | None = None,
) -> dict[str, object]:
    if model_version is not None and model_version != MODEL_VERSION_BASELINE:
        raise ValueError(f"Neznama verze modelu: {model_version}")

    ensure_prediction_tables()
    windows = build_rebuild_windows(reference_time=reference_time)
    session = get_session_pg()

    try:
        summary = _rebuild_baseline_candidate(
            session,
            model_version=MODEL_VERSION_BASELINE,
            windows=windows,
        )
        session.commit()
    finally:
        session.close()

    if model_version is not None:
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

    result = {
        "selection_run_id": None,
        "active_model_version": summary.model_version,
        "active_model_name": summary.model_name,
        "previous_active_model_version": summary.model_version,
        "previous_active_model_name": summary.model_name,
        "windows": {
            "train_start": windows.train_start,
            "train_end": windows.train_end,
            "validation_start": windows.validation_start,
            "validation_end": windows.validation_end,
            "deploy_start": windows.deploy_start,
            "deploy_end": windows.deploy_end,
        },
        "candidates": [summary.to_dict(selected=True)],
    }
    print(
        "Plynomery profiles rebuild complete "
        f"(active_model_version={summary.model_version}, profile_count={summary.profile_count})"
    )
    return result


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
