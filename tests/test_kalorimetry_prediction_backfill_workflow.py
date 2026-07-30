import datetime
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from moduly.mereni.kalorimetry import prediction_backfill
from moduly.mereni.kalorimetry import prediction_backfill_workflow as workflow
from moduly.mereni.kalorimetry.snapshot_persistence import (
    KalorimetrySnapshotPersistencePlan,
)


def _plan():
    period = prediction_backfill.build_kalorimetry_backfill_period(
        datetime.datetime(2026, 7, 27)
    )
    return prediction_backfill.KalorimetryBackfillPlan(
        start_date=period.start,
        end_date=period.end,
        archive_version=1,
        items=(
            prediction_backfill.KalorimetryBackfillPlanItem(
                identifier="K1",
                forecast_period=period,
                first_measurement_at=datetime.datetime(2025, 1, 1),
            ),
        ),
    )


def _calculation():
    period = _plan().items[0].forecast_period
    decision = SimpleNamespace(
        identifier="K1",
        selected_model_version=1,
    )
    return prediction_backfill.KalorimetryBackfillWeekCalculation(
        forecast_period=period,
        planned_identifiers=("K1",),
        snapshot_plan=KalorimetrySnapshotPersistencePlan(
            decisions=(decision,),
            profile_rows=tuple(
                {
                    "identifier": "K1",
                    "model_version": 1,
                    "slot": slot,
                }
                for slot in range(672)
            ),
            unavailable_identifiers=(),
        ),
        candidate_metric_rows=(
            {
                "identifier": "K1",
                "model_version": 1,
                "selected": True,
            },
            {
                "identifier": "K1",
                "model_version": 2,
                "selected": False,
            },
        ),
        unavailable_reasons={},
    )


def _calculator(period, identifiers, archive_run_id, archive_version):
    assert period == _calculation().forecast_period
    assert identifiers == ("K1",)
    assert archive_run_id == "kalorimetry-backfill-v1"
    assert archive_version == 1
    return _calculation()


class _Session:
    def __init__(self):
        self.calls = []

    def begin_nested(self):
        self.calls.append("begin_nested")
        return nullcontext()

    def flush(self):
        self.calls.append("flush")

    def commit(self):
        self.calls.append("commit")

    def rollback(self):
        self.calls.append("rollback")


def test_dry_run_reports_absent_without_writes():
    session = _Session()

    result = workflow.dry_run_kalorimetry_prediction_backfill(
        _plan(),
        archive_run_id="kalorimetry-backfill-v1",
        calculate_week=_calculator,
        session=session,
        load_state=lambda *args: workflow.KalorimetryBackfillIdentityState(),
    )

    assert result.mode == "dry_run"
    assert result.absent_week_count == 1
    assert result.weeks[0].decision_count == 1
    assert result.weeks[0].candidate_metric_count == 2
    assert result.weeks[0].profile_point_count == 672
    assert session.calls == []


def test_apply_requires_explicit_confirmation():
    with pytest.raises(PermissionError, match="explicit confirmation"):
        workflow.apply_kalorimetry_prediction_backfill(
            _plan(),
            archive_run_id="kalorimetry-backfill-v1",
            calculate_week=_calculator,
            session=_Session(),
        )


def test_apply_persists_all_three_sets_in_one_savepoint_and_commits(
    monkeypatch,
):
    session = _Session()
    monkeypatch.setattr(
        workflow,
        "persist_selected_model_decisions",
        lambda session, rows, **kwargs: session.calls.append("decisions")
        or len(rows),
    )
    monkeypatch.setattr(
        workflow,
        "persist_prediction_backfill_candidate_metrics",
        lambda session, rows: session.calls.append("metrics") or len(rows),
    )
    monkeypatch.setattr(
        workflow,
        "persist_prediction_profile_snapshots",
        lambda session, rows: session.calls.append("profiles") or len(rows),
    )

    expected = workflow.build_expected_kalorimetry_backfill_identity_state(
        _calculation()
    )
    states = iter(
        (workflow.KalorimetryBackfillIdentityState(), expected)
    )
    result = workflow.apply_kalorimetry_prediction_backfill(
        _plan(),
        archive_run_id="kalorimetry-backfill-v1",
        calculate_week=_calculator,
        session=session,
        confirm_apply=True,
        load_state=lambda *args: next(states),
    )

    assert session.calls == [
        "begin_nested",
        "decisions",
        "metrics",
        "profiles",
        "flush",
        "commit",
    ]
    assert result.complete_week_count == 1
    assert result.weeks[0].inserted_decision_count == 1
    assert result.weeks[0].inserted_candidate_metric_count == 2
    assert result.weeks[0].inserted_profile_point_count == 672


