from __future__ import annotations

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    PlynomeryAnomalyScore,
    PlynomeryProfilesAnomaly,
    PlynomeryScoringState,
)


MIN_STD = 0.0001


def ensure_scoring_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        PlynomeryProfilesAnomaly.__table__.create(bind=conn, checkfirst=True)
        PlynomeryAnomalyScore.__table__.create(bind=conn, checkfirst=True)
        PlynomeryScoringState.__table__.create(bind=conn, checkfirst=True)


def score_new_measurements(
    model_version: int = 1,
    batch_size: int = 1000,
    *,
    bootstrap_to_latest_if_missing: bool = False,
):
    ensure_scoring_tables()

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        state = session.get(PlynomeryScoringState, model_version)

        if state is None:
            initial_checkpoint = 0
            if bootstrap_to_latest_if_missing:
                initial_checkpoint = int(
                    session.query(func.max(Mereni_plynomery.id)).scalar() or 0
                )
            state = PlynomeryScoringState(
                model_version=model_version,
                last_measurement_id=initial_checkpoint,
            )
            session.add(state)
            session.commit()

        profiles = session.execute(
            select(PlynomeryProfilesAnomaly).where(
                PlynomeryProfilesAnomaly.model_version == model_version
            )
        ).scalars().all()
        if not profiles:
            return 0

        profile_cache = {
            (
                profile.identifikace,
                profile.interval_minutes,
                profile.day_of_week,
                profile.slot,
            ): profile
            for profile in profiles
        }

        last_id = int(state.last_measurement_id or 0)
        measurements = (
            session.query(Mereni_plynomery)
            .filter(
                Mereni_plynomery.id > last_id,
                Mereni_plynomery.synthetic.is_(False),
                Mereni_plynomery.platne.is_(True),
                Mereni_plynomery.reset_detected.is_(False),
                Mereni_plynomery.delta.is_not(None),
            )
            .order_by(Mereni_plynomery.id)
            .limit(batch_size)
            .all()
        )
        if not measurements:
            return 0

        rows_to_insert = []
        max_processed_id = last_id
        for measurement in measurements:
            profile = profile_cache.get(
                (
                    measurement.identifikace,
                    measurement.interval_minutes,
                    measurement.day_of_week,
                    measurement.slot,
                )
            )
            if profile is None:
                max_processed_id = max(max_processed_id, int(measurement.id))
                continue

            expected_mean = float(profile.mean)
            expected_std = max(float(profile.std), MIN_STD)
            expected_median = float(profile.median)
            expected_p10 = float(profile.p10)
            expected_p90 = float(profile.p90)
            actual_value = float(measurement.delta)
            deviation = actual_value - expected_mean
            z_score = deviation / expected_std
            is_anomaly = (
                actual_value > expected_p90
                or actual_value < expected_p10
                or abs(z_score) >= 3
            )

            severity = None
            if abs(z_score) >= 5:
                severity = "CRITICAL"
            elif abs(z_score) >= 4:
                severity = "HIGH"
            elif abs(z_score) >= 3:
                severity = "MEDIUM"

            rows_to_insert.append(
                {
                    "measurement_id": measurement.id,
                    "identifikace": measurement.identifikace,
                    "date": measurement.date,
                    "actual_value": actual_value,
                    "expected_mean": expected_mean,
                    "expected_std": expected_std,
                    "expected_median": expected_median,
                    "expected_p10": expected_p10,
                    "expected_p90": expected_p90,
                    "deviation": deviation,
                    "z_score": z_score,
                    "is_anomaly": is_anomaly,
                    "severity": severity,
                    "model_version": model_version,
                }
            )
            max_processed_id = max(max_processed_id, int(measurement.id))

        if rows_to_insert:
            session.execute(
                insert(PlynomeryAnomalyScore).on_conflict_do_nothing(
                    index_elements=["measurement_id", "model_version"]
                ),
                rows_to_insert,
            )

        session.execute(
            update(PlynomeryScoringState)
            .where(PlynomeryScoringState.model_version == model_version)
            .values(
                last_measurement_id=max_processed_id,
                updated_at=utc_now_naive(),
            )
        )
        session.commit()

        return len(rows_to_insert)
