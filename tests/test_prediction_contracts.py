import datetime

import pytest

from moduly.mereni.prediction import (
    PredictionCandidateResult,
    PredictionCandidateSpec,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionForecastPeriodDefinition,
    PredictionMetricSummary,
    PredictionRebuildWindows,
    PredictionSelectedModelDecision,
    PredictionSelectionFallbackReason,
    PredictionTimeWindow,
)


def test_prediction_time_window_requires_ordered_bounds():
    with pytest.raises(ValueError, match="end must be after start"):
        PredictionTimeWindow(
            start=datetime.datetime(2026, 7, 8, 12, 0),
            end=datetime.datetime(2026, 7, 8, 12, 0),
        )


def test_prediction_candidate_spec_records_selection_eligibility():
    spec = PredictionCandidateSpec(
        medium_key="vodomery",
        model_version=4,
        model_key="seasonal_yearly_blend",
        model_name="Model 4 - seasonal yearly blend",
        training_window_months=12,
        selection_enabled=False,
    )

    assert spec.medium_key == "vodomery"
    assert spec.model_version == 4
    assert spec.training_window_months == 12
    assert spec.validation_window_months == 1
    assert spec.selection_enabled is False


def test_prediction_candidate_result_serializes_metrics_and_metadata():
    spec = PredictionCandidateSpec(
        medium_key="vodomery",
        model_version=1,
        model_key="baseline",
        model_name="Model 1 - baseline",
        training_window_months=3,
    )
    result = PredictionCandidateResult(
        spec=spec,
        metrics=PredictionMetricSummary(
            validation_total_count=100,
            matched_validation_count=95,
            coverage=0.9512349,
            mae=0.1234567,
            rmse=0.2345678,
            bias=-0.0345678,
            wape=0.156789,
        ),
        profile_count=672,
        selected_device_count=42,
        validation_candidate_count=126,
    )

    assert result.to_dict(selected=True) == {
        "model_version": 1,
        "model_key": "baseline",
        "model_name": "Model 1 - baseline",
        "selection_enabled": True,
        "profile_count": 672,
        "selected_device_count": 42,
        "validation_candidate_count": 126,
        "selected": True,
        "validation_total_count": 100,
        "matched_validation_count": 95,
        "coverage": 0.951235,
        "mae": 0.123457,
        "rmse": 0.234568,
        "bias": -0.034568,
        "wape": 0.156789,
    }


def test_prediction_rebuild_windows_groups_train_validation_and_deploy_windows():
    train = PredictionTimeWindow(
        start=datetime.datetime(2026, 1, 1),
        end=datetime.datetime(2026, 4, 1),
        label="train",
    )
    validation = PredictionTimeWindow(
        start=datetime.datetime(2026, 4, 1),
        end=datetime.datetime(2026, 5, 1),
        label="validation",
    )
    deploy = PredictionTimeWindow(
        start=datetime.datetime(2026, 1, 1),
        end=datetime.datetime(2026, 5, 1),
        label="deploy",
    )

    windows = PredictionRebuildWindows(
        train=train,
        validation=validation,
        deploy=deploy,
    )

    assert windows.train.label == "train"
    assert windows.validation.start == train.end
    assert windows.deploy.end == validation.end


def test_prediction_forecast_period_definition_records_cadence_and_length():
    weekly = PredictionForecastPeriodDefinition(
        cadence=PredictionForecastCadence.WEEKLY,
        period_count=1,
        label="weekly_vodomery",
    )
    monthly = PredictionForecastPeriodDefinition(
        cadence="monthly",
        period_count=1,
        label="monthly_elektromery",
    )

    assert weekly.to_dict() == {
        "cadence": "weekly",
        "period_count": 1,
        "label": "weekly_vodomery",
    }
    assert monthly.cadence is PredictionForecastCadence.MONTHLY


def test_prediction_forecast_period_requires_ordered_bounds():
    with pytest.raises(ValueError, match="forecast period end must be after start"):
        PredictionForecastPeriod(
            start=datetime.datetime(2026, 7, 13),
            end=datetime.datetime(2026, 7, 13),
            cadence=PredictionForecastCadence.WEEKLY,
        )


