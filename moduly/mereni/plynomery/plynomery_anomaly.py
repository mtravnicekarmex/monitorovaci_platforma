from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.apps.meteo.database.models import MeteoForecastHourly, MeteoHourly
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    PlynomeryAnomalyScore,
    PlynomeryProfilesAnomaly,
    PlynomeryScoringState,
    PlynomeryWeatherModelProfile,
)
from moduly.mereni.plynomery.plynomery_prediction import (
    MODEL_VERSION_WEATHER_ADJUSTED,
    ensure_prediction_tables,
)


MIN_STD = 0.0001
LOCAL_TIMEZONE = ZoneInfo("Europe/Prague")


def ensure_scoring_tables() -> None:
    ensure_prediction_tables()
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
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

        if model_version == MODEL_VERSION_WEATHER_ADJUSTED:
            return _score_weather_adjusted_measurements(
                session,
                state,
                batch_size=batch_size,
            )

        return _score_static_profile_measurements(
            session,
            state,
            model_version=model_version,
            batch_size=batch_size,
        )


def _score_static_profile_measurements(
    session: Session,
    state: PlynomeryScoringState,
    *,
    model_version: int,
    batch_size: int,
) -> int:
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

    measurements = _load_measurement_batch(session, state, batch_size=batch_size)
    if not measurements:
        return 0

    rows_to_insert = []
    max_processed_id = int(state.last_measurement_id or 0)
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

        rows_to_insert.append(
            _build_score_row(
                measurement=measurement,
                actual_value=actual_value,
                expected_mean=expected_mean,
                expected_std=expected_std,
                expected_median=expected_median,
                expected_p10=expected_p10,
                expected_p90=expected_p90,
                model_version=model_version,
            )
        )
        max_processed_id = max(max_processed_id, int(measurement.id))

    return _persist_scores_and_checkpoint(
        session,
        model_version=model_version,
        rows_to_insert=rows_to_insert,
        max_processed_id=max_processed_id,
    )


def _score_weather_adjusted_measurements(
    session: Session,
    state: PlynomeryScoringState,
    *,
    batch_size: int,
) -> int:
    profiles = session.execute(
        select(PlynomeryWeatherModelProfile).where(
            PlynomeryWeatherModelProfile.model_version == MODEL_VERSION_WEATHER_ADJUSTED
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

    measurements = _load_measurement_batch(session, state, batch_size=batch_size)
    if not measurements:
        return 0

    hdd_24h_by_measurement_id = _load_hdd_24h_by_measurement_id(session, measurements)
    rows_to_insert = []
    max_processed_id = int(state.last_measurement_id or 0)

    for measurement in measurements:
        profile = profile_cache.get(
            (
                measurement.identifikace,
                measurement.interval_minutes,
                measurement.day_of_week,
                measurement.slot,
            )
        )
        hdd_24h = hdd_24h_by_measurement_id.get(int(measurement.id))
        if profile is None or hdd_24h is None:
            max_processed_id = max(max_processed_id, int(measurement.id))
            continue

        expected_mean = float(profile.base_mean) + float(profile.hdd_slope) * hdd_24h
        expected_std = max(float(profile.residual_std), MIN_STD)
        expected_median = expected_mean + float(profile.residual_median)
        expected_p10 = expected_mean + float(profile.residual_p10)
        expected_p90 = expected_mean + float(profile.residual_p90)
        actual_value = float(measurement.delta)

        rows_to_insert.append(
            _build_score_row(
                measurement=measurement,
                actual_value=actual_value,
                expected_mean=expected_mean,
                expected_std=expected_std,
                expected_median=expected_median,
                expected_p10=expected_p10,
                expected_p90=expected_p90,
                model_version=MODEL_VERSION_WEATHER_ADJUSTED,
            )
        )
        max_processed_id = max(max_processed_id, int(measurement.id))

    return _persist_scores_and_checkpoint(
        session,
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
        rows_to_insert=rows_to_insert,
        max_processed_id=max_processed_id,
    )


def _load_measurement_batch(
    session: Session,
    state: PlynomeryScoringState,
    *,
    batch_size: int,
) -> list[Mereni_plynomery]:
    last_id = int(state.last_measurement_id or 0)
    return (
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


def _load_hdd_24h_by_measurement_id(
    session: Session,
    measurements: list[Mereni_plynomery],
) -> dict[int, float]:
    weather_hour_by_measurement_id = {
        int(measurement.id): _local_prague_to_utc_hour(measurement.date)
        for measurement in measurements
        if measurement.date is not None
    }
    if not weather_hour_by_measurement_id:
        return {}

    min_hour = min(weather_hour_by_measurement_id.values()) - timedelta(hours=23)
    max_hour = max(weather_hour_by_measurement_id.values())
    forecast_rows = session.execute(
        select(MeteoForecastHourly.datetime_hour, MeteoForecastHourly.heating_degree_hours).where(
            MeteoForecastHourly.datetime_hour >= min_hour,
            MeteoForecastHourly.datetime_hour <= max_hour,
        )
    ).all()
    historical_rows = session.execute(
        select(MeteoHourly.datetime_hour, MeteoHourly.heating_degree_hours).where(
            MeteoHourly.datetime_hour >= min_hour,
            MeteoHourly.datetime_hour <= max_hour,
        )
    ).all()
    hdd_by_hour = {
        row.datetime_hour: float(row.heating_degree_hours)
        for row in forecast_rows
        if row.heating_degree_hours is not None
    }
    hdd_by_hour.update(
        {
            row.datetime_hour: float(row.heating_degree_hours)
            for row in historical_rows
            if row.heating_degree_hours is not None
        }
    )

    result: dict[int, float] = {}
    for measurement_id, weather_hour in weather_hour_by_measurement_id.items():
        current_hdd = hdd_by_hour.get(weather_hour)
        if current_hdd is None:
            continue

        values = [
            hdd_by_hour[weather_hour - timedelta(hours=offset)]
            for offset in range(24)
            if weather_hour - timedelta(hours=offset) in hdd_by_hour
        ]
        if values:
            result[measurement_id] = sum(values) / len(values)

    return result


def _local_prague_to_utc_hour(value: datetime) -> datetime:
    if value.tzinfo is None:
        aware_value = value.replace(tzinfo=LOCAL_TIMEZONE)
    else:
        aware_value = value.astimezone(LOCAL_TIMEZONE)
    return (
        aware_value.astimezone(UTC)
        .replace(tzinfo=None, minute=0, second=0, microsecond=0)
    )


def _build_score_row(
    *,
    measurement: Mereni_plynomery,
    actual_value: float,
    expected_mean: float,
    expected_std: float,
    expected_median: float,
    expected_p10: float,
    expected_p90: float,
    model_version: int,
) -> dict[str, object]:
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

    return {
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


def _persist_scores_and_checkpoint(
    session: Session,
    *,
    model_version: int,
    rows_to_insert: list[dict[str, object]],
    max_processed_id: int,
) -> int:
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
