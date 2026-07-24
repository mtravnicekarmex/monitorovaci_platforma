import datetime
import sys
import warnings
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.api.services.vodomery import (
    BranchDashboardConfig,
    _aggregate_hourly_branch_values,
    _build_branch_billing_payload,
    _load_archived_prediction_profiles,
    _prepare_branch_measurements,
    _serialize_dataframe_rows,
)


class _FakeMappingResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeArchiveSession:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = statement
        self.params = params
        return _FakeMappingResult(self.rows)


def test_load_archived_prediction_profiles_returns_overlapping_validity_metadata():
    period_start = datetime.datetime(2026, 1, 5)
    period_end = datetime.datetime(2026, 1, 12)
    base_row = {
        "forecast_period_start": period_start,
        "forecast_period_end": period_end,
        "archive_source": "historical_backfill",
        "archive_version": 1,
        "selection_run_id": 42,
        "model_version": 2,
        "model_key": "adaptive_strategy",
        "interval_minutes": 15,
        "day_of_week": 0,
        "slot": 8,
        "expected_mean": 1.25,
        "expected_median": 1.0,
        "expected_p10": None,
        "expected_p90": 2.0,
        "expected_std": 0.5,
        "sample_size": 10,
        "created_at": datetime.datetime(2026, 7, 1),
        "id": 2,
    }
    older_duplicate = {
        **base_row,
        "archive_version": 0,
        "expected_mean": 99.0,
        "created_at": datetime.datetime(2026, 6, 1),
        "id": 1,
    }
    session = _FakeArchiveSession([base_row, older_duplicate])

    rows = _load_archived_prediction_profiles(
        session,
        identifikace="L1_V1",
        start_date=datetime.date(2026, 1, 6),
        end_date=datetime.date(2026, 1, 7),
    )

    assert session.params == {
        "identifikace": "L1_V1",
        "range_start": datetime.datetime(2026, 1, 6),
        "range_end": datetime.datetime(2026, 1, 8),
    }
    assert "forecast_period_start <" in str(session.statement)
    assert len(rows) == 1
    assert rows[0] == {
        "interval_minutes": 15,
        "day_of_week": 0,
        "slot": 8,
        "expected_mean": 1.25,
        "expected_median": 1.0,
        "expected_p10": None,
        "expected_p90": 2.0,
        "expected_std": 0.5,
        "sample_size": 10,
        "model_version": 2,
        "model_key": "adaptive_strategy",
        "valid_from": period_start,
        "valid_to": period_end,
        "archive_source": "historical_backfill",
        "selection_run_id": 42,
    }


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


def test_aggregate_hourly_branch_values_rounds_numeric_column_without_datetime_warning():
    frame = pd.DataFrame(
        {
            "identifikace": ["A", "A", "B"],
            "hour_bucket": pd.to_datetime(
                [
                    "2026-04-10 10:00:00",
                    "2026-04-10 10:00:00",
                    "2026-04-10 11:00:00",
                ]
            ),
            "spotreba": [0.3333, 0.3333, 1.6666],
        }
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        hourly = _aggregate_hourly_branch_values(frame, value_column="spotreba")

    assert hourly.to_dict(orient="records") == [
        {
            "identifikace": "A",
            "hour_bucket": pd.Timestamp("2026-04-10 10:00:00"),
            "spotreba": 0.667,
        },
        {
            "identifikace": "B",
            "hour_bucket": pd.Timestamp("2026-04-10 11:00:00"),
            "spotreba": 1.667,
        },
    ]


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
    assert payload["segment_rows"][0]["device_consumptions"] == [
        {"identifikace": "A", "spotreba": 5.0},
        {"identifikace": "B", "spotreba": 4.0},
    ]
    assert payload["segment_rows"][1]["device_consumptions"] == [
        {"identifikace": "A", "spotreba": 10.0},
        {"identifikace": "C", "spotreba": 15.0},
    ]

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
