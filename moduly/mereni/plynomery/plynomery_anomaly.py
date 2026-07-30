from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from decouple import config
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
    get_runtime_model_version,
)
from moduly.mereni.prediction.storage import (
    PredictionSelectedModelSnapshot,
    SELECTION_MODE_ACTIVE,
    normalize_selection_mode,
)


MIN_STD = 0.0001
LOCAL_TIMEZONE = ZoneInfo("Europe/Prague")
PLYNOMERY_MEDIUM_KEY = "plynomery"
PER_IDENTIFIER_SELECTION_ENV = "PLYNOMERY_PER_IDENTIFIER_MODEL_SELECTION_ENABLED"


@dataclass(frozen=True)
class PlynomeryProfileSelection:
    model_version: int | None
    prediction_available: bool
    fallback_reason: str
    snapshot: PredictionSelectedModelSnapshot | None = None


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
    use_per_identifier_selection: bool | None = None,
    selection_mode: str = SELECTION_MODE_ACTIVE,
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

        if _per_identifier_selection_enabled(
            session,
            model_version=model_version,
            use_per_identifier_selection=use_per_identifier_selection,
        ):
            return _score_per_identifier_selected_measurements(
                session,
                state,
                model_version=model_version,
                batch_size=batch_size,
                selection_mode=selection_mode,
            )

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


def _score_per_identifier_selected_measurements(
    session: Session,
    state: PlynomeryScoringState,
    *,
    model_version: int,
    batch_size: int,
    selection_mode: str,
) -> int:
    measurements = _load_measurement_batch(session, state, batch_size=batch_size)
    if not measurements:
        return 0

    rows_to_insert = _build_per_identifier_selected_score_rows(
        session,
        measurements=measurements,
        output_model_version=model_version,
        selection_mode=selection_mode,
    )
    max_processed_id = max(
        int(state.last_measurement_id or 0),
        *(int(measurement.id) for measurement in measurements),
    )
    return _persist_scores_and_checkpoint(
        session,
        model_version=model_version,
        rows_to_insert=rows_to_insert,
        max_processed_id=max_processed_id,
    )


