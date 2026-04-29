import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.api.services import elektromery as service


def test_load_branch_period_overview_aggregates_midnight_state_differences(monkeypatch):
    period_start = datetime.datetime(2026, 4, 15, 0, 0, 0)
    period_end = datetime.datetime(2026, 4, 17, 0, 0, 0)

    def resolver(_timestamp):
        return ["A", "B"]

    monkeypatch.setattr(
        service,
        "BRANCH_DASHBOARD_CONFIGS",
        (
            service.BranchDashboardConfig(
                key="TEST_TS",
                title="Test TS",
                intervals=((period_start, period_end, ["A", "B"]),),
                membership_resolver=resolver,
            ),
        ),
    )

    rows = [
        {
            "date": datetime.datetime(2026, 4, 15, 0, 0, 0),
            "identifikace": "A",
            "seriove_cislo": 1,
            "vt": 60.0,
            "nt": 40.0,
            "total": 100.0,
        },
        {
            "date": datetime.datetime(2026, 4, 16, 0, 0, 0),
            "identifikace": "A",
            "seriove_cislo": 1,
            "vt": 60.5,
            "nt": 40.5,
            "total": 101.0,
        },
        {
            "date": datetime.datetime(2026, 4, 17, 0, 0, 0),
            "identifikace": "A",
            "seriove_cislo": 1,
            "vt": 62.0,
            "nt": 41.0,
            "total": 103.0,
        },
        {
            "date": datetime.datetime(2026, 4, 15, 0, 0, 0),
            "identifikace": "B",
            "seriove_cislo": 2,
            "vt": None,
            "nt": None,
            "total": 50.0,
        },
        {
            "date": datetime.datetime(2026, 4, 16, 0, 0, 0),
            "identifikace": "B",
            "seriove_cislo": 2,
            "vt": None,
            "nt": None,
            "total": 52.0,
        },
        {
            "date": datetime.datetime(2026, 4, 17, 0, 0, 0),
            "identifikace": "B",
            "seriove_cislo": 2,
            "vt": None,
            "nt": None,
            "total": 55.0,
        },
    ]

    def fake_load_measurement_rows(identifiers, *, lookback_start, period_end):
        assert identifiers == ("A", "B")
        assert lookback_start == datetime.datetime(2026, 4, 1, 0, 0, 0)
        assert period_end == datetime.datetime(2026, 4, 17, 0, 0, 0)
        return rows

    monkeypatch.setattr(service, "_load_measurement_rows", fake_load_measurement_rows)

    payloads = service.load_branch_period_overview(period_start=period_start, period_end=period_end)

    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["key"] == "TEST_TS"
    assert payload["title"] == "Test TS"
    assert payload["actual_total"] == 8.0
    assert payload["vt_total"] == 2.0
    assert payload["nt_total"] == 1.0
    assert payload["last_actual_timestamp"] == datetime.datetime(2026, 4, 17, 0, 0, 0)

    device_rows = {row["identifikace"]: row for row in payload["device_consumption_rows"]}
    assert device_rows["A"]["start_value"] == 100.0
    assert device_rows["A"]["end_value"] == 103.0
    assert device_rows["A"]["spotreba"] == 3.0
    assert device_rows["A"]["spotreba_vt"] == 2.0
    assert device_rows["A"]["spotreba_nt"] == 1.0
    assert device_rows["A"]["podil_procent"] == 37.5
    assert device_rows["A"]["active_days"] == 2
    assert device_rows["B"]["start_value"] == 50.0
    assert device_rows["B"]["end_value"] == 55.0
    assert device_rows["B"]["spotreba"] == 5.0
    assert device_rows["B"]["podil_procent"] == 62.5

    assert len(payload["daily_rows"]) == 2
    assert payload["daily_rows"][0]["actual_total"] == 3.0
    assert payload["daily_rows"][1]["actual_total"] == 5.0
