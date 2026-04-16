import datetime
import warnings

import pandas as pd

from services.api.services.vodomery import (
    BranchDashboardConfig,
    _build_branch_billing_payload,
    _prepare_branch_measurements,
    _serialize_dataframe_rows,
)


def test_serialize_dataframe_rows_converts_datetime_columns_without_future_warning():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-04-09 10:15:00", None]),
            "value": [1, 2],
        }
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", FutureWarning)
        rows = _serialize_dataframe_rows(frame)

    assert rows[0]["date"] == datetime.datetime(2026, 4, 9, 10, 15)
    assert isinstance(rows[0]["date"], datetime.datetime)
    assert rows[1]["date"] is None
    assert rows[0]["value"] == 1
    assert rows[1]["value"] == 2


def test_prepare_branch_measurements_zeroes_invalid_rows():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2026-04-10 10:00:00",
                    "2026-04-10 10:15:00",
                    "2026-04-10 10:30:00",
                ]
            ),
            "identifikace": ["A", "A", "A"],
            "objem": [100.0, 120.0, 100.6],
            "delta": [None, None, 0.6],
            "platne": [True, False, True],
            "reset_detected": [False, False, False],
        }
    )

    prepared = _prepare_branch_measurements(frame)

    assert prepared["spotreba"].tolist() == [0.0, 0.0, 0.6]


def test_build_branch_billing_payload_allocates_consumption_and_merges_assignments():
    period_start = datetime.datetime(2026, 4, 1, 0, 0, 0)
    midpoint = datetime.datetime(2026, 4, 15, 0, 0, 0)
    period_end = datetime.datetime(2026, 5, 1, 0, 0, 0)
    config = BranchDashboardConfig(
        key="TEST",
        title="Test větev",
        billing_ident="MAIN",
        daily_limit=None,
        intervals=(),
        membership_resolver=lambda _: [],
    )
    effective_segments = [
        (period_start, midpoint, ("A", "B")),
        (midpoint, period_end, ("A", "C")),
    ]
    snapshot_cache = {
        period_start: {"MAIN": 100.0, "A": 10.0, "B": 20.0, "C": 30.0},
        midpoint: {"MAIN": 120.0, "A": 15.0, "B": 24.0, "C": 30.0},
        period_end: {"MAIN": 150.0, "A": 25.0, "B": 24.0, "C": 45.0},
    }

    payload = _build_branch_billing_payload(
        config_item=config,
        start_date=datetime.date(2026, 4, 1),
        end_date=datetime.date(2026, 4, 30),
        period_start=period_start,
        period_end=period_end,
        effective_segments=effective_segments,
        snapshot_cache=snapshot_cache,
    )

    assert payload["billing_consumption"] == 50.0
    assert payload["submeter_consumption_total"] == 34.0
    assert payload["difference"] == 16.0
    assert payload["coverage_percent"] == 68.0

    assignment_rows = payload["assignment_rows"]
    assert len(assignment_rows) == 3
    row_a = next(row for row in assignment_rows if row["identifikace"] == "A")
    assert row_a["start_time"] == period_start
    assert row_a["end_time"] == datetime.datetime(2026, 4, 30, 23, 59, 59)

    device_rows = {row["identifikace"]: row for row in payload["device_rows"]}
    assert device_rows["A"]["spotreba"] == 15.0
    assert device_rows["A"]["active_segment_count"] == 2
    assert device_rows["A"]["segments_with_data_count"] == 2
    assert device_rows["A"]["segments_without_data_count"] == 0
    assert device_rows["A"]["rozpoctena_fakturacni_spotreba"] == 22.059
    assert device_rows["B"]["spotreba"] == 4.0
    assert device_rows["C"]["spotreba"] == 15.0
