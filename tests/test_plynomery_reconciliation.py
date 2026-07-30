from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from moduly.mereni.plynomery import reconciliation


def test_float_comparison_is_stable_for_database_rounding():
    assert reconciliation._floats_match(1.0, 1.0 + 1e-12)
    assert not reconciliation._floats_match(1.0, 1.01)
    assert reconciliation._floats_match(None, None)
    assert not reconciliation._floats_match(None, 0.0)


def test_scope_guard_fails_closed_without_sensitive_values():
    with pytest.raises(
        reconciliation.ReconciliationScopeError,
        match="decision_count differs from approved scope",
    ) as exc:
        reconciliation._require(False, "decision_count")

    assert "identifier" not in str(exc.value).lower()
    assert "measurement" not in str(exc.value).lower()


def test_summary_serialization_contains_aggregate_counts_only():
    summary = reconciliation.ReconciliationDryRunSummary(
        selection_run_id=21,
        active_model_version=2,
        decision_count=18,
        available_decision_count=5,
        unavailable_decision_count=13,
        measured_identifier_count=18,
        measured_identifiers_without_decision=0,
        profile_pair_count=5,
        profile_row_count=3360,
        missing_available_profile_pairs=0,
        profiles_for_unavailable_decisions=0,
        profile_period_model_mismatches=0,
        eligible_measurement_count=1026,
        expected_score_count=285,
        intentionally_unscored_count=741,
        persisted_score_count=285,
        missing_score_count=0,
        unexpected_score_count=0,
        unavailable_selection_score_count=0,
        mismatched_score_count=135,
        mismatched_processed_score_count=135,
        anomaly_flag_change_count=10,
        severity_change_count=0,
        affected_identifier_count=2,
    )

    result = summary.to_dict()

    assert result["selection_run_id"] == 21
    assert result["mismatched_score_count"] == 135
    assert all(isinstance(value, int) for value in result.values())
    assert "identifier" not in result
    assert "measurement_id" not in result


def test_approval_sha256_changes_with_any_aggregate_scope_change():
    summary = reconciliation.ReconciliationDryRunSummary(
        selection_run_id=21,
        active_model_version=2,
        decision_count=18,
        available_decision_count=5,
        unavailable_decision_count=13,
        measured_identifier_count=18,
        measured_identifiers_without_decision=0,
        profile_pair_count=5,
        profile_row_count=3360,
        missing_available_profile_pairs=0,
        profiles_for_unavailable_decisions=0,
        profile_period_model_mismatches=0,
        eligible_measurement_count=1116,
        expected_score_count=310,
        intentionally_unscored_count=806,
        persisted_score_count=310,
        missing_score_count=0,
        unexpected_score_count=0,
        unavailable_selection_score_count=0,
        mismatched_score_count=136,
        mismatched_processed_score_count=136,
        anomaly_flag_change_count=10,
        severity_change_count=0,
        affected_identifier_count=5,
    )
    changed = reconciliation.ReconciliationDryRunSummary(
        **{
            **summary.to_dict(),
            "mismatched_score_count": 137,
        }
    )

    assert len(reconciliation.reconciliation_approval_sha256(summary)) == 64
    assert (
        reconciliation.reconciliation_approval_sha256(summary)
        != reconciliation.reconciliation_approval_sha256(changed)
    )


