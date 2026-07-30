from __future__ import annotations

import dataclasses
import datetime

import pytest

from moduly.mereni.kalorimetry.calendar_baseline import (
    KALORIMETRY_BASELINE_PROFILE_POINTS,
    KalorimetryCalendarBaselineCandidate,
)
from moduly.mereni.kalorimetry.deployable_catalog import (
    PROFILE_AVAILABLE,
    PROFILE_INSUFFICIENT_HISTORY,
    PROFILE_MISSING_FORECAST_WEATHER,
    KalorimetryDeployableProfileEntry,
    build_kalorimetry_deployable_candidate_catalog,
    validate_deployable_kalorimetry_profiles,
)
from moduly.mereni.kalorimetry.weather_candidate import (
    KalorimetryWeatherCandidate,
)
from moduly.mereni.prediction import (
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionObservation,
)


def observation(
    identifier: str,
    *,
    day: int,
    slot: int,
    sample: int,
    weather: bool,
) -> PredictionObservation:
    features = {"hdd_24h": float(sample)} if weather else {}
    return PredictionObservation(
        identifier=identifier,
        timestamp=datetime.datetime(2026, 1, 5)
        + datetime.timedelta(days=day, minutes=slot * 15),
        actual_value=1.0 + 0.5 * sample,
        interval_minutes=15,
        day_of_week=day,
        slot=slot,
        features=features,
    )


def complete_observations(
    identifier: str,
    *,
    weather: bool,
) -> tuple[PredictionObservation, ...]:
    return tuple(
        observation(
            identifier,
            day=day,
            slot=slot,
            sample=sample,
            weather=weather,
        )
        for day in range(7)
        for slot in range(96)
        for sample in range(8)
    )


def period() -> PredictionForecastPeriod:
    return PredictionForecastPeriod(
        start=datetime.datetime(2026, 7, 27),
        end=datetime.datetime(2026, 8, 3),
        cadence=PredictionForecastCadence.WEEKLY,
    )


def complete_weather() -> dict[datetime.datetime, float]:
    start = datetime.datetime(2026, 7, 26, 22)
    return {
        start + datetime.timedelta(hours=offset): 4.0
        for offset in range(168)
    }


def test_catalog_publishes_complete_profiles_for_both_candidates():
    catalog = build_kalorimetry_deployable_candidate_catalog(
        baseline_observations=complete_observations("K1", weather=False),
        weather_observations=complete_observations("K1", weather=True),
        forecast_period=period(),
        hdd_24h_by_utc_hour=complete_weather(),
    )

    assert len(catalog.entries) == 2
    baseline = catalog.get(identifier="K1", model_version=1)
    weather = catalog.get(identifier="K1", model_version=2)
    assert baseline.available is True
    assert baseline.reason == PROFILE_AVAILABLE
    assert len(baseline.profiles) == KALORIMETRY_BASELINE_PROFILE_POINTS
    assert weather.available is True
    assert weather.reason == PROFILE_AVAILABLE
    assert len(weather.profiles) == KALORIMETRY_BASELINE_PROFILE_POINTS
    assert all(point.expected_mean >= 0 for point in weather.profiles)


def test_missing_weather_makes_only_weather_candidate_unavailable():
    weather = complete_weather()
    del weather[sorted(weather)[20]]
    catalog = build_kalorimetry_deployable_candidate_catalog(
        baseline_observations=complete_observations("K1", weather=False),
        weather_observations=complete_observations("K1", weather=True),
        forecast_period=period(),
        hdd_24h_by_utc_hour=weather,
    )

    baseline = catalog.get(identifier="K1", model_version=1)
    weather_entry = catalog.get(identifier="K1", model_version=2)
    assert baseline.available is True
    assert weather_entry.available is False
    assert weather_entry.reason == PROFILE_MISSING_FORECAST_WEATHER
    assert weather_entry.profiles == ()


def test_insufficient_history_is_recorded_per_candidate_and_identifier():
    baseline_rows = complete_observations("K1", weather=False)
    weather_rows = tuple(
        row
        for row in complete_observations("K1", weather=True)
        if not (row.day_of_week == 6 and row.slot == 95)
    )
    catalog = build_kalorimetry_deployable_candidate_catalog(
        baseline_observations=baseline_rows,
        weather_observations=weather_rows,
        forecast_period=period(),
        hdd_24h_by_utc_hour=complete_weather(),
    )

    assert catalog.get(identifier="K1", model_version=1).available is True
    weather_entry = catalog.get(identifier="K1", model_version=2)
    assert weather_entry.available is False
    assert weather_entry.reason == PROFILE_INSUFFICIENT_HISTORY


def test_catalog_keeps_identifier_missing_from_one_candidate_input():
    catalog = build_kalorimetry_deployable_candidate_catalog(
        baseline_observations=complete_observations("K1", weather=False),
        weather_observations=complete_observations("K2", weather=True),
        forecast_period=period(),
        hdd_24h_by_utc_hour=complete_weather(),
    )

    assert len(catalog.entries) == 4
    assert catalog.get(identifier="K1", model_version=1).available is True
    assert catalog.get(identifier="K1", model_version=2).reason == (
        PROFILE_INSUFFICIENT_HISTORY
    )
    assert catalog.get(identifier="K2", model_version=1).reason == (
        PROFILE_INSUFFICIENT_HISTORY
    )
    assert catalog.get(identifier="K2", model_version=2).available is True


def test_validator_rejects_partial_duplicate_and_negative_profiles():
    profiles = list(
        KalorimetryCalendarBaselineCandidate(
            minimum_slot_samples=1
        ).build_profile_catalog(
            tuple(
                observation(
                    "K1",
                    day=day,
                    slot=slot,
                    sample=0,
                    weather=False,
                )
                for day in range(7)
                for slot in range(96)
            )
        ).profiles
    )

    with pytest.raises(ValueError, match="672"):
        validate_deployable_kalorimetry_profiles(
            profiles[:-1],
            expected_identifier="K1",
            expected_model_version=1,
        )

    duplicate = [*profiles[:-1], profiles[0]]
    with pytest.raises(ValueError, match="duplicate"):
        validate_deployable_kalorimetry_profiles(
            duplicate,
            expected_identifier="K1",
            expected_model_version=1,
        )

    negative = list(profiles)
    negative[0] = dataclasses.replace(negative[0], expected_mean=-0.1)
    with pytest.raises(ValueError, match="invalid expected energy"):
        validate_deployable_kalorimetry_profiles(
            negative,
            expected_identifier="K1",
            expected_model_version=1,
        )


def test_unavailable_entry_cannot_carry_profiles():
    point = KalorimetryWeatherCandidate(
        minimum_slot_samples=1
    ).build_profile_catalog(
        tuple(
            observation(
                "K1",
                day=day,
                slot=slot,
                sample=sample,
                weather=True,
            )
            for day in range(7)
            for slot in range(96)
            for sample in range(2)
        )
    ).profiles[0]

    with pytest.raises(ValueError, match="must not carry"):
        KalorimetryDeployableProfileEntry(
            identifier="K1",
            model_version=2,
            model_key="weather",
            available=False,
            reason=PROFILE_INSUFFICIENT_HISTORY,
            profiles=(point,),
        )
