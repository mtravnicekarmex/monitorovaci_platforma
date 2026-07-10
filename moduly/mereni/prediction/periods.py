from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from moduly.mereni.prediction.contracts import (
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionForecastPeriodDefinition,
)


def add_months(value: datetime, months: int) -> datetime:
    if months < 0:
        raise ValueError("Month addition expects a non-negative value.")
    return _shift_months(value, months)


def subtract_months(value: datetime, months: int) -> datetime:
    if months < 0:
        raise ValueError("Month subtraction expects a non-negative value.")
    return _shift_months(value, -months)


def month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_month_start(value: datetime) -> datetime:
    return add_months(month_start(value), 1)


def build_next_forecast_period(
    *,
    reference_time: datetime,
    definition: PredictionForecastPeriodDefinition,
) -> PredictionForecastPeriod:
    period_definition = PredictionForecastPeriodDefinition(
        cadence=definition.cadence,
        period_count=definition.period_count,
        label=definition.label,
    )

    if period_definition.cadence is PredictionForecastCadence.WEEKLY:
        start = reference_time
        end = start + timedelta(days=7 * period_definition.period_count)
        label = period_definition.label or _format_range_label(start, end)
    elif period_definition.cadence is PredictionForecastCadence.MONTHLY:
        start = next_month_start(reference_time)
        end = add_months(start, period_definition.period_count)
        label = period_definition.label or _format_monthly_label(start, end)
    else:
        raise ValueError(
            f"Unsupported prediction forecast cadence: {period_definition.cadence.value}"
        )

    return PredictionForecastPeriod(
        start=start,
        end=end,
        cadence=period_definition.cadence,
        label=label,
    )


def _shift_months(value: datetime, months: int) -> datetime:
    month_index = value.month + months - 1
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _format_range_label(start: datetime, end: datetime) -> str:
    return f"{start:%Y-%m-%d %H:%M} - {end:%Y-%m-%d %H:%M}"


def _format_monthly_label(start: datetime, end: datetime) -> str:
    last_month_start = subtract_months(end, 1)
    if start.year == last_month_start.year and start.month == last_month_start.month:
        return f"{start:%Y-%m}"
    return f"{start:%Y-%m} - {last_month_start:%Y-%m}"
