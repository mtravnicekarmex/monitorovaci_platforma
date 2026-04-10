from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from sqlalchemy import bindparam, insert, text

from app.time_utils import utc_now_naive
from core.db.connect import get_session_pg
from moduly.mereni.vodomery.database.model_validation import ensure_vodomery_model_validation_tables
from moduly.mereni.vodomery.database.models import (
    VodomeryModelValidationMetric,
    VodomeryModelValidationRun,
)


MODEL_VERSION_LEARNING = 2
MODEL_V2_TRAINING_WINDOW_DAYS = 120
MODEL_V2_VALIDATION_WINDOW_DAYS = 7
MODEL_V2_COVERAGE_THRESHOLD = 0.85

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
class RebuildWindows:
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    deploy_start: datetime
    deploy_end: datetime


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


def build_model_2_rebuild_windows(
    reference_time: datetime | None = None,
    *,
    training_window_days: int = MODEL_V2_TRAINING_WINDOW_DAYS,
    validation_window_days: int = MODEL_V2_VALIDATION_WINDOW_DAYS,
) -> RebuildWindows:
    deploy_end = reference_time or utc_now_naive()
    validation_end = deploy_end
    validation_start = validation_end - timedelta(days=validation_window_days)
    train_end = validation_start
    train_start = train_end - timedelta(days=training_window_days)
    deploy_start = deploy_end - timedelta(days=training_window_days)
    return RebuildWindows(
        train_start=train_start,
        train_end=train_end,
        validation_start=validation_start,
        validation_end=validation_end,
        deploy_start=deploy_start,
        deploy_end=deploy_end,
    )


def select_best_strategy(
    candidates: Sequence[ValidationCandidate],
    *,
    coverage_threshold: float = MODEL_V2_COVERAGE_THRESHOLD,
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


def rebuild_profiles(model_version: int = 1, reference_time: datetime | None = None):
    if model_version == MODEL_VERSION_LEARNING:
        return _rebuild_profiles_v2(reference_time=reference_time)
    return _rebuild_profiles_v1(model_version=model_version)


def _rebuild_profiles_v1(model_version: int = 1):
    """
    Full rebuild baseline profilů pro všechna odběrná místa.
    Používá robustní MAD std.
    """

    session = get_session_pg()

    try:
        session.execute(
            text(
                """
                DELETE FROM monitoring.vodomery_anomaly_profiles
                WHERE model_version = :model_version
                """
            ),
            {"model_version": model_version},
        )

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
                        synthetic = false
                        AND platne = true
                        AND reset_detected = false
                        AND delta IS NOT NULL
                ),
                stats AS (
                    SELECT
                        identifikace,
                        interval_minutes,
                        day_of_week,
                        slot,
                        percentile_cont(0.5) WITHIN GROUP (ORDER BY delta) AS median,
                        avg(delta) AS mean,
                        percentile_cont(0.1) WITHIN GROUP (ORDER BY delta) AS p10,
                        percentile_cont(0.9) WITHIN GROUP (ORDER BY delta) AS p90,
                        COUNT(*) AS sample_size
                    FROM base
                    GROUP BY
                        identifikace,
                        interval_minutes,
                        day_of_week,
                        slot
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
                    GROUP BY
                        b.identifikace,
                        b.interval_minutes,
                        b.day_of_week,
                        b.slot
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
            {"model_version": model_version},
        )

        session.commit()
        print(f"Profiles rebuild complete (model_version={model_version})")
        return {"model_version": model_version}

    finally:
        session.close()


def _rebuild_profiles_v2(reference_time: datetime | None = None) -> dict[str, object]:
    ensure_vodomery_model_validation_tables()
    windows = build_model_2_rebuild_windows(reference_time)
    session = get_session_pg()

    try:
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

        if not selected_by_ident:
            run.selected_device_count = 0
            run.inserted_profile_count = 0
            session.commit()
            print("Profiles rebuild complete (model_version=2, selected_devices=0, inserted_profiles=0)")
            return {
                "model_version": MODEL_VERSION_LEARNING,
                "selected_device_count": 0,
                "inserted_profile_count": 0,
                "validation_candidate_count": 0,
                "run_id": int(run.id),
            }

        _replace_model_2_profiles(session, windows, selected_by_ident)
        inserted_profile_count = int(
            session.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM monitoring.vodomery_anomaly_profiles
                    WHERE model_version = :model_version
                    """
                ),
                {"model_version": MODEL_VERSION_LEARNING},
            ).scalar_one()
        )

        run.selected_device_count = len(selected_by_ident)
        run.inserted_profile_count = inserted_profile_count
        session.commit()

        print(
            "Profiles rebuild complete "
            f"(model_version=2, selected_devices={len(selected_by_ident)}, inserted_profiles={inserted_profile_count})"
        )
        return {
            "model_version": MODEL_VERSION_LEARNING,
            "selected_device_count": len(selected_by_ident),
            "inserted_profile_count": inserted_profile_count,
            "validation_candidate_count": len(candidates),
            "run_id": int(run.id),
        }

    finally:
        session.close()


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
                    AVG(actual_value - predicted_mean) AS bias
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
                metric.bias
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
    windows: RebuildWindows,
    selected_by_ident: dict[str, ValidationCandidate],
) -> None:
    session.execute(
        text(
            """
            DELETE FROM monitoring.vodomery_anomaly_profiles
            WHERE model_version = :model_version
            """
        ),
        {"model_version": MODEL_VERSION_LEARNING},
    )

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
            windows=windows,
        )


def _insert_profiles_for_strategy(
    session,
    *,
    strategy_key: str,
    identifiers: Sequence[str],
    windows: RebuildWindows,
) -> None:
    if not identifiers:
        return

    if strategy_key == STRATEGY_DOW_SLOT_MEAN:
        statement = text(
            """
            WITH deploy_base AS (
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
                    AND date >= :deploy_start
                    AND date < :deploy_end
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
            FROM deploy_base
            GROUP BY identifikace, interval_minutes, day_of_week, slot
            """
        ).bindparams(bindparam("identifiers", expanding=True))
    elif strategy_key == STRATEGY_WORKDAY_SLOT_MEAN:
        statement = text(
            """
            WITH deploy_base AS (
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
                    AND date >= :deploy_start
                    AND date < :deploy_end
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
                FROM deploy_base
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
            WITH deploy_base AS (
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
                    AND date >= :deploy_start
                    AND date < :deploy_end
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
                FROM deploy_base
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
            "deploy_start": windows.deploy_start,
            "deploy_end": windows.deploy_end,
            "model_version": MODEL_VERSION_LEARNING,
            "identifiers": list(identifiers),
        },
    )
