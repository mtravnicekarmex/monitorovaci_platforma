from collections import defaultdict

from decouple import config
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from moduly.mereni.vodomery.database.models import *
from core.db.connect import ENGINE_PG
from app.time_utils import utc_now_naive
from moduly.mereni.prediction.storage import (
    PredictionSelectedModelSnapshot,
    SELECTION_MODE_ACTIVE,
    normalize_selection_mode,
)
from moduly.mereni.vodomery.database.model_validation import (
    get_active_vodomery_model_version,
)


VODOMERY_MEDIUM_KEY = "vodomery"
PER_IDENTIFIER_SELECTION_ENV = "VODOMERY_PER_IDENTIFIER_MODEL_SELECTION_ENABLED"



def score_new_measurements(
    model_version: int = 1,
    batch_size: int = 1000,
    *,
    bootstrap_to_latest_if_missing: bool = False,
    use_per_identifier_selection: bool | None = None,
    selection_mode: str = SELECTION_MODE_ACTIVE,
):
    """
    Ultra-efektivní inkrementální scoring (FINÁLNÍ VERZE)

    - PK index scan
    - preload baseline profilů
    - žádné další DB dotazy během loopu
    - bulk insert
    - update scoring state v jedné transakci
    """

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:

        # -------------------------------------------------
        # 1️⃣ Načti nebo inicializuj scoring state
        # -------------------------------------------------
        state = session.get(VodomeryScoringState, model_version)

        if state is None:
            initial_checkpoint = 0
            if bootstrap_to_latest_if_missing:
                initial_checkpoint = int(
                    session.query(func.max(Mereni_vodomery.id)).scalar() or 0
                )
            state = VodomeryScoringState(
                model_version=model_version,
                last_measurement_id=initial_checkpoint,
            )
            session.add(state)
            session.commit()

        last_id = state.last_measurement_id

        per_identifier_selection_enabled = _per_identifier_selection_enabled(
            session,
            model_version=model_version,
            use_per_identifier_selection=use_per_identifier_selection,
        )

        # -------------------------------------------------
        # 2️⃣ Preload baseline profilů (1 dotaz)
        # -------------------------------------------------
        profiles = _load_profiles(session, {model_version})

        if not profiles:
            print("No baseline profiles found.")
            return

        profile_cache = _build_profile_cache(
            profiles,
            default_model_version=model_version,
        )

        # -------------------------------------------------
        # 3️⃣ Načti nové measurementy (PK scan)
        # -------------------------------------------------
        measurements = (
            session.query(Mereni_vodomery)
            .filter(
                Mereni_vodomery.id > last_id,
                Mereni_vodomery.synthetic.is_(False),
                Mereni_vodomery.platne.is_(True),
                Mereni_vodomery.reset_detected.is_(False),
                Mereni_vodomery.delta.is_not(None),
            )
            .order_by(Mereni_vodomery.id)
            .limit(batch_size)
            .all()
        )

        if not measurements:
            print("No new measurements to score.")
            return 0

        snapshots_by_identifier = {}
        if per_identifier_selection_enabled:
            snapshots_by_identifier = _load_selected_model_snapshots(
                session,
                measurements=measurements,
                selection_mode=selection_mode,
            )
            selected_profile_versions = _selected_profile_versions(
                snapshots_by_identifier,
            )
            profile_source_versions = {model_version, *selected_profile_versions}
            if profile_source_versions != {model_version}:
                profiles = _load_profiles(session, profile_source_versions)
                profile_cache = _build_profile_cache(
                    profiles,
                    default_model_version=model_version,
                )

        rows_to_insert = []
        max_processed_id = last_id

        # -------------------------------------------------
        # 4️⃣ Scoring (čistá CPU část)
        # -------------------------------------------------
        for m in measurements:

            profile_model_version = _profile_model_version_for_measurement(
                m,
                snapshots_by_identifier=snapshots_by_identifier,
                default_model_version=model_version,
            )
            key = _profile_cache_key(
                profile_model_version,
                m,
            )

            profile = profile_cache.get(key)
            if not profile and profile_model_version != model_version:
                profile = profile_cache.get(_profile_cache_key(model_version, m))
            if not profile:
                continue

            expected_mean = profile.mean
            expected_std = profile.std if profile.std > 0 else 0.0001
            expected_median = profile.median
            expected_p10 = profile.p10
            expected_p90 = profile.p90

            deviation = m.delta - expected_mean
            z_score = deviation / expected_std

            # kombinovaná detekce
            is_anomaly = (
                m.delta > expected_p90
                or m.delta < expected_p10
                or abs(z_score) >= 3
            )

            if abs(z_score) >= 5:
                severity = "CRITICAL"
            elif abs(z_score) >= 4:
                severity = "HIGH"
            elif abs(z_score) >= 3:
                severity = "MEDIUM"
            else:
                severity = None

            rows_to_insert.append(
                {
                    "measurement_id": m.id,
                    "identifikace": m.identifikace,
                    "date": m.date,
                    "actual_value": m.delta,
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

            max_processed_id = m.id

        # -------------------------------------------------
        # 5️⃣ Jedna transakce
        # -------------------------------------------------
        if rows_to_insert:
            session.execute(
                insert(VodomeryAnomalyScore).on_conflict_do_nothing(
                    index_elements=["measurement_id", "model_version"]
                ),
                rows_to_insert,
            )

        # Posun checkpointu vždy na poslední zpracovaný záznam dávky
        session.execute(
            update(VodomeryScoringState)
            .where(VodomeryScoringState.model_version == model_version)
            .values(
                last_measurement_id=max_processed_id,
                updated_at=utc_now_naive(),
            )
        )

        session.commit()

        if rows_to_insert:
            print(
                f"Scored {len(rows_to_insert)} measurements. "
                f"Last processed id: {max_processed_id}"
            )
            return len(rows_to_insert)

        print(f"No scores inserted. Advanced checkpoint to id: {max_processed_id}")
        return 0





def backfill_vodomery_scores(model_version: int = 1, batch_size: int = 5000):
    """
    Jednorázové naplnění historických dat.
    Běží dávkově, dokud nejsou všechna data zpracována.
    """

    print(f"Starting backfill for model_version={model_version}")

    total_inserted = 0
    iteration = 0

    while True:
        iteration += 1

        inserted = score_new_measurements(
            model_version=model_version,
            batch_size=batch_size,
        )

        if inserted == 0:
            break

        total_inserted += inserted

        print(
            f"[Batch {iteration}] Inserted: {inserted} | "
            f"Total: {total_inserted}"
        )

    print(
        f"Backfill completed for model_version={model_version}. "
        f"Total inserted: {total_inserted}"
    )


# backfill_vodomery_scores(model_version=1, batch_size=3000)


def _per_identifier_selection_enabled(
    session,
    *,
    model_version: int,
    use_per_identifier_selection: bool | None,
) -> bool:
    if use_per_identifier_selection is not None:
        return bool(use_per_identifier_selection)

    enabled = config(PER_IDENTIFIER_SELECTION_ENV, default=False, cast=bool)
    if not enabled:
        return False

    active_model_version = get_active_vodomery_model_version(
        session=session,
        default=model_version,
    )
    return int(active_model_version) == int(model_version)


def _load_profiles(session, model_versions):
    versions = tuple(sorted({int(version) for version in model_versions}))
    if not versions:
        return []

    if len(versions) == 1:
        condition = VodomeryProfilesAnomaly.model_version == versions[0]
    else:
        condition = VodomeryProfilesAnomaly.model_version.in_(versions)

    return (
        session.execute(select(VodomeryProfilesAnomaly).where(condition))
        .scalars()
        .all()
    )


def _build_profile_cache(profiles, *, default_model_version: int):
    profile_cache = {}
    for profile in profiles:
        profile_model_version = int(
            getattr(profile, "model_version", default_model_version)
        )
        profile_cache[
            _profile_cache_key(
                profile_model_version,
                profile,
            )
        ] = profile
    return profile_cache


def _profile_cache_key(model_version: int, item):
    return (
        int(model_version),
        item.identifikace,
        item.interval_minutes,
        item.day_of_week,
        item.slot,
    )


def _load_selected_model_snapshots(
    session,
    *,
    measurements,
    selection_mode: str,
):
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
                snapshot.medium_key == VODOMERY_MEDIUM_KEY,
                snapshot.selection_mode == normalize_selection_mode(selection_mode),
                snapshot.identifier.in_(identifiers),
                snapshot.forecast_period_start <= max_date,
                snapshot.forecast_period_end > min_date,
            )
        )
        .scalars()
        .all()
    )

    snapshots_by_identifier = defaultdict(list)
    for row in rows:
        snapshots_by_identifier[row.identifier].append(row)

    for identifier_rows in snapshots_by_identifier.values():
        identifier_rows.sort(
            key=lambda row: row.forecast_period_start,
            reverse=True,
        )
    return dict(snapshots_by_identifier)


def _selected_profile_versions(snapshots_by_identifier) -> set[int]:
    return {
        int(snapshot.selected_model_version)
        for snapshots in snapshots_by_identifier.values()
        for snapshot in snapshots
    }


def _profile_model_version_for_measurement(
    measurement,
    *,
    snapshots_by_identifier,
    default_model_version: int,
) -> int:
    if not snapshots_by_identifier:
        return int(default_model_version)

    measurement_date = getattr(measurement, "date", None)
    if measurement_date is None:
        return int(default_model_version)

    for snapshot in snapshots_by_identifier.get(measurement.identifikace, ()):
        if (
            snapshot.forecast_period_start <= measurement_date
            and measurement_date < snapshot.forecast_period_end
        ):
            return int(snapshot.selected_model_version)

    return int(default_model_version)