def test_prediction_forecast_period_serializes_and_converts_to_time_window():
    period = PredictionForecastPeriod(
        start=datetime.datetime(2026, 7, 13),
        end=datetime.datetime(2026, 7, 20),
        cadence="weekly",
        label="2026-W29",
    )

    assert period.cadence is PredictionForecastCadence.WEEKLY
    assert period.to_dict() == {
        "start": datetime.datetime(2026, 7, 13),
        "end": datetime.datetime(2026, 7, 20),
        "cadence": "weekly",
        "label": "2026-W29",
    }
    assert period.to_time_window() == PredictionTimeWindow(
        start=datetime.datetime(2026, 7, 13),
        end=datetime.datetime(2026, 7, 20),
        label="2026-W29",
    )


def test_prediction_selected_model_decision_serializes_selected_candidate():
    decision = PredictionSelectedModelDecision(
        medium_key="vodomery",
        identifier="L1_V1",
        forecast_period=PredictionForecastPeriod(
            start=datetime.datetime(2026, 7, 13),
            end=datetime.datetime(2026, 7, 20),
            cadence=PredictionForecastCadence.WEEKLY,
            label="2026-W29",
        ),
        selection_run_id=29,
        selected_model_version=2,
        selected_model_key="adaptive_strategy",
        selected_model_name="Model 2 - adaptive strategy",
        global_model_version=3,
        global_model_key="recency_weighted_blend",
        global_model_name="Model 3 - recency weighted blend",
        metrics=PredictionMetricSummary(
            validation_total_count=100,
            matched_validation_count=100,
            coverage=1.0,
            mae=0.1,
            rmse=0.2,
            bias=-0.03,
            wape=0.15,
        ),
        created_at=datetime.datetime(2026, 7, 9, 8, 0),
        metadata={"source": "dry_run"},
    )

    assert decision.uses_fallback is False
    assert decision.to_dict() == {
        "medium_key": "vodomery",
        "identifier": "L1_V1",
        "forecast_period": {
            "start": datetime.datetime(2026, 7, 13),
            "end": datetime.datetime(2026, 7, 20),
            "cadence": "weekly",
            "label": "2026-W29",
        },
        "selection_run_id": 29,
        "selected_model_version": 2,
        "selected_model_key": "adaptive_strategy",
        "selected_model_name": "Model 2 - adaptive strategy",
        "global_model_version": 3,
        "global_model_key": "recency_weighted_blend",
        "global_model_name": "Model 3 - recency weighted blend",
        "fallback_reason": "none",
        "uses_fallback": False,
        "metrics": {
            "validation_total_count": 100,
            "matched_validation_count": 100,
            "coverage": 1.0,
            "mae": 0.1,
            "rmse": 0.2,
            "bias": -0.03,
            "wape": 0.15,
        },
        "created_at": datetime.datetime(2026, 7, 9, 8, 0),
        "metadata": {"source": "dry_run"},
    }


def test_prediction_selected_model_decision_supports_global_fallback():
    decision = PredictionSelectedModelDecision(
        medium_key="vodomery",
        identifier="L1_V1",
        forecast_period=PredictionForecastPeriod(
            start=datetime.datetime(2026, 7, 13),
            end=datetime.datetime(2026, 7, 20),
            cadence=PredictionForecastCadence.WEEKLY,
        ),
        selection_run_id=29,
        selected_model_version=3,
        selected_model_key="recency_weighted_blend",
        selected_model_name="Model 3 - recency weighted blend",
        global_model_version=3,
        global_model_key="recency_weighted_blend",
        global_model_name="Model 3 - recency weighted blend",
        fallback_reason=PredictionSelectionFallbackReason.NO_ELIGIBLE_CANDIDATE,
    )

    assert decision.uses_fallback is True
    assert decision.to_dict()["fallback_reason"] == "no_eligible_candidate"


def test_prediction_selected_model_decision_rejects_non_global_fallback():
    with pytest.raises(ValueError, match="fallback decisions must select"):
        PredictionSelectedModelDecision(
            medium_key="vodomery",
            identifier="L1_V1",
            forecast_period=PredictionForecastPeriod(
                start=datetime.datetime(2026, 7, 13),
                end=datetime.datetime(2026, 7, 20),
                cadence=PredictionForecastCadence.WEEKLY,
            ),
            selection_run_id=29,
            selected_model_version=2,
            selected_model_key="adaptive_strategy",
            selected_model_name="Model 2 - adaptive strategy",
            global_model_version=3,
            global_model_key="recency_weighted_blend",
            global_model_name="Model 3 - recency weighted blend",
            fallback_reason=PredictionSelectionFallbackReason.NO_ELIGIBLE_CANDIDATE,
        )
