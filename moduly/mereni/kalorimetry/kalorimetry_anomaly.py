from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.mereni.kalorimetry.active_profile import (
    MISSING_PROFILE,
    KalorimetryActiveProfile,
    KalorimetryProfileLookupRequest,
    load_period_valid_active_profiles,
)
from moduly.mereni.kalorimetry.database.models import (
    KalorimetryAnomalyScore,
    KalorimetryScoringState,
    Mereni_kalorimetry,
)
from moduly.mereni.kalorimetry.observation_quality import (
    KalorimetryObservationPurpose,
    evaluate_kalorimetry_observation,
)
from moduly.mereni.prediction.storage import SELECTION_MODE_ACTIVE


ACTIVE_SELECTION_SCORE_MODEL_VERSION = 1
MIN_EXPECTED_STD = 0.0001


@dataclass(frozen=True)
class KalorimetryScoringResult:
    processed_count: int
    scored_count: int
    unavailable_count: int
    ineligible_count: int
    checkpoint: int


def ensure_scoring_tables() -> None:
    with ENGINE_PG.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        KalorimetryAnomalyScore.__table__.create(
            bind=connection,
            checkfirst=True,
        )
        KalorimetryScoringState.__table__.create(
            bind=connection,
            checkfirst=True,
        )


def score_new_measurements(
    *,
    batch_size: int = 1000,
    scoring_model_version: int = ACTIVE_SELECTION_SCORE_MODEL_VERSION,
    bootstrap_to_latest_if_missing: bool = False,
    selection_mode: str = SELECTION_MODE_ACTIVE,
) -> KalorimetryScoringResult:
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    ensure_scoring_tables()

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        state = session.get(KalorimetryScoringState, scoring_model_version)
        if state is None:
            initial_checkpoint = 0
            if bootstrap_to_latest_if_missing:
                initial_checkpoint = int(
                    session.query(func.max(Mereni_kalorimetry.id)).scalar() or 0
                )
            state = KalorimetryScoringState(
                model_version=scoring_model_version,
                last_measurement_id=initial_checkpoint,
            )
            session.add(state)
            session.commit()

        measurements = _load_measurement_batch(
            session,
            state,
            batch_size=batch_size,
        )
        return score_measurement_batch(
            session,
            state=state,
            measurements=measurements,
            scoring_model_version=scoring_model_version,
            selection_mode=selection_mode,
        )


def score_measurement_batch(
    session: Session,
    *,
    state: KalorimetryScoringState,
    measurements: list[Mereni_kalorimetry],
    scoring_model_version: int = ACTIVE_SELECTION_SCORE_MODEL_VERSION,
    selection_mode: str = SELECTION_MODE_ACTIVE,
) -> KalorimetryScoringResult:
    if not measurements:
        return KalorimetryScoringResult(
            processed_count=0,
            scored_count=0,
            unavailable_count=0,
            ineligible_count=0,
            checkpoint=int(state.last_measurement_id or 0),
        )

    eligible_measurements: list[Mereni_kalorimetry] = []
    ineligible_count = 0
    for measurement in measurements:
        eligibility = evaluate_kalorimetry_observation(
            _observation_mapping(measurement),
            purpose=KalorimetryObservationPurpose.SCORING,
        )
        if eligibility.eligible:
            eligible_measurements.append(measurement)
        else:
            ineligible_count += 1

    requests = [
        KalorimetryProfileLookupRequest(
            identifier=measurement.identifikace,
            timestamp=measurement.date,
            interval_minutes=measurement.interval_minutes,
        )
        for measurement in eligible_measurements
    ]
    lookups = load_period_valid_active_profiles(
        session,
        requests,
        selection_mode=selection_mode,
    )

    rows_to_insert: list[dict[str, object]] = []
    unavailable_count = 0
    for measurement, lookup in zip(eligible_measurements, lookups, strict=True):
        if not lookup.prediction_available:
            if lookup.availability_reason == MISSING_PROFILE:
                raise RuntimeError(
                    "Available kalorimetry selection is missing its exact "
                    "period-valid profile slot."
                )
            unavailable_count += 1
            continue
        rows_to_insert.append(
            build_score_row(
                measurement,
                lookup=lookup,
                scoring_model_version=scoring_model_version,
            )
        )

    checkpoint = max(
        int(state.last_measurement_id or 0),
        *(int(measurement.id) for measurement in measurements),
    )
    _persist_scores_and_checkpoint(
        session,
        scoring_model_version=scoring_model_version,
        rows_to_insert=rows_to_insert,
        checkpoint=checkpoint,
    )
    return KalorimetryScoringResult(
        processed_count=len(measurements),
        scored_count=len(rows_to_insert),
        unavailable_count=unavailable_count,
        ineligible_count=ineligible_count,
        checkpoint=checkpoint,
    )


