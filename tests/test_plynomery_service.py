import datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from services.api.services import plynomery as plynomery_service


class FakeMappingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, result_sets):
        self.result_sets = list(result_sets)
        self.close_calls = 0
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append(str(statement))
        return FakeMappingsResult(self.result_sets.pop(0))

    def close(self):
        self.close_calls += 1


def _user():
    return SimpleNamespace(
        is_admin=False,
        allowed_sections=("plynomery",),
        allowed_devices=("P_A1",),
    )


def _decision(*, fallback_reason="none"):
    return {
        "selection_run_id": 21,
        "selected_model_version": 2,
        "selected_model_name": "Weather adjusted",
        "fallback_reason": fallback_reason,
        "forecast_period_start": datetime.datetime(2026, 7, 27),
        "forecast_period_end": datetime.datetime(2026, 8, 3),
    }


def test_current_prediction_profiles_return_explicit_insufficient_history(
    monkeypatch,
):
    session = FakeSession([[_decision(fallback_reason="insufficient_history")]])
    monkeypatch.setattr(plynomery_service, "get_session_pg", lambda: session)

    result = plynomery_service.load_current_prediction_profiles(
        _user(),
        identifikace="P_A1",
        reference_time=datetime.datetime(2026, 7, 29, 12, 0),
    )

    assert result["prediction_available"] is False
    assert result["availability_status"] == "unavailable"
    assert result["availability_reason"] == "insufficient_history"
    assert result["selection_run_id"] == 21
    assert result["rows"] == []
    assert session.close_calls == 1


def test_current_prediction_profiles_return_no_snapshot_without_global_fallback(
    monkeypatch,
):
    session = FakeSession([[]])
    monkeypatch.setattr(plynomery_service, "get_session_pg", lambda: session)

    result = plynomery_service.load_current_prediction_profiles(
        _user(),
        identifikace="P_A1",
        reference_time=datetime.datetime(2026, 7, 29, 12, 0),
    )

    assert result["prediction_available"] is False
    assert result["availability_status"] == "unavailable"
    assert result["availability_reason"] == "no_selection_snapshot"
    assert result["selected_model_version"] is None
    assert result["rows"] == []


def test_current_prediction_profiles_preserve_weather_features(monkeypatch):
    profile = {
        "interval_minutes": 15,
        "day_of_week": 2,
        "slot": 48,
        "expected_mean": 3.0,
        "expected_median": 3.1,
        "expected_p10": 2.8,
        "expected_p90": 3.4,
        "expected_std": 0.3,
        "sample_size": 12,
        "model_version": 2,
        "model_key": "weather_adjusted",
        "metadata_json": (
            '{"base_mean":1.0,"hdd_24h_mean":4.0,'
            '"hdd_slope":0.5,"profile_kind":"weather_adjusted"}'
        ),
    }
    session = FakeSession([[_decision()], [profile]])
    monkeypatch.setattr(plynomery_service, "get_session_pg", lambda: session)

    result = plynomery_service.load_current_prediction_profiles(
        _user(),
        identifikace="P_A1",
        reference_time=datetime.datetime(2026, 7, 29, 12, 0),
    )

    assert result["prediction_available"] is True
    assert result["availability_status"] == "available"
    assert result["availability_reason"] is None
    assert result["selected_model_version"] == 2
    assert result["rows"] == [
        {
            "interval_minutes": 15,
            "day_of_week": 2,
            "slot": 48,
            "expected_mean": 3.0,
            "expected_median": 3.1,
            "expected_p10": 2.8,
            "expected_p90": 3.4,
            "expected_std": 0.3,
            "sample_size": 12,
            "model_version": 2,
            "model_key": "weather_adjusted",
            "profile_kind": "weather_adjusted",
            "base_mean": 1.0,
            "hdd_slope": 0.5,
            "hdd_24h_mean": 4.0,
            "selection_run_id": 21,
            "valid_from": datetime.datetime(2026, 7, 27),
            "valid_to": datetime.datetime(2026, 8, 3),
        }
    ]
    assert "forecast_period_start DESC" in session.statements[0]
    assert "created_at DESC" in session.statements[0]
    assert "id DESC" in session.statements[0]


