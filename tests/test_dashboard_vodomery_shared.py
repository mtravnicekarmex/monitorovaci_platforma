import datetime
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.vodomery_shared import (
    align_latest_hour_timestamp,
    apply_prediction_profiles,
)


def test_align_latest_hour_timestamp_moves_only_current_hour_rows():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2026-06-09 05:00:00",
                    "2026-06-09 06:00:00",
                    "2026-06-09 07:00:00",
                ]
            ),
            "value": [1.0, 2.0, 3.0],
        }
    )

    aligned = align_latest_hour_timestamp(
        frame,
        datetime.datetime(2026, 6, 9, 6, 45, 49),
    )

    assert aligned["date"].tolist() == [
        pd.Timestamp("2026-06-09 05:00:00"),
        pd.Timestamp("2026-06-09 06:45:49"),
        pd.Timestamp("2026-06-09 07:00:00"),
    ]
    assert frame["date"].iloc[1] == pd.Timestamp("2026-06-09 06:00:00")


def test_apply_prediction_profiles_uses_profile_valid_for_each_week():
    measurements = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2026-01-05 02:00:00",
                    "2026-01-12 02:00:00",
                    "2026-01-19 02:00:00",
                ]
            ),
            "interval_minutes": [15, 15, 15],
            "day_of_week": [0, 0, 0],
            "slot": [8, 8, 8],
        }
    )
    profiles = pd.DataFrame(
        {
            "interval_minutes": [15, 15],
            "day_of_week": [0, 0],
            "slot": [8, 8],
            "expected_mean": [1.0, 2.0],
            "model_version": [1, 2],
            "valid_from": pd.to_datetime(["2026-01-05", "2026-01-12"]),
            "valid_to": pd.to_datetime(["2026-01-12", "2026-01-19"]),
        }
    )

    result = apply_prediction_profiles(measurements, profiles)

    assert result["ocekavana_spotreba"].tolist()[:2] == [1.0, 2.0]
    assert pd.isna(result["ocekavana_spotreba"].iloc[2])
    assert result["model_version"].tolist()[:2] == [1.0, 2.0]
    assert pd.isna(result["model_version"].iloc[2])
    assert pd.isna(result["ocekavana_kumulovana_spotreba"].iloc[2])


def test_apply_prediction_profiles_preserves_current_profile_compatibility():
    measurements = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-05 02:00:00"]),
            "interval_minutes": [15],
            "day_of_week": [0],
            "slot": [8],
        }
    )
    profiles = pd.DataFrame(
        {
            "interval_minutes": [15],
            "day_of_week": [0],
            "slot": [8],
            "expected_mean": [1.5],
            "model_version": [3],
        }
    )

    result = apply_prediction_profiles(measurements, profiles)

    assert result["ocekavana_spotreba"].tolist() == [1.5]
    assert result["model_version"].tolist() == [3]