def build_score_row(
    measurement: Mereni_kalorimetry,
    *,
    lookup: KalorimetryActiveProfile,
    scoring_model_version: int = ACTIVE_SELECTION_SCORE_MODEL_VERSION,
) -> dict[str, object]:
    if (
        not lookup.prediction_available
        or lookup.decision is None
        or lookup.profile is None
        or lookup.expected_mean is None
    ):
        raise ValueError("an available profile lookup is required")

    actual_value = float(measurement.delta)
    expected_mean = float(lookup.expected_mean)
    expected_std = max(
        float(lookup.expected_std or 0.0),
        MIN_EXPECTED_STD,
    )
    deviation = actual_value - expected_mean
    z_score = deviation / expected_std
    expected_p10 = lookup.expected_p10
    expected_p90 = lookup.expected_p90
    outside_prediction_interval = (
        expected_p90 is not None and actual_value > expected_p90
    ) or (
        expected_p10 is not None and actual_value < expected_p10
    )
    is_anomaly = outside_prediction_interval or abs(z_score) >= 3

    severity = None
    if abs(z_score) >= 5:
        severity = "CRITICAL"
    elif abs(z_score) >= 4:
        severity = "HIGH"
    elif abs(z_score) >= 3:
        severity = "MEDIUM"

    values = {
        "actual_value": actual_value,
        "expected_mean": expected_mean,
        "expected_std": expected_std,
        "deviation": deviation,
        "z_score": z_score,
    }
    if not all(isfinite(value) for value in values.values()):
        raise ValueError("score inputs and outputs must be finite")

    return {
        "measurement_id": int(measurement.id),
        "identifikace": str(measurement.identifikace),
        "date": measurement.date,
        "actual_value": actual_value,
        "expected_mean": expected_mean,
        "expected_std": expected_std,
        "expected_median": lookup.expected_median,
        "expected_p10": expected_p10,
        "expected_p90": expected_p90,
        "deviation": deviation,
        "z_score": z_score,
        "is_anomaly": is_anomaly,
        "severity": severity,
        "model_version": int(scoring_model_version),
        "selected_model_version": int(lookup.selected_model_version),
        "selection_snapshot_id": int(lookup.decision.id),
        "profile_snapshot_id": int(lookup.profile.id),
    }


def rebuild_active_scores_for_measurements(
    session: Session,
    *,
    measurements: list[Mereni_kalorimetry],
    scoring_model_version: int = ACTIVE_SELECTION_SCORE_MODEL_VERSION,
    selection_mode: str = SELECTION_MODE_ACTIVE,
) -> int:
    eligible_measurements = [
        measurement
        for measurement in measurements
        if evaluate_kalorimetry_observation(
            _observation_mapping(measurement),
            purpose=KalorimetryObservationPurpose.SCORING,
        ).eligible
    ]
    lookups = load_period_valid_active_profiles(
        session,
        [
            KalorimetryProfileLookupRequest(
                identifier=measurement.identifikace,
                timestamp=measurement.date,
                interval_minutes=measurement.interval_minutes,
            )
            for measurement in eligible_measurements
        ],
        selection_mode=selection_mode,
    )
    rows: list[dict[str, object]] = []
    for measurement, lookup in zip(eligible_measurements, lookups, strict=True):
        if not lookup.prediction_available:
            if lookup.availability_reason == MISSING_PROFILE:
                raise RuntimeError(
                    "Available kalorimetry selection is missing its exact "
                    "period-valid profile slot."
                )
            continue
        rows.append(
            build_score_row(
                measurement,
                lookup=lookup,
                scoring_model_version=scoring_model_version,
            )
        )
    if rows:
        session.execute(
            insert(KalorimetryAnomalyScore).on_conflict_do_nothing(
                index_elements=["measurement_id", "model_version"]
            ),
            rows,
        )
    return len(rows)


def _load_measurement_batch(
    session: Session,
    state: KalorimetryScoringState,
    *,
    batch_size: int,
) -> list[Mereni_kalorimetry]:
    return list(
        session.execute(
            select(Mereni_kalorimetry)
            .where(Mereni_kalorimetry.id > int(state.last_measurement_id or 0))
            .order_by(Mereni_kalorimetry.id)
            .limit(batch_size)
        )
        .scalars()
        .all()
    )


def _persist_scores_and_checkpoint(
    session: Session,
    *,
    scoring_model_version: int,
    rows_to_insert: list[dict[str, object]],
    checkpoint: int,
) -> None:
    if rows_to_insert:
        session.execute(
            insert(KalorimetryAnomalyScore).on_conflict_do_nothing(
                index_elements=["measurement_id", "model_version"]
            ),
            rows_to_insert,
        )
    session.execute(
        update(KalorimetryScoringState)
        .where(KalorimetryScoringState.model_version == scoring_model_version)
        .values(
            last_measurement_id=checkpoint,
            updated_at=utc_now_naive(),
        )
    )
    session.commit()


def _observation_mapping(measurement: Mereni_kalorimetry) -> dict[str, object]:
    return {
        "identifikace": measurement.identifikace,
        "date": measurement.date,
        "interval_minutes": measurement.interval_minutes,
        "spotreba_energie": measurement.spotreba_energie,
        "platne": measurement.platne,
        "reset_detected": measurement.reset_detected,
        "delta": measurement.delta,
        "synthetic": measurement.synthetic,
        "gap_detected": measurement.gap_detected,
    }
