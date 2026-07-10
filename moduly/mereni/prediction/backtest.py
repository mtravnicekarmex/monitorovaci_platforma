from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt
from typing import Protocol, Sequence

from moduly.mereni.prediction.contracts import (
    PredictionCandidateSpec,
    PredictionForecastCadence,
    PredictionForecastPeriodDefinition,
    PredictionMediaAdapter,
    PredictionMetricSummary,
    PredictionTimeWindow,
)
from moduly.mereni.prediction.periods import month_start, subtract_months


@dataclass(frozen=True)
class PredictionBacktestFold:
    fold_index: int
    train: PredictionTimeWindow
    validation: PredictionTimeWindow


@dataclass(frozen=True)
class PredictionBacktestPoint:
    identifier: str
    timestamp: datetime
    actual_value: float
    predicted_mean: float | None


@dataclass(frozen=True)
class PredictionBacktestFoldResult:
    fold: PredictionBacktestFold
    metrics: PredictionMetricSummary
    points: tuple[PredictionBacktestPoint, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "fold_index": self.fold.fold_index,
            "train_start": self.fold.train.start,
            "train_end": self.fold.train.end,
            "validation_start": self.fold.validation.start,
            "validation_end": self.fold.validation.end,
            "prediction_count": len(self.points),
            **self.metrics.to_dict(),
        }


@dataclass(frozen=True)
class PredictionBacktestResult:
    spec: PredictionCandidateSpec
    folds: tuple[PredictionBacktestFoldResult, ...]
    metrics: PredictionMetricSummary

    def to_dict(self) -> dict[str, object]:
        return {
            "model_version": self.spec.model_version,
            "model_key": self.spec.model_key,
            "model_name": self.spec.model_name,
            "selection_enabled": self.spec.selection_enabled,
            "fold_count": len(self.folds),
            **self.metrics.to_dict(),
        }


class RollingBacktestCandidate(Protocol):
    spec: PredictionCandidateSpec

    def predict_validation(
        self,
        adapter: PredictionMediaAdapter,
        *,
        train_window: PredictionTimeWindow,
        validation_window: PredictionTimeWindow,
    ) -> Sequence[PredictionBacktestPoint]:
        ...


def build_rolling_weekly_folds(
    *,
    reference_end: datetime,
    fold_count: int,
    training_window_months: int,
    validation_days: int = 7,
) -> tuple[PredictionBacktestFold, ...]:
    if validation_days <= 0:
        raise ValueError("Rolling backtest validation days must be positive.")
    return _build_fixed_delta_folds(
        reference_end=reference_end,
        fold_count=fold_count,
        training_window_months=training_window_months,
        validation_delta=timedelta(days=validation_days),
    )


def build_rolling_backtest_folds(
    *,
    reference_end: datetime,
    fold_count: int,
    training_window_months: int,
    validation_period: PredictionForecastPeriodDefinition,
) -> tuple[PredictionBacktestFold, ...]:
    period_definition = PredictionForecastPeriodDefinition(
        cadence=validation_period.cadence,
        period_count=validation_period.period_count,
        label=validation_period.label,
    )
    if period_definition.cadence is PredictionForecastCadence.WEEKLY:
        return _build_fixed_delta_folds(
            reference_end=reference_end,
            fold_count=fold_count,
            training_window_months=training_window_months,
            validation_delta=timedelta(days=7 * period_definition.period_count),
        )
    if period_definition.cadence is PredictionForecastCadence.MONTHLY:
        return _build_calendar_month_folds(
            reference_end=reference_end,
            fold_count=fold_count,
            training_window_months=training_window_months,
            validation_months=period_definition.period_count,
        )
    raise ValueError(
        f"Unsupported rolling backtest cadence: {period_definition.cadence.value}"
    )


def _validate_rolling_backtest_windows(
    *,
    fold_count: int,
    training_window_months: int,
) -> None:
    if fold_count <= 0:
        raise ValueError("Rolling backtest fold count must be positive.")
    if training_window_months <= 0:
        raise ValueError("Rolling backtest training window must be positive.")


def _build_fixed_delta_folds(
    *,
    reference_end: datetime,
    fold_count: int,
    training_window_months: int,
    validation_delta: timedelta,
) -> tuple[PredictionBacktestFold, ...]:
    _validate_rolling_backtest_windows(
        fold_count=fold_count,
        training_window_months=training_window_months,
    )
    if validation_delta <= timedelta(0):
        raise ValueError("Rolling backtest validation window must be positive.")

    folds: list[PredictionBacktestFold] = []
    for offset in reversed(range(fold_count)):
        validation_end = reference_end - validation_delta * offset
        validation_start = validation_end - validation_delta
        train_start = subtract_months(validation_start, training_window_months)
        fold_index = len(folds) + 1
        folds.append(
            PredictionBacktestFold(
                fold_index=fold_index,
                train=PredictionTimeWindow(
                    start=train_start,
                    end=validation_start,
                    label=f"train_fold_{fold_index}",
                ),
                validation=PredictionTimeWindow(
                    start=validation_start,
                    end=validation_end,
                    label=f"validation_fold_{fold_index}",
                ),
            )
        )
    return tuple(folds)


