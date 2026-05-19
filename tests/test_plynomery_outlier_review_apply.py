import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.plynomery.database.outlier_review_apply import (
    _build_weather_adjusted_score_rows,
)
from moduly.mereni.plynomery.plynomery_prediction import MODEL_VERSION_WEATHER_ADJUSTED


def test_build_weather_adjusted_score_rows_uses_weather_profile_and_hdd():
    measurement = SimpleNamespace(
        id=10,
        identifikace="P1",
        date=datetime.datetime(2026, 1, 10, 12, 0, 0),
        interval_minutes=15,
        day_of_week=5,
        slot=48,
        delta=3.5,
    )
    profile = SimpleNamespace(
        identifikace="P1",
        interval_minutes=15,
        day_of_week=5,
        slot=48,
        base_mean=1.0,
        hdd_slope=0.2,
        residual_std=0.5,
        residual_median=0.1,
        residual_p10=-0.4,
        residual_p90=0.8,
    )

    rows = _build_weather_adjusted_score_rows(
        measurements=[measurement],
        profile_cache={("P1", 15, 5, 48): profile},
        hdd_24h_by_measurement_id={10: 4.0},
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["measurement_id"] == 10
    assert row["expected_mean"] == pytest.approx(1.8)
    assert row["expected_median"] == pytest.approx(1.9)
    assert row["expected_p10"] == pytest.approx(1.4)
    assert row["expected_p90"] == pytest.approx(2.6)
    assert row["z_score"] == pytest.approx(3.4)
    assert row["is_anomaly"] is True
    assert row["severity"] == "MEDIUM"
    assert row["model_version"] == MODEL_VERSION_WEATHER_ADJUSTED
    assert row["processed"] is False


def test_build_weather_adjusted_score_rows_skips_missing_hdd_or_profile():
    measurements = [
        SimpleNamespace(
            id=10,
            identifikace="P1",
            date=datetime.datetime(2026, 1, 10, 12, 0, 0),
            interval_minutes=15,
            day_of_week=5,
            slot=48,
            delta=3.5,
        ),
        SimpleNamespace(
            id=11,
            identifikace="P2",
            date=datetime.datetime(2026, 1, 10, 12, 15, 0),
            interval_minutes=15,
            day_of_week=5,
            slot=49,
            delta=2.0,
        ),
    ]
    profile = SimpleNamespace(
        identifikace="P1",
        interval_minutes=15,
        day_of_week=5,
        slot=48,
        base_mean=1.0,
        hdd_slope=0.2,
        residual_std=0.5,
        residual_median=0.1,
        residual_p10=-0.4,
        residual_p90=0.8,
    )

    assert _build_weather_adjusted_score_rows(
        measurements=measurements,
        profile_cache={("P1", 15, 5, 48): profile},
        hdd_24h_by_measurement_id={},
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
    ) == []
    assert _build_weather_adjusted_score_rows(
        measurements=measurements,
        profile_cache={},
        hdd_24h_by_measurement_id={10: 4.0, 11: 3.0},
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
    ) == []
