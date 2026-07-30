from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from core.db.connect import ENGINE_PG
from moduly.mereni.kalorimetry.database.models import (
    KalorimetryModelSelectionRun,
    KalorimetryModelValidationMetric,
    KalorimetryModelValidationRun,
    KalorimetryProfilesAnomaly,
    KalorimetryWeatherModelProfile,
)
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_MEDIUM_KEY,
)
from moduly.mereni.prediction import (
    CandidateProfileBuildResult,
    PredictionCandidateSpec,
    PredictionObservation,
    PredictionProfilePoint,
    PredictionRebuildWindows,
)


KALORIMETRY_BASELINE_MODEL_VERSION = 1
KALORIMETRY_BASELINE_MODEL_KEY = "calendar_week_slot_baseline"
KALORIMETRY_BASELINE_MODEL_NAME = "Kalorimetry calendar-week slot baseline"
KALORIMETRY_BASELINE_INTERVAL_MINUTES = 15
KALORIMETRY_BASELINE_SLOTS_PER_DAY = 96
KALORIMETRY_BASELINE_PROFILE_POINTS = 7 * KALORIMETRY_BASELINE_SLOTS_PER_DAY
KALORIMETRY_BASELINE_MIN_SLOT_SAMPLES = 8


@dataclass(frozen=True)
class KalorimetryCalendarProfileCatalog:
    profiles: tuple[PredictionProfilePoint, ...]
    eligible_identifiers: tuple[str, ...]
    insufficient_history_identifiers: tuple[str, ...]


def ensure_kalorimetry_prediction_tables(engine=ENGINE_PG) -> None:
    with engine.begin() as connection:
        KalorimetryProfilesAnomaly.__table__.create(
            bind=connection,
            checkfirst=True,
        )
        KalorimetryModelSelectionRun.__table__.create(
            bind=connection,
            checkfirst=True,
        )
        KalorimetryWeatherModelProfile.__table__.create(
            bind=connection,
            checkfirst=True,
        )
        KalorimetryModelValidationRun.__table__.create(
            bind=connection,
            checkfirst=True,
        )
        KalorimetryModelValidationMetric.__table__.create(
            bind=connection,
            checkfirst=True,
        )


@dataclass(frozen=True)
class KalorimetryCalendarBaselineCandidate:
    minimum_slot_samples: int = KALORIMETRY_BASELINE_MIN_SLOT_SAMPLES
    bootstrap_fn: Callable[[], None] = ensure_kalorimetry_prediction_tables

    @property
    def spec(self) -> PredictionCandidateSpec:
        return PredictionCandidateSpec(
            medium_key=KALORIMETRY_MEDIUM_KEY,
            model_version=KALORIMETRY_BASELINE_MODEL_VERSION,
            model_key=KALORIMETRY_BASELINE_MODEL_KEY,
            model_name=KALORIMETRY_BASELINE_MODEL_NAME,
            training_window_months=12,
            validation_window_months=1,
            selection_enabled=True,
        )

    def build_profile_catalog(
        self,
        observations: Sequence[PredictionObservation],
    ) -> KalorimetryCalendarProfileCatalog:
        return build_kalorimetry_calendar_profile_catalog(
            observations,
            model_version=self.spec.model_version,
            minimum_slot_samples=self.minimum_slot_samples,
        )

    def build_profiles(
        self,
        adapter,
        windows: PredictionRebuildWindows,
    ) -> CandidateProfileBuildResult:
        self.bootstrap_fn()
        observations = adapter.load_observations(windows.train)
        catalog = self.build_profile_catalog(observations)
        persisted = adapter.replace_profiles(
            model_version=self.spec.model_version,
            profiles=catalog.profiles,
        )
        return CandidateProfileBuildResult(
            model_version=persisted.model_version,
            profile_count=persisted.profile_count,
            metadata={
                **dict(persisted.metadata),
                "eligible_identifier_count": len(catalog.eligible_identifiers),
                "insufficient_history_identifier_count": len(
                    catalog.insufficient_history_identifiers
                ),
                "expected_profile_points_per_identifier": (
                    KALORIMETRY_BASELINE_PROFILE_POINTS
                ),
                "minimum_slot_samples": self.minimum_slot_samples,
            },
        )

    def predict_validation(
        self,
        adapter,
        *,
        train_window,
        validation_window,
    ):
        from moduly.mereni.prediction import PredictionBacktestPoint

        catalog = self.build_profile_catalog(
            adapter.load_observations(train_window)
        )
        expected_by_slot = {
            (point.identifier, point.day_of_week, point.slot): point.expected_mean
            for point in catalog.profiles
        }
        return tuple(
            PredictionBacktestPoint(
                identifier=observation.identifier,
                timestamp=observation.timestamp,
                actual_value=observation.actual_value,
                predicted_mean=expected_by_slot.get(
                    (
                        observation.identifier,
                        observation.day_of_week,
                        observation.slot,
                    )
                ),
            )
            for observation in adapter.load_observations(validation_window)
        )
