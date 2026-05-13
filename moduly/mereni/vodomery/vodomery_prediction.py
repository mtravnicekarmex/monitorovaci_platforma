from __future__ import annotations

import calendar
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import bindparam, insert, text

from app.time_utils import utc_now_naive
from core.db.connect import get_session_pg
from moduly.mereni.vodomery.database.model_validation import (
    ensure_vodomery_model_validation_tables,
    get_active_vodomery_model_version,
)
from moduly.mereni.vodomery.database.models import (
    VodomeryProfilesAnomaly,
    VodomeryModelSelectionCandidate,
    VodomeryModelSelectionRun,
    VodomeryModelValidationMetric,
    VodomeryModelValidationRun,
)
from moduly.mereni.vodomery.database.runtime_schema import drop_legacy_identifikace_fk


MODEL_VERSION_BASELINE = 1
MODEL_VERSION_LEARNING = 2
MODEL_VERSION_HIERARCHICAL = 3
DEFAULT_MODEL_VERSION = MODEL_VERSION_BASELINE
MODEL_SELECTION_TRAINING_MONTHS = 3
MODEL_SELECTION_VALIDATION_MONTHS = 1
MODEL_SELECTION_COVERAGE_THRESHOLD = 0.85
MODEL_EVALUATION_VERSION_OFFSET = 1000
MODEL_V3_RECENCY_HALF_LIFE_DAYS = 21.0
MODEL_V3_DOW_WEIGHT_TARGET = 4.0
MODEL_V3_WORKDAY_WEIGHT_TARGET = 10.0
MODEL_V3_SLOT_WEIGHT_TARGET = 14.0

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


CANDIDATE_MODELS: tuple[CandidateModelDefinition, ...] = (
    CandidateModelDefinition(
        model_version=MODEL_VERSION_BASELINE,
        model_name="Model 1 - baseline MAD",
    ),
    CandidateModelDefinition(
        model_version=MODEL_VERSION_LEARNING,
        model_name="Model 2 - adaptive strategy",
    ),
    CandidateModelDefinition(
        model_version=MODEL_VERSION_HIERARCHICAL,
        model_name="Model 3 - recency weighted blend",
    ),
)
MODEL_NAME_BY_VERSION = {
    definition.model_version: definition.model_name
    for definition in CANDIDATE_MODELS
}


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
    selected_device_count: int | None = None
    validation_candidate_count: int | None = None

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
            "selected_device_count": self.selected_device_count,
            "validation_candidate_count": self.validation_candidate_count,
            "selected": selected,
        }


def get_candidate_model_definitions() -> tuple[CandidateModelDefinition, ...]:
    return CANDIDATE_MODELS


def get_candidate_model_versions() -> tuple[int, ...]:
    return tuple(definition.model_version for definition in get_candidate_model_definitions())


def get_runtime_model_version(*, session=None, default: int = DEFAULT_MODEL_VERSION) -> int:
    return get_active_vodomery_model_version(session=session, default=default)


def build_rebuild_windows(
    reference_time: datetime | None = None,
    *,
    training_window_months: int = MODEL_SELECTION_TRAINING_MONTHS,
    validation_window_months: int = MODEL_SELECTION_VALIDATION_MONTHS,
) -> RebuildWindows:
    deploy_end = reference_time or utc_now_naive()
    validation_end = deploy_end
    validation_start = _subtract_months(validation_end, validation_window_months)
    train_end = validation_start
    train_start = _subtract_months(train_end, training_window_months)
    deploy_start = train_start
    return RebuildWindows(
        train_start=train_start,
        train_end=train_end,
        validation_start=validation_start,
        validation_end=validation_end,
        deploy_start=deploy_start,
        deploy_end=deploy_end,
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
    if model_version is not None:
        windows = build_rebuild_windows(reference_time=reference_time)
        drop_legacy_identifikace_fk(VodomeryProfilesAnomaly.__tablename__)
        return _rebuild_single_candidate_model(model_version=model_version, windows=windows)

    ensure_vodomery_model_validation_tables()
    drop_legacy_identifikace_fk(VodomeryProfilesAnomaly.__tablename__)
    windows = build_rebuild_windows(reference_time=reference_time)
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
            "Profiles rebuild complete "
            f"(selection_run_id={selection_run.id}, active_model_version={selected_summary.model_version})"
        )
        return result
    finally:
        session.close()


