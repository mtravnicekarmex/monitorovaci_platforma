from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_MEDIUM_KEY,
    _to_prague_wall_time,
)
from moduly.mereni.prediction.storage import (
    PredictionProfileSnapshot,
    PredictionSelectedModelSnapshot,
    SELECTION_MODE_ACTIVE,
    normalize_selection_mode,
)


NO_SELECTION_SNAPSHOT = "no_selection_snapshot"
INSUFFICIENT_HISTORY = "insufficient_history"
MISSING_PROFILE = "missing_profile"


@dataclass(frozen=True)
class KalorimetryProfileLookupRequest:
    identifier: str
    timestamp: datetime
    interval_minutes: int = 15

    def __post_init__(self) -> None:
        if not str(self.identifier).strip():
            raise ValueError("identifier must not be empty")
        if self.interval_minutes <= 0 or 1440 % self.interval_minutes != 0:
            raise ValueError("interval_minutes must divide one day")

    @property
    def prague_timestamp(self) -> datetime:
        return _to_prague_wall_time(self.timestamp)

    @property
    def day_of_week(self) -> int:
        return self.prague_timestamp.weekday()

    @property
    def slot(self) -> int:
        value = self.prague_timestamp
        return (value.hour * 60 + value.minute) // self.interval_minutes


@dataclass(frozen=True)
class KalorimetryActiveProfile:
    request: KalorimetryProfileLookupRequest
    prediction_available: bool
    availability_reason: str | None
    selected_model_version: int | None = None
    selected_model_key: str | None = None
    selected_model_name: str | None = None
    expected_mean: float | None = None
    expected_median: float | None = None
    expected_p10: float | None = None
    expected_p90: float | None = None
    expected_std: float | None = None
    sample_size: int | None = None
    decision: PredictionSelectedModelSnapshot | None = None
    profile: PredictionProfileSnapshot | None = None


def load_period_valid_active_profiles(
    session: Session,
    requests: Sequence[KalorimetryProfileLookupRequest],
    *,
    selection_mode: str = SELECTION_MODE_ACTIVE,
) -> tuple[KalorimetryActiveProfile, ...]:
    normalized_requests = tuple(requests)
    if not normalized_requests:
        return ()

    normalized_mode = normalize_selection_mode(selection_mode)
    identifiers = sorted({request.identifier for request in normalized_requests})
    timestamps = [request.prague_timestamp for request in normalized_requests]
    period_start = min(timestamps)
    period_end = max(timestamps)

    decision = PredictionSelectedModelSnapshot
    decisions = (
        session.execute(
            select(decision).where(
                decision.medium_key == KALORIMETRY_MEDIUM_KEY,
                decision.selection_mode == normalized_mode,
                decision.identifier.in_(identifiers),
                decision.forecast_period_start <= period_end,
                decision.forecast_period_end > period_start,
            )
        )
        .scalars()
        .all()
    )

    profile = PredictionProfileSnapshot
    profiles = (
        session.execute(
            select(profile).where(
                profile.medium_key == KALORIMETRY_MEDIUM_KEY,
                profile.selection_mode == normalized_mode,
                profile.identifier.in_(identifiers),
                profile.forecast_period_start <= period_end,
                profile.forecast_period_end > period_start,
            )
        )
        .scalars()
        .all()
    )

    decisions_by_identifier: dict[
        str,
        list[PredictionSelectedModelSnapshot],
    ] = {}
    for row in decisions:
        decisions_by_identifier.setdefault(str(row.identifier), []).append(row)

    profiles_by_slot: dict[
        tuple[str, datetime, datetime, int, int, int, int],
        list[PredictionProfileSnapshot],
    ] = {}
    for row in profiles:
        key = (
            str(row.identifier),
            row.forecast_period_start,
            row.forecast_period_end,
            int(row.model_version),
            int(row.interval_minutes),
            int(row.day_of_week),
            int(row.slot),
        )
        profiles_by_slot.setdefault(key, []).append(row)

    results = []
    for request in normalized_requests:
        identifier_decisions = decisions_by_identifier.get(
            request.identifier,
            [],
        )
        timestamp = request.prague_timestamp
        matching_decisions = [
            row
            for row in identifier_decisions
            if row.forecast_period_start <= timestamp < row.forecast_period_end
        ]
        selected_decision = (
            None
            if not matching_decisions
            else max(matching_decisions, key=_decision_precedence_key)
        )
        candidate_profiles = []
        if selected_decision is not None:
            candidate_profiles = profiles_by_slot.get(
                (
                    request.identifier,
                    selected_decision.forecast_period_start,
                    selected_decision.forecast_period_end,
                    int(selected_decision.selected_model_version),
                    request.interval_minutes,
                    request.day_of_week,
                    request.slot,
                ),
                [],
            )
        results.append(
            resolve_period_valid_active_profile(
                request,
                decisions=(
                    [] if selected_decision is None else [selected_decision]
                ),
                profiles=candidate_profiles,
            )
        )
    return tuple(results)


