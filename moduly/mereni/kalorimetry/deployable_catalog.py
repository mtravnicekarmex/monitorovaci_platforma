from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from moduly.mereni.kalorimetry.calendar_baseline import (
    KALORIMETRY_BASELINE_MODEL_KEY,
    KALORIMETRY_BASELINE_MODEL_VERSION,
    KALORIMETRY_BASELINE_PROFILE_POINTS,
    KalorimetryCalendarBaselineCandidate,
)
from moduly.mereni.kalorimetry.weather_candidate import (
    KALORIMETRY_WEATHER_MODEL_KEY,
    KALORIMETRY_WEATHER_MODEL_VERSION,
    KalorimetryWeatherCandidate,
    build_kalorimetry_weather_deploy_profiles,
)
from moduly.mereni.prediction import (
    PredictionForecastPeriod,
    PredictionObservation,
    PredictionProfilePoint,
)


PROFILE_AVAILABLE = "available"
PROFILE_INSUFFICIENT_HISTORY = "insufficient_history"
PROFILE_MISSING_FORECAST_WEATHER = "missing_forecast_weather"
PROFILE_INCOMPLETE = "incomplete_profile"
PROFILE_INVALID = "invalid_profile"


@dataclass(frozen=True)
class KalorimetryDeployableProfileEntry:
    identifier: str
    model_version: int
    model_key: str
    available: bool
    reason: str
    profiles: tuple[PredictionProfilePoint, ...]

    def __post_init__(self) -> None:
        if self.available:
            validate_deployable_kalorimetry_profiles(
                self.profiles,
                expected_identifier=self.identifier,
                expected_model_version=self.model_version,
            )
            if self.reason != PROFILE_AVAILABLE:
                raise ValueError("Available profile entry needs available reason.")
        elif self.profiles:
            raise ValueError("Unavailable profile entry must not carry profiles.")


@dataclass(frozen=True)
class KalorimetryDeployableCandidateCatalog:
    forecast_period: PredictionForecastPeriod
    entries: tuple[KalorimetryDeployableProfileEntry, ...]

    def get(
        self,
        *,
        identifier: str,
        model_version: int,
    ) -> KalorimetryDeployableProfileEntry | None:
        return next(
            (
                entry
                for entry in self.entries
                if entry.identifier == identifier
                and entry.model_version == model_version
            ),
            None,
        )


def build_kalorimetry_deployable_candidate_catalog(
    *,
    baseline_observations: Sequence[PredictionObservation],
    weather_observations: Sequence[PredictionObservation],
    forecast_period: PredictionForecastPeriod,
    hdd_24h_by_utc_hour: Mapping,
    baseline_candidate: KalorimetryCalendarBaselineCandidate | None = None,
    weather_candidate: KalorimetryWeatherCandidate | None = None,
) -> KalorimetryDeployableCandidateCatalog:
    resolved_baseline_candidate = (
        baseline_candidate or KalorimetryCalendarBaselineCandidate()
    )
    resolved_weather_candidate = (
        weather_candidate or KalorimetryWeatherCandidate()
    )
    identifiers = sorted(
        {
            str(observation.identifier).strip()
            for observation in (
                *baseline_observations,
                *weather_observations,
            )
            if str(observation.identifier).strip()
        }
    )

    baseline_catalog = resolved_baseline_candidate.build_profile_catalog(
        baseline_observations
    )
    baseline_by_identifier = _profiles_by_identifier(
        baseline_catalog.profiles
    )
    weather_catalog = resolved_weather_candidate.build_profile_catalog(
        weather_observations
    )
    weather_by_identifier = _profiles_by_identifier(weather_catalog.profiles)
    weather_deploy = build_kalorimetry_weather_deploy_profiles(
        weather_catalog.profiles,
        forecast_period=forecast_period,
        hdd_24h_by_utc_hour=hdd_24h_by_utc_hour,
    )
    weather_deploy_by_identifier = _profiles_by_identifier(
        weather_deploy.profiles
    )

    entries: list[KalorimetryDeployableProfileEntry] = []
    for identifier in identifiers:
        entries.append(
            _build_entry(
                identifier=identifier,
                model_version=KALORIMETRY_BASELINE_MODEL_VERSION,
                model_key=KALORIMETRY_BASELINE_MODEL_KEY,
                profiles=baseline_by_identifier.get(identifier, ()),
                unavailable_reason=PROFILE_INSUFFICIENT_HISTORY,
            )
        )

        if identifier not in weather_by_identifier:
            weather_profiles: tuple[PredictionProfilePoint, ...] = ()
            weather_reason = PROFILE_INSUFFICIENT_HISTORY
        elif not weather_deploy.available:
            weather_profiles = ()
            weather_reason = (
                weather_deploy.reason or PROFILE_MISSING_FORECAST_WEATHER
            )
        else:
            weather_profiles = weather_deploy_by_identifier.get(
                identifier,
                (),
            )
            weather_reason = PROFILE_INCOMPLETE
        entries.append(
            _build_entry(
                identifier=identifier,
                model_version=KALORIMETRY_WEATHER_MODEL_VERSION,
                model_key=KALORIMETRY_WEATHER_MODEL_KEY,
                profiles=weather_profiles,
                unavailable_reason=weather_reason,
            )
        )

    return KalorimetryDeployableCandidateCatalog(
        forecast_period=forecast_period,
        entries=tuple(entries),
    )


