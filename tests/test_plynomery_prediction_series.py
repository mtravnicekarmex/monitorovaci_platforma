import datetime

import pandas as pd
import pytest

from moduly.mereni.plynomery.prediction_series import (
    build_plynomery_prediction_series,
)


def _profile(
    *,
    expected_mean=1.0,
    profile_kind="static",
    model_version=1,
    selection_run_id=1,
    valid_from=datetime.datetime(2026, 7, 27),
    valid_to=datetime.datetime(2026, 8, 3),
    base_mean=None,
    hdd_slope=None,
):
    return {
        "interval_minutes": 60,
        "day_of_week": 0,
        "slot": 8,
        "expected_mean": expected_mean,
        "model_version": model_version,
        "profile_kind": profile_kind,
        "selection_run_id": selection_run_id,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "base_mean": base_mean,
        "hdd_slope": hdd_slope,
    }


@pytest.mark.parametrize(
    ("granularity", "expected_date"),
    [
        ("hourly", pd.Timestamp("2026-07-27 08:00:00")),
        ("daily", pd.Timestamp("2026-07-27 00:00:00")),
        ("monthly", pd.Timestamp("2026-07-31 00:00:00")),
    ],
)
def test_build_prediction_supports_dashboard_granularities(
    granularity,
    expected_date,
):
    result = build_plynomery_prediction_series(
        pd.DataFrame([_profile(expected_mean=1.25)]),
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        granularity=granularity,
    )

    assert result["date"].tolist() == [expected_date]
    assert result["ocekavana_spotreba"].tolist() == [1.25]
    assert result["ocekavana_kumulovana_spotreba"].tolist() == [1.25]


def test_build_prediction_resolves_overlap_by_latest_period_then_run():
    profiles = pd.DataFrame(
        [
            _profile(
                expected_mean=99.0,
                valid_from=datetime.datetime(2026, 7, 20),
                valid_to=datetime.datetime(2026, 7, 28),
                selection_run_id=50,
            ),
            _profile(expected_mean=2.0, selection_run_id=20),
            _profile(expected_mean=3.0, selection_run_id=21),
        ]
    )

    result = build_plynomery_prediction_series(
        profiles,
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        granularity="hourly",
    )

    assert result["ocekavana_spotreba"].tolist() == [3.0]
    assert result["model_versions"].tolist() == [(1,)]


def test_negative_expected_consumption_is_clamped_before_cumulative_sum():
    profiles = pd.DataFrame(
        [
            _profile(expected_mean=-0.25),
            {**_profile(expected_mean=0.4), "slot": 9},
        ]
    )

    result = build_plynomery_prediction_series(
        profiles,
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        granularity="hourly",
    )

    assert result["ocekavana_spotreba"].tolist() == [0.0, 0.4]
    assert result["ocekavana_kumulovana_spotreba"].tolist() == [0.0, 0.4]
    assert result["ocekavana_kumulovana_spotreba"].is_monotonic_increasing


def test_build_prediction_uses_weather_adjusted_value():
    profile = _profile(
        expected_mean=3.0,
        profile_kind="weather_adjusted",
        model_version=2,
        base_mean=1.0,
        hdd_slope=0.5,
    )
    weather = pd.DataFrame(
        {
            "datetime_hour": pd.date_range(
                "2026-07-26 07:00:00",
                periods=24,
                freq="h",
            ),
            "heating_degree_hours": [4.0] * 24,
        }
    )

    result = build_plynomery_prediction_series(
        pd.DataFrame([profile]),
        weather_df=weather,
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        granularity="hourly",
    )

    assert result["ocekavana_spotreba"].tolist() == [3.0]
    assert result["profile_kinds"].tolist() == [("weather_adjusted",)]


def test_weather_profile_without_hdd_is_intentionally_absent():
    result = build_plynomery_prediction_series(
        pd.DataFrame(
            [
                _profile(
                    profile_kind="weather_adjusted",
                    model_version=2,
                    base_mean=1.0,
                    hdd_slope=0.5,
                )
            ]
        ),
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        granularity="hourly",
    )

    assert result.empty


def test_partial_weather_marks_aggregate_incomplete():
    profiles = pd.DataFrame(
        [
            _profile(
                profile_kind="weather_adjusted",
                model_version=2,
                base_mean=1.0,
                hdd_slope=0.5,
            ),
            {
                **_profile(
                    profile_kind="weather_adjusted",
                    model_version=2,
                    base_mean=1.0,
                    hdd_slope=0.5,
                ),
                "slot": 9,
            },
        ]
    )
    weather = pd.DataFrame(
        {
            "datetime_hour": [datetime.datetime(2026, 7, 27, 6)],
            "hdd_24h": [4.0],
        }
    )

    result = build_plynomery_prediction_series(
        profiles,
        weather_df=weather,
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        granularity="daily",
    )

    assert result["ocekavana_spotreba"].tolist() == [3.0]
    assert result["interval_count"].tolist() == [1]
    assert result["candidate_interval_count"].tolist() == [2]
    assert result["prediction_complete"].tolist() == [False]


def test_daily_prediction_can_combine_baseline_and_weather_profiles():
    profiles = pd.DataFrame(
        [
            _profile(expected_mean=2.0, model_version=1),
            {
                **_profile(
                    profile_kind="weather_adjusted",
                    model_version=2,
                    base_mean=1.0,
                    hdd_slope=0.5,
                ),
                "slot": 9,
            },
        ]
    )
    weather = pd.DataFrame(
        {
            "datetime_hour": [
                datetime.datetime(2026, 7, 27, 7),
            ],
            "hdd_24h": [4.0],
        }
    )

    result = build_plynomery_prediction_series(
        profiles,
        weather_df=weather,
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        granularity="daily",
    )

    assert result["ocekavana_spotreba"].tolist() == [5.0]
    assert result["interval_count"].tolist() == [2]
    assert result["candidate_interval_count"].tolist() == [2]
    assert result["prediction_complete"].tolist() == [True]
    assert result["model_versions"].tolist() == [(1, 2)]
    assert result["profile_kinds"].tolist() == [
        ("static", "weather_adjusted")
    ]


def test_build_prediction_rejects_invalid_inputs():
    profiles = pd.DataFrame([_profile()])

    with pytest.raises(ValueError, match="granularity"):
        build_plynomery_prediction_series(
            profiles,
            start_date=datetime.date(2026, 7, 27),
            end_date=datetime.date(2026, 7, 27),
            granularity="weekly",
        )
    with pytest.raises(ValueError, match="start_date"):
        build_plynomery_prediction_series(
            profiles,
            start_date=datetime.date(2026, 7, 28),
            end_date=datetime.date(2026, 7, 27),
            granularity="daily",
        )
