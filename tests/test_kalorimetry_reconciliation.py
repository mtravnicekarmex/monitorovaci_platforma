from datetime import datetime
from types import SimpleNamespace

from moduly.mereni.kalorimetry.reconciliation import (
    _Counters,
    compare_events,
    compare_score_rows,
)


def _expected_score(measurement_id=1):
    return {
        "measurement_id": measurement_id,
        "actual_value": 12.0,
        "expected_mean": 10.0,
        "expected_std": 1.0,
        "expected_median": 10.0,
        "expected_p10": 8.0,
        "expected_p90": 12.0,
        "deviation": 2.0,
        "z_score": 2.0,
        "is_anomaly": False,
        "severity": None,
        "selected_model_version": 1,
        "selection_snapshot_id": 10,
        "profile_snapshot_id": 20,
    }


def _persisted_score(**overrides):
    values = _expected_score()
    values.update(overrides)
    values.pop("measurement_id")
    return SimpleNamespace(**values)


def test_score_comparison_classifies_missing_and_exact_rows():
    counters = compare_score_rows(
        [_expected_score(1), _expected_score(2)],
        {1: _persisted_score()},
    )

    assert counters.expected_score_count == 2
    assert counters.missing_score_count == 1
    assert counters.mismatched_score_count == 0


def test_score_comparison_counts_value_flag_severity_and_identity_changes():
    persisted = _persisted_score(
        expected_mean=11.0,
        is_anomaly=True,
        severity="MEDIUM",
        profile_snapshot_id=21,
    )

    counters = compare_score_rows(
        [_expected_score()],
        {1: persisted},
        counters=_Counters(),
    )

    assert counters.mismatched_score_count == 1
    assert counters.anomaly_flag_change_count == 1
    assert counters.severity_change_count == 1


def test_event_comparison_uses_created_identity_and_final_transition_values():
    start = datetime(2026, 4, 22, 12)
    created = SimpleNamespace(
        identifier="KAL-01",
        event_type="SPIKE",
        transition="CREATED",
        transition_time=start,
        severity="HIGH",
        max_z_score=6.0,
    )
    resolved = SimpleNamespace(
        identifier="KAL-01",
        event_type="SPIKE",
        transition="RESOLVED",
        transition_time=datetime(2026, 4, 22, 12, 15),
        severity="CRITICAL",
        max_z_score=8.0,
    )
    persisted = SimpleNamespace(
        identifikace="KAL-01",
        event_type="SPIKE",
        start_time=start,
        severity="CRITICAL",
        max_z_score=8.0,
    )

    assert compare_events([created, resolved], [persisted]) == (0, 0, 0)


def test_event_comparison_classifies_missing_unexpected_and_mismatch():
    start = datetime(2026, 4, 22, 12)
    expected = SimpleNamespace(
        identifier="KAL-01",
        event_type="SPIKE",
        transition="CREATED",
        transition_time=start,
        severity="HIGH",
        max_z_score=6.0,
    )
    mismatched = SimpleNamespace(
        identifikace="KAL-01",
        event_type="SPIKE",
        start_time=start,
        severity="MEDIUM",
        max_z_score=6.0,
    )
    unexpected = SimpleNamespace(
        identifikace="KAL-02",
        event_type="SPIKE",
        start_time=start,
        severity="HIGH",
        max_z_score=6.0,
    )

    assert compare_events([expected], [mismatched, unexpected]) == (0, 1, 1)
