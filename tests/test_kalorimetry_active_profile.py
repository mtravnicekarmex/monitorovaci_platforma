from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from moduly.mereni.kalorimetry.active_profile import (
    INSUFFICIENT_HISTORY,
    MISSING_PROFILE,
    NO_SELECTION_SNAPSHOT,
    KalorimetryProfileLookupRequest,
    load_period_valid_active_profiles,
    resolve_period_valid_active_profile,
)


def _decision(
    *,
    row_id: int = 1,
    start: datetime = datetime(2026, 4, 20),
    end: datetime = datetime(2026, 4, 27),
    model_version: int = 1,
    fallback_reason: str = "none",
    created_at: datetime = datetime(2026, 4, 20, 1),
):
    return SimpleNamespace(
        id=row_id,
        identifier="KAL-01",
        forecast_period_start=start,
        forecast_period_end=end,
        selected_model_version=model_version,
        selected_model_key=f"model-{model_version}",
        selected_model_name=f"Model {model_version}",
        fallback_reason=fallback_reason,
        created_at=created_at,
    )


def _profile(
    *,
    row_id: int = 1,
    start: datetime = datetime(2026, 4, 20),
    end: datetime = datetime(2026, 4, 27),
    model_version: int = 1,
    archive_version: int = 1,
    mean: float = 2.5,
    created_at: datetime = datetime(2026, 4, 20, 1),
):
    return SimpleNamespace(
        id=row_id,
        identifier="KAL-01",
        forecast_period_start=start,
        forecast_period_end=end,
        model_version=model_version,
        interval_minutes=15,
        day_of_week=2,
        slot=49,
        archive_version=archive_version,
        expected_mean=mean,
        expected_median=mean,
        expected_p10=mean - 1,
        expected_p90=mean + 1,
        expected_std=0.5,
        sample_size=10,
        created_at=created_at,
    )


def _request(timestamp: datetime = datetime(2026, 4, 22, 12, 15)):
    return KalorimetryProfileLookupRequest(
        identifier="KAL-01",
        timestamp=timestamp,
    )


def test_resolves_latest_overlapping_period_and_highest_archive_version():
    older_period = _decision(
        row_id=1,
        start=datetime(2026, 4, 13),
        end=datetime(2026, 4, 27),
    )
    current_period = _decision(row_id=2)
    old_archive = _profile(row_id=10, archive_version=1, mean=2.0)
    new_archive = _profile(row_id=11, archive_version=2, mean=3.0)

    result = resolve_period_valid_active_profile(
        _request(),
        decisions=[older_period, current_period],
        profiles=[old_archive, new_archive],
    )

    assert result.prediction_available is True
    assert result.availability_reason is None
    assert result.decision is current_period
    assert result.profile is new_archive
    assert result.expected_mean == 3.0


def test_period_end_is_exclusive():
    result = resolve_period_valid_active_profile(
        _request(datetime(2026, 4, 27)),
        decisions=[_decision()],
        profiles=[_profile()],
    )

    assert result.prediction_available is False
    assert result.availability_reason == NO_SELECTION_SNAPSHOT


def test_insufficient_history_produces_no_available_profile():
    decision = _decision(fallback_reason=INSUFFICIENT_HISTORY)

    result = resolve_period_valid_active_profile(
        _request(),
        decisions=[decision],
        profiles=[_profile()],
    )

    assert result.prediction_available is False
    assert result.availability_reason == INSUFFICIENT_HISTORY
    assert result.profile is None


def test_available_decision_without_exact_slot_is_explicitly_missing():
    result = resolve_period_valid_active_profile(
        _request(),
        decisions=[_decision()],
        profiles=[],
    )

    assert result.prediction_available is False
    assert result.availability_reason == MISSING_PROFILE
    assert result.selected_model_version == 1


def test_profile_from_other_model_or_period_is_not_used_as_fallback():
    other_model = _profile(model_version=2)
    stale_profile = _profile(
        start=datetime(2026, 4, 13),
        end=datetime(2026, 4, 20),
    )

    result = resolve_period_valid_active_profile(
        _request(),
        decisions=[_decision()],
        profiles=[other_model, stale_profile],
    )

    assert result.prediction_available is False
    assert result.availability_reason == MISSING_PROFILE


def test_aware_timestamp_is_converted_to_prague_wall_time():
    request = _request(datetime(2026, 4, 22, 10, 15, tzinfo=timezone.utc))

    assert request.prague_timestamp == datetime(2026, 4, 22, 12, 15)
    assert request.day_of_week == 2
    assert request.slot == 49


def test_loader_scopes_both_queries_and_preserves_request_order():
    class ScalarRows:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return self

        def all(self):
            return self.rows

    class CapturingSession:
        def __init__(self):
            self.statements = []
            self.results = iter(
                [
                    ScalarRows([_decision()]),
                    ScalarRows([_profile()]),
                ]
            )

        def execute(self, statement):
            self.statements.append(statement)
            return next(self.results)

    session = CapturingSession()
    requests = (
        _request(),
        KalorimetryProfileLookupRequest(
            identifier="KAL-NO-SNAPSHOT",
            timestamp=datetime(2026, 4, 22, 12, 15),
        ),
    )

    results = load_period_valid_active_profiles(session, requests)

    assert len(session.statements) == 2
    assert [result.request for result in results] == list(requests)
    assert results[0].prediction_available is True
    assert results[1].availability_reason == NO_SELECTION_SNAPSHOT
    for statement in session.statements:
        sql = str(statement.compile()).lower()
        assert "medium_key" in sql
        assert "selection_mode" in sql
        assert "identifier in" in sql
        assert "forecast_period_start <=" in sql
        assert "forecast_period_end >" in sql


@pytest.mark.parametrize("interval", [0, 17])
def test_invalid_interval_is_rejected(interval):
    with pytest.raises(ValueError):
        KalorimetryProfileLookupRequest(
            identifier="KAL-01",
            timestamp=datetime(2026, 4, 22),
            interval_minutes=interval,
        )
