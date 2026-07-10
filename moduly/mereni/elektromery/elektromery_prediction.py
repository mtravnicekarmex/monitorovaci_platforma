from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median

from moduly.mereni.elektromery.prediction_adapter import (
    ELECTROMERY_MEDIUM_KEY,
    ElektromeryMonthlyConsumption,
    ElektromeryPredictionAdapter,
)
from moduly.mereni.prediction import (
    PredictionBacktestPoint,
    PredictionBacktestResult,
    PredictionCandidateRegistry,
    PredictionCandidateResult,
    PredictionCandidateSpec,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionForecastPeriodDefinition,
    PredictionMetricSummary,
    PredictionPipelineRunner,
    PredictionPipelineSettings,
    PredictionRebuildWindows,
    PredictionTimeWindow,
    month_start,
    run_rolling_backtest,
    subtract_months,
)


MODEL_VERSION_RECENT_AVERAGE = 1
MODEL_VERSION_TWELVE_MONTH_MEDIAN = 2
MODEL_VERSION_SAME_MONTH_LAST_YEAR = 3
MODEL_REBUILD_TRAINING_MONTHS = 12
MODEL_VALIDATION_MONTHS = 1
MODEL_SELECTION_COVERAGE_THRESHOLD = 0.75
ROLLING_BACKTEST_FOLD_COUNT = 6

ELEKTROMERY_FORECAST_PERIOD_DEFINITION = PredictionForecastPeriodDefinition(
    cadence=PredictionForecastCadence.MONTHLY,
    period_count=1,
)
ELEKTROMERY_PIPELINE_SETTINGS = PredictionPipelineSettings(
    medium_key=ELECTROMERY_MEDIUM_KEY,
    forecast_period_definition=ELEKTROMERY_FORECAST_PERIOD_DEFINITION,
    default_training_window_months=MODEL_REBUILD_TRAINING_MONTHS,
    default_validation_window_months=MODEL_VALIDATION_MONTHS,
    candidate_coverage_threshold=MODEL_SELECTION_COVERAGE_THRESHOLD,
    rolling_backtest_fold_count=ROLLING_BACKTEST_FOLD_COUNT,
    rolling_validation_period=ELEKTROMERY_FORECAST_PERIOD_DEFINITION,
)


@dataclass(frozen=True)
class ElektromeryCandidateModelDefinition:
    model_version: int
    model_key: str
    model_name: str
    training_window_months: int
    validation_window_months: int = MODEL_VALIDATION_MONTHS
    selection_enabled: bool = True

    def to_prediction_spec(self) -> PredictionCandidateSpec:
        return PredictionCandidateSpec(
            medium_key=ELECTROMERY_MEDIUM_KEY,
            model_version=self.model_version,
            model_key=self.model_key,
            model_name=self.model_name,
            training_window_months=self.training_window_months,
            validation_window_months=self.validation_window_months,
            selection_enabled=self.selection_enabled,
        )


@dataclass(frozen=True)
class ElektromeryMonthlyCandidatePlugin:
    definition: ElektromeryCandidateModelDefinition
    prediction_fn: Callable[
        [Sequence[ElektromeryMonthlyConsumption], ElektromeryMonthlyConsumption],
        float | None,
    ]

    @property
    def spec(self) -> PredictionCandidateSpec:
        return self.definition.to_prediction_spec()

    def predict_validation(
        self,
        adapter: ElektromeryPredictionAdapter,
        *,
        train_window: PredictionTimeWindow,
        validation_window: PredictionTimeWindow,
    ) -> Sequence[PredictionBacktestPoint]:
        train_rows = tuple(adapter.load_monthly_consumption(train_window))
        validation_rows = tuple(adapter.load_monthly_consumption(validation_window))
        train_rows_by_identifier = _group_monthly_rows_by_identifier(train_rows)
        points: list[PredictionBacktestPoint] = []
        for validation_row in validation_rows:
            points.append(
                PredictionBacktestPoint(
                    identifier=validation_row.identifier,
                    timestamp=validation_row.month_start,
                    actual_value=validation_row.consumption_kwh,
                    predicted_mean=self.prediction_fn(
                        train_rows_by_identifier.get(validation_row.identifier, ()),
                        validation_row,
                    ),
                )
            )
        return tuple(points)


def _build_elektromery_pipeline_runner() -> PredictionPipelineRunner[ElektromeryMonthlyCandidatePlugin]:
    registry = PredictionCandidateRegistry(
        medium_key=ELECTROMERY_MEDIUM_KEY,
        plugins=(
            ElektromeryMonthlyCandidatePlugin(
                definition=ElektromeryCandidateModelDefinition(
                    model_version=MODEL_VERSION_RECENT_AVERAGE,
                    model_key="recent_3_month_average",
                    model_name="Model 1 - recent 3 month average",
                    training_window_months=3,
                ),
                prediction_fn=_predict_recent_average,
            ),
            ElektromeryMonthlyCandidatePlugin(
                definition=ElektromeryCandidateModelDefinition(
                    model_version=MODEL_VERSION_TWELVE_MONTH_MEDIAN,
                    model_key="twelve_month_median",
                    model_name="Model 2 - trailing 12 month median",
                    training_window_months=12,
                ),
                prediction_fn=_predict_trailing_median,
            ),
            ElektromeryMonthlyCandidatePlugin(
                definition=ElektromeryCandidateModelDefinition(
                    model_version=MODEL_VERSION_SAME_MONTH_LAST_YEAR,
                    model_key="same_month_last_year",
                    model_name="Model 3 - same month last year",
                    training_window_months=12,
                ),
                prediction_fn=_predict_same_month_last_year,
            ),
        ),
    )
    return PredictionPipelineRunner(
        settings=ELEKTROMERY_PIPELINE_SETTINGS,
        registry=registry,
    )


