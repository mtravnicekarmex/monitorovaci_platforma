from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from moduly.mereni.kalorimetry import kalorimetry_anomaly
from moduly.mereni.kalorimetry.active_profile import (
    MISSING_PROFILE,
    NO_SELECTION_SNAPSHOT,
    KalorimetryActiveProfile,
    KalorimetryProfileLookupRequest,
)


class FakeSession:
    def __init__(self):
        self.insert_statement = None
        self.insert_rows = None
        self.update_statement = None
        self.commit_count = 0

    def execute(self, statement, params=None):
        if params is not None:
            self.insert_statement = statement
            self.insert_rows = params
        else:
            self.update_statement = statement
        return SimpleNamespace()

    def commit(self):
        self.commit_count += 1


def _measurement(
    *,
    row_id: int = 101,
    identifier: str = "KAL-01",
    delta: float = 14.0,
    valid: bool = True,
):
    return SimpleNamespace(
        id=row_id,
        identifikace=identifier,
        date=datetime(2026, 4, 22, 12, 15),
        interval_minutes=15,
        day_of_week=2,
        slot=49,
        spotreba_energie=1000.0,
        delta=delta,
        platne=valid,
        reset_detected=False,
        synthetic=False,
        gap_detected=False,
    )


def _lookup(
    measurement,
    *,
    available: bool = True,
    reason: str | None = None,
    mean: float = 10.0,
    std: float = 1.0,
    p10: float | None = 8.0,
    p90: float | None = 12.0,
):
    request = KalorimetryProfileLookupRequest(
        identifier=measurement.identifikace,
        timestamp=measurement.date,
    )
    decision = SimpleNamespace(
        id=501,
        selected_model_version=2,
    )
    profile = SimpleNamespace(id=601)
    return KalorimetryActiveProfile(
        request=request,
        prediction_available=available,
        availability_reason=reason,
        selected_model_version=2 if decision else None,
        selected_model_key="weather",
        selected_model_name="Weather",
        expected_mean=mean if available else None,
        expected_median=mean if available else None,
        expected_p10=p10 if available else None,
        expected_p90=p90 if available else None,
        expected_std=std if available else None,
        sample_size=20 if available else None,
        decision=decision if available or reason == MISSING_PROFILE else None,
        profile=profile if available else None,
    )


def _normalized_sql(statement) -> str:
    return " ".join(
        str(statement.compile(dialect=postgresql.dialect())).upper().split()
    )


def test_score_row_preserves_stream_and_selected_model_identities():
    measurement = _measurement()

    row = kalorimetry_anomaly.build_score_row(
        measurement,
        lookup=_lookup(measurement),
    )

    assert row["model_version"] == 1
    assert row["selected_model_version"] == 2
    assert row["selection_snapshot_id"] == 501
    assert row["profile_snapshot_id"] == 601
    assert row["z_score"] == 4.0
    assert row["is_anomaly"] is True
    assert row["severity"] == "HIGH"


def test_zero_profile_std_uses_strict_positive_floor():
    measurement = _measurement(delta=10.0001)

    row = kalorimetry_anomaly.build_score_row(
        measurement,
        lookup=_lookup(
            measurement,
            mean=10.0,
            std=0.0,
            p10=None,
            p90=None,
        ),
    )

    assert row["expected_std"] == kalorimetry_anomaly.MIN_EXPECTED_STD
    assert row["z_score"] == pytest.approx(1.0)
    assert row["is_anomaly"] is False


def test_unavailable_and_ineligible_rows_advance_checkpoint_without_scores(
    monkeypatch,
):
    unavailable = _measurement(row_id=102)
    ineligible = _measurement(row_id=103, valid=False)
    session = FakeSession()
    state = SimpleNamespace(model_version=1, last_measurement_id=100)
    monkeypatch.setattr(
        kalorimetry_anomaly,
        "load_period_valid_active_profiles",
        lambda *args, **kwargs: (
            _lookup(
                unavailable,
                available=False,
                reason=NO_SELECTION_SNAPSHOT,
            ),
        ),
    )

    result = kalorimetry_anomaly.score_measurement_batch(
        session,
        state=state,
        measurements=[unavailable, ineligible],
    )

    assert result.processed_count == 2
    assert result.scored_count == 0
    assert result.unavailable_count == 1
    assert result.ineligible_count == 1
    assert result.checkpoint == 103
    assert session.insert_rows is None
    assert session.update_statement.compile().params["last_measurement_id"] == 103
    assert session.commit_count == 1


def test_available_rows_insert_conflict_safely_and_checkpoint_atomically(
    monkeypatch,
):
    measurement = _measurement()
    session = FakeSession()
    state = SimpleNamespace(model_version=1, last_measurement_id=100)
    monkeypatch.setattr(
        kalorimetry_anomaly,
        "load_period_valid_active_profiles",
        lambda *args, **kwargs: (_lookup(measurement),),
    )

    result = kalorimetry_anomaly.score_measurement_batch(
        session,
        state=state,
        measurements=[measurement],
    )

    assert result.scored_count == 1
    assert result.checkpoint == 101
    assert session.insert_rows[0]["measurement_id"] == 101
    assert (
        "ON CONFLICT (MEASUREMENT_ID, MODEL_VERSION) DO NOTHING"
        in _normalized_sql(session.insert_statement)
    )
    assert session.update_statement.compile().params["last_measurement_id"] == 101
    assert session.commit_count == 1


def test_missing_profile_aborts_before_checkpoint(monkeypatch):
    measurement = _measurement()
    session = FakeSession()
    state = SimpleNamespace(model_version=1, last_measurement_id=100)
    monkeypatch.setattr(
        kalorimetry_anomaly,
        "load_period_valid_active_profiles",
        lambda *args, **kwargs: (
            _lookup(
                measurement,
                available=False,
                reason=MISSING_PROFILE,
            ),
        ),
    )

    with pytest.raises(RuntimeError, match="missing its exact"):
        kalorimetry_anomaly.score_measurement_batch(
            session,
            state=state,
            measurements=[measurement],
        )

    assert session.insert_rows is None
    assert session.update_statement is None
    assert session.commit_count == 0


def test_empty_batch_does_not_write():
    session = FakeSession()
    state = SimpleNamespace(model_version=1, last_measurement_id=100)

    result = kalorimetry_anomaly.score_measurement_batch(
        session,
        state=state,
        measurements=[],
    )

    assert result.processed_count == 0
    assert result.checkpoint == 100
    assert session.commit_count == 0


def test_active_repair_uses_period_valid_lookup_without_checkpoint(
    monkeypatch,
):
    measurement = _measurement()
    session = FakeSession()
    monkeypatch.setattr(
        kalorimetry_anomaly,
        "load_period_valid_active_profiles",
        lambda *args, **kwargs: (_lookup(measurement),),
    )

    rebuilt = kalorimetry_anomaly.rebuild_active_scores_for_measurements(
        session,
        measurements=[measurement],
    )

    assert rebuilt == 1
    assert session.insert_rows[0]["selected_model_version"] == 2
    assert session.update_statement is None
    assert session.commit_count == 0