def _build_calendar_month_folds(
    *,
    reference_end: datetime,
    fold_count: int,
    training_window_months: int,
    validation_months: int,
) -> tuple[PredictionBacktestFold, ...]:
    _validate_rolling_backtest_windows(
        fold_count=fold_count,
        training_window_months=training_window_months,
    )
    if validation_months <= 0:
        raise ValueError("Rolling backtest validation months must be positive.")

    latest_validation_end = month_start(reference_end)
    folds: list[PredictionBacktestFold] = []
    for offset in reversed(range(fold_count)):
        validation_end = subtract_months(
            latest_validation_end,
            validation_months * offset,
        )
        validation_start = subtract_months(validation_end, validation_months)
        train_start = subtract_months(validation_start, training_window_months)
        fold_index = len(folds) + 1
        folds.append(
            PredictionBacktestFold(
                fold_index=fold_index,
                train=PredictionTimeWindow(
                    start=train_start,
                    end=validation_start,
                    label=f"train_fold_{fold_index}",
                ),
                validation=PredictionTimeWindow(
                    start=validation_start,
                    end=validation_end,
                    label=f"validation_fold_{fold_index}",
                ),
            )
        )
    return tuple(folds)


def calculate_metric_summary(
    points: Sequence[PredictionBacktestPoint],
) -> PredictionMetricSummary:
    validation_total_count = len(points)
    matched_points = [point for point in points if point.predicted_mean is not None]
    matched_validation_count = len(matched_points)
    coverage = (
        matched_validation_count / validation_total_count
        if validation_total_count > 0
        else 0.0
    )

    if matched_validation_count == 0:
        return PredictionMetricSummary(
            validation_total_count=validation_total_count,
            matched_validation_count=0,
            coverage=coverage,
            mae=None,
            rmse=None,
            bias=None,
            wape=None,
        )

    errors = [
        point.actual_value - float(point.predicted_mean)
        for point in matched_points
    ]
    absolute_error_sum = sum(abs(error) for error in errors)
    squared_error_sum = sum(error * error for error in errors)
    actual_absolute_sum = sum(abs(point.actual_value) for point in matched_points)

    return PredictionMetricSummary(
        validation_total_count=validation_total_count,
        matched_validation_count=matched_validation_count,
        coverage=coverage,
        mae=absolute_error_sum / matched_validation_count,
        rmse=sqrt(squared_error_sum / matched_validation_count),
        bias=sum(errors) / matched_validation_count,
        wape=(
            absolute_error_sum / actual_absolute_sum
            if actual_absolute_sum > 0
            else None
        ),
    )


def run_rolling_weekly_backtest(
    *,
    adapter: PredictionMediaAdapter,
    candidate: RollingBacktestCandidate,
    reference_end: datetime,
    fold_count: int,
    validation_days: int = 7,
) -> PredictionBacktestResult:
    folds = build_rolling_weekly_folds(
        reference_end=reference_end,
        fold_count=fold_count,
        training_window_months=candidate.spec.training_window_months,
        validation_days=validation_days,
    )
    return _run_rolling_backtest_for_folds(
        adapter=adapter,
        candidate=candidate,
        folds=folds,
    )


def run_rolling_backtest(
    *,
    adapter: PredictionMediaAdapter,
    candidate: RollingBacktestCandidate,
    reference_end: datetime,
    fold_count: int,
    validation_period: PredictionForecastPeriodDefinition,
) -> PredictionBacktestResult:
    folds = build_rolling_backtest_folds(
        reference_end=reference_end,
        fold_count=fold_count,
        training_window_months=candidate.spec.training_window_months,
        validation_period=validation_period,
    )
    return _run_rolling_backtest_for_folds(
        adapter=adapter,
        candidate=candidate,
        folds=folds,
    )


def _run_rolling_backtest_for_folds(
    *,
    adapter: PredictionMediaAdapter,
    candidate: RollingBacktestCandidate,
    folds: Sequence[PredictionBacktestFold],
) -> PredictionBacktestResult:
    fold_results: list[PredictionBacktestFoldResult] = []
    all_points: list[PredictionBacktestPoint] = []
    for fold in folds:
        points = tuple(
            candidate.predict_validation(
                adapter,
                train_window=fold.train,
                validation_window=fold.validation,
            )
        )
        all_points.extend(points)
        fold_results.append(
            PredictionBacktestFoldResult(
                fold=fold,
                metrics=calculate_metric_summary(points),
                points=points,
            )
        )

    return PredictionBacktestResult(
        spec=candidate.spec,
        folds=tuple(fold_results),
        metrics=calculate_metric_summary(tuple(all_points)),
    )
