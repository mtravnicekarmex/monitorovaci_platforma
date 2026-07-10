from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, select

from core.db.connect import get_session_pg
from moduly.mereni.elektromery.database.models import Mereni_elektromery
from moduly.mereni.prediction import (
    CandidateProfileBuildResult,
    PredictionObservation,
    PredictionProfilePoint,
    PredictionSelectionMetadata,
    PredictionTimeWindow,
    month_start,
)


ELECTROMERY_MEDIUM_KEY = "elektromery"
SOFTLINK_SOURCE = "SOFTLINK"


@dataclass(frozen=True)
class ElektromeryMonthlyConsumption:
    identifier: str
    month_start: datetime
    consumption_kwh: float
    measurement_count: int
    selected_source_kind: str
    source_names: tuple[str, ...]


class ElektromeryPredictionAdapter:
    medium_key = ELECTROMERY_MEDIUM_KEY

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any] = get_session_pg,
        default_model_version: int = 1,
    ) -> None:
        self._session_factory = session_factory
        self._default_model_version = default_model_version

    def get_active_model_version(self) -> int:
        return self._default_model_version

    def load_selection_metadata(self) -> PredictionSelectionMetadata | None:
        return None

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
                    build_elektromery_observations_statement(
                        window,
                        identifiers=identifiers,
                    )
                )
                .mappings()
                .all()
            )
            return tuple(serialize_elektromery_observation(row) for row in rows)
        finally:
            session.close()

    def load_monthly_consumption(
        self,
        window: PredictionTimeWindow,
        *,
        identifiers: Sequence[str] | None = None,
    ) -> Sequence[ElektromeryMonthlyConsumption]:
        return aggregate_monthly_consumption(
            self.load_observations(window, identifiers=identifiers)
        )

    def replace_profiles(
        self,
        *,
        model_version: int,
        profiles: Iterable[PredictionProfilePoint],
    ) -> CandidateProfileBuildResult:
        del profiles
        raise NotImplementedError(
            "Elektromery monthly prediction candidates do not persist runtime profiles yet."
        )

    def count_profiles(self, model_version: int) -> int:
        del model_version
        return 0


def build_elektromery_observations_statement(
    window: PredictionTimeWindow,
    *,
    identifiers: Sequence[str] | None = None,
) -> Select:
    statement = (
        select(
            Mereni_elektromery.id.label("measurement_id"),
            Mereni_elektromery.identifikace,
            Mereni_elektromery.date,
            Mereni_elektromery.delta,
            Mereni_elektromery.interval_minutes,
            Mereni_elektromery.day_of_week,
            Mereni_elektromery.slot,
            Mereni_elektromery.objem,
            Mereni_elektromery.nocni_odber,
            Mereni_elektromery.gap_detected,
            Mereni_elektromery.synthetic,
            Mereni_elektromery.zdroj,
            Mereni_elektromery.time_utc,
        )
        .where(
            Mereni_elektromery.platne.is_(True),
            Mereni_elektromery.reset_detected.is_(False),
            Mereni_elektromery.delta.is_not(None),
            Mereni_elektromery.delta >= 0,
            Mereni_elektromery.date >= window.start,
            Mereni_elektromery.date < window.end,
        )
        .order_by(
            Mereni_elektromery.identifikace.asc(),
            Mereni_elektromery.date.asc(),
            Mereni_elektromery.id.asc(),
        )
    )
    normalized_identifiers = tuple(
        dict.fromkeys(str(identifier) for identifier in identifiers or () if identifier)
    )
    if normalized_identifiers:
        statement = statement.where(Mereni_elektromery.identifikace.in_(normalized_identifiers))
    return statement


def serialize_elektromery_observation(row: Mapping[str, Any]) -> PredictionObservation:
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
            "gap_detected": bool(row["gap_detected"]),
            "synthetic": bool(row["synthetic"]),
            "zdroj": str(row["zdroj"]) if row["zdroj"] is not None else None,
            "time_utc": row["time_utc"],
        },
    )


def aggregate_monthly_consumption(
    observations: Sequence[PredictionObservation],
) -> tuple[ElektromeryMonthlyConsumption, ...]:
    grouped: dict[tuple[str, object], list[PredictionObservation]] = {}
    for observation in observations:
        grouped.setdefault(
            (observation.identifier, month_start(observation.timestamp)),
            [],
        ).append(observation)

    rows: list[ElektromeryMonthlyConsumption] = []
    for (identifier, month), month_observations in grouped.items():
        selected_observations = _select_observations_for_month(month_observations)
        source_names = tuple(
            sorted(
                {
                    str(observation.features.get("zdroj") or "")
                    for observation in selected_observations
                    if observation.features.get("zdroj")
                }
            )
        )
        rows.append(
            ElektromeryMonthlyConsumption(
                identifier=identifier,
                month_start=month,
                consumption_kwh=round(
                    sum(float(observation.actual_value) for observation in selected_observations),
                    6,
                ),
                measurement_count=len(selected_observations),
                selected_source_kind=(
                    "detailed" if _has_detailed_source(selected_observations) else "softlink"
                ),
                source_names=source_names,
            )
        )
    return tuple(sorted(rows, key=lambda row: (row.identifier, row.month_start)))


def _select_observations_for_month(
    observations: Sequence[PredictionObservation],
) -> tuple[PredictionObservation, ...]:
    detailed_observations = tuple(
        observation
        for observation in observations
        if _is_detailed_source(str(observation.features.get("zdroj") or ""))
    )
    if detailed_observations:
        return detailed_observations
    return tuple(observations)


def _has_detailed_source(observations: Sequence[PredictionObservation]) -> bool:
    return any(
        _is_detailed_source(str(observation.features.get("zdroj") or ""))
        for observation in observations
    )


def _is_detailed_source(source_name: str) -> bool:
    normalized = source_name.strip().upper()
    return bool(normalized) and normalized != SOFTLINK_SOURCE
