import datetime
from contextlib import nullcontext
from dataclasses import replace

import pytest

from moduly.mereni.kalorimetry.calendar_baseline import (
    KalorimetryCalendarBaselineCandidate,
)
from moduly.mereni.kalorimetry.deployable_catalog import (
    PROFILE_INSUFFICIENT_HISTORY,
    KalorimetryDeployableCandidateCatalog,
    KalorimetryDeployableProfileEntry,
)
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    build_kalorimetry_weekly_forecast_period,
)
from moduly.mereni.kalorimetry.selection import (
    FALLBACK_NONE,
    KalorimetryDryRunSelectionDecision,
)
from moduly.mereni.kalorimetry.snapshot_persistence import (
    build_kalorimetry_snapshot_persistence_plan,
    persist_kalorimetry_snapshot_plan,
)
from moduly.mereni.prediction import (
    PredictionMetricSummary,
    PredictionObservation,
    PredictionSelectionFallbackReason,
)


def _observations(identifier="K1"):
    start = datetime.datetime(2025, 1, 6)
    return tuple(
        PredictionObservation(
            identifier=identifier,
            timestamp=start + datetime.timedelta(weeks=week, minutes=15 * slot),
            actual_value=float(slot % 7),
            interval_minutes=15,
            day_of_week=(slot // 96),
            slot=(slot % 96),
        )
        for week in range(8)
        for slot in range(672)
    )


def _catalog():
    period = build_kalorimetry_weekly_forecast_period(
        datetime.datetime(2026, 7, 29)
    )
    candidate = KalorimetryCalendarBaselineCandidate()
    profiles = candidate.build_profile_catalog(_observations()).profiles
    return KalorimetryDeployableCandidateCatalog(
        forecast_period=period,
        entries=(
            KalorimetryDeployableProfileEntry(
                identifier="K1",
                model_version=candidate.spec.model_version,
                model_key=candidate.spec.model_key,
                available=True,
                reason="available",
                profiles=profiles,
            ),
        ),
    )


def _decision(catalog=None):
    resolved_catalog = catalog or _catalog()
    spec = KalorimetryCalendarBaselineCandidate().spec
    return KalorimetryDryRunSelectionDecision(
        identifier="K1",
        forecast_period_start=resolved_catalog.forecast_period.start,
        forecast_period_end=resolved_catalog.forecast_period.end,
        available=True,
        selected_model_version=spec.model_version,
        selected_model_key=spec.model_key,
        selected_model_name=spec.model_name,
        fallback_reason=FALLBACK_NONE,
        selected_metrics=PredictionMetricSummary(
            validation_total_count=100,
            matched_validation_count=90,
            coverage=0.9,
            mae=1.0,
            rmse=2.0,
            bias=-0.2,
            wape=0.3,
        ),
        candidate_audits=(),
    )


def _plan(**kwargs):
    catalog = kwargs.pop("catalog", _catalog())
    return build_kalorimetry_snapshot_persistence_plan(
        dry_run_decisions=kwargs.pop("decisions", (_decision(catalog),)),
        deployable_catalog=catalog,
        global_candidate=KalorimetryCalendarBaselineCandidate().spec,
        selection_run_id=7,
        archive_run_id="kalorimetry-selection-7",
        **kwargs,
    )


def test_build_plan_has_one_shared_decision_and_complete_profile():
    plan = _plan()

    assert plan.available_identifier_count == 1
    assert plan.profile_point_count == 672
    assert plan.unavailable_identifiers == ()
    decision = plan.decisions[0]
    assert decision.medium_key == "kalorimetry"
    assert decision.identifier == "K1"
    assert decision.selection_run_id == 7
    assert decision.fallback_reason is PredictionSelectionFallbackReason.NONE
    assert {row["selection_run_id"] for row in plan.profile_rows} == {7}
    assert {row["model_version"] for row in plan.profile_rows} == {1}


def test_build_plan_preserves_detailed_profile_fallback_in_metadata():
    decision = replace(
        _decision(),
        fallback_reason="missing_forecast_weather",
    )

    plan = _plan(decisions=(decision,))

    assert (
        plan.decisions[0].fallback_reason
        is PredictionSelectionFallbackReason.MISSING_PROFILE
    )
    assert (
        plan.decisions[0].metadata["selection_fallback_detail"]
        == "missing_forecast_weather"
    )


def test_available_selection_without_profile_fails_before_plan_exists():
    catalog = _catalog()
    unavailable_entry = replace(
        catalog.entries[0],
        available=False,
        reason=PROFILE_INSUFFICIENT_HISTORY,
        profiles=(),
    )
    incomplete_catalog = replace(catalog, entries=(unavailable_entry,))

    with pytest.raises(RuntimeError, match="missing its deployable profile"):
        _plan(
            catalog=incomplete_catalog,
            decisions=(_decision(incomplete_catalog),),
        )


def test_unavailable_identifier_is_not_persisted_as_selected_model():
    catalog = _catalog()
    unavailable = replace(
        _decision(catalog),
        available=False,
        selected_model_version=None,
        selected_model_key=None,
        selected_model_name=None,
        selected_metrics=None,
        fallback_reason=PROFILE_INSUFFICIENT_HISTORY,
    )

    plan = _plan(catalog=catalog, decisions=(unavailable,))

    assert plan.decisions == ()
    assert plan.profile_rows == ()
    assert plan.unavailable_identifiers == ("K1",)


def test_unavailable_identifier_cannot_carry_selected_identity():
    unavailable = replace(
        _decision(),
        available=False,
        fallback_reason=PROFILE_INSUFFICIENT_HISTORY,
    )

    with pytest.raises(ValueError, match="must not identify"):
        _plan(decisions=(unavailable,))


def test_batch_rejects_duplicate_identifiers():
    decision = _decision()

    with pytest.raises(ValueError, match="duplicate identifiers"):
        _plan(decisions=(decision, decision))


def test_batch_rejects_period_mismatch():
    decision = replace(
        _decision(),
        forecast_period_end=datetime.datetime(2026, 8, 10),
    )

    with pytest.raises(ValueError, match="periods differ"):
        _plan(decisions=(decision,))


def test_persistence_uses_one_savepoint_and_does_not_commit(monkeypatch):
    calls = []

    class Session:
        def begin_nested(self):
            calls.append("begin_nested")
            return nullcontext()

        def flush(self):
            calls.append("flush")

        def commit(self):
            raise AssertionError("Persistence helper must not commit.")

    monkeypatch.setattr(
        "moduly.mereni.kalorimetry.snapshot_persistence."
        "persist_selected_model_decisions",
        lambda session, decisions, selection_mode: calls.append("decisions") or 1,
    )
    monkeypatch.setattr(
        "moduly.mereni.kalorimetry.snapshot_persistence."
        "persist_prediction_profile_snapshots",
        lambda session, rows: calls.append("profiles") or 672,
    )

    result = persist_kalorimetry_snapshot_plan(Session(), _plan())

    assert calls == ["begin_nested", "decisions", "profiles", "flush"]
    assert result.selected_model_snapshot_count == 1
    assert result.profile_snapshot_count == 672
