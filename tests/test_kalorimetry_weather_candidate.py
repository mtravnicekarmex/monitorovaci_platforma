from __future__ import annotations

import datetime

import pytest

from moduly.mereni.kalorimetry.calendar_baseline import (
    KALORIMETRY_BASELINE_PROFILE_POINTS,
)
from moduly.mereni.kalorimetry.weather_candidate import (
    KALORIMETRY_WEATHER_MODEL_KEY,
    KalorimetryWeatherCandidate,
    build_kalorimetry_weather_deploy_profiles,
    build_kalorimetry_weather_profile_catalog,
    weather_profile_point_to_row,
)
from moduly.mereni.prediction import (
    CandidateProfileBuildResult,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionObservation,
    PredictionRebuildWindows,
    PredictionTimeWindow,
)


def weather_observation(
    identifier: str,
    *,
    day_of_week: int,
    slot: int,
    actual: float,
    hdd_24h: float | None,
) -> PredictionObservation:
    return PredictionObservation(
        identifier=identifier,
        timestamp=datetime.datetime(2026, 1, 5)
        + datetime.timedelta(days=day_of_week, minutes=slot * 15),
        actual_value=actual,
        interval_minutes=15,
        day_of_week=day_of_week,
        slot=slot,
        features={"hdd_24h": hdd_24h},
    )


def complete_weather_observations(
    identifier: str,
    *,
    samples_per_slot: int = 8,
) -> tuple[PredictionObservation, ...]:
    return tuple(
        weather_observation(
            identifier,
            day_of_week=day_of_week,
            slot=slot,
            hdd_24h=float(sample),
            actual=1.0 + 0.5 * sample,
        )
        for day_of_week in range(7)
        for slot in range(96)
        for sample in range(samples_per_slot)
    )


def forecast_period() -> PredictionForecastPeriod:
    return PredictionForecastPeriod(
        start=datetime.datetime(2026, 7, 27),
        end=datetime.datetime(2026, 8, 3),
        cadence=PredictionForecastCadence.WEEKLY,
    )


def complete_hdd_forecast(value: float = 4.0) -> dict[datetime.datetime, float]:
    start_utc = datetime.datetime(2026, 7, 26, 22)
    return {
        start_utc + datetime.timedelta(hours=offset): value
        for offset in range(168)
    }


def test_weather_candidate_fits_complete_non_negative_hdd_profile():
    catalog = build_kalorimetry_weather_profile_catalog(
        complete_weather_observations("KAL-01"),
    )

    assert catalog.eligible_identifiers == ("KAL-01",)
    assert catalog.insufficient_history_identifiers == ()
    assert len(catalog.profiles) == KALORIMETRY_BASELINE_PROFILE_POINTS
    point = catalog.profiles[0]
    assert point.expected_mean == pytest.approx(2.75)
    assert point.features["hdd_slope"] == pytest.approx(0.5)
    assert point.features["base_mean"] == pytest.approx(1.0)
    assert point.features["hdd_24h_mean"] == pytest.approx(3.5)
    assert point.features["profile_kind"] == "weather_adjusted"


def test_weather_candidate_spec_is_selection_eligible_model_two():
    candidate = KalorimetryWeatherCandidate()

    assert candidate.spec.medium_key == "kalorimetry"
    assert candidate.spec.model_version == 2
    assert candidate.spec.model_key == KALORIMETRY_WEATHER_MODEL_KEY
    assert candidate.spec.training_window_months == 12
    assert candidate.spec.selection_enabled is True


def test_weather_candidate_build_profiles_uses_weather_adapter_contract():
    rows = complete_weather_observations("KAL-01")
    windows = PredictionRebuildWindows(
        train=PredictionTimeWindow(
            start=datetime.datetime(2025, 6, 1),
            end=datetime.datetime(2026, 6, 1),
        ),
        validation=PredictionTimeWindow(
            start=datetime.datetime(2026, 6, 1),
            end=datetime.datetime(2026, 7, 1),
        ),
        deploy=PredictionTimeWindow(
            start=datetime.datetime(2026, 7, 27),
            end=datetime.datetime(2026, 8, 3),
        ),
    )
    calls = []

    class FakeAdapter:
        def load_weather_observations(self, window):
            calls.append(("load", window))
            return rows

        def replace_weather_profiles(self, *, model_version, profiles):
            resolved = tuple(profiles)
            calls.append(("replace", model_version, len(resolved)))
            return CandidateProfileBuildResult(
                model_version=model_version,
                profile_count=len(resolved),
            )

    candidate = KalorimetryWeatherCandidate(
        bootstrap_fn=lambda: calls.append(("bootstrap",)),
    )

    result = candidate.build_profiles(FakeAdapter(), windows)

    assert calls == [
        ("bootstrap",),
        ("load", windows.train),
        ("replace", 2, KALORIMETRY_BASELINE_PROFILE_POINTS),
    ]
    assert result.profile_count == KALORIMETRY_BASELINE_PROFILE_POINTS
    assert result.metadata["eligible_identifier_count"] == 1


