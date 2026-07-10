import datetime
from dataclasses import dataclass

import pytest

from moduly.mereni.prediction import (
    PredictionCandidateRegistry,
    PredictionCandidateResult,
    PredictionCandidateSpec,
    PredictionForecastCadence,
    PredictionForecastPeriodDefinition,
    PredictionMetricSummary,
    PredictionPipelineRunner,
    PredictionPipelineSettings,
    build_prediction_rebuild_windows,
    select_best_prediction_candidate,
)


@dataclass(frozen=True)
class SyntheticPlugin:
    spec: PredictionCandidateSpec


def _spec(
    model_version: int,
    *,
    medium_key: str = "synthetic",
    model_key: str | None = None,
    training_window_months: int = 3,
    selection_enabled: bool = True,
) -> PredictionCandidateSpec:
    return PredictionCandidateSpec(
        medium_key=medium_key,
        model_version=model_version,
        model_key=model_key or f"model_{model_version}",
        model_name=f"Model {model_version}",
        training_window_months=training_window_months,
        selection_enabled=selection_enabled,
    )


def _result(
    spec: PredictionCandidateSpec,
    *,
    coverage: float,
    mae: float | None,
    rmse: float | None = 1.0,
    bias: float | None = 0.0,
    total: int = 100,
    matched: int = 90,
) -> PredictionCandidateResult:
    return PredictionCandidateResult(
        spec=spec,
        metrics=PredictionMetricSummary(
            validation_total_count=total,
            matched_validation_count=matched,
            coverage=coverage,
            mae=mae,
            rmse=rmse,
            bias=bias,
        ),
        profile_count=10,
    )


def test_prediction_candidate_registry_validates_medium_and_uniqueness():
    registry = PredictionCandidateRegistry(
        medium_key="synthetic",
        plugins=(
            SyntheticPlugin(_spec(1, model_key="baseline")),
            SyntheticPlugin(_spec(2, model_key="adaptive", selection_enabled=False)),
        ),
    )

    assert registry.list_model_versions() == (1, 2)
    assert registry.list_model_versions(include_non_selectable=False) == (1,)
    assert registry.get_by_model_version(2).spec.model_key == "adaptive"

    with pytest.raises(ValueError, match="Duplicate prediction model version"):
        PredictionCandidateRegistry(
            medium_key="synthetic",
            plugins=(SyntheticPlugin(_spec(1)), SyntheticPlugin(_spec(1, model_key="v1b"))),
        )

    with pytest.raises(ValueError, match="medium key does not match"):
        PredictionCandidateRegistry(
            medium_key="synthetic",
            plugins=(SyntheticPlugin(_spec(1, medium_key="other")),),
        )


def test_prediction_pipeline_runner_builds_windows_and_forecast_period_from_metadata():
    settings = PredictionPipelineSettings(
        medium_key="synthetic",
        forecast_period_definition=PredictionForecastPeriodDefinition(
            cadence=PredictionForecastCadence.MONTHLY,
            period_count=1,
        ),
        default_training_window_months=6,
        default_validation_window_months=1,
        candidate_coverage_threshold=0.9,
    )
    registry = PredictionCandidateRegistry(
        medium_key="synthetic",
        plugins=(SyntheticPlugin(_spec(1, training_window_months=12)),),
    )
    runner = PredictionPipelineRunner(settings=settings, registry=registry)
    reference_time = datetime.datetime(2026, 7, 15, 9, 30, 5)

    default_windows = runner.build_rebuild_windows(reference_time=reference_time)
    candidate_windows = runner.build_rebuild_windows(
        reference_time=reference_time,
        spec=registry.get_by_model_version(1).spec,
    )
    period = runner.build_forecast_period(reference_time=reference_time)
    candidate_runs = runner.build_candidate_runs(reference_time=reference_time)

    assert default_windows.train.start == datetime.datetime(2025, 12, 15, 9, 30, 5)
    assert candidate_windows.train.start == datetime.datetime(2025, 6, 15, 9, 30, 5)
    assert candidate_runs[0].plugin.spec.model_version == 1
    assert candidate_runs[0].windows.train.start == candidate_windows.train.start
    assert period.start == datetime.datetime(2026, 8, 1)
    assert period.end == datetime.datetime(2026, 9, 1)


def test_build_prediction_rebuild_windows_rejects_empty_windows():
    with pytest.raises(ValueError, match="Training window"):
        build_prediction_rebuild_windows(
            reference_time=datetime.datetime(2026, 7, 1),
            training_window_months=0,
            validation_window_months=1,
        )


def test_select_best_prediction_candidate_uses_shared_selection_rules():
    low_coverage = _result(
        _spec(1),
        coverage=0.4,
        mae=0.01,
        matched=40,
    )
    high_coverage = _result(
        _spec(2),
        coverage=0.95,
        mae=0.2,
        matched=95,
    )
    measured_only = _result(
        _spec(3, selection_enabled=False),
        coverage=1.0,
        mae=0.001,
        matched=100,
    )
    invalid_metrics = _result(
        _spec(4),
        coverage=1.0,
        mae=None,
        matched=100,
    )

    assert (
        select_best_prediction_candidate(
            (low_coverage, high_coverage, measured_only, invalid_metrics),
            coverage_threshold=0.85,
        )
        == high_coverage
    )


def test_prediction_pipeline_runner_selects_with_configured_threshold():
    runner = PredictionPipelineRunner(
        settings=PredictionPipelineSettings(
            medium_key="synthetic",
            forecast_period_definition=PredictionForecastPeriodDefinition(
                cadence=PredictionForecastCadence.WEEKLY,
            ),
            default_training_window_months=3,
            candidate_coverage_threshold=0.95,
        ),
        registry=PredictionCandidateRegistry(
            medium_key="synthetic",
            plugins=(SyntheticPlugin(_spec(1)), SyntheticPlugin(_spec(2))),
        ),
    )
    lower_error = _result(_spec(1), coverage=0.9, mae=0.1, matched=90)
    higher_coverage = _result(_spec(2), coverage=0.96, mae=0.2, matched=96)

    assert runner.select_best_candidate((lower_error, higher_coverage)) == higher_coverage
