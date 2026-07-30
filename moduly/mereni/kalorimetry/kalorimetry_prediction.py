from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.time_utils import prague_now_naive
from moduly.mereni.prediction import (
    PredictionCandidateSpec,
    PredictionPipelineSettings,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionForecastPeriodDefinition,
    build_calendar_week_forecast_period,
)


KALORIMETRY_MEDIUM_KEY = "kalorimetry"
KALORIMETRY_TIMEZONE_NAME = "Europe/Prague"
KALORIMETRY_TIMEZONE = ZoneInfo(KALORIMETRY_TIMEZONE_NAME)
KALORIMETRY_FORECAST_PERIOD_DEFINITION = PredictionForecastPeriodDefinition(
    cadence=PredictionForecastCadence.WEEKLY,
    period_count=1,
)
KALORIMETRY_PIPELINE_SETTINGS = PredictionPipelineSettings(
    medium_key=KALORIMETRY_MEDIUM_KEY,
    forecast_period_definition=KALORIMETRY_FORECAST_PERIOD_DEFINITION,
    default_training_window_months=12,
    default_validation_window_months=1,
    candidate_coverage_threshold=0.85,
    rolling_backtest_fold_count=8,
    rolling_validation_period=KALORIMETRY_FORECAST_PERIOD_DEFINITION,
)


def build_kalorimetry_weekly_forecast_period(
    reference_time: datetime | None = None,
) -> PredictionForecastPeriod:
    resolved_reference_time = _to_prague_wall_time(
        reference_time or prague_now_naive()
    )
    return build_calendar_week_forecast_period(
        reference_time=resolved_reference_time,
        period_count=KALORIMETRY_FORECAST_PERIOD_DEFINITION.period_count,
    )


def get_candidate_model_specs() -> tuple[PredictionCandidateSpec, ...]:
    from moduly.mereni.kalorimetry.calendar_baseline import (
        KalorimetryCalendarBaselineCandidate,
    )
    from moduly.mereni.kalorimetry.weather_candidate import (
        KalorimetryWeatherCandidate,
    )

    return (
        KalorimetryCalendarBaselineCandidate().spec,
        KalorimetryWeatherCandidate().spec,
    )


def _to_prague_wall_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(KALORIMETRY_TIMEZONE).replace(tzinfo=None)