def _build_per_identifier_selected_score_rows(
    session: Session,
    *,
    measurements: list[Mereni_plynomery],
    output_model_version: int,
    selection_mode: str = SELECTION_MODE_ACTIVE,
) -> list[dict[str, object]]:
    if not measurements:
        return []

    snapshots_by_identifier = _load_selected_model_snapshots(
        session,
        measurements=measurements,
        selection_mode=selection_mode,
    )
    selections_by_measurement_id = {
        int(measurement.id): _resolve_profile_selection_for_measurement(
            measurement,
            snapshots_by_identifier=snapshots_by_identifier,
        )
        for measurement in measurements
    }
    selected_versions = {
        int(selection.model_version)
        for selection in selections_by_measurement_id.values()
        if selection.prediction_available and selection.model_version is not None
    }
    identifiers_by_version: dict[int, set[str]] = defaultdict(set)
    for measurement in measurements:
        selection = selections_by_measurement_id[int(measurement.id)]
        if selection.prediction_available and selection.model_version is not None:
            identifiers_by_version[int(selection.model_version)].add(
                str(measurement.identifikace)
            )

    static_versions = selected_versions - {MODEL_VERSION_WEATHER_ADJUSTED}
    static_profiles = _load_static_profiles(
        session,
        static_versions,
        identifiers={
            identifier
            for version in static_versions
            for identifier in identifiers_by_version.get(version, ())
        },
    )
    static_profile_cache = {
        (
            int(profile.model_version),
            profile.identifikace,
            profile.interval_minutes,
            profile.day_of_week,
            profile.slot,
        ): profile
        for profile in static_profiles
    }

    weather_profile_cache = {}
    if MODEL_VERSION_WEATHER_ADJUSTED in selected_versions:
        weather_profiles = _load_weather_profiles(
            session,
            identifiers=identifiers_by_version.get(
                MODEL_VERSION_WEATHER_ADJUSTED,
                set(),
            ),
        )
        weather_profile_cache = {
            (
                profile.identifikace,
                profile.interval_minutes,
                profile.day_of_week,
                profile.slot,
            ): profile
            for profile in weather_profiles
        }

    weather_measurements = [
        measurement
        for measurement in measurements
        if selections_by_measurement_id[int(measurement.id)].model_version
        == MODEL_VERSION_WEATHER_ADJUSTED
    ]
    hdd_24h_by_measurement_id = (
        _load_hdd_24h_by_measurement_id(session, weather_measurements)
        if weather_measurements
        else {}
    )

    rows_to_insert = []
    for measurement in measurements:
        selection = selections_by_measurement_id[int(measurement.id)]
        if not selection.prediction_available or selection.model_version is None:
            continue

        selected_model_version = int(selection.model_version)
        if selected_model_version == MODEL_VERSION_WEATHER_ADJUSTED:
            profile = weather_profile_cache.get(
                (
                    measurement.identifikace,
                    measurement.interval_minutes,
                    measurement.day_of_week,
                    measurement.slot,
                )
            )
            hdd_24h = hdd_24h_by_measurement_id.get(int(measurement.id))
            if profile is None or hdd_24h is None:
                continue
            expected_mean = (
                float(profile.base_mean)
                + float(profile.hdd_slope) * hdd_24h
            )
            expected_std = max(float(profile.residual_std), MIN_STD)
            expected_median = expected_mean + float(profile.residual_median)
            expected_p10 = expected_mean + float(profile.residual_p10)
            expected_p90 = expected_mean + float(profile.residual_p90)
        else:
            profile = static_profile_cache.get(
                (
                    selected_model_version,
                    measurement.identifikace,
                    measurement.interval_minutes,
                    measurement.day_of_week,
                    measurement.slot,
                )
            )
            if profile is None:
                continue
            expected_mean = float(profile.mean)
            expected_std = max(float(profile.std), MIN_STD)
            expected_median = float(profile.median)
            expected_p10 = float(profile.p10)
            expected_p90 = float(profile.p90)

        rows_to_insert.append(
            _build_score_row(
                measurement=measurement,
                actual_value=float(measurement.delta),
                expected_mean=expected_mean,
                expected_std=expected_std,
                expected_median=expected_median,
                expected_p10=expected_p10,
                expected_p90=expected_p90,
                model_version=output_model_version,
            )
        )

    return rows_to_insert


def _load_static_profiles(
    session: Session,
    model_versions: set[int],
    *,
    identifiers: set[str] | None = None,
) -> list[PlynomeryProfilesAnomaly]:
    versions = tuple(sorted(int(version) for version in model_versions))
    if not versions:
        return []
    conditions = [
        PlynomeryProfilesAnomaly.model_version == versions[0]
        if len(versions) == 1
        else PlynomeryProfilesAnomaly.model_version.in_(versions)
    ]
    if identifiers is not None:
        if not identifiers:
            return []
        conditions.append(
            PlynomeryProfilesAnomaly.identifikace.in_(sorted(identifiers))
        )
    return (
        session.execute(select(PlynomeryProfilesAnomaly).where(*conditions))
        .scalars()
        .all()
    )


