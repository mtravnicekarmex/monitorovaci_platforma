from __future__ import annotations

import datetime

import pandas as pd

from moduly.apps.dashboard import elektromery_shared


def test_prepare_measurements_uses_pg_delta_when_available():
    measurements = pd.DataFrame(
        [
            {
                "date": datetime.datetime(2026, 4, 29, 0, 15),
                "identifikace": "B-1.1",
                "seriove_cislo": 25722370615,
                "total": 100.0,
                "delta": None,
                "reset_detected": False,
            },
            {
                "date": datetime.datetime(2026, 4, 30, 0, 15),
                "identifikace": "B-1.1",
                "seriove_cislo": 25722370615,
                "total": 125.5,
                "delta": 25.5,
                "reset_detected": False,
            },
        ]
    )

    prepared = elektromery_shared.prepare_measurements(measurements)

    assert prepared["stav_celkem"].tolist() == [100.0, 125.5]
    assert prepared["spotreba"].tolist() == [0.0, 25.5]
    assert prepared["kumulovana_spotreba"].tolist() == [0.0, 25.5]


def test_prepare_measurements_keeps_ote_delta_only_rows():
    measurements = pd.DataFrame(
        [
            {
                "date": datetime.datetime(2026, 2, 1, 0, 15),
                "identifikace": "TS2",
                "seriove_cislo": 859182400409180513,
                "total": None,
                "delta": 1.25,
                "zdroj": "OTE",
                "reset_detected": False,
            },
            {
                "date": datetime.datetime(2026, 2, 1, 0, 30),
                "identifikace": "TS2",
                "seriove_cislo": 859182400409180513,
                "total": None,
                "delta": 2.0,
                "zdroj": "OTE",
                "reset_detected": False,
            },
        ]
    )

    prepared = elektromery_shared.prepare_measurements(measurements)

    assert len(prepared) == 2
    assert prepared["stav_celkem"].isna().all()
    assert prepared["spotreba"].tolist() == [1.25, 2.0]
    assert prepared["kumulovana_spotreba"].tolist() == [1.25, 3.25]
    assert elektromery_shared.build_change_table(prepared).empty


def test_delta_consumption_summary_is_used_for_ote_source():
    measurements = pd.DataFrame(
        [
            {
                "date": datetime.datetime(2026, 2, 1, 0, 15),
                "zdroj": "OTE",
                "spotreba": 1.25,
            },
            {
                "date": datetime.datetime(2026, 2, 1, 0, 30),
                "zdroj": "OTE",
                "spotreba": 2.0,
            },
        ]
    )

    summary = elektromery_shared.build_delta_consumption_summary(measurements)

    assert elektromery_shared.uses_ote_delta_source(measurements) is True
    assert summary.to_dict(orient="records") == [
        {
            "Zdroj": "OTE",
            "První měření": pd.Timestamp("2026-02-01 00:15:00"),
            "Poslední měření": pd.Timestamp("2026-02-01 00:30:00"),
            "Počet měření": 2,
            "Spotřeba z delta": 3.25,
        }
    ]