def test_resume_skips_only_exact_complete_identity(monkeypatch):
    calculation = _calculation()
    expected = workflow.build_expected_kalorimetry_backfill_identity_state(
        calculation
    )
    session = _Session()
    monkeypatch.setattr(
        workflow,
        "persist_selected_model_decisions",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Complete identity must not be written.")
        ),
    )

    result = workflow.apply_kalorimetry_prediction_backfill(
        _plan(),
        archive_run_id="kalorimetry-backfill-v1",
        calculate_week=_calculator,
        session=session,
        confirm_apply=True,
        load_state=lambda *args: expected,
    )

    assert result.complete_week_count == 1
    assert result.weeks[0].inserted_profile_point_count == 0
    assert session.calls == []


def test_partial_identity_is_conflict_and_rolls_back():
    partial = workflow.KalorimetryBackfillIdentityState(
        decision_models=(("K1", 1),),
    )
    session = _Session()

    with pytest.raises(RuntimeError, match="conflict"):
        workflow.apply_kalorimetry_prediction_backfill(
            _plan(),
            archive_run_id="kalorimetry-backfill-v1",
            calculate_week=_calculator,
            session=session,
            confirm_apply=True,
            load_state=lambda *args: partial,
        )

    assert session.calls == ["rollback"]


def test_verify_distinguishes_complete_and_conflict():
    calculation = _calculation()
    expected = workflow.build_expected_kalorimetry_backfill_identity_state(
        calculation
    )

    complete = workflow.verify_kalorimetry_prediction_backfill(
        _plan(),
        archive_run_id="kalorimetry-backfill-v1",
        calculate_week=_calculator,
        session=_Session(),
        load_state=lambda *args: expected,
    )
    conflict = workflow.verify_kalorimetry_prediction_backfill(
        _plan(),
        archive_run_id="kalorimetry-backfill-v1",
        calculate_week=_calculator,
        session=_Session(),
        load_state=lambda *args: workflow.KalorimetryBackfillIdentityState(
            profile_point_counts=(("K1", 1, 671),),
        ),
    )

    assert complete.complete_week_count == 1
    assert conflict.conflict_week_count == 1


def test_all_missing_tables_are_absent_but_apply_refuses_them():
    missing = workflow.KalorimetryBackfillIdentityState(
        missing_tables=(
            "monitoring.prediction_selected_model_snapshots",
            "monitoring.prediction_backfill_candidate_metrics",
            "monitoring.prediction_profile_snapshots",
        )
    )
    expected = workflow.build_expected_kalorimetry_backfill_identity_state(
        _calculation()
    )
    assert workflow.classify_kalorimetry_backfill_identity(
        existing=missing,
        expected=expected,
    ) == workflow.BACKFILL_STATE_ABSENT

    session = _Session()
    with pytest.raises(RuntimeError, match="requires all shared"):
        workflow.apply_kalorimetry_prediction_backfill(
            _plan(),
            archive_run_id="kalorimetry-backfill-v1",
            calculate_week=_calculator,
            session=session,
            confirm_apply=True,
            load_state=lambda *args: missing,
        )
    assert session.calls == ["rollback"]


def test_post_insert_content_mismatch_rolls_back_week(monkeypatch):
    session = _Session()
    monkeypatch.setattr(
        workflow,
        "persist_selected_model_decisions",
        lambda *args, **kwargs: 1,
    )
    monkeypatch.setattr(
        workflow,
        "persist_prediction_backfill_candidate_metrics",
        lambda *args, **kwargs: 2,
    )
    monkeypatch.setattr(
        workflow,
        "persist_prediction_profile_snapshots",
        lambda *args, **kwargs: 671,
    )

    with pytest.raises(RuntimeError, match="post-insert verification"):
        workflow.apply_kalorimetry_prediction_backfill(
            _plan(),
            archive_run_id="kalorimetry-backfill-v1",
            calculate_week=_calculator,
            session=session,
            confirm_apply=True,
            load_state=lambda *args: workflow.KalorimetryBackfillIdentityState(),
        )

    assert session.calls == ["begin_nested", "flush", "rollback"]


def test_same_counts_with_changed_content_are_conflict():
    expected = workflow.build_expected_kalorimetry_backfill_identity_state(
        _calculation()
    )
    changed = workflow.KalorimetryBackfillIdentityState(
        decision_models=expected.decision_models,
        candidate_models=expected.candidate_models,
        selected_candidate_models=expected.selected_candidate_models,
        profile_point_counts=expected.profile_point_counts,
        decision_fingerprints=("changed",),
        candidate_fingerprints=expected.candidate_fingerprints,
        profile_fingerprints=expected.profile_fingerprints,
    )

    assert workflow.classify_kalorimetry_backfill_identity(
        existing=changed,
        expected=expected,
    ) == workflow.BACKFILL_STATE_CONFLICT