def test_dry_run_builds_aggregate_drift_summary(monkeypatch):
    available = {f"available-{index}" for index in range(5)}
    unavailable = {f"unavailable-{index}" for index in range(13)}
    decisions = [
        SimpleNamespace(
            identifier=identifier,
            fallback_reason=(
                "none" if identifier in available else "insufficient_history"
            ),
            selected_model_version=1,
            global_model_version=2,
        )
        for identifier in sorted(available | unavailable)
    ]
    profiles = [
        SimpleNamespace(identifier=identifier, model_version=1)
        for identifier in sorted(available)
        for _slot in range(672)
    ]
    measurement_time = datetime.datetime(2026, 7, 27, 0, 15)
    measurements = [
        SimpleNamespace(
            id=index,
            identifikace=identifier,
            date=measurement_time,
        )
        for index, identifier in enumerate(
            sorted(available | unavailable),
            start=1,
        )
    ]
    available_measurements = [
        row for row in measurements if row.identifikace in available
    ]
    expected_rows = [
        {
            "measurement_id": row.id,
            "actual_value": 1.0,
            "expected_mean": 1.0,
            "expected_std": 1.0,
            "expected_median": 1.0,
            "expected_p10": 0.0,
            "expected_p90": 2.0,
            "deviation": 0.0,
            "z_score": 0.0,
            "is_anomaly": False,
            "severity": None,
        }
        for row in available_measurements
    ]
    persisted_scores = [
        SimpleNamespace(
            measurement_id=row["measurement_id"],
            actual_value=row["actual_value"],
            expected_mean=(
                2.0 if index == 0 else row["expected_mean"]
            ),
            expected_std=row["expected_std"],
            expected_median=row["expected_median"],
            expected_p10=row["expected_p10"],
            expected_p90=row["expected_p90"],
            deviation=row["deviation"],
            z_score=row["z_score"],
            is_anomaly=row["is_anomaly"],
            severity=row["severity"],
            processed=True,
        )
        for index, row in enumerate(expected_rows)
    ]

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return self

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.results = [
                Result(decisions),
                Result(profiles),
                Result(measurements),
                Result(persisted_scores),
            ]

        def execute(self, _statement):
            return self.results.pop(0)

    monkeypatch.setattr(
        reconciliation,
        "_load_runtime_model_version_read_only",
        lambda _session: 2,
    )
    monkeypatch.setattr(
        reconciliation,
        "_build_per_identifier_selected_score_rows",
        lambda *_args, **_kwargs: expected_rows,
    )

    summary = reconciliation.build_active_period_reconciliation_dry_run(
        FakeSession()
    )

    assert summary.decision_count == 18
    assert summary.profile_row_count == 3360
    assert summary.eligible_measurement_count == 18
    assert summary.expected_score_count == 5
    assert summary.intentionally_unscored_count == 13
    assert summary.mismatched_score_count == 1
    assert summary.mismatched_processed_score_count == 1
    assert summary.affected_identifier_count == 1


def test_public_runner_sets_transaction_read_only_and_rolls_back(monkeypatch):
    calls = []

    class Transaction:
        def rollback(self):
            calls.append("rollback")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            calls.append("connection_closed")

        def begin(self):
            calls.append("begin")
            return Transaction()

        def execute(self, statement):
            calls.append(str(statement))

    class Session:
        def __init__(self, **_kwargs):
            calls.append("session")

        def close(self):
            calls.append("session_closed")

    expected = SimpleNamespace()
    monkeypatch.setattr(
        reconciliation.ENGINE_PG,
        "connect",
        lambda: Connection(),
    )
    monkeypatch.setattr(reconciliation, "Session", Session)
    monkeypatch.setattr(
        reconciliation,
        "build_active_period_reconciliation_dry_run",
        lambda _session: expected,
    )

    result = reconciliation.run_active_period_reconciliation_dry_run()

    assert result is expected
    assert calls[:3] == ["begin", "SET TRANSACTION READ ONLY", "session"]
    assert calls[-3:] == ["session_closed", "rollback", "connection_closed"]


