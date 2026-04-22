import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.overview_shared import build_vodomery_alarm_payload


def test_build_vodomery_alarm_payload_sorts_and_limits_visible_rows():
    events_df = pd.DataFrame(
        [
            {
                "identifikace": "VDM-02",
                "event_type": "SPIKE",
                "start_time": "2026-04-22T07:00:00",
                "duration_minutes": 260,
                "max_z_score": 4.1,
                "severity": "HIGH",
            },
            {
                "identifikace": "VDM-01",
                "event_type": "ZERO_FLOW",
                "start_time": "2026-04-22T06:00:00",
                "duration_minutes": 180,
                "max_z_score": 9.3,
                "severity": "CRITICAL",
            },
            {
                "identifikace": "VDM-03",
                "event_type": "NIGHT_USAGE",
                "start_time": "2026-04-22T03:00:00",
                "duration_minutes": 120,
                "max_z_score": 3.2,
                "severity": "MEDIUM",
            },
        ]
    )

    payload = build_vodomery_alarm_payload(events_df, limit=2)

    assert payload["total_open_events"] == 3
    assert payload["affected_devices"] == 3
    assert payload["critical_count"] == 1
    assert payload["high_count"] == 1
    assert payload["medium_count"] == 1
    assert payload["hidden_event_count"] == 1
    assert [row["identifikace"] for row in payload["open_event_rows"]] == ["VDM-01", "VDM-02"]
    assert payload["open_event_rows"][0]["event_type_label"] == "Bez průtoku"
    assert payload["open_event_rows"][1]["event_type_label"] == "Špička"


def test_build_vodomery_alarm_payload_returns_empty_state_for_empty_dataframe():
    payload = build_vodomery_alarm_payload(pd.DataFrame())

    assert payload == {
        "total_open_events": 0,
        "affected_devices": 0,
        "critical_count": 0,
        "high_count": 0,
        "medium_count": 0,
        "hidden_event_count": 0,
        "open_event_rows": [],
    }