def build_kalorimetry_calendar_profile_catalog(
    observations: Iterable[PredictionObservation],
    *,
    model_version: int = KALORIMETRY_BASELINE_MODEL_VERSION,
    minimum_slot_samples: int = KALORIMETRY_BASELINE_MIN_SLOT_SAMPLES,
) -> KalorimetryCalendarProfileCatalog:
    if minimum_slot_samples <= 0:
        raise ValueError("Minimum kalorimetry slot sample count must be positive.")

    values_by_identifier_slot: dict[
        tuple[str, int, int],
        list[float],
    ] = defaultdict(list)
    identifiers: set[str] = set()

    for observation in observations:
        identifier = str(observation.identifier).strip()
        if not identifier:
            continue
        identifiers.add(identifier)
        if observation.interval_minutes != KALORIMETRY_BASELINE_INTERVAL_MINUTES:
            continue
        if not 0 <= observation.day_of_week <= 6:
            continue
        if not 0 <= observation.slot < KALORIMETRY_BASELINE_SLOTS_PER_DAY:
            continue
        actual_value = float(observation.actual_value)
        if not math.isfinite(actual_value) or actual_value < 0:
            continue
        values_by_identifier_slot[
            (identifier, observation.day_of_week, observation.slot)
        ].append(actual_value)

    profiles: list[PredictionProfilePoint] = []
    eligible_identifiers: list[str] = []
    insufficient_identifiers: list[str] = []

    for identifier in sorted(identifiers):
        identifier_profiles: list[PredictionProfilePoint] = []
        complete = True
        for day_of_week in range(7):
            for slot in range(KALORIMETRY_BASELINE_SLOTS_PER_DAY):
                values = values_by_identifier_slot.get(
                    (identifier, day_of_week, slot),
                    [],
                )
                if len(values) < minimum_slot_samples:
                    complete = False
                    break
                identifier_profiles.append(
                    _build_profile_point(
                        identifier=identifier,
                        day_of_week=day_of_week,
                        slot=slot,
                        values=values,
                        model_version=model_version,
                    )
                )
            if not complete:
                break

        if not complete:
            insufficient_identifiers.append(identifier)
            continue
        if len(identifier_profiles) != KALORIMETRY_BASELINE_PROFILE_POINTS:
            raise RuntimeError("Complete kalorimetry profile has an invalid size.")
        eligible_identifiers.append(identifier)
        profiles.extend(identifier_profiles)

    return KalorimetryCalendarProfileCatalog(
        profiles=tuple(profiles),
        eligible_identifiers=tuple(eligible_identifiers),
        insufficient_history_identifiers=tuple(insufficient_identifiers),
    )


def _build_profile_point(
    *,
    identifier: str,
    day_of_week: int,
    slot: int,
    values: Sequence[float],
    model_version: int,
) -> PredictionProfilePoint:
    ordered = sorted(float(value) for value in values)
    return PredictionProfilePoint(
        identifier=identifier,
        interval_minutes=KALORIMETRY_BASELINE_INTERVAL_MINUTES,
        day_of_week=day_of_week,
        slot=slot,
        expected_mean=max(float(statistics.fmean(ordered)), 0.0),
        expected_median=max(float(statistics.median(ordered)), 0.0),
        expected_p10=max(_linear_quantile(ordered, 0.10), 0.0),
        expected_p90=max(_linear_quantile(ordered, 0.90), 0.0),
        expected_std=max(float(statistics.pstdev(ordered)), 0.0001),
        sample_size=len(ordered),
        model_version=model_version,
        features={"strategy": KALORIMETRY_BASELINE_MODEL_KEY},
    )


def _linear_quantile(ordered_values: Sequence[float], quantile: float) -> float:
    if not ordered_values:
        raise ValueError("Cannot calculate a quantile without values.")
    if not 0 <= quantile <= 1:
        raise ValueError("Quantile must be between zero and one.")
    if len(ordered_values) == 1:
        return float(ordered_values[0])
    position = (len(ordered_values) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return float(ordered_values[lower_index])
    weight = position - lower_index
    lower = float(ordered_values[lower_index])
    upper = float(ordered_values[upper_index])
    return lower + (upper - lower) * weight
