from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import sqrt
from typing import Protocol, Sequence

from moduly.mereni.prediction.contracts import (
    PredictionCandidateSpec,
    PredictionMediaAdapter,
    PredictionMetricSummary,
    PredictionTimeWindow,
)


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
    if fold_count <= 0:
        raise ValueError("Rolling backtest fold count must be positive.")
    if training_window_months <= 0:
        raise ValueError("Rolling backtest training window must be positive.")
    if validation_days <= 0:
        raise ValueError("Rolling backtest validation days must be positive.")

    validation_delta = timedelta(days=validation_days)
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


def subtract_months(value: datetime, months: int) -> datetime:
    if months < 0:
        raise ValueError("Month subtraction expects a non-negative value.")
    month_index = value.month - months - 1
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
