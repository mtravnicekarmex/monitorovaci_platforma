import datetime

import pandas as pd

from moduly.apps.dashboard.nabijecky_shared import build_daily_summary, prepare_charge_sessions
from moduly.apps.dashboard.time_semantics import add_chart_time, local_date_range_to_utc, time_axis_column


def test_local_date_range_to_utc_preserves_prague_dst_day_length():
    start_utc, end_utc = local_date_range_to_utc(datetime.date(2026, 3, 29), datetime.date(2026, 3, 29))

    assert start_utc == datetime.datetime(2026, 3, 28, 23, 0, tzinfo=datetime.UTC)
    assert end_utc == datetime.datetime(2026, 3, 29, 22, 0, tzinfo=datetime.UTC)


def test_add_chart_time_prefers_canonical_utc_and_falls_back_to_legacy_date():
    df = pd.DataFrame(
        [
            {"time_utc": "2026-07-01T00:00:00Z", "date": "2026-07-01T01:00:00"},
            {"time_utc": None, "date": "2026-07-02T03:00:00"},
        ]
    )

    prepared = add_chart_time(df)

    assert time_axis_column(prepared) == "chart_time"
    assert prepared["chart_time"].tolist() == [
        pd.Timestamp("2026-07-01T02:00:00"),
        pd.Timestamp("2026-07-02T03:00:00"),
    ]


def test_charge_sessions_group_by_local_day_from_utc_endpoints():
    prepared = prepare_charge_sessions(
        pd.DataFrame(
            [
                {
                    "id_relace": "rel-local-next-day",
                    "kwh": 2,
                    "suma": 20,
                    "started_at": "2026-05-01T22:30:00",
                    "ended_at": "2026-05-01T23:00:00",
                    "started_at_utc": "2026-05-01T22:30:00Z",
                    "ended_at_utc": "2026-05-01T23:00:00Z",
                },
                {
                    "id_relace": "rel-local-same-day",
                    "kwh": 3,
                    "suma": 30,
                    "started_at": "2026-05-01T20:00:00",
                    "ended_at": "2026-05-01T20:30:00",
                    "started_at_utc": "2026-05-01T20:00:00Z",
                    "ended_at_utc": "2026-05-01T20:30:00Z",
                },
            ]
        )
    )

    assert prepared["id_relace"].tolist() == ["rel-local-same-day", "rel-local-next-day"]
    assert prepared["started_chart_time"].tolist() == [
        pd.Timestamp("2026-05-01T22:00:00"),
        pd.Timestamp("2026-05-02T00:30:00"),
    ]

    daily_summary = build_daily_summary(prepared)

    assert daily_summary["date"].tolist() == [
        pd.Timestamp("2026-05-01T00:00:00"),
        pd.Timestamp("2026-05-02T00:00:00"),
    ]
    assert daily_summary["kwh"].tolist() == [3, 2]
