import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.plynomery.plynomery_prediction import (
    MODEL_VERSION_BASELINE,
    build_rebuild_windows,
    get_candidate_model_versions,
    get_runtime_model_version,
)


def test_plynomery_build_rebuild_windows_reserves_last_week_for_validation():
    reference_time = datetime.datetime(2026, 4, 10, 6, 10, 5)

    windows = build_rebuild_windows(reference_time=reference_time)

    assert windows.deploy_end == reference_time
    assert windows.validation_end == reference_time
    assert windows.validation_start == reference_time - datetime.timedelta(days=7)
    assert windows.train_start == reference_time - datetime.timedelta(days=120)
    assert windows.train_end == windows.validation_start


def test_plynomery_candidate_model_versions_exposes_baseline_only():
    assert get_candidate_model_versions() == (MODEL_VERSION_BASELINE,)


def test_plynomery_runtime_model_version_is_baseline():
    assert get_runtime_model_version() == MODEL_VERSION_BASELINE