def validate_deployable_kalorimetry_profiles(
    profiles: Sequence[PredictionProfilePoint],
    *,
    expected_identifier: str,
    expected_model_version: int,
) -> None:
    if len(profiles) != KALORIMETRY_BASELINE_PROFILE_POINTS:
        raise ValueError("Deployable kalorimetry profile must have 672 points.")
    keys = set()
    for profile in profiles:
        if profile.identifier != expected_identifier:
            raise ValueError("Deployable profile mixes identifiers.")
        if profile.model_version != expected_model_version:
            raise ValueError("Deployable profile has an unexpected model version.")
        if profile.interval_minutes != 15:
            raise ValueError("Deployable profile must use 15-minute intervals.")
        key = (profile.day_of_week, profile.slot)
        if key in keys:
            raise ValueError("Deployable profile contains a duplicate slot.")
        keys.add(key)
        if not 0 <= profile.day_of_week <= 6 or not 0 <= profile.slot < 96:
            raise ValueError("Deployable profile contains an invalid slot.")
        for value in (
            profile.expected_mean,
            profile.expected_median,
            profile.expected_p10,
            profile.expected_p90,
            profile.expected_std,
        ):
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError(
                    "Deployable profile contains invalid expected energy."
                )
        if profile.expected_p10 > profile.expected_p90:
            raise ValueError("Deployable profile quantiles are not ordered.")
        if profile.sample_size <= 0:
            raise ValueError("Deployable profile needs a positive sample size.")
    expected_keys = {
        (day_of_week, slot)
        for day_of_week in range(7)
        for slot in range(96)
    }
    if keys != expected_keys:
        raise ValueError("Deployable profile does not cover the complete week.")


def _profiles_by_identifier(
    profiles: Iterable[PredictionProfilePoint],
) -> dict[str, tuple[PredictionProfilePoint, ...]]:
    grouped: dict[str, list[PredictionProfilePoint]] = defaultdict(list)
    for profile in profiles:
        grouped[profile.identifier].append(profile)
    return {
        identifier: tuple(
            sorted(
                identifier_profiles,
                key=lambda point: (point.day_of_week, point.slot),
            )
        )
        for identifier, identifier_profiles in grouped.items()
    }


def _build_entry(
    *,
    identifier: str,
    model_version: int,
    model_key: str,
    profiles: Sequence[PredictionProfilePoint],
    unavailable_reason: str,
) -> KalorimetryDeployableProfileEntry:
    resolved_profiles = tuple(profiles)
    if not resolved_profiles:
        return KalorimetryDeployableProfileEntry(
            identifier=identifier,
            model_version=model_version,
            model_key=model_key,
            available=False,
            reason=unavailable_reason,
            profiles=(),
        )
    try:
        validate_deployable_kalorimetry_profiles(
            resolved_profiles,
            expected_identifier=identifier,
            expected_model_version=model_version,
        )
    except ValueError:
        return KalorimetryDeployableProfileEntry(
            identifier=identifier,
            model_version=model_version,
            model_key=model_key,
            available=False,
            reason=PROFILE_INVALID,
            profiles=(),
        )
    return KalorimetryDeployableProfileEntry(
        identifier=identifier,
        model_version=model_version,
        model_key=model_key,
        available=True,
        reason=PROFILE_AVAILABLE,
        profiles=resolved_profiles,
    )