def get_candidate_model_plugins() -> tuple[ElektromeryMonthlyCandidatePlugin, ...]:
    return _build_elektromery_pipeline_runner().list_plugins()


def get_candidate_model_specs() -> tuple[PredictionCandidateSpec, ...]:
    return _build_elektromery_pipeline_runner().list_specs()


def get_candidate_model_versions() -> tuple[int, ...]:
    return _build_elektromery_pipeline_runner().list_model_versions()


def build_next_month_forecast_period(
    *,
    reference_time: datetime,
) -> PredictionForecastPeriod:
    return _build_elektromery_pipeline_runner().build_forecast_period(
        reference_time=reference_time,
    )


def build_monthly_rebuild_windows(
    *,
    reference_time: datetime,
    spec: PredictionCandidateSpec | None = None,
) -> PredictionRebuildWindows:
    training_window_months = (
        spec.training_window_months
        if spec is not None
        else ELEKTROMERY_PIPELINE_SETTINGS.default_training_window_months
    )
    validation_window_months = (
        spec.validation_window_months
        if spec is not None
        else ELEKTROMERY_PIPELINE_SETTINGS.default_validation_window_months
    )
    validation_end = month_start(reference_time)
    validation_start = subtract_months(validation_end, validation_window_months)
    train_end = validation_start
    train_start = subtract_months(train_end, training_window_months)
    return PredictionRebuildWindows(
        train=PredictionTimeWindow(start=train_start, end=train_end, label="train"),
        validation=PredictionTimeWindow(
            start=validation_start,
            end=validation_end,
            label="validation",
        ),
        deploy=PredictionTimeWindow(
            start=train_start,
            end=validation_end,
            label="deploy",
        ),
    )


def run_monthly_candidate_backtests(
    *,
    adapter: ElektromeryPredictionAdapter | None = None,
    reference_time: datetime,
    fold_count: int | None = None,
) -> tuple[PredictionBacktestResult, ...]:
    resolved_adapter = adapter or ElektromeryPredictionAdapter()
    runner = _build_elektromery_pipeline_runner()
    return tuple(
        run_rolling_backtest(
            adapter=resolved_adapter,
            candidate=plugin,
            reference_end=reference_time,
            fold_count=(
                runner.settings.rolling_backtest_fold_count
                if fold_count is None
                else fold_count
            ),
            validation_period=(
                runner.settings.rolling_validation_period
                or ELEKTROMERY_FORECAST_PERIOD_DEFINITION
            ),
        )
        for plugin in runner.list_plugins()
    )


def select_best_backtested_candidate(
    backtest_results: Sequence[PredictionBacktestResult],
) -> PredictionCandidateResult | None:
    return _build_elektromery_pipeline_runner().select_best_candidate(
        backtest_result_to_candidate_result(result) for result in backtest_results
    )


def backtest_result_to_candidate_result(
    result: PredictionBacktestResult,
) -> PredictionCandidateResult:
    return PredictionCandidateResult(
        spec=result.spec,
        metrics=PredictionMetricSummary(
            validation_total_count=result.metrics.validation_total_count,
            matched_validation_count=result.metrics.matched_validation_count,
            coverage=result.metrics.coverage,
            mae=result.metrics.mae,
            rmse=result.metrics.rmse,
            bias=result.metrics.bias,
            wape=result.metrics.wape,
        ),
        profile_count=0,
    )


def _group_monthly_rows_by_identifier(
    rows: Sequence[ElektromeryMonthlyConsumption],
) -> dict[str, tuple[ElektromeryMonthlyConsumption, ...]]:
    grouped: dict[str, list[ElektromeryMonthlyConsumption]] = {}
    for row in rows:
        grouped.setdefault(row.identifier, []).append(row)
    return {
        identifier: tuple(sorted(identifier_rows, key=lambda item: item.month_start))
        for identifier, identifier_rows in grouped.items()
    }


def _predict_recent_average(
    train_rows: Sequence[ElektromeryMonthlyConsumption],
    validation_row: ElektromeryMonthlyConsumption,
) -> float | None:
    del validation_row
    values = [row.consumption_kwh for row in sorted(train_rows, key=lambda item: item.month_start)[-3:]]
    return _average(values)


def _predict_trailing_median(
    train_rows: Sequence[ElektromeryMonthlyConsumption],
    validation_row: ElektromeryMonthlyConsumption,
) -> float | None:
    del validation_row
    values = [row.consumption_kwh for row in train_rows]
    if not values:
        return None
    return float(median(values))


def _predict_same_month_last_year(
    train_rows: Sequence[ElektromeryMonthlyConsumption],
    validation_row: ElektromeryMonthlyConsumption,
) -> float | None:
    matching_rows = [
        row
        for row in train_rows
        if row.month_start.month == validation_row.month_start.month
        and row.month_start < validation_row.month_start
    ]
    if not matching_rows:
        return None
    return float(max(matching_rows, key=lambda row: row.month_start).consumption_kwh)


def _average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))
