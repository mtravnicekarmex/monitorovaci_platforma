import datetime
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.api.services.vodomery import (
    BranchDashboardConfig,
    _aggregate_hourly_branch_values,
    _build_branch_billing_payload,
    _load_archived_prediction_profiles,
    _load_branch_archived_prediction_rows,
    _load_branch_unavailable_prediction_identifiers,
    _load_current_prediction_profiles,
    _prepare_branch_measurements,
    _serialize_dataframe_rows,
)
from services.api.services import vodomery as vodomery_service


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


class _FakeRowResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.params = None

    def execute(self, statement, params):
        self.statement = statement
        self.params = params
        return _FakeRowResult(self.rows)


class _FakeBranchOverviewConnection:
    def __init__(self, *, measurement_rows=(), prediction_rows=(), decision_rows=()):
        self.measurement_rows = list(measurement_rows)
        self.prediction_rows = list(prediction_rows)
        self.decision_rows = list(decision_rows)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if 'monitoring."Mereni_vodomery_vse"' in sql:
            return _FakeRowResult(self.measurement_rows)
        if "monitoring.prediction_profile_snapshots" in sql:
            return _FakeRowResult(self.prediction_rows)
        if "monitoring.prediction_selected_model_snapshots" in sql:
            return _FakeRowResult(self.decision_rows)
        raise AssertionError(f"Unexpected SQL in branch overview test: {sql}")


class _FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


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
    assert "selection_mode = 'active'" in str(session.statement)
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


def test_load_current_prediction_profiles_prefers_period_active_snapshot(monkeypatch):
    older_rows = [
        {
            "model_version": 3,
            "expected_mean": 9.0,
            "valid_from": datetime.datetime(2026, 7, 20, 4, 10),
            "valid_to": datetime.datetime(2026, 7, 27, 4, 10),
        }
    ]
    expected_rows = [
        {
            "model_version": 5,
            "expected_mean": 1.25,
            "valid_from": datetime.datetime(2026, 7, 27),
            "valid_to": datetime.datetime(2026, 8, 3),
        }
    ]
    calls = {}

    def fake_archive(session, *, identifikace, start_date, end_date):
        calls["archive"] = (session, identifikace, start_date, end_date)
        return older_rows + expected_rows

    def fail_global(*args, **kwargs):
        raise AssertionError("Global fallback must not be used when a snapshot exists.")

    monkeypatch.setattr(
        vodomery_service,
        "prague_now_naive",
        lambda: datetime.datetime(2026, 7, 27, 8, 0),
    )
    monkeypatch.setattr(
        vodomery_service,
        "_load_archived_prediction_profiles",
        fake_archive,
    )
    monkeypatch.setattr(
        vodomery_service,
        "_load_global_prediction_profiles",
        fail_global,
    )
    session = object()

    rows = _load_current_prediction_profiles(
        session,
        identifikace="I_V1",
    )

    assert rows == expected_rows
    assert calls["archive"] == (
        session,
        "I_V1",
        datetime.date(2026, 7, 27),
        datetime.date(2026, 7, 27),
    )


def test_prediction_profile_result_exposes_insufficient_history(monkeypatch):
    monkeypatch.setattr(
        vodomery_service,
        "load_prediction_profiles",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        vodomery_service,
        "prague_now_naive",
        lambda: datetime.datetime(2026, 7, 27, 8, 0),
    )

    class DecisionSession:
        def execute(self, statement, params):
            return _FakeMappingResult(
                [
                    {
                        "forecast_period_start": datetime.datetime(2026, 7, 27),
                        "forecast_period_end": datetime.datetime(2026, 8, 3),
                        "fallback_reason": "insufficient_history",
                    }
                ]
            )

        def close(self):
            pass

    monkeypatch.setattr(
        vodomery_service,
        "get_session_pg",
        lambda: DecisionSession(),
    )

    result = vodomery_service.load_prediction_profile_result(
        object(),
        identifikace="NEW_V1",
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 8, 2),
    )

    assert result == {
        "prediction_available": False,
        "availability_status": "unavailable",
        "availability_reason": "insufficient_history",
        "rows": [],
    }


def test_prediction_profile_result_fails_when_available_profile_is_missing(monkeypatch):
    monkeypatch.setattr(
        vodomery_service,
        "load_prediction_profiles",
        lambda *args, **kwargs: [],
    )

    class DecisionSession:
        def execute(self, statement, params):
            return _FakeMappingResult(
                [
                    {
                        "forecast_period_start": datetime.datetime(2026, 7, 27),
                        "forecast_period_end": datetime.datetime(2026, 8, 3),
                        "fallback_reason": "none",
                    }
                ]
            )

        def close(self):
            pass

    monkeypatch.setattr(
        vodomery_service,
        "get_session_pg",
        lambda: DecisionSession(),
    )

    with pytest.raises(RuntimeError, match="missing its profile"):
        vodomery_service.load_prediction_profile_result(
            object(),
            identifikace="BROKEN_V1",
            start_date=datetime.date(2026, 7, 27),
            end_date=datetime.date(2026, 8, 2),
        )


