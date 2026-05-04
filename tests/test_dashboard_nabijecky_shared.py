import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.nabijecky_shared import (
    build_daily_summary,
    prepare_charge_sessions,
    summarize_charge_sessions,
)


def test_prepare_charge_sessions_coerces_types_and_computes_duration():
    raw_df = pd.DataFrame(
        [
            {
                "id_relace": "rel-002",
                "kwh": "8.125",
                "tarif": "ARMEX HOLDING 15Kč + 20,00%",
                "battery_status": "85",
                "suma": "121.25",
                "started_at": "2026-05-02T09:15:00",
                "ended_at": "2026-05-02T09:45:00",
                "lokace": "Budova E",
                "rychlost_nabijeni": "16.250",
                "imported_at": "2026-05-04T07:00:00",
            },
            {
                "id_relace": "rel-001",
                "kwh": "12.500",
                "tarif": "ARMEX HOLDING 15Kč + 20,00%",
                "battery_status": "70",
                "suma": "187.50",
                "started_at": "2026-05-01T16:30:00",
                "ended_at": "2026-05-01T17:00:00",
                "lokace": "Budova E",
                "rychlost_nabijeni": "25.000",
                "imported_at": "2026-05-04T07:00:00",
            },
        ]
    )

    prepared = prepare_charge_sessions(raw_df)

    assert list(prepared["id_relace"]) == ["rel-001", "rel-002"]
    assert prepared["kwh"].tolist() == [12.5, 8.125]
    assert prepared["battery_status"].tolist() == [70, 85]
    assert prepared["duration_minutes"].tolist() == [30.0, 30.0]


def test_build_daily_summary_and_summary_metrics_aggregate_sessions():
    prepared_df = prepare_charge_sessions(
        pd.DataFrame(
            [
                {
                    "id_relace": "rel-001",
                    "kwh": 12.5,
                    "tarif": "A",
                    "battery_status": 70,
                    "suma": 187.5,
                    "started_at": "2026-05-01T16:30:00",
                    "ended_at": "2026-05-01T17:00:00",
                    "lokace": "Budova E",
                    "rychlost_nabijeni": 25.0,
                    "imported_at": "2026-05-04T07:00:00",
                },
                {
                    "id_relace": "rel-002",
                    "kwh": 8.125,
                    "tarif": "A",
                    "battery_status": 85,
                    "suma": 121.25,
                    "started_at": "2026-05-02T09:15:00",
                    "ended_at": "2026-05-02T09:45:00",
                    "lokace": "Budova E",
                    "rychlost_nabijeni": 16.25,
                    "imported_at": "2026-05-04T07:00:00",
                },
                {
                    "id_relace": "rel-003",
                    "kwh": 4.375,
                    "tarif": "B",
                    "battery_status": 90,
                    "suma": 65.5,
                    "started_at": "2026-05-02T15:00:00",
                    "ended_at": "2026-05-02T15:20:00",
                    "lokace": "Budova F",
                    "rychlost_nabijeni": 13.125,
                    "imported_at": "2026-05-04T07:00:00",
                },
            ]
        )
    )

    daily_summary = build_daily_summary(prepared_df)
    summary = summarize_charge_sessions(prepared_df)

    assert daily_summary["session_count"].tolist() == [1, 2]
    assert daily_summary["kwh"].tolist() == [12.5, 12.5]
    assert daily_summary["suma"].tolist() == [187.5, 186.75]
    assert summary == {
        "session_count": 3,
        "total_kwh": 25.0,
        "total_suma": 374.25,
        "average_speed": 18.125,
    }
