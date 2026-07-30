import datetime

import pandas as pd
import pytest

from moduly.mereni.kalorimetry.prediction_series import (
    build_kalorimetry_prediction_series,
)


def _profile_rows(day: datetime.date, values=(1.0, 2.0)):
    return pd.DataFrame(
        [
            {
                "interval_minutes": 15,
                "day_of_week": day.weekday(),
                "slot": slot,
                "expected_mean": value,
                "model_version": 1,
                "profile_kind": "static",
                "selection_run_id": None,
                "valid_from": datetime.datetime.combine(day, datetime.time()),
                "valid_to": datetime.datetime.combine(
                    day + datetime.timedelta(days=7), datetime.time()
                ),
            }
            for slot, value in enumerate(values)
        ]
    )


def test_builds_hourly_and_continuous_cumulative_series():
    monday = datetime.date(2026, 7, 27)
    profiles = pd.concat(
        [_profile_rows(monday), _profile_rows(monday + datetime.timedelta(days=7))],
        ignore_index=True,
    )
    result = build_kalorimetry_prediction_series(
        profiles,
        start_date=monday,
        end_date=monday + datetime.timedelta(days=7),
        granularity="hourly",
    )
    assert result["ocekavana_spotreba"].tolist() == [3.0, 3.0]
    assert result["ocekavana_kumulovana_spotreba"].tolist() == [3.0, 6.0]
    assert result["model_versions"].tolist() == [(1,), (1,)]


def test_negative_expected_values_are_clamped_to_zero():
    day = datetime.date(2026, 7, 27)
    result = build_kalorimetry_prediction_series(
        _profile_rows(day, values=(-2.0, 1.0)),
        start_date=day,
        end_date=day,
        granularity="daily",
    )
    assert result.iloc[0]["ocekavana_spotreba"] == 1.0


def test_rejects_invalid_range_and_granularity():
    day = datetime.date(2026, 7, 27)
    with pytest.raises(ValueError, match="start_date"):
        build_kalorimetry_prediction_series(
            pd.DataFrame(),
            start_date=day,
            end_date=day - datetime.timedelta(days=1),
            granularity="daily",
        )
    with pytest.raises(ValueError, match="granularity"):
        build_kalorimetry_prediction_series(
            pd.DataFrame(),
            start_date=day,
            end_date=day,
            granularity="weekly",
        )