def test_branch_unavailable_lookup_uses_latest_period_decision():
    connection = _FakeConnection(
        [
            ("NEW_V1", "insufficient_history"),
            ("READY_V1", "none"),
        ]
    )

    unavailable = _load_branch_unavailable_prediction_identifiers(
        connection,
        identifiers=("NEW_V1", "READY_V1"),
        day_start=datetime.datetime(2026, 7, 27),
        day_end=datetime.datetime(2026, 7, 28),
    )

    assert unavailable == {"NEW_V1"}
    assert "DISTINCT ON (identifier)" in str(connection.statement)
    assert "forecast_period_start DESC" in str(connection.statement)


def test_load_current_prediction_profiles_falls_back_to_global(monkeypatch):
    fallback_rows = [{"model_version": 3, "expected_mean": 2.5}]
    calls = {}

    monkeypatch.setattr(
        vodomery_service,
        "prague_now_naive",
        lambda: datetime.datetime(2026, 7, 27, 8, 0),
    )
    monkeypatch.setattr(
        vodomery_service,
        "_load_archived_prediction_profiles",
        lambda *args, **kwargs: [],
    )

    def fake_global(session, *, identifikace):
        calls["global"] = (session, identifikace)
        return fallback_rows

    monkeypatch.setattr(
        vodomery_service,
        "_load_global_prediction_profiles",
        fake_global,
    )
    session = object()

    rows = _load_current_prediction_profiles(
        session,
        identifikace="B_V4",
    )

    assert rows == fallback_rows
    assert calls["global"] == (session, "B_V4")


def test_load_branch_archived_prediction_rows_uses_active_per_identifier_period_snapshots():
    rows = [
        ("A", 15, 0, 8, 1.25, 2),
        ("B", 15, 0, 8, 2.5, 3),
    ]
    connection = _FakeConnection(rows)
    day_start = datetime.datetime(2026, 1, 6)
    day_end = datetime.datetime(2026, 1, 7)

    result = _load_branch_archived_prediction_rows(
        connection,
        identifiers=("A", "B"),
        day_start=day_start,
        day_end=day_end,
    )

    assert result == rows
    assert connection.params == {
        "identifiers": ["A", "B"],
        "day_start": day_start,
        "day_end": day_end,
    }
    sql = str(connection.statement)
    assert "monitoring.prediction_profile_snapshots" in sql
    assert "selection_mode = 'active'" in sql
    assert "forecast_period_start <" in sql
    assert "forecast_period_end >" in sql
    assert "DISTINCT ON" in sql
    assert "archive_version DESC" in sql
    assert "vodomery_anomaly_profiles" not in sql


def test_load_branch_archived_prediction_rows_skips_database_for_no_devices():
    connection = _FakeConnection([])

    result = _load_branch_archived_prediction_rows(
        connection,
        identifiers=(),
        day_start=datetime.datetime(2026, 1, 6),
        day_end=datetime.datetime(2026, 1, 7),
    )

    assert result == []
    assert connection.statement is None


def test_load_branch_day_overview_marks_missing_prediction_snapshot_unavailable(monkeypatch):
    target_date = datetime.date(2026, 1, 6)
    branch_config = BranchDashboardConfig(
        key="TEST_BRANCH",
        title="Test branch",
        billing_ident="BILLING_V1",
        daily_limit=10.0,
        intervals=(
            (
                datetime.datetime(2026, 1, 6, 0, 0, 0),
                datetime.datetime(2026, 1, 6, 23, 59, 59),
                ["A_V1"],
            ),
        ),
        membership_resolver=lambda _moment: ["A_V1"],
    )
    connection = _FakeBranchOverviewConnection(
        measurement_rows=[],
        prediction_rows=[],
        decision_rows=[],
    )
    monkeypatch.setattr(vodomery_service, "BRANCH_DASHBOARD_CONFIGS", (branch_config,))
    monkeypatch.setattr(vodomery_service, "ENGINE_PG", _FakeEngine(connection))

    payloads = vodomery_service.load_branch_day_overview(
        vodomery_service.DashboardUserContext(
            username="admin",
            email=None,
            is_admin=True,
            is_active=True,
            allowed_sections=(),
            allowed_pages=(),
            allowed_devices=(),
            last_login_at=None,
            token_version=0,
        ),
        target_date=target_date,
    )

    assert len(payloads) == 1
    branch = payloads[0]
    assert branch["expected_total"] is None
    assert branch["expected_end_of_day"] is None
    assert branch["remaining_to_limit"] is None
    assert branch["expected_vs_limit"] is None
    assert all(row["ocekavana_spotreba"] is None for row in branch["hourly_rows"])
    assert branch["device_consumption_rows"] == [
        {
            "identifikace": "A_V1",
            "start_value": None,
            "end_value": None,
            "spotreba": 0.0,
            "ocekavana_spotreba": None,
            "odchylka_od_ocekavani_procent": None,
            "podil_procent": 0.0,
        }
    ]


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
