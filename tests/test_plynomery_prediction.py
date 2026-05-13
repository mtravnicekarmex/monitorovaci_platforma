import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.plynomery import plynomery_prediction
from moduly.mereni.plynomery.plynomery_prediction import (
    MODEL_VERSION_BASELINE,
    MODEL_VERSION_WEATHER_ADJUSTED,
    ModelPerformanceSummary,
    build_rebuild_windows,
    get_candidate_model_versions,
    select_best_model_summary,
)


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSelectionSession:
    def __init__(self, selected_model_version):
        self.selected_model_version = selected_model_version

    def execute(self, statement):
        return FakeScalarResult(self.selected_model_version)


def test_plynomery_build_rebuild_windows_reserves_last_week_for_validation():
    reference_time = datetime.datetime(2026, 4, 10, 6, 10, 5)

    windows = build_rebuild_windows(reference_time=reference_time)

    assert windows.deploy_end == reference_time
    assert windows.validation_end == reference_time
    assert windows.validation_start == reference_time - datetime.timedelta(days=7)
    assert windows.train_start == reference_time - datetime.timedelta(days=120)
    assert windows.train_end == windows.validation_start


def test_plynomery_candidate_model_versions_includes_weather_adjusted_candidate():
    assert get_candidate_model_versions() == (
        MODEL_VERSION_BASELINE,
        MODEL_VERSION_WEATHER_ADJUSTED,
    )


def test_plynomery_runtime_model_version_uses_latest_selection(monkeypatch):
    monkeypatch.setattr(plynomery_prediction, "ensure_prediction_tables", lambda: None)

    selected = plynomery_prediction.get_runtime_model_version(
        session=FakeSelectionSession(MODEL_VERSION_WEATHER_ADJUSTED)
    )

    assert selected == MODEL_VERSION_WEATHER_ADJUSTED


def test_plynomery_runtime_model_version_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(plynomery_prediction, "ensure_prediction_tables", lambda: None)

    selected = plynomery_prediction.get_runtime_model_version(
        session=FakeSelectionSession(None)
    )

    assert selected == MODEL_VERSION_BASELINE


def test_plynomery_select_best_model_summary_prefers_coverage_before_lower_error():
    low_coverage = ModelPerformanceSummary(
        model_version=MODEL_VERSION_BASELINE,
        model_name="Model 1",
        validation_total_count=100,
        matched_validation_count=40,
        coverage=0.4,
        mae=0.1,
        rmse=0.2,
        bias=0.01,
        profile_count=500,
    )
    high_coverage = ModelPerformanceSummary(
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
        model_name="Model 2",
        validation_total_count=100,
        matched_validation_count=95,
        coverage=0.95,
        mae=0.15,
        rmse=0.25,
        bias=0.02,
        profile_count=520,
    )

    selected = select_best_model_summary((low_coverage, high_coverage))

    assert selected == high_coverage
