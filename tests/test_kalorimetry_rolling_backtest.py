from __future__ import annotations

import datetime

import pytest

from moduly.mereni.kalorimetry.calendar_baseline import (
    KalorimetryCalendarBaselineCandidate,
)
from moduly.mereni.kalorimetry.rolling_backtest import (
    persist_kalorimetry_rolling_metrics,
    run_kalorimetry_candidate_rolling_backtest,
)
from moduly.mereni.kalorimetry.weather_candidate import (
    KalorimetryWeatherCandidate,
)
from moduly.mereni.prediction import (
    PredictionBacktestPoint,
    PredictionCandidateSpec,
    PredictionObservation,
)


class StubCandidate:
    spec = PredictionCandidateSpec(
        medium_key="kalorimetry",
        model_version=1,
        model_key="stub",
        model_name="Stub",
        training_window_months=12,
    )

    def predict_validation(self, adapter, *, train_window, validation_window):
        del adapter, train_window
        return (
            PredictionBacktestPoint(
                identifier="K1",
                timestamp=validation_window.start,
                actual_value=2.0,
                predicted_mean=1.0,
            ),
            PredictionBacktestPoint(
                identifier="K1",
                timestamp=validation_window.start
                + datetime.timedelta(minutes=15),
                actual_value=0.0,
                predicted_mean=0.0,
            ),
            PredictionBacktestPoint(
                identifier="K2",
                timestamp=validation_window.start,
                actual_value=5.0,
                predicted_mean=None,
            ),
        )


def test_runner_aggregates_required_metrics_per_identifier_and_candidate():
    result = run_kalorimetry_candidate_rolling_backtest(
        adapter=object(),
        candidate=StubCandidate(),
        reference_end=datetime.datetime(2026, 7, 27),
        fold_count=2,
    )

    assert len(result.result.folds) == 2
    assert result.result.metrics.validation_total_count == 6
    assert result.result.metrics.matched_validation_count == 4
    assert result.result.metrics.coverage == pytest.approx(4 / 6)
    assert result.result.metrics.mae == pytest.approx(0.5)
    assert result.result.metrics.rmse == pytest.approx(2 ** -0.5)
    assert result.result.metrics.bias == pytest.approx(0.5)
    assert result.result.metrics.wape == pytest.approx(0.5)

    by_identifier = {
        metric.identifier: metric
        for metric in result.identifier_metrics
    }
    k1 = by_identifier["K1"]
    assert k1.rolling_backtest_fold_count == 2
    assert k1.matched_fold_count == 2
    assert k1.metrics.validation_total_count == 4
    assert k1.metrics.coverage == 1.0
    assert k1.metrics.wape == pytest.approx(0.5)
    k2 = by_identifier["K2"]
    assert k2.rolling_backtest_fold_count == 2
    assert k2.matched_fold_count == 0
    assert k2.metrics.coverage == 0.0
    assert k2.metrics.mae is None
    assert k2.metrics.wape is None


def observation(
    *,
    measurement_id: int,
    day_of_week: int,
    slot: int,
    value: float,
    hdd_24h: float | None = None,
) -> PredictionObservation:
    features = {"measurement_id": measurement_id}
    if hdd_24h is not None:
        features["hdd_24h"] = hdd_24h
    return PredictionObservation(
        identifier="K1",
        timestamp=datetime.datetime(2026, 7, 20)
        + datetime.timedelta(days=day_of_week, minutes=slot * 15),
        actual_value=value,
        interval_minutes=15,
        day_of_week=day_of_week,
        slot=slot,
        features=features,
    )


def complete_training(*, weather: bool) -> tuple[PredictionObservation, ...]:
    return tuple(
        observation(
            measurement_id=day * 10000 + slot * 100 + sample,
            day_of_week=day,
            slot=slot,
            value=1.0 + 0.5 * sample,
            hdd_24h=float(sample) if weather else None,
        )
        for day in range(7)
        for slot in range(96)
        for sample in range(8)
    )


def test_baseline_candidate_predicts_validation_from_train_only():
    train = complete_training(weather=False)
    validation = (
        observation(
            measurement_id=999001,
            day_of_week=0,
            slot=0,
            value=3.0,
        ),
    )

    class Adapter:
        def load_observations(self, window):
            return train if str(window.label).startswith("train") else validation

    points = KalorimetryCalendarBaselineCandidate().predict_validation(
        Adapter(),
        train_window=type("Window", (), {"label": "train"})(),
        validation_window=type("Window", (), {"label": "validation"})(),
    )

    assert len(points) == 1
    assert points[0].predicted_mean == pytest.approx(2.75)


def test_weather_candidate_missing_validation_hdd_reduces_coverage():
    train = complete_training(weather=True)
    validation_actual = (
        observation(
            measurement_id=999001,
            day_of_week=0,
            slot=0,
            value=3.0,
        ),
        observation(
            measurement_id=999002,
            day_of_week=0,
            slot=1,
            value=2.0,
        ),
    )
    validation_weather = (
        observation(
            measurement_id=999001,
            day_of_week=0,
            slot=0,
            value=3.0,
            hdd_24h=4.0,
        ),
    )

    class Adapter:
        def load_observations(self, window):
            del window
            return validation_actual

        def load_weather_observations(self, window):
            return (
                train
                if str(window.label).startswith("train")
                else validation_weather
            )

    points = KalorimetryWeatherCandidate().predict_validation(
        Adapter(),
        train_window=type("Window", (), {"label": "train"})(),
        validation_window=type("Window", (), {"label": "validation"})(),
    )

    assert len(points) == 2
    assert points[0].predicted_mean == pytest.approx(3.0)
    assert points[1].predicted_mean is None


def test_persistence_writes_one_metric_row_per_identifier():
    result = run_kalorimetry_candidate_rolling_backtest(
        adapter=object(),
        candidate=StubCandidate(),
        reference_end=datetime.datetime(2026, 7, 27),
        fold_count=1,
    )

    class FakeSession:
        def __init__(self):
            self.added = None
            self.executed = []

        def add(self, row):
            self.added = row
            row.id = 17

        def flush(self):
            pass

        def execute(self, statement, rows):
            self.executed.append((statement, rows))

    session = FakeSession()
    count = persist_kalorimetry_rolling_metrics(
        session,
        candidate_result=result,
        reference_end=datetime.datetime(2026, 7, 27),
    )

    assert count == 2
    assert session.added.model_version == 1
    assert session.added.fold_count == 1
    assert len(session.executed) == 1
    rows = session.executed[0][1]
    assert {row["identifikace"] for row in rows} == {"K1", "K2"}
    assert all(row["run_id"] == 17 for row in rows)
