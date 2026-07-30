import datetime
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.vodomery_shared import (
    align_latest_hour_timestamp,
    apply_prediction_profiles,
    build_period_prediction,
    select_prediction_profiles_for_range,
)
from moduly.apps.dashboard import vodomery_shared


VODOMERY_OVERVIEW_PAGE = (
    Path(__file__).resolve().parents[1]
    / "moduly"
    / "apps"
    / "dashboard"
    / "pages"
    / "2_vodomery.py"
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


def test_load_prediction_profiles_preserves_unavailable_metadata(monkeypatch):
    monkeypatch.setattr(
        vodomery_shared,
        "require_dashboard_api_token",
        lambda: "token",
    )
    monkeypatch.setattr(
        vodomery_shared,
        "api_get_vodomery_prediction_profiles",
        lambda *args, **kwargs: {
            "prediction_available": False,
            "availability_status": "unavailable",
            "availability_reason": "insufficient_history",
            "rows": [],
        },
    )

    frame = vodomery_shared.load_prediction_profiles.__wrapped__(
        "NEW_V1",
        ("NEW_V1",),
        False,
        datetime.date(2026, 7, 27),
        datetime.date(2026, 8, 2),
    )

    assert frame.empty
    assert frame.attrs == {
        "prediction_available": False,
        "availability_status": "unavailable",
        "availability_reason": "insufficient_history",
    }


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


def test_build_period_prediction_covers_complete_selected_week():
    period_start = datetime.datetime(2026, 7, 27)
    period_end = datetime.datetime(2026, 8, 3)
    profiles = pd.DataFrame(
        [
            {
                "interval_minutes": 720,
                "day_of_week": day_of_week,
                "slot": slot,
                "expected_mean": float(day_of_week + 1),
                "valid_from": period_start,
                "valid_to": period_end,
            }
            for day_of_week in range(7)
            for slot in (0, 1)
        ]
    )

    prediction = build_period_prediction(
        profiles,
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 8, 2),
        frequency="D",
    )

    assert prediction["date"].dt.date.tolist() == [
        datetime.date(2026, 7, 27) + datetime.timedelta(days=offset)
        for offset in range(7)
    ]
    assert prediction["ocekavana_spotreba"].tolist() == [
        2.0,
        4.0,
        6.0,
        8.0,
        10.0,
        12.0,
        14.0,
    ]
    assert prediction["ocekavana_kumulovana_spotreba"].tolist() == [
        2.0,
        6.0,
        12.0,
        20.0,
        30.0,
        42.0,
        56.0,
    ]


def test_build_period_prediction_resolves_overlapping_period_to_latest_start():
    profiles = pd.DataFrame(
        [
            {
                "interval_minutes": 60,
                "day_of_week": 0,
                "slot": 8,
                "expected_mean": 99.0,
                "valid_from": datetime.datetime(2026, 7, 20, 4, 10),
                "valid_to": datetime.datetime(2026, 7, 27, 9, 0),
            },
            {
                "interval_minutes": 60,
                "day_of_week": 0,
                "slot": 8,
                "expected_mean": 1.5,
                "valid_from": datetime.datetime(2026, 7, 27),
                "valid_to": datetime.datetime(2026, 8, 3),
            },
        ]
    )

    prediction = build_period_prediction(
        profiles,
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        frequency="h",
    )

    assert prediction[["date", "ocekavana_spotreba"]].to_dict(
        orient="records"
    ) == [
        {
            "date": pd.Timestamp("2026-07-27 08:00:00"),
            "ocekavana_spotreba": 1.5,
        }
    ]


def test_complete_current_snapshot_excludes_older_partial_overlap():
    profiles = pd.DataFrame(
        [
            {
                "interval_minutes": 60,
                "day_of_week": 0,
                "slot": 0,
                "expected_mean": 99.0,
                "valid_from": datetime.datetime(2026, 7, 20, 4, 10),
                "valid_to": datetime.datetime(2026, 7, 27, 4, 10),
            },
            {
                "interval_minutes": 60,
                "day_of_week": 0,
                "slot": 0,
                "expected_mean": 1.5,
                "valid_from": datetime.datetime(2026, 7, 27),
                "valid_to": datetime.datetime(2026, 8, 3),
            },
        ]
    )

    selected = select_prediction_profiles_for_range(
        profiles,
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 8, 2),
    )

    assert len(selected) == 1
    assert selected.iloc[0]["expected_mean"] == 1.5
    assert selected.iloc[0]["valid_from"] == pd.Timestamp("2026-07-27 00:00:00")


def test_complete_snapshot_selection_accepts_mixed_api_datetime_precision():
    profiles = pd.DataFrame(
        [
            {
                "interval_minutes": 60,
                "day_of_week": 0,
                "slot": 0,
                "expected_mean": 99.0,
                "valid_from": "2026-07-20T04:10:05.081179",
                "valid_to": "2026-07-27T04:10:05.081179",
            },
            {
                "interval_minutes": 60,
                "day_of_week": 0,
                "slot": 0,
                "expected_mean": 1.5,
                "valid_from": "2026-07-27T00:00:00",
                "valid_to": "2026-08-03T00:00:00",
            },
        ]
    )

    selected = select_prediction_profiles_for_range(
        profiles,
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 8, 2),
    )

    assert len(selected) == 1
    assert selected.iloc[0]["expected_mean"] == 1.5
    assert selected.iloc[0]["valid_from"] == pd.Timestamp("2026-07-27 00:00:00")


def test_overview_uses_complete_period_prediction_as_separate_series():
    source = VODOMERY_OVERVIEW_PAGE.read_text(encoding="utf-8")

    assert "prediction_df = build_period_prediction(" in source
    assert "measurements_df = apply_prediction_layer(" not in source
    assert "render_graph_legend(not prediction_df.empty)" in source


def test_overview_detail_table_matches_plynomery_user_columns():
    source = VODOMERY_OVERVIEW_PAGE.read_text(encoding="utf-8")

    for label in (
        '"Vodoměr"',
        '"Sériové číslo"',
        '"Objem"',
        '"Spotřeba"',
        '"Kumulovaná spotřeba"',
        '"Platná data"',
        '"Počet resetů"',
    ):
        assert label in source
    assert '"Ocekavana spotreba"' not in source
    assert '"Synteticka data"' not in source
    assert 'st.subheader("Data")' in source
