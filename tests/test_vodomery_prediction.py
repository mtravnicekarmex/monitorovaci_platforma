import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.vodomery_prediction import (
    ModelPerformanceSummary,
    build_rebuild_windows,
    get_candidate_model_versions,
    select_best_model_summary,
)


def test_build_rebuild_windows_reserves_last_week_for_validation():
    reference_time = datetime.datetime(2026, 4, 10, 6, 10, 5)

    windows = build_rebuild_windows(reference_time=reference_time)

    assert windows.deploy_end == reference_time
    assert windows.validation_end == reference_time
    assert windows.validation_start == reference_time - datetime.timedelta(days=7)
    assert windows.train_start == reference_time - datetime.timedelta(days=120)
    assert windows.train_end == windows.validation_start


def test_get_candidate_model_versions_includes_new_hierarchical_candidate():
    assert get_candidate_model_versions() == (1, 2, 3)


def test_select_best_model_summary_prefers_coverage_before_lower_error():
    low_coverage = ModelPerformanceSummary(
        model_version=1,
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
        model_version=2,
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
