from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest

from moduly.mereni.kalorimetry import kalorimetry_prediction
from moduly.mereni.prediction import PredictionForecastCadence


PRAGUE = ZoneInfo("Europe/Prague")


@pytest.mark.parametrize(
    "reference_time",
    [
        datetime.datetime(2026, 7, 27),
        datetime.datetime(2026, 7, 29, 14, 30, 15, 123456),
        datetime.datetime(2026, 8, 2, 23, 59, 59, 999999),
    ],
)
def test_kalorimetry_forecast_period_is_current_prague_calendar_week(
    reference_time,
):
    period = kalorimetry_prediction.build_kalorimetry_weekly_forecast_period(
        reference_time
    )

    assert period.start == datetime.datetime(2026, 7, 27)
    assert period.end == datetime.datetime(2026, 8, 3)
    assert period.cadence is PredictionForecastCadence.WEEKLY
    assert period.label == "2026-07-27 - 2026-08-03"


def test_kalorimetry_forecast_period_switches_at_prague_monday_midnight():
    before = kalorimetry_prediction.build_kalorimetry_weekly_forecast_period(
        datetime.datetime(2026, 8, 2, 23, 59, 59, 999999)
    )
    after = kalorimetry_prediction.build_kalorimetry_weekly_forecast_period(
        datetime.datetime(2026, 8, 3)
    )

    assert before.start == datetime.datetime(2026, 7, 27)
    assert before.end == after.start == datetime.datetime(2026, 8, 3)
    assert after.end == datetime.datetime(2026, 8, 10)


def test_aware_utc_reference_is_resolved_by_prague_wall_time():
    period = kalorimetry_prediction.build_kalorimetry_weekly_forecast_period(
        datetime.datetime(2026, 8, 2, 22, 30, tzinfo=datetime.UTC)
    )

    assert period.start == datetime.datetime(2026, 8, 3)
    assert period.end == datetime.datetime(2026, 8, 10)


@pytest.mark.parametrize(
    ("reference_time", "expected_start", "expected_end"),
    [
        (
            datetime.datetime(2026, 3, 29, 1, 30, tzinfo=datetime.UTC),
            datetime.datetime(2026, 3, 23),
            datetime.datetime(2026, 3, 30),
        ),
        (
            datetime.datetime(2026, 10, 25, 1, 30, tzinfo=datetime.UTC),
            datetime.datetime(2026, 10, 19),
            datetime.datetime(2026, 10, 26),
        ),
    ],
)
def test_kalorimetry_forecast_period_preserves_prague_week_across_dst_changes(
    reference_time,
    expected_start,
    expected_end,
):
    period = kalorimetry_prediction.build_kalorimetry_weekly_forecast_period(
        reference_time
    )

    assert period.start == expected_start
    assert period.end == expected_end


def test_kalorimetry_forecast_period_defaults_to_current_prague_wall_time(
    monkeypatch,
):
    monkeypatch.setattr(
        kalorimetry_prediction,
        "prague_now_naive",
        lambda: datetime.datetime(2026, 8, 2, 23, 30),
    )

    period = kalorimetry_prediction.build_kalorimetry_weekly_forecast_period()

    assert period.start == datetime.datetime(2026, 7, 27)
    assert period.end == datetime.datetime(2026, 8, 3)


def test_kalorimetry_period_definition_is_one_week():
    definition = kalorimetry_prediction.KALORIMETRY_FORECAST_PERIOD_DEFINITION

    assert definition.cadence is PredictionForecastCadence.WEEKLY
    assert definition.period_count == 1
    assert kalorimetry_prediction.KALORIMETRY_MEDIUM_KEY == "kalorimetry"
    assert kalorimetry_prediction.KALORIMETRY_TIMEZONE is PRAGUE