def test_apply_uses_scheduler_lock_single_transaction_and_precommit_audit(
    monkeypatch,
):
    calls = []
    before = reconciliation.ReconciliationDryRunSummary(
        selection_run_id=21,
        active_model_version=2,
        decision_count=18,
        available_decision_count=5,
        unavailable_decision_count=13,
        measured_identifier_count=18,
        measured_identifiers_without_decision=0,
        profile_pair_count=5,
        profile_row_count=3360,
        missing_available_profile_pairs=0,
        profiles_for_unavailable_decisions=0,
        profile_period_model_mismatches=0,
        eligible_measurement_count=1116,
        expected_score_count=310,
        intentionally_unscored_count=806,
        persisted_score_count=310,
        missing_score_count=0,
        unexpected_score_count=0,
        unavailable_selection_score_count=0,
        mismatched_score_count=136,
        mismatched_processed_score_count=136,
        anomaly_flag_change_count=10,
        severity_change_count=0,
        affected_identifier_count=2,
    )
    after = reconciliation.ReconciliationDryRunSummary(
        **{
            **before.to_dict(),
            "mismatched_score_count": 0,
            "mismatched_processed_score_count": 0,
            "anomaly_flag_change_count": 0,
            "affected_identifier_count": 0,
        }
    )

    class Transaction:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            calls.append("connection_closed")

        def begin(self):
            calls.append("begin")
            return Transaction()

    class Session:
        def __init__(self, **_kwargs):
            calls.append("session")

        def flush(self):
            calls.append("flush")

        def close(self):
            calls.append("session_closed")

    audits = iter(
        (
            (before, frozenset(("identifier-b", "identifier-a"))),
            (after, frozenset()),
        )
    )
    monkeypatch.setattr(
        reconciliation,
        "_try_acquire_process_lock",
        lambda name: calls.append(f"lock:{name}") or object(),
    )
    monkeypatch.setattr(
        reconciliation,
        "_release_process_lock",
        lambda _handle: calls.append("unlock"),
    )
    monkeypatch.setattr(
        reconciliation.ENGINE_PG,
        "connect",
        lambda: Connection(),
    )
    monkeypatch.setattr(reconciliation, "Session", Session)
    monkeypatch.setattr(
        reconciliation,
        "_build_active_period_reconciliation_audit",
        lambda _session: next(audits),
    )
    monkeypatch.setattr(
        reconciliation,
        "_rebuild_scores_for_ident",
        lambda _session, **kwargs: (
            calls.append(f"score:{kwargs['identifikace']}")
            or {"inserted_scores": 3}
        ),
    )
    monkeypatch.setattr(
        reconciliation,
        "_rebuild_events_for_ident",
        lambda _session, **kwargs: (
            calls.append(
                f"event:{kwargs['identifikace']}:{kwargs['ensure_schema']}"
            )
            or {
                "processed_scores": 4,
                "created_events": 1,
                "resolved_events": 2,
            }
        ),
    )

    result = reconciliation.run_active_period_reconciliation_apply(
        approved_dry_run_sha256=(
            reconciliation.reconciliation_approval_sha256(before)
        )
    )

    assert calls[:3] == ["lock:quarter_hour_job", "begin", "session"]
    assert calls.index("score:identifier-a") < calls.index("score:identifier-b")
    assert "event:identifier-a:False" in calls
    assert calls[-4:] == [
        "commit",
        "session_closed",
        "connection_closed",
        "unlock",
    ]
    assert result.rebuilt_identifier_count == 2
    assert result.rebuilt_score_count == 6
    assert result.processed_score_count == 8


def test_apply_rolls_back_when_approved_scope_hash_changed(monkeypatch):
    calls = []
    summary = reconciliation.ReconciliationDryRunSummary(
        selection_run_id=21,
        active_model_version=2,
        decision_count=18,
        available_decision_count=5,
        unavailable_decision_count=13,
        measured_identifier_count=18,
        measured_identifiers_without_decision=0,
        profile_pair_count=5,
        profile_row_count=3360,
        missing_available_profile_pairs=0,
        profiles_for_unavailable_decisions=0,
        profile_period_model_mismatches=0,
        eligible_measurement_count=1116,
        expected_score_count=310,
        intentionally_unscored_count=806,
        persisted_score_count=310,
        missing_score_count=0,
        unexpected_score_count=0,
        unavailable_selection_score_count=0,
        mismatched_score_count=136,
        mismatched_processed_score_count=136,
        anomaly_flag_change_count=10,
        severity_change_count=0,
        affected_identifier_count=5,
    )

    class Transaction:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def begin(self):
            return Transaction()

    class Session:
        def __init__(self, **_kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(
        reconciliation,
        "_try_acquire_process_lock",
        lambda _name: object(),
    )
    monkeypatch.setattr(
        reconciliation,
        "_release_process_lock",
        lambda _handle: calls.append("unlock"),
    )
    monkeypatch.setattr(
        reconciliation.ENGINE_PG,
        "connect",
        lambda: Connection(),
    )
    monkeypatch.setattr(reconciliation, "Session", Session)
    monkeypatch.setattr(
        reconciliation,
        "_build_active_period_reconciliation_audit",
        lambda _session: (summary, frozenset(("identifier",))),
    )

    with pytest.raises(
        reconciliation.ReconciliationScopeError,
        match="approved_dry_run_sha256 differs",
    ):
        reconciliation.run_active_period_reconciliation_apply(
            approved_dry_run_sha256="0" * 64
        )

    assert calls == ["rollback", "unlock"]