def resolve_period_valid_active_profile(
    request: KalorimetryProfileLookupRequest,
    *,
    decisions: Sequence[PredictionSelectedModelSnapshot],
    profiles: Sequence[PredictionProfileSnapshot],
) -> KalorimetryActiveProfile:
    timestamp = request.prague_timestamp
    matching_decisions = [
        row
        for row in decisions
        if str(row.identifier) == request.identifier
        and row.forecast_period_start <= timestamp < row.forecast_period_end
    ]
    if not matching_decisions:
        return _unavailable(request, NO_SELECTION_SNAPSHOT)

    selected_decision = max(matching_decisions, key=_decision_precedence_key)
    fallback_reason = str(selected_decision.fallback_reason or "none")
    if fallback_reason == INSUFFICIENT_HISTORY:
        return _unavailable(
            request,
            INSUFFICIENT_HISTORY,
            decision=selected_decision,
        )

    matching_profiles = [
        row
        for row in profiles
        if str(row.identifier) == request.identifier
        and row.forecast_period_start == selected_decision.forecast_period_start
        and row.forecast_period_end == selected_decision.forecast_period_end
        and int(row.model_version) == int(selected_decision.selected_model_version)
        and int(row.interval_minutes) == request.interval_minutes
        and int(row.day_of_week) == request.day_of_week
        and int(row.slot) == request.slot
        and row.forecast_period_start <= timestamp < row.forecast_period_end
    ]
    if not matching_profiles:
        return _unavailable(
            request,
            MISSING_PROFILE,
            decision=selected_decision,
        )

    selected_profile = max(matching_profiles, key=_profile_precedence_key)
    return KalorimetryActiveProfile(
        request=request,
        prediction_available=True,
        availability_reason=None,
        selected_model_version=int(selected_decision.selected_model_version),
        selected_model_key=str(selected_decision.selected_model_key),
        selected_model_name=str(selected_decision.selected_model_name),
        expected_mean=float(selected_profile.expected_mean),
        expected_median=_optional_float(selected_profile.expected_median),
        expected_p10=_optional_float(selected_profile.expected_p10),
        expected_p90=_optional_float(selected_profile.expected_p90),
        expected_std=_optional_float(selected_profile.expected_std),
        sample_size=(
            None
            if selected_profile.sample_size is None
            else int(selected_profile.sample_size)
        ),
        decision=selected_decision,
        profile=selected_profile,
    )


def _decision_precedence_key(
    row: PredictionSelectedModelSnapshot,
) -> tuple[datetime, datetime, int]:
    return (
        row.forecast_period_start,
        getattr(row, "created_at", None) or datetime.min,
        int(getattr(row, "id", 0) or 0),
    )


def _profile_precedence_key(
    row: PredictionProfileSnapshot,
) -> tuple[int, datetime, int]:
    return (
        int(getattr(row, "archive_version", 1) or 1),
        getattr(row, "created_at", None) or datetime.min,
        int(getattr(row, "id", 0) or 0),
    )


def _unavailable(
    request: KalorimetryProfileLookupRequest,
    reason: str,
    *,
    decision: PredictionSelectedModelSnapshot | None = None,
) -> KalorimetryActiveProfile:
    return KalorimetryActiveProfile(
        request=request,
        prediction_available=False,
        availability_reason=reason,
        selected_model_version=(
            None if decision is None else int(decision.selected_model_version)
        ),
        selected_model_key=(
            None if decision is None else str(decision.selected_model_key)
        ),
        selected_model_name=(
            None if decision is None else str(decision.selected_model_name)
        ),
        decision=decision,
    )


def _optional_float(value: float | None) -> float | None:
    return None if value is None else float(value)
