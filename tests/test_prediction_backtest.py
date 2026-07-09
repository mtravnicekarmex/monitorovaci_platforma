import datetime

import pytest

from moduly.mereni.prediction import (
    CandidateProfileBuildResult,
    PredictionBacktestPoint,
    PredictionCandidateSpec,
    PredictionProfilePoint,
    PredictionTimeWindow,
    build_rolling_weekly_folds,
    calculate_metric_summary,
    run_rolling_weekly_backtest,
    subtract_months,
)


class SyntheticAdapter:
    medium_key = "synthetic"

    def get_active_model_version(self) -> int:
        return 1

    def load_observations(self, window: PredictionTimeWindow, *, identifiers=None):
        return []

    def replace_profiles(
        self,
        *,
        model_version: int,
        profiles,
    ) -> CandidateProfileBuildResult:
        profile_tuple = tuple(profiles)
        assert all(isinstance(profile, PredictionProfilePoint) for profile in profile_tuple)
        return CandidateProfileBuildResult(
            model_version=model_version,
            profile_count=len(profile_tuple),
        )

    def count_profiles(self, model_version: int) -> int:
        return 0


class SyntheticWeeklyCandidate:
    spec = PredictionCandidateSpec(
        medium_key="synthetic",
        model_version=1,
        model_key="weekly_mean",
        model_name="Synthetic weekly mean",
        training_window_months=3,
    )

    def __init__(self) -> None:
        self.calls: list[tuple[PredictionTimeWindow, PredictionTimeWindow]] = []

    def predict_validation(
        self,
        adapter: SyntheticAdapter,
        *,
        train_window: PredictionTimeWindow,
        validation_window: PredictionTimeWindow,
    ) -> list[PredictionBacktestPoint]:
        assert adapter.medium_key == "synthetic"
        self.calls.append((train_window, validation_window))
        return [
            PredictionBacktestPoint(
                identifier="A",
                timestamp=validation_window.start,
                actual_value=10.0,
                predicted_mean=9.0,
            ),
            PredictionBacktestPoint(
                identifier="B",
                timestamp=validation_window.start + datetime.timedelta(days=1),
                actual_value=20.0,
                predicted_mean=19.0,
            ),
        ]


def test_subtract_months_clamps_to_valid_month_day():
    assert subtract_months(datetime.datetime(2026, 3, 31, 8, 0), 1) == datetime.datetime(
        2026,
        2,
        28,
        8,
        0,
    )


def test_build_rolling_weekly_folds_returns_oldest_to_newest_folds():
    folds = build_rolling_weekly_folds(
        reference_end=datetime.datetime(2026, 7, 6),
        fold_count=3,
        training_window_months=3,
    )

    assert [(fold.validation.start, fold.validation.end) for fold in folds] == [
        (datetime.datetime(2026, 6, 15), datetime.datetime(2026, 6, 22)),
        (datetime.datetime(2026, 6, 22), datetime.datetime(2026, 6, 29)),
        (datetime.datetime(2026, 6, 29), datetime.datetime(2026, 7, 6)),
    ]
    assert folds[0].fold_index == 1
    assert folds[0].train.start == datetime.datetime(2026, 3, 15)
    assert folds[0].train.end == folds[0].validation.start
    assert folds[-1].train.start == datetime.datetime(2026, 3, 29)


def test_build_rolling_weekly_folds_rejects_empty_fold_count():
    with pytest.raises(ValueError, match="fold count"):
        build_rolling_weekly_folds(
            reference_end=datetime.datetime(2026, 7, 6),
            fold_count=0,
            training_window_months=3,
        )


def test_calculate_metric_summary_counts_unmatched_points_in_coverage():
    timestamp = datetime.datetime(2026, 7, 1)
    summary = calculate_metric_summary(
        [
            PredictionBacktestPoint("A", timestamp, actual_value=10.0, predicted_mean=8.0),
            PredictionBacktestPoint("A", timestamp, actual_value=5.0, predicted_mean=7.0),
            PredictionBacktestPoint("A", timestamp, actual_value=3.0, predicted_mean=None),
        ]
    )

    assert summary.to_dict() == {
        "validation_total_count": 3,
        "matched_validation_count": 2,
        "coverage": 0.666667,
        "mae": 2.0,
        "rmse": 2.0,
        "bias": 0.0,
        "wape": 0.266667,
    }


def test_calculate_metric_summary_keeps_wape_empty_when_actual_sum_is_zero():
    timestamp = datetime.datetime(2026, 7, 1)
    summary = calculate_metric_summary(
        [
            PredictionBacktestPoint("A", timestamp, actual_value=0.0, predicted_mean=1.0),
        ]
    )

    assert summary.validation_total_count == 1
    assert summary.matched_validation_count == 1
    assert summary.mae == 1.0
    assert summary.rmse == 1.0
    assert summary.bias == -1.0
    assert summary.wape is None


def test_run_rolling_weekly_backtest_aggregates_synthetic_fold_metrics():
    candidate = SyntheticWeeklyCandidate()
    result = run_rolling_weekly_backtest(
        adapter=SyntheticAdapter(),
        candidate=candidate,
        reference_end=datetime.datetime(2026, 7, 6),
        fold_count=2,
    )

    assert len(result.folds) == 2
    assert len(candidate.calls) == 2
    assert candidate.calls[0][0].start == datetime.datetime(2026, 3, 22)
    assert candidate.calls[0][1].start == datetime.datetime(2026, 6, 22)
    assert result.to_dict() == {
        "model_version": 1,
        "model_key": "weekly_mean",
        "model_name": "Synthetic weekly mean",
        "selection_enabled": True,
        "fold_count": 2,
        "validation_total_count": 4,
        "matched_validation_count": 4,
        "coverage": 1.0,
        "mae": 1.0,
        "rmse": 1.0,
        "bias": 1.0,
        "wape": 0.066667,
    }
    assert result.folds[0].to_dict()["prediction_count"] == 2
