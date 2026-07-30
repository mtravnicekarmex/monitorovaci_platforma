from datetime import date, datetime
from types import SimpleNamespace

import pytest

from services.api.services import kalorimetry
from services.api.services.dashboard_auth import (
    AuthorizationError,
    DashboardUserContext,
)


class ScalarResult:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class FakeSession:
    def __init__(self, result_sets):
        self.result_sets = iter(result_sets)
        self.statements = []
        self.closed = False

    def execute(self, statement):
        self.statements.append(statement)
        return ScalarResult(next(self.result_sets))

    def close(self):
        self.closed = True


def _user(*, devices=("KAL-01",), sections=("kalorimetry",)):
    return DashboardUserContext(
        username="tester",
        email=None,
        is_admin=False,
        is_active=True,
        last_login_at=None,
        token_version=1,
        allowed_devices=devices,
        allowed_sections=sections,
        allowed_pages=("kalorimetry_overview",),
    )


def _decision(**overrides):
    values = {
        "id": 1,
        "identifier": "KAL-01",
        "selection_run_id": None,
        "selected_model_version": 1,
        "selected_model_name": "Baseline",
        "fallback_reason": "none",
        "forecast_period_start": datetime(2026, 4, 20),
        "forecast_period_end": datetime(2026, 4, 27),
        "created_at": datetime(2026, 4, 20, 1),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _profile(**overrides):
    values = {
        "id": 1,
        "interval_minutes": 15,
        "day_of_week": 0,
        "slot": 0,
        "archive_version": 1,
        "created_at": datetime(2026, 4, 20, 1),
        "expected_mean": 10.0,
        "expected_median": 10.0,
        "expected_p10": 8.0,
        "expected_p90": 12.0,
        "expected_std": 1.0,
        "sample_size": 10,
        "model_version": 1,
        "model_key": "baseline",
        "metadata_json": '{"profile_kind":"calendar_baseline"}',
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_service_checks_section_and_device_before_database(monkeypatch):
    monkeypatch.setattr(
        kalorimetry,
        "get_session_pg",
        lambda: pytest.fail("database must not be opened"),
    )

    with pytest.raises(AuthorizationError):
        kalorimetry.load_measurement_series(
            _user(devices=("OTHER",)),
            identifikace="KAL-01",
            start_date=date(2026, 4, 20),
            end_date=date(2026, 4, 21),
        )


def test_current_profile_has_explicit_no_snapshot_without_fallback(monkeypatch):
    session = FakeSession([[]])
    monkeypatch.setattr(kalorimetry, "get_session_pg", lambda: session)

    result = kalorimetry.load_prediction_profiles(
        _user(),
        identifikace="KAL-01",
        reference_time=datetime(2026, 4, 22),
    )

    assert result["prediction_available"] is False
    assert result["availability_reason"] == "no_selection_snapshot"
    assert result["rows"] == []
    assert session.closed is True


def test_current_profile_prefers_highest_archive_slot(monkeypatch):
    old = _profile(id=10, archive_version=1, expected_mean=9.0)
    new = _profile(id=11, archive_version=2, expected_mean=10.0)
    session = FakeSession([[_decision()], [new, old]])
    monkeypatch.setattr(kalorimetry, "get_session_pg", lambda: session)

    result = kalorimetry.load_prediction_profiles(
        _user(),
        identifikace="KAL-01",
        reference_time=datetime(2026, 4, 22),
    )

    assert result["prediction_available"] is True
    assert result["rows"][0]["expected_mean"] == 10.0
    assert len(result["rows"]) == 1


def test_historical_profiles_report_partial_period_availability(monkeypatch):
    available = _decision()
    unavailable = _decision(
        id=2,
        fallback_reason="insufficient_history",
        forecast_period_start=datetime(2026, 4, 27),
        forecast_period_end=datetime(2026, 5, 4),
    )
    session = FakeSession([[available, unavailable], [[_profile()][0]]])
    monkeypatch.setattr(kalorimetry, "get_session_pg", lambda: session)

    result = kalorimetry.load_prediction_profiles(
        _user(),
        identifikace="KAL-01",
        start_date=date(2026, 4, 20),
        end_date=date(2026, 5, 3),
    )

    assert result["availability_status"] == "partial"
    assert result["availability_reason"] == "partial_unavailable"
    assert len(result["availability_periods"]) == 2
    assert result["availability_periods"][1]["availability_reason"] == (
        "insufficient_history"
    )


def test_profile_range_requires_both_dates_before_database(monkeypatch):
    monkeypatch.setattr(
        kalorimetry,
        "get_session_pg",
        lambda: pytest.fail("database must not be opened"),
    )

    with pytest.raises(ValueError):
        kalorimetry.load_prediction_profiles(
            _user(),
            identifikace="KAL-01",
            start_date=date(2026, 4, 20),
        )


def test_prediction_series_preserves_explicit_unavailable_reason(monkeypatch):
    monkeypatch.setattr(
        kalorimetry,
        "load_prediction_profiles",
        lambda *_args, **_kwargs: {
            "prediction_available": False,
            "availability_status": "unavailable",
            "availability_reason": "insufficient_history",
            "rows": [],
        },
    )
    result = kalorimetry.load_prediction_series(
        _user(),
        identifikace="KAL-01",
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 20),
        granularity="daily",
    )
    assert result["prediction_available"] is False
    assert result["availability_reason"] == "insufficient_history"
    assert result["rows"] == []


def test_prediction_series_builds_daily_rows(monkeypatch):
    monkeypatch.setattr(
        kalorimetry,
        "load_prediction_profiles",
        lambda *_args, **_kwargs: {
            "prediction_available": True,
            "availability_status": "available",
            "availability_reason": None,
            "rows": [
                {
                    "interval_minutes": 15,
                    "day_of_week": 0,
                    "slot": 0,
                    "expected_mean": 2.5,
                    "model_version": 1,
                    "profile_kind": "static",
                    "selection_run_id": None,
                    "valid_from": datetime(2026, 4, 20),
                    "valid_to": datetime(2026, 4, 27),
                }
            ],
        },
    )
    result = kalorimetry.load_prediction_series(
        _user(),
        identifikace="KAL-01",
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 20),
        granularity="daily",
    )
    assert result["prediction_available"] is True
    assert result["availability_status"] == "available"
    assert result["rows"][0]["ocekavana_spotreba"] == 2.5
    assert result["rows"][0]["model_versions"] == [1]