def _load_weather_profiles(
    session: Session,
    *,
    identifiers: set[str] | None = None,
) -> list[PlynomeryWeatherModelProfile]:
    conditions = [
        PlynomeryWeatherModelProfile.model_version
        == MODEL_VERSION_WEATHER_ADJUSTED
    ]
    if identifiers is not None:
        if not identifiers:
            return []
        conditions.append(
            PlynomeryWeatherModelProfile.identifikace.in_(sorted(identifiers))
        )
    return (
        session.execute(
            select(PlynomeryWeatherModelProfile).where(*conditions)
        )
        .scalars()
        .all()
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


def _per_identifier_selection_enabled(
    session: Session,
    *,
    model_version: int,
    use_per_identifier_selection: bool | None,
) -> bool:
    if use_per_identifier_selection is not None:
        return bool(use_per_identifier_selection)
    if not config(PER_IDENTIFIER_SELECTION_ENV, default=False, cast=bool):
        return False
    return int(
        get_runtime_model_version(session=session, default=model_version)
    ) == int(model_version)


def _load_selected_model_snapshots(
    session: Session,
    *,
    measurements: list[Mereni_plynomery],
    selection_mode: str = SELECTION_MODE_ACTIVE,
) -> dict[str, list[PredictionSelectedModelSnapshot]]:
    identifiers = sorted(
        {
            measurement.identifikace
            for measurement in measurements
            if getattr(measurement, "identifikace", None)
        }
    )
    dated_measurements = [
        measurement
        for measurement in measurements
        if getattr(measurement, "date", None) is not None
    ]
    if not identifiers or not dated_measurements:
        return {}

    min_date = min(measurement.date for measurement in dated_measurements)
    max_date = max(measurement.date for measurement in dated_measurements)
    snapshot = PredictionSelectedModelSnapshot
    rows = (
        session.execute(
            select(snapshot).where(
                snapshot.medium_key == PLYNOMERY_MEDIUM_KEY,
                snapshot.selection_mode == normalize_selection_mode(selection_mode),
                snapshot.identifier.in_(identifiers),
                snapshot.forecast_period_start <= max_date,
                snapshot.forecast_period_end > min_date,
            )
        )
        .scalars()
        .all()
    )

    snapshots_by_identifier: dict[
        str,
        list[PredictionSelectedModelSnapshot],
    ] = defaultdict(list)
    for row in rows:
        snapshots_by_identifier[str(row.identifier)].append(row)

    for identifier_rows in snapshots_by_identifier.values():
        identifier_rows.sort(key=_snapshot_precedence_key, reverse=True)
    return dict(snapshots_by_identifier)


def _snapshot_precedence_key(
    snapshot: PredictionSelectedModelSnapshot,
) -> tuple[datetime, datetime, int]:
    return (
        snapshot.forecast_period_start,
        getattr(snapshot, "created_at", None) or datetime.min,
        int(getattr(snapshot, "id", 0) or 0),
    )


def _resolve_profile_selection_for_measurement(
    measurement: Mereni_plynomery,
    *,
    snapshots_by_identifier: dict[
        str,
        list[PredictionSelectedModelSnapshot],
    ],
) -> PlynomeryProfileSelection:
    measurement_date = getattr(measurement, "date", None)
    if measurement_date is not None:
        for snapshot in snapshots_by_identifier.get(
            str(measurement.identifikace),
            (),
        ):
            if (
                snapshot.forecast_period_start <= measurement_date
                and measurement_date < snapshot.forecast_period_end
            ):
                fallback_reason = str(
                    getattr(snapshot, "fallback_reason", "none") or "none"
                )
                if fallback_reason == "insufficient_history":
                    return PlynomeryProfileSelection(
                        model_version=None,
                        prediction_available=False,
                        fallback_reason=fallback_reason,
                        snapshot=snapshot,
                    )
                return PlynomeryProfileSelection(
                    model_version=int(snapshot.selected_model_version),
                    prediction_available=True,
                    fallback_reason=fallback_reason,
                    snapshot=snapshot,
                )

    return PlynomeryProfileSelection(
        model_version=None,
        prediction_available=False,
        fallback_reason="no_selection_snapshot",
    )


def _selected_profile_versions(
    snapshots_by_identifier: dict[
        str,
        list[PredictionSelectedModelSnapshot],
    ],
) -> set[int]:
    return {
        int(snapshot.selected_model_version)
        for snapshots in snapshots_by_identifier.values()
        for snapshot in snapshots
        if str(getattr(snapshot, "fallback_reason", "none"))
        != "insufficient_history"
    }


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
        ).order_by(
            MeteoForecastHourly.datetime_hour,
            MeteoForecastHourly.forecast_run_at,
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
