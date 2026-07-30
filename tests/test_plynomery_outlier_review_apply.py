import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.plynomery.database.outlier_review_apply import (
    _build_weather_adjusted_score_rows,
)
from moduly.mereni.plynomery.database import outlier_review_apply
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


def test_review_rebuild_uses_selection_only_for_active_model(monkeypatch):
    score_calls = []
    event_calls = []
    monkeypatch.setattr(
        outlier_review_apply,
        "_rebuild_measurements_for_review",
        lambda *_args: {"inserted_actual_rows": 1},
    )
    monkeypatch.setattr(
        outlier_review_apply,
        "get_runtime_model_version",
        lambda *, session: 2,
    )
    monkeypatch.setattr(
        outlier_review_apply,
        "get_candidate_model_versions",
        lambda: (1, 2),
    )

    def rebuild_scores(_session, **kwargs):
        score_calls.append(kwargs)
        return kwargs

    def rebuild_events(_session, **kwargs):
        event_calls.append(kwargs)
        return kwargs

    monkeypatch.setattr(
        outlier_review_apply,
        "_rebuild_scores_for_ident",
        rebuild_scores,
    )
    monkeypatch.setattr(
        outlier_review_apply,
        "_rebuild_events_for_ident",
        rebuild_events,
    )
    review = SimpleNamespace(
        identifikace="P1",
        date=datetime.datetime(2026, 7, 27),
    )

    result = outlier_review_apply._rebuild_after_review_update(
        object(),
        review,
    )

    assert [
        (
            call["model_version"],
            call["use_per_identifier_selection"],
        )
        for call in score_calls
    ] == [(1, False), (2, True)]
    assert [call["model_version"] for call in event_calls] == [1, 2]
    assert len(result["scores"]) == 2


def test_active_review_score_rebuild_uses_shared_selected_builder(monkeypatch):
    measurement = SimpleNamespace(id=10)
    selected_row = {
        "measurement_id": 10,
        "model_version": 2,
    }

    class FakeSession:
        def __init__(self):
            self.executed = []

        def execute(self, statement, params=None):
            self.executed.append((statement, params))
            return SimpleNamespace()

    session = FakeSession()
    monkeypatch.setattr(
        outlier_review_apply,
        "_load_measurements_for_score_rebuild",
        lambda *_args, **_kwargs: [measurement],
    )
    captured = {}

    def build_selected(_session, **kwargs):
        captured.update(kwargs)
        return [selected_row]

    monkeypatch.setattr(
        outlier_review_apply,
        "_build_per_identifier_selected_score_rows",
        build_selected,
    )

    result = outlier_review_apply._rebuild_scores_for_ident(
        session,
        identifikace="P1",
        model_version=2,
        start_date=datetime.datetime(2026, 7, 27),
        use_per_identifier_selection=True,
    )

    assert captured == {
        "measurements": [measurement],
        "output_model_version": 2,
    }
    assert result == {
        "model_version": 2,
        "inserted_scores": 1,
        "profile_source": "active_per_identifier_selection",
    }
    assert len(session.executed) == 2


def test_non_active_review_rebuild_retains_static_candidate_profile():
    profile = SimpleNamespace(
        identifikace="P1",
        interval_minutes=15,
        day_of_week=0,
        slot=8,
        mean=1.0,
        std=0.5,
        median=1.0,
        p10=0.5,
        p90=1.5,
    )
    measurement = SimpleNamespace(
        id=10,
        identifikace="P1",
        date=datetime.datetime(2026, 7, 27, 2),
        interval_minutes=15,
        day_of_week=0,
        slot=8,
        delta=2.0,
    )

    class Result:
        def __init__(self, rows=None):
            self.rows = rows or []

        def scalars(self):
            return self

        def all(self):
            return self.rows

    class FakeSession:
        def __init__(self):
            self.results = [
                Result(),
                Result([profile]),
                Result([measurement]),
                Result(),
            ]

        def execute(self, _statement, _params=None):
            return self.results.pop(0)

    result = outlier_review_apply._rebuild_scores_for_ident(
        FakeSession(),
        identifikace="P1",
        model_version=1,
        start_date=datetime.datetime(2026, 7, 27),
        use_per_identifier_selection=False,
    )

    assert result == {
        "model_version": 1,
        "inserted_scores": 1,
    }


def test_non_active_review_rebuild_retains_weather_candidate_profile(
    monkeypatch,
):
    profile = SimpleNamespace(
        identifikace="P1",
        interval_minutes=15,
        day_of_week=0,
        slot=8,
    )

    class Result:
        def scalars(self):
            return self

        def all(self):
            return [profile]

    class FakeSession:
        def __init__(self):
            self.execute_calls = 0

        def execute(self, _statement, _params=None):
            self.execute_calls += 1
            return Result()

    session = FakeSession()
    monkeypatch.setattr(
        outlier_review_apply,
        "_load_measurements_for_score_rebuild",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        outlier_review_apply,
        "_load_hdd_24h_by_measurement_id",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        outlier_review_apply,
        "_build_weather_adjusted_score_rows",
        lambda **_kwargs: [],
    )

    result = outlier_review_apply._rebuild_weather_adjusted_scores_for_ident(
        session,
        identifikace="P1",
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
        start_date=datetime.datetime(2026, 7, 27),
    )

    assert result == {
        "model_version": MODEL_VERSION_WEATHER_ADJUSTED,
        "inserted_scores": 0,
    }
    assert session.execute_calls == 1