def _rebuild_single_candidate_model(
    *,
    model_version: int,
    windows: RebuildWindows,
) -> dict[str, object]:
    definition = _get_candidate_model_definition(model_version)
    if definition is None:
        raise ValueError(f"Neznama verze modelu: {model_version}")

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


def _get_candidate_model_definition(model_version: int) -> CandidateModelDefinition | None:
    return next(
        (
            definition
            for definition in get_candidate_model_definitions()
            if definition.model_version == model_version
        ),
        None,
    )


def _rebuild_candidate_model(
    session,
    *,
    definition: CandidateModelDefinition,
    windows: RebuildWindows,
) -> ModelPerformanceSummary:
    if definition.model_version == MODEL_VERSION_BASELINE:
        return _rebuild_model_1_candidate(session, definition=definition, windows=windows)
    if definition.model_version == MODEL_VERSION_LEARNING:
        return _rebuild_model_2_candidate(session, definition=definition, windows=windows)
    if definition.model_version == MODEL_VERSION_HIERARCHICAL:
        return _rebuild_model_3_candidate(session, definition=definition, windows=windows)
    raise ValueError(f"Neznama verze modelu: {definition.model_version}")


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
    return ModelPerformanceSummary(
        model_version=definition.model_version,
        model_name=definition.model_name,
        validation_total_count=validation.validation_total_count,
        matched_validation_count=validation.matched_validation_count,
        coverage=validation.coverage,
        mae=validation.mae,
        rmse=validation.rmse,
        bias=validation.bias,
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

    return ModelPerformanceSummary(
        model_version=definition.model_version,
        model_name=definition.model_name,
        validation_total_count=validation.validation_total_count,
        matched_validation_count=validation.matched_validation_count,
        coverage=validation.coverage,
        mae=validation.mae,
        rmse=validation.rmse,
        bias=validation.bias,
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
    return ModelPerformanceSummary(
        model_version=definition.model_version,
        model_name=definition.model_name,
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
                "model_name": summary.model_name,
                "validation_total_count": summary.validation_total_count,
                "matched_validation_count": summary.matched_validation_count,
                "coverage": round(summary.coverage, 6),
                "mae": None if summary.mae is None else round(summary.mae, 6),
                "rmse": None if summary.rmse is None else round(summary.rmse, 6),
                "bias": None if summary.bias is None else round(summary.bias, 6),
                "profile_count": summary.profile_count,
                "selected": summary.model_version == selected_summary.model_version,
            }
            for summary in summaries
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

    candidates = _load_model_2_candidate_metrics(session, windows)
    selected_by_ident: dict[str, ValidationCandidate] = {}
    candidates_by_ident: dict[str, list[ValidationCandidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_ident[candidate.identifikace].append(candidate)

    for identifikace, ident_candidates in candidates_by_ident.items():
        best_candidate = select_best_strategy(ident_candidates)
        if best_candidate is not None:
            selected_by_ident[identifikace] = best_candidate

    _persist_validation_metrics(
        session,
        run_id=int(run.id),
        model_version=MODEL_VERSION_LEARNING,
        candidates=candidates,
        selected_by_ident=selected_by_ident,
    )
    return run, candidates, selected_by_ident


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
            "half_life_days": MODEL_V3_RECENCY_HALF_LIFE_DAYS,
            "dow_weight_target": MODEL_V3_DOW_WEIGHT_TARGET,
            "workday_weight_target": MODEL_V3_WORKDAY_WEIGHT_TARGET,
            "slot_weight_target": MODEL_V3_SLOT_WEIGHT_TARGET,
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