def test_missing_hdd_or_slot_history_publishes_no_partial_identifier_profile():
    rows = list(complete_weather_observations("KAL-01"))
    rows = [
        row
        for row in rows
        if not (row.day_of_week == 6 and row.slot == 95)
    ]
    rows.append(
        weather_observation(
            "KAL-01",
            day_of_week=6,
            slot=95,
            actual=1.0,
            hdd_24h=None,
        )
    )

    catalog = build_kalorimetry_weather_profile_catalog(rows)

    assert catalog.profiles == ()
    assert catalog.eligible_identifiers == ()
    assert catalog.insufficient_history_identifiers == ("KAL-01",)


def test_flat_hdd_uses_zero_slope_instead_of_inventing_weather_response():
    rows = tuple(
        weather_observation(
            "KAL-01",
            day_of_week=day,
            slot=slot,
            actual=float(sample),
            hdd_24h=2.0,
        )
        for day in range(7)
        for slot in range(96)
        for sample in range(8)
    )

    catalog = build_kalorimetry_weather_profile_catalog(rows)

    assert catalog.profiles[0].features["hdd_slope"] == 0.0


def test_complete_forecast_builds_672_deploy_points_per_identifier():
    catalog = build_kalorimetry_weather_profile_catalog(
        complete_weather_observations("KAL-01"),
    )

    result = build_kalorimetry_weather_deploy_profiles(
        catalog.profiles,
        forecast_period=forecast_period(),
        hdd_24h_by_utc_hour=complete_hdd_forecast(4.0),
    )

    assert result.available is True
    assert result.reason is None
    assert result.missing_weather_hours == ()
    assert len(result.profiles) == KALORIMETRY_BASELINE_PROFILE_POINTS
    assert result.profiles[0].expected_mean == pytest.approx(3.0)
    assert result.profiles[0].features["deploy_hdd_24h"] == 4.0


def test_any_missing_forecast_hour_makes_whole_deploy_profile_unavailable():
    catalog = build_kalorimetry_weather_profile_catalog(
        complete_weather_observations("KAL-01"),
    )
    weather = complete_hdd_forecast()
    missing_hour = sorted(weather)[50]
    del weather[missing_hour]

    result = build_kalorimetry_weather_deploy_profiles(
        catalog.profiles,
        forecast_period=forecast_period(),
        hdd_24h_by_utc_hour=weather,
    )

    assert result.available is False
    assert result.profiles == ()
    assert result.reason == "missing_forecast_weather"
    assert result.missing_weather_hours == (missing_hour,)


def test_incomplete_source_profile_fails_before_weather_application():
    catalog = build_kalorimetry_weather_profile_catalog(
        complete_weather_observations("KAL-01"),
    )

    result = build_kalorimetry_weather_deploy_profiles(
        catalog.profiles[:-1],
        forecast_period=forecast_period(),
        hdd_24h_by_utc_hour=complete_hdd_forecast(),
    )

    assert result.available is False
    assert result.profiles == ()
    assert result.reason == "incomplete_weather_profile"


def test_weather_profile_row_preserves_fit_metadata():
    catalog = build_kalorimetry_weather_profile_catalog(
        complete_weather_observations("KAL-01"),
    )

    row = weather_profile_point_to_row(catalog.profiles[0])

    assert row["identifikace"] == "KAL-01"
    assert row["model_version"] == 2
    assert row["hdd_slope"] == pytest.approx(0.5)
    assert row["base_mean"] == pytest.approx(1.0)
    assert row["sample_size"] == 8


@pytest.mark.parametrize(
    ("minimum_slot_samples", "minimum_hdd_variance", "message"),
    [
        (0, 0.0001, "sample count"),
        (8, -1.0, "variance"),
    ],
)
def test_weather_fit_thresholds_are_validated(
    minimum_slot_samples,
    minimum_hdd_variance,
    message,
):
    with pytest.raises(ValueError, match=message):
        build_kalorimetry_weather_profile_catalog(
            (),
            minimum_slot_samples=minimum_slot_samples,
            minimum_hdd_variance=minimum_hdd_variance,
        )
