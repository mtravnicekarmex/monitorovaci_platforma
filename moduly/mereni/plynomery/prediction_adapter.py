from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy import Select, delete, func, insert, select

from core.db.connect import get_session_pg
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    PlynomeryModelSelectionRun,
    PlynomeryProfilesAnomaly,
)
from moduly.mereni.plynomery.plynomery_prediction import (
    DEFAULT_MODEL_VERSION,
    get_runtime_model_version,
)
from moduly.mereni.prediction import (
    CandidateProfileBuildResult,
    PredictionObservation,
    PredictionProfilePoint,
    PredictionSelectionMetadata,
    PredictionTimeWindow,
)


class PlynomeryPredictionAdapter:
    medium_key = "plynomery"

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any] = get_session_pg,
        active_model_loader: Callable[..., int] = get_runtime_model_version,
    ) -> None:
        self._session_factory = session_factory
        self._active_model_loader = active_model_loader

    def get_active_model_version(self) -> int:
        session = self._session_factory()
        try:
            return self._active_model_loader(
                session=session,
                default=DEFAULT_MODEL_VERSION,
            )
        finally:
            session.close()

    def load_selection_metadata(self) -> PredictionSelectionMetadata | None:
        session = self._session_factory()
        try:
            row = session.execute(build_plynomery_selection_metadata_statement()).mappings().first()
            if row is None:
                return None
            return serialize_plynomery_selection_metadata(row)
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
                    build_plynomery_observations_statement(
                        window,
                        identifiers=identifiers,
                    )
                )
                .mappings()
                .all()
            )
            return tuple(serialize_plynomery_observation(row) for row in rows)
        finally:
            session.close()

    def replace_profiles(
        self,
        *,
        model_version: int,
        profiles: Iterable[PredictionProfilePoint],
    ) -> CandidateProfileBuildResult:
        profile_rows = [
            profile_point_to_plynomery_row(profile, model_version=model_version)
            for profile in profiles
        ]
        session = self._session_factory()
        try:
            session.execute(
                delete(PlynomeryProfilesAnomaly).where(
                    PlynomeryProfilesAnomaly.model_version == model_version
                )
            )
            if profile_rows:
                session.execute(insert(PlynomeryProfilesAnomaly), profile_rows)
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
                    select(func.count()).select_from(PlynomeryProfilesAnomaly).where(
                        PlynomeryProfilesAnomaly.model_version == model_version
                    )
                ).scalar_one()
            )
        finally:
            session.close()


def build_plynomery_observations_statement(
    window: PredictionTimeWindow,
    *,
    identifiers: Sequence[str] | None = None,
) -> Select:
    statement = (
        select(
            Mereni_plynomery.id.label("measurement_id"),
            Mereni_plynomery.identifikace,
            Mereni_plynomery.date,
            Mereni_plynomery.delta,
            Mereni_plynomery.interval_minutes,
            Mereni_plynomery.day_of_week,
            Mereni_plynomery.slot,
            Mereni_plynomery.objem,
            Mereni_plynomery.nocni_odber,
            Mereni_plynomery.zdroj,
            Mereni_plynomery.time_utc,
        )
        .where(
            Mereni_plynomery.synthetic.is_(False),
            Mereni_plynomery.platne.is_(True),
            Mereni_plynomery.reset_detected.is_(False),
            Mereni_plynomery.delta.is_not(None),
            Mereni_plynomery.date >= window.start,
            Mereni_plynomery.date < window.end,
        )
        .order_by(
            Mereni_plynomery.identifikace.asc(),
            Mereni_plynomery.date.asc(),
            Mereni_plynomery.id.asc(),
        )
    )
    normalized_identifiers = tuple(
        dict.fromkeys(str(identifier) for identifier in identifiers or () if identifier)
    )
    if normalized_identifiers:
        statement = statement.where(Mereni_plynomery.identifikace.in_(normalized_identifiers))
    return statement


def build_plynomery_selection_metadata_statement() -> Select:
    return (
        select(
            PlynomeryModelSelectionRun.id.label("selection_run_id"),
            PlynomeryModelSelectionRun.selected_model_version,
            PlynomeryModelSelectionRun.selected_model_name,
            PlynomeryModelSelectionRun.train_start,
            PlynomeryModelSelectionRun.train_end,
            PlynomeryModelSelectionRun.validation_start,
            PlynomeryModelSelectionRun.validation_end,
            PlynomeryModelSelectionRun.deploy_start,
            PlynomeryModelSelectionRun.deploy_end,
            PlynomeryModelSelectionRun.created_at,
        )
        .order_by(
            PlynomeryModelSelectionRun.created_at.desc(),
            PlynomeryModelSelectionRun.id.desc(),
        )
        .limit(1)
    )


def serialize_plynomery_observation(row: Mapping[str, Any]) -> PredictionObservation:
    return PredictionObservation(
        identifier=str(row["identifikace"]),
        timestamp=row["date"],
        actual_value=float(row["delta"]),
        interval_minutes=int(row["interval_minutes"]),
        day_of_week=int(row["day_of_week"]),
        slot=int(row["slot"]),
        features={
            "measurement_id": int(row["measurement_id"]),
            "objem": float(row["objem"]) if row["objem"] is not None else None,
            "nocni_odber": bool(row["nocni_odber"]),
            "zdroj": str(row["zdroj"]) if row["zdroj"] is not None else None,
            "time_utc": row["time_utc"],
        },
    )


def serialize_plynomery_selection_metadata(
    row: Mapping[str, Any],
) -> PredictionSelectionMetadata:
    return PredictionSelectionMetadata(
        medium_key=PlynomeryPredictionAdapter.medium_key,
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


def profile_point_to_plynomery_row(
    profile: PredictionProfilePoint,
    *,
    model_version: int,
) -> dict[str, object]:
    return {
        "identifikace": profile.identifier,
        "interval_minutes": int(profile.interval_minutes),
        "day_of_week": int(profile.day_of_week),
        "slot": int(profile.slot),
        "median": float(profile.expected_median),
        "mean": float(profile.expected_mean),
        "p10": float(profile.expected_p10),
        "p90": float(profile.expected_p90),
        "std": max(float(profile.expected_std), 0.0001),
        "model_version": int(model_version),
        "sample_size": int(profile.sample_size),
    }
