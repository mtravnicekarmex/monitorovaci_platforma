from datetime import datetime
from types import SimpleNamespace

import pytest

from moduly.mereni.kalorimetry import current_snapshot_activation as activation


def _metrics(*, wape=0.2, coverage=0.9):
    return SimpleNamespace(
        wape=wape,
        mae=0.1,
        rmse=0.2,
        bias=0.01,
        coverage=coverage,
    )


def _dry_run():
    start = datetime(2026, 8, 3)
    end = datetime(2026, 8, 10)
    available = SimpleNamespace(
        identifier="available",
        available=True,
        selected_model_version=2,
        selected_metrics=_metrics(),
        candidate_audits=(
            SimpleNamespace(
                model_version=2,
                matched_fold_count=8,
                metrics=_metrics(),
                profile_available=True,
            ),
        ),
    )
    unavailable = SimpleNamespace(
        identifier="unavailable",
        available=False,
        selected_model_version=None,
        selected_metrics=None,
        candidate_audits=(),
    )
    return SimpleNamespace(
        deployable_catalog=SimpleNamespace(
            forecast_period=SimpleNamespace(start=start, end=end),
        ),
        forecast_run_at=datetime(2026, 8, 1, 22, 15),
        forecast_hdd_hour_count=168,
        latest_observation_at=datetime(2026, 8, 2, 23, 45),
        decisions=(available, unavailable),
        candidate_results=(
            SimpleNamespace(
                result=SimpleNamespace(
                    spec=SimpleNamespace(
                        model_version=2,
                        model_name="weather",
                        training_window_months=12,
                    ),
                    metrics=_metrics(),
                ),
                identifier_metrics=(available,),
            ),
        ),
    )


def test_scheduled_rebuild_verifies_exact_existing_period(monkeypatch):
    ensure_calls = []
    monkeypatch.setattr(
        activation,
        "_verify_exact_period_matches_dry_run",
        lambda **kwargs: {
            "selection_run_id": 7,
            "selected_model_snapshot_count": 1,
            "profile_snapshot_count": 672,
        },
    )
    monkeypatch.setattr(
        activation,
        "activate_kalorimetry_current_snapshots",
        lambda **kwargs: pytest.fail("Exact existing state must be a no-op."),
    )

    result = activation.rebuild_current_kalorimetry_snapshots(
        reference_time=datetime(2026, 8, 3, 8),
        dry_run_fn=lambda **kwargs: _dry_run(),
        ensure_kalorimetry_tables_fn=lambda: ensure_calls.append("kalorimetry"),
        ensure_selected_snapshot_table_fn=lambda: ensure_calls.append("selected"),
        ensure_profile_snapshot_table_fn=lambda: ensure_calls.append("profiles"),
    )

    assert result["action"] == "verified_existing"
    assert result["verified"] is True
    assert result["available_identifier_count"] == 1
    assert result["unavailable_identifier_count"] == 1
    assert ensure_calls == ["kalorimetry", "selected", "profiles"]


def test_activation_requires_confirmation_before_dry_run():
    def unexpected_dry_run(**kwargs):
        raise AssertionError("Dry-run must not start without confirmation.")

    with pytest.raises(PermissionError):
        activation.activate_kalorimetry_current_snapshots(
            reference_time=datetime(2026, 8, 3, 8),
            expected_period_start=datetime(2026, 8, 3),
            expected_period_end=datetime(2026, 8, 10),
            expected_available_identifier_count=1,
            expected_unavailable_identifier_count=1,
            confirm_activation=False,
            dry_run_fn=unexpected_dry_run,
        )


def test_activation_preconditions_accept_exact_approved_state():
    activation._validate_dry_run_for_activation(
        _dry_run(),
        expected_period_start=datetime(2026, 8, 3),
        expected_period_end=datetime(2026, 8, 10),
        expected_available_identifier_count=1,
        expected_unavailable_identifier_count=1,
    )


def test_activation_preconditions_reject_stale_observations():
    dry_run = _dry_run()
    dry_run.latest_observation_at = datetime(2026, 8, 2, 23, 30)

    with pytest.raises(RuntimeError, match="observations are stale"):
        activation._validate_dry_run_for_activation(
            dry_run,
            expected_period_start=datetime(2026, 8, 3),
            expected_period_end=datetime(2026, 8, 10),
            expected_available_identifier_count=1,
            expected_unavailable_identifier_count=1,
        )


def test_activation_preconditions_reject_changed_availability_counts():
    with pytest.raises(RuntimeError, match="availability counts changed"):
        activation._validate_dry_run_for_activation(
            _dry_run(),
            expected_period_start=datetime(2026, 8, 3),
            expected_period_end=datetime(2026, 8, 10),
            expected_available_identifier_count=2,
            expected_unavailable_identifier_count=0,
        )


def test_global_candidate_uses_aggregate_policy_order():
    baseline = SimpleNamespace(
        result=SimpleNamespace(
            spec=SimpleNamespace(model_version=1),
            metrics=_metrics(wape=0.4),
        )
    )
    weather = SimpleNamespace(
        result=SimpleNamespace(
            spec=SimpleNamespace(model_version=2),
            metrics=_metrics(wape=0.2),
        )
    )
    dry_run = SimpleNamespace(candidate_results=(baseline, weather))

    assert activation._select_global_candidate(dry_run).model_version == 2
