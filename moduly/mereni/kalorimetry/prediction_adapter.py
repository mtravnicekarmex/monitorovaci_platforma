from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import Float, Select, cast, delete, func, insert, select

from core.db.connect import get_session_pg
from moduly.mereni.kalorimetry.database.models import (
    KalorimetryModelSelectionRun,
    KalorimetryProfilesAnomaly,
    KalorimetryWeatherModelProfile,
    Mereni_kalorimetry,
)
from moduly.apps.meteo.database.models import MeteoHourly
from moduly.mereni.kalorimetry.observation_quality import (
    KalorimetryObservationPurpose,
    is_kalorimetry_observation_eligible,
)
from moduly.mereni.prediction import (
    CandidateProfileBuildResult,
    PredictionObservation,
    PredictionProfilePoint,
    PredictionSelectionMetadata,
    PredictionTimeWindow,
)


DEFAULT_KALORIMETRY_MODEL_VERSION = 1


class KalorimetryPredictionAdapter:
    medium_key = "kalorimetry"

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any] = get_session_pg,
        active_model_loader: Callable[..., int] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._active_model_loader = (
            active_model_loader or load_active_kalorimetry_model_version
        )

    def get_active_model_version(self) -> int:
        session = self._session_factory()
        try:
            return self._active_model_loader(
                session=session,
                default=DEFAULT_KALORIMETRY_MODEL_VERSION,
            )
        finally:
            session.close()

    def load_selection_metadata(self) -> PredictionSelectionMetadata | None:
        session = self._session_factory()
        try:
            row = session.execute(
                build_kalorimetry_selection_metadata_statement()
            ).mappings().first()
            if row is None:
                return None
            return serialize_kalorimetry_selection_metadata(row)
        finally:
            session.close()

    def load_observations(
        self,
        window: PredictionTimeWindow,
        *,
        identifiers: Sequence[str] | None = None,
    ) -> Sequence[PredictionObservation]:
        session = self._session_factory()
        try:
            rows = (
                session.execute(
                    build_kalorimetry_observations_statement(
                        window,
                        identifiers=identifiers,
                    )
                )
                .mappings()
                .all()
            )
            return tuple(
                serialize_kalorimetry_observation(row)
                for row in rows
                if is_kalorimetry_observation_eligible(
                    row,
                    purpose=KalorimetryObservationPurpose.MODEL_INPUT,
                )
            )
        finally:
            session.close()

    def load_weather_observations(
        self,
        window: PredictionTimeWindow,
        *,
        identifiers: Sequence[str] | None = None,
    ) -> Sequence[PredictionObservation]:
        session = self._session_factory()
        try:
            rows = (
                session.execute(
                    build_kalorimetry_weather_observations_statement(
                        window,
                        identifiers=identifiers,
                    )
                )
                .mappings()
                .all()
            )
            return tuple(
                serialize_kalorimetry_observation(row)
                for row in rows
                if is_kalorimetry_observation_eligible(
                    row,
                    purpose=KalorimetryObservationPurpose.MODEL_INPUT,
                )
                and row.get("hdd_24h") is not None
            )
        finally:
            session.close()

    def replace_profiles(
        self,
        *,
        model_version: int,
        profiles: Iterable[PredictionProfilePoint],
    ) -> CandidateProfileBuildResult:
        profile_rows = [
            profile_point_to_kalorimetry_row(
                profile,
                model_version=model_version,
            )
            for profile in profiles
        ]
        session = self._session_factory()
        try:
            session.execute(
                delete(KalorimetryProfilesAnomaly).where(
                    KalorimetryProfilesAnomaly.model_version == model_version
                )
            )
            if profile_rows:
                session.execute(insert(KalorimetryProfilesAnomaly), profile_rows)
            session.commit()
            return CandidateProfileBuildResult(
                model_version=model_version,
                profile_count=len(profile_rows),
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def count_profiles(self, model_version: int) -> int:
        session = self._session_factory()
        try:
            return int(
                session.execute(
                    select(func.count())
                    .select_from(KalorimetryProfilesAnomaly)
                    .where(
                        KalorimetryProfilesAnomaly.model_version == model_version
                    )
                ).scalar_one()
            )
        finally:
            session.close()

    def replace_weather_profiles(
        self,
        *,
        model_version: int,
        profiles: Iterable[PredictionProfilePoint],
    ) -> CandidateProfileBuildResult:
        from moduly.mereni.kalorimetry.weather_candidate import (
            weather_profile_point_to_row,
        )

        profile_rows = [
            weather_profile_point_to_row(
                profile,
                model_version=model_version,
            )
            for profile in profiles
        ]
        session = self._session_factory()
        try:
            session.execute(
                delete(KalorimetryWeatherModelProfile).where(
                    KalorimetryWeatherModelProfile.model_version == model_version
                )
            )
            if profile_rows:
                session.execute(
                    insert(KalorimetryWeatherModelProfile),
                    profile_rows,
                )
            session.commit()
            return CandidateProfileBuildResult(
                model_version=model_version,
                profile_count=len(profile_rows),
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def load_active_kalorimetry_model_version(
    *,
    session,
    default: int = DEFAULT_KALORIMETRY_MODEL_VERSION,
) -> int:
    value = session.execute(
        select(KalorimetryModelSelectionRun.selected_model_version)
        .order_by(
            KalorimetryModelSelectionRun.created_at.desc(),
            KalorimetryModelSelectionRun.id.desc(),
        )
        .limit(1)
    ).scalar_one_or_none()
    return int(value) if value is not None else int(default)


def build_kalorimetry_observations_statement(
    window: PredictionTimeWindow,
    *,
    identifiers: Sequence[str] | None = None,
) -> Select:
    statement = (
        select(
            Mereni_kalorimetry.id.label("measurement_id"),
            Mereni_kalorimetry.identifikace,
            Mereni_kalorimetry.date,
            Mereni_kalorimetry.delta,
            Mereni_kalorimetry.interval_minutes,
            Mereni_kalorimetry.day_of_week,
            Mereni_kalorimetry.slot,
            Mereni_kalorimetry.spotreba_energie,
            Mereni_kalorimetry.objem,
            Mereni_kalorimetry.nocni_odber,
            Mereni_kalorimetry.zdroj,
            Mereni_kalorimetry.time_utc,
            Mereni_kalorimetry.platne,
            Mereni_kalorimetry.reset_detected,
            Mereni_kalorimetry.synthetic,
            Mereni_kalorimetry.gap_detected,
        )
        .where(
            Mereni_kalorimetry.platne.is_(True),
            Mereni_kalorimetry.reset_detected.is_(False),
            Mereni_kalorimetry.synthetic.is_(False),
            Mereni_kalorimetry.gap_detected.is_(False),
            Mereni_kalorimetry.delta.is_not(None),
            Mereni_kalorimetry.delta >= 0,
            Mereni_kalorimetry.interval_minutes > 0,
            Mereni_kalorimetry.date >= window.start,
            Mereni_kalorimetry.date < window.end,
        )
        .order_by(
            Mereni_kalorimetry.identifikace.asc(),
            Mereni_kalorimetry.date.asc(),
            Mereni_kalorimetry.id.asc(),
        )
    )
    normalized_identifiers = tuple(
        dict.fromkeys(
            str(identifier)
            for identifier in identifiers or ()
            if str(identifier).strip()
        )
    )
    if normalized_identifiers:
        statement = statement.where(
            Mereni_kalorimetry.identifikace.in_(normalized_identifiers)
        )
    return statement


def build_kalorimetry_selection_metadata_statement() -> Select:
    return (
        select(
            KalorimetryModelSelectionRun.id.label("selection_run_id"),
            KalorimetryModelSelectionRun.selected_model_version,
            KalorimetryModelSelectionRun.selected_model_name,
            KalorimetryModelSelectionRun.train_start,
            KalorimetryModelSelectionRun.train_end,
            KalorimetryModelSelectionRun.validation_start,
            KalorimetryModelSelectionRun.validation_end,
            KalorimetryModelSelectionRun.deploy_start,
            KalorimetryModelSelectionRun.deploy_end,
            KalorimetryModelSelectionRun.created_at,
        )
        .order_by(
            KalorimetryModelSelectionRun.created_at.desc(),
            KalorimetryModelSelectionRun.id.desc(),
        )
        .limit(1)
    )


def build_kalorimetry_weather_observations_statement(
    window: PredictionTimeWindow,
    *,
    identifiers: Sequence[str] | None = None,
) -> Select:
    weather_features = (
        select(
            MeteoHourly.datetime_hour.label("datetime_hour"),
            func.avg(cast(MeteoHourly.heating_degree_hours, Float))
            .over(
                order_by=MeteoHourly.datetime_hour,
                rows=(-23, 0),
            )
            .label("hdd_24h"),
        )
        .subquery("kalorimetry_weather_features")
    )
    measurement_utc_hour = func.date_trunc(
        "hour",
        func.timezone(
            "UTC",
            func.timezone(
                "Europe/Prague",
                Mereni_kalorimetry.date,
            ),
        ),
    )
    statement = (
        select(
            Mereni_kalorimetry.id.label("measurement_id"),
            Mereni_kalorimetry.identifikace,
            Mereni_kalorimetry.date,
            Mereni_kalorimetry.delta,
            Mereni_kalorimetry.interval_minutes,
            Mereni_kalorimetry.day_of_week,
            Mereni_kalorimetry.slot,
            Mereni_kalorimetry.spotreba_energie,
            Mereni_kalorimetry.objem,
            Mereni_kalorimetry.nocni_odber,
            Mereni_kalorimetry.zdroj,
            Mereni_kalorimetry.time_utc,
            Mereni_kalorimetry.platne,
            Mereni_kalorimetry.reset_detected,
            Mereni_kalorimetry.synthetic,
            Mereni_kalorimetry.gap_detected,
            weather_features.c.hdd_24h,
        )
        .join(
            weather_features,
            weather_features.c.datetime_hour == measurement_utc_hour,
        )
        .where(
            Mereni_kalorimetry.platne.is_(True),
            Mereni_kalorimetry.reset_detected.is_(False),
            Mereni_kalorimetry.synthetic.is_(False),
            Mereni_kalorimetry.gap_detected.is_(False),
            Mereni_kalorimetry.delta.is_not(None),
            Mereni_kalorimetry.delta >= 0,
            Mereni_kalorimetry.interval_minutes > 0,
            Mereni_kalorimetry.date >= window.start,
            Mereni_kalorimetry.date < window.end,
        )
        .order_by(
            Mereni_kalorimetry.identifikace.asc(),
            Mereni_kalorimetry.date.asc(),
            Mereni_kalorimetry.id.asc(),
        )
    )
    normalized_identifiers = tuple(
        dict.fromkeys(
            str(identifier)
            for identifier in identifiers or ()
            if str(identifier).strip()
        )
    )
    if normalized_identifiers:
        statement = statement.where(
            Mereni_kalorimetry.identifikace.in_(normalized_identifiers)
        )
    return statement


def serialize_kalorimetry_observation(
    row: Mapping[str, Any],
) -> PredictionObservation:
    if not is_kalorimetry_observation_eligible(
        row,
        purpose=KalorimetryObservationPurpose.MODEL_INPUT,
    ):
        raise ValueError("Kalorimetry observation does not satisfy model-input quality.")
    return PredictionObservation(
        identifier=str(row["identifikace"]),
        timestamp=row["date"],
        actual_value=float(row["delta"]),
        interval_minutes=int(row["interval_minutes"]),
        day_of_week=int(row["day_of_week"]),
        slot=int(row["slot"]),
        features={
            "measurement_id": int(row["measurement_id"]),
            "spotreba_energie": float(row["spotreba_energie"]),
            "objem": (
                float(row["objem"])
                if row.get("objem") is not None
                else None
            ),
            "nocni_odber": bool(row.get("nocni_odber", False)),
            "zdroj": (
                str(row["zdroj"])
                if row.get("zdroj") is not None
                else None
            ),
            "time_utc": row.get("time_utc"),
            **(
                {"hdd_24h": float(row["hdd_24h"])}
                if row.get("hdd_24h") is not None
                else {}
            ),
        },
    )


def serialize_kalorimetry_selection_metadata(
    row: Mapping[str, Any],
) -> PredictionSelectionMetadata:
    return PredictionSelectionMetadata(
        medium_key=KalorimetryPredictionAdapter.medium_key,
        selection_run_id=int(row["selection_run_id"]),
        selected_model_version=int(row["selected_model_version"]),
        selected_model_name=str(row["selected_model_name"]),
        train=PredictionTimeWindow(
            start=row["train_start"],
            end=row["train_end"],
            label="train",
        ),
        validation=PredictionTimeWindow(
            start=row["validation_start"],
            end=row["validation_end"],
            label="validation",
        ),
        deploy=PredictionTimeWindow(
            start=row["deploy_start"],
            end=row["deploy_end"],
            label="deploy",
        ),
        created_at=row["created_at"],
    )


def profile_point_to_kalorimetry_row(
    profile: PredictionProfilePoint,
    *,
    model_version: int,
) -> dict[str, object]:
    return {
        "identifikace": profile.identifier,
        "interval_minutes": int(profile.interval_minutes),
        "day_of_week": int(profile.day_of_week),
        "slot": int(profile.slot),
        "median": max(float(profile.expected_median), 0.0),
        "mean": max(float(profile.expected_mean), 0.0),
        "p10": max(float(profile.expected_p10), 0.0),
        "p90": max(float(profile.expected_p90), 0.0),
        "std": max(float(profile.expected_std), 0.0001),
        "model_version": int(model_version),
        "sample_size": int(profile.sample_size),
    }