def test_historical_prediction_profiles_return_partial_active_periods(monkeypatch):
    decisions = [
        {
            **_decision(),
            "created_at": datetime.datetime(2026, 7, 27, 6, 10),
            "id": 1,
        },
        {
            **_decision(fallback_reason="insufficient_history"),
            "selection_run_id": 22,
            "forecast_period_start": datetime.datetime(2026, 8, 3),
            "forecast_period_end": datetime.datetime(2026, 8, 10),
            "created_at": datetime.datetime(2026, 8, 3, 6, 10),
            "id": 2,
        },
    ]
    profile = {
        "selection_run_id": 21,
        "forecast_period_start": datetime.datetime(2026, 7, 27),
        "forecast_period_end": datetime.datetime(2026, 8, 3),
        "interval_minutes": 15,
        "day_of_week": 2,
        "slot": 48,
        "expected_mean": 3.0,
        "expected_median": 3.1,
        "expected_p10": 2.8,
        "expected_p90": 3.4,
        "expected_std": 0.3,
        "sample_size": 12,
        "model_version": 2,
        "model_key": "weather_adjusted",
        "metadata_json": '{"profile_kind":"weather_adjusted"}',
    }
    session = FakeSession([decisions, [profile]])
    monkeypatch.setattr(plynomery_service, "get_session_pg", lambda: session)

    result = plynomery_service.load_prediction_profiles(
        _user(),
        identifikace="P_A1",
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 8, 9),
    )

    assert result["prediction_available"] is True
    assert result["availability_status"] == "partial"
    assert result["availability_reason"] == "partial_unavailable"
    assert len(result["availability_periods"]) == 2
    assert result["availability_periods"][0]["prediction_available"] is True
    assert result["availability_periods"][1]["availability_reason"] == (
        "insufficient_history"
    )
    assert len(result["rows"]) == 1
    assert result["rows"][0]["selection_run_id"] == 21
    assert all("selection_mode = 'active'" in sql for sql in session.statements)
    assert all("plynomery_anomaly_profiles" not in sql for sql in session.statements)


def test_historical_prediction_profiles_do_not_fall_back_without_snapshots(
    monkeypatch,
):
    session = FakeSession([[]])
    monkeypatch.setattr(plynomery_service, "get_session_pg", lambda: session)

    result = plynomery_service.load_prediction_profiles(
        _user(),
        identifikace="P_A1",
        start_date=datetime.date(2025, 1, 1),
        end_date=datetime.date(2025, 1, 7),
    )

    assert result["prediction_available"] is False
    assert result["availability_status"] == "unavailable"
    assert result["availability_reason"] == "no_selection_snapshot"
    assert result["rows"] == []
    assert len(session.statements) == 1


def test_measurement_series_rejects_reversed_range_before_database(monkeypatch):
    monkeypatch.setattr(
        plynomery_service,
        "get_session_pg",
        lambda: pytest.fail("Database must not open for an invalid range."),
    )

    with pytest.raises(ValueError, match="start_date"):
        plynomery_service.load_measurement_series(
            _user(),
            identifikace="P_A1",
            start_date=datetime.date(2026, 7, 30),
            end_date=datetime.date(2026, 7, 29),
        )


def test_prediction_series_builds_weather_adjusted_daily_value(monkeypatch):
    monkeypatch.setattr(
        plynomery_service,
        "load_prediction_profiles",
        lambda *_args, **_kwargs: {
            "prediction_available": True,
            "availability_status": "available",
            "availability_reason": None,
            "rows": [
                {
                    "interval_minutes": 60,
                    "day_of_week": 0,
                    "slot": 8,
                    "expected_mean": 3.0,
                    "model_version": 2,
                    "profile_kind": "weather_adjusted",
                    "selection_run_id": 21,
                    "valid_from": datetime.datetime(2026, 7, 27),
                    "valid_to": datetime.datetime(2026, 8, 3),
                    "base_mean": 1.0,
                    "hdd_slope": 0.5,
                }
            ],
        },
    )
    monkeypatch.setattr(
        plynomery_service,
        "_load_prediction_weather",
        lambda **_kwargs: pd.DataFrame(
            {
                "datetime_hour": [datetime.datetime(2026, 7, 27, 6)],
                "hdd_24h": [4.0],
            }
        ),
    )

    result = plynomery_service.load_prediction_series(
        _user(),
        identifikace="P_A1",
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        granularity="daily",
    )

    assert result["prediction_available"] is True
    assert result["availability_status"] == "available"
    assert result["rows"][0]["ocekavana_spotreba"] == 3.0
    assert result["rows"][0]["model_versions"] == [2]


def test_prediction_series_preserves_explicit_insufficient_history(monkeypatch):
    monkeypatch.setattr(
        plynomery_service,
        "load_prediction_profiles",
        lambda *_args, **_kwargs: {
            "prediction_available": False,
            "availability_status": "unavailable",
            "availability_reason": "insufficient_history",
            "rows": [],
        },
    )
    monkeypatch.setattr(
        plynomery_service,
        "_load_prediction_weather",
        lambda **_kwargs: pd.DataFrame(),
    )

    result = plynomery_service.load_prediction_series(
        _user(),
        identifikace="P_A1",
        start_date=datetime.date(2026, 7, 27),
        end_date=datetime.date(2026, 7, 27),
        granularity="daily",
    )

    assert result["prediction_available"] is False
    assert result["availability_status"] == "unavailable"
    assert result["availability_reason"] == "insufficient_history"
    assert result["rows"] == []
