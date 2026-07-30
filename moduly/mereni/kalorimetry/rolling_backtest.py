from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from sqlalchemy import insert

from moduly.mereni.kalorimetry.database.models import (
    KalorimetryModelValidationMetric,
    KalorimetryModelValidationRun,
)
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_FORECAST_PERIOD_DEFINITION,
    KALORIMETRY_PIPELINE_SETTINGS,
)
from moduly.mereni.prediction import (
    PredictionBacktestFoldResult,
    PredictionBacktestPoint,
    PredictionBacktestResult,
    PredictionMetricSummary,
    build_rolling_backtest_folds,
    calculate_metric_summary,
)


@dataclass(frozen=True)
class KalorimetryIdentifierRollingMetric:
    identifier: str
    model_version: int
    model_key: str
    rolling_backtest_fold_count: int
    matched_fold_count: int
    metrics: PredictionMetricSummary

    def to_row(self, *, run_id: int) -> dict[str, object]:
        return {
            "run_id": int(run_id),
            "model_version": self.model_version,
            "identifikace": self.identifier,
            "rolling_backtest_fold_count": self.rolling_backtest_fold_count,
            "matched_fold_count": self.matched_fold_count,
            "validation_total_count": self.metrics.validation_total_count,
            "matched_validation_count": self.metrics.matched_validation_count,
            "coverage": self.metrics.coverage,
            "mae": self.metrics.mae,
            "rmse": self.metrics.rmse,
            "bias": self.metrics.bias,
            "wape": self.metrics.wape,
        }


@dataclass(frozen=True)
class KalorimetryCandidateRollingBacktestResult:
    result: PredictionBacktestResult
    identifier_metrics: tuple[KalorimetryIdentifierRollingMetric, ...]


def run_kalorimetry_candidate_rolling_backtest(
    *,
    adapter,
    candidate,
    reference_end: datetime,
    fold_count: int | None = None,
) -> KalorimetryCandidateRollingBacktestResult:
    resolved_fold_count = (
        KALORIMETRY_PIPELINE_SETTINGS.rolling_backtest_fold_count
        if fold_count is None
        else int(fold_count)
    )
    folds = build_rolling_backtest_folds(
        reference_end=reference_end,
        fold_count=resolved_fold_count,
        training_window_months=candidate.spec.training_window_months,
        validation_period=KALORIMETRY_FORECAST_PERIOD_DEFINITION,
    )
    fold_results: list[PredictionBacktestFoldResult] = []
    all_points: list[PredictionBacktestPoint] = []
    fold_indexes_by_identifier: dict[str, set[int]] = defaultdict(set)
    matched_fold_indexes_by_identifier: dict[str, set[int]] = defaultdict(set)

    for fold in folds:
        points = tuple(
            candidate.predict_validation(
                adapter,
                train_window=fold.train,
                validation_window=fold.validation,
            )
        )
        all_points.extend(points)
        for point in points:
            fold_indexes_by_identifier[point.identifier].add(fold.fold_index)
            if point.predicted_mean is not None:
                matched_fold_indexes_by_identifier[point.identifier].add(
                    fold.fold_index
                )
        fold_results.append(
            PredictionBacktestFoldResult(
                fold=fold,
                metrics=calculate_metric_summary(points),
                points=points,
            )
        )

    result = PredictionBacktestResult(
        spec=candidate.spec,
        folds=tuple(fold_results),
        metrics=calculate_metric_summary(tuple(all_points)),
    )
    points_by_identifier: dict[str, list[PredictionBacktestPoint]] = defaultdict(
        list
    )
    for point in all_points:
        points_by_identifier[point.identifier].append(point)
    identifier_metrics = tuple(
        KalorimetryIdentifierRollingMetric(
            identifier=identifier,
            model_version=candidate.spec.model_version,
            model_key=candidate.spec.model_key,
            rolling_backtest_fold_count=len(
                fold_indexes_by_identifier[identifier]
            ),
            matched_fold_count=len(
                matched_fold_indexes_by_identifier[identifier]
            ),
            metrics=calculate_metric_summary(tuple(points)),
        )
        for identifier, points in sorted(points_by_identifier.items())
    )
    return KalorimetryCandidateRollingBacktestResult(
        result=result,
        identifier_metrics=identifier_metrics,
    )


def persist_kalorimetry_rolling_metrics(
    session,
    *,
    candidate_result: KalorimetryCandidateRollingBacktestResult,
    reference_end: datetime,
) -> int:
    spec = candidate_result.result.spec
    run = KalorimetryModelValidationRun(
        model_version=spec.model_version,
        model_key=spec.model_key,
        reference_end=reference_end,
        fold_count=len(candidate_result.result.folds),
    )
    session.add(run)
    session.flush()
    rows = [
        metric.to_row(run_id=int(run.id))
        for metric in candidate_result.identifier_metrics
    ]
    if rows:
        session.execute(insert(KalorimetryModelValidationMetric), rows)
    return len(rows)
