import datetime

from moduly.mereni.kalorimetry import prediction_backfill
from moduly.mereni.kalorimetry.production_dry_run import (
    required_kalorimetry_forecast_utc_hours,
)
from moduly.mereni.prediction import (
    ARCHIVE_SOURCE_HISTORICAL_BACKFILL,
    PredictionObservation,
)


def _history(identifier="K1"):
    return prediction_backfill.KalorimetryBackfillIdentifierHistory(
        identifier=identifier,
        first_measurement_at=datetime.datetime(2025, 1, 1),
        last_measurement_at=datetime.datetime(2026, 8, 9),
    )


def _observations(*, include_future=False, future_value=1000.0):
    rows = []
    cursor = datetime.datetime(2025, 6, 1)
    end = datetime.datetime(2026, 8, 3) if include_future else datetime.datetime(
        2026, 7, 27
    )
    measurement_id = 1
    while cursor < end:
        actual = (
            future_value
            if cursor >= datetime.datetime(2026, 7, 27)
            else float((cursor.hour + cursor.weekday() + 1) % 9)
        )
        rows.append(
            PredictionObservation(
                identifier="K1",
                timestamp=cursor,
                actual_value=actual,
                interval_minutes=15,
                day_of_week=cursor.weekday(),
                slot=(cursor.hour * 60 + cursor.minute) // 15,
                features={
                    "measurement_id": measurement_id,
                    "hdd_24h": float(cursor.month),
                },
            )
        )
        measurement_id += 1
        cursor += datetime.timedelta(minutes=15)
    return tuple(rows)


def _period():
    return prediction_backfill.build_kalorimetry_backfill_period(
        datetime.datetime(2026, 7, 27)
    )


def _forecast_hdd(period=None):
    return {
        hour: 4.0
        for hour in required_kalorimetry_forecast_utc_hours(
            period or _period()
        )
    }


def test_plan_uses_calendar_weeks_and_skips_existing_identity():
    plan = prediction_backfill.build_kalorimetry_backfill_plan(
        [_history()],
        start_date=datetime.datetime(2026, 7, 28),
        end_date=datetime.datetime(2026, 8, 10),
        existing_periods=(("K1", datetime.datetime(2026, 8, 3)),),
    )

    assert [item.forecast_period.start for item in plan.items] == [
        datetime.datetime(2026, 7, 27)
    ]
    assert plan.identifier_count == 1
    assert plan.forecast_week_count == 1
    assert plan.identifier_week_count == 1
    assert plan.skipped_counts == {"existing_period": 1}


def test_week_calculation_builds_historical_snapshots_without_runtime_run_id():
    period = _period()
    observations = _observations()

    result = prediction_backfill.calculate_kalorimetry_backfill_week(
        forecast_period=period,
        identifiers=("K1",),
        observations=observations,
        weather_observations=observations,
        forecast_hdd_24h_by_utc_hour=_forecast_hdd(period),
        forecast_issued_at=period.start - datetime.timedelta(hours=1),
        archive_run_id="kalorimetry-history-20260727-v1",
    )

    assert result.snapshot_plan.available_identifier_count == 1
    assert result.snapshot_plan.profile_point_count == 672
    assert result.snapshot_plan.decisions[0].selection_run_id is None
    assert {
        row["archive_source"] for row in result.snapshot_plan.profile_rows
    } == {ARCHIVE_SOURCE_HISTORICAL_BACKFILL}
    assert {row["selection_mode"] for row in result.snapshot_plan.profile_rows} == {
        "active"
    }
    assert len(result.candidate_metric_rows) == 2
    assert sum(row["selected"] for row in result.candidate_metric_rows) == 1


def test_future_measurements_cannot_change_historical_week_result():
    period = _period()
    base = _observations()
    with_future = _observations(include_future=True, future_value=999999.0)
    kwargs = {
        "forecast_period": period,
        "identifiers": ("K1",),
        "forecast_hdd_24h_by_utc_hour": _forecast_hdd(period),
        "forecast_issued_at": period.start - datetime.timedelta(hours=1),
        "archive_run_id": "kalorimetry-history-20260727-v1",
    }

    before = prediction_backfill.calculate_kalorimetry_backfill_week(
        observations=base,
        weather_observations=base,
        **kwargs,
    )
    after = prediction_backfill.calculate_kalorimetry_backfill_week(
        observations=with_future,
        weather_observations=with_future,
        **kwargs,
    )

    assert before.candidate_metric_rows == after.candidate_metric_rows
    assert before.snapshot_plan.decisions == after.snapshot_plan.decisions
    assert before.snapshot_plan.profile_rows == after.snapshot_plan.profile_rows


def test_missing_historical_forecast_is_audited_without_weather_fallback_data():
    observations = _observations()

    result = prediction_backfill.calculate_kalorimetry_backfill_week(
        forecast_period=_period(),
        identifiers=("K1",),
        observations=observations,
        weather_observations=observations,
        forecast_hdd_24h_by_utc_hour={},
        forecast_issued_at=None,
        archive_run_id="kalorimetry-history-missing-weather",
    )

    candidate_audit = result.snapshot_plan.decisions[0].metadata[
        "candidate_audit"
    ]
    weather = next(row for row in candidate_audit if row["model_version"] == 2)
    assert weather["profile_available"] is False
    assert weather["profile_reason"] == "missing_forecast_weather"
    assert {
        row["model_version"] for row in result.snapshot_plan.profile_rows
    } == {1}


def test_forecast_issued_at_or_after_week_start_is_rejected():
    observations = _observations()
    period = _period()

    try:
        prediction_backfill.calculate_kalorimetry_backfill_week(
            forecast_period=period,
            identifiers=("K1",),
            observations=observations,
            weather_observations=observations,
            forecast_hdd_24h_by_utc_hour=_forecast_hdd(period),
            forecast_issued_at=period.start,
            archive_run_id="kalorimetry-history-leaking-weather",
        )
    except ValueError as exc:
        assert "issued before" in str(exc)
    else:
        raise AssertionError("Leaking historical forecast was accepted.")
