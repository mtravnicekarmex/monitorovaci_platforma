from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from core.db.connect import get_session_pg
from moduly.apps.meteo.database.models import MeteoForecastHourly
from moduly.mereni.kalorimetry.database.models import Mereni_kalorimetry
from moduly.mereni.kalorimetry.prediction_adapter import (
    KalorimetryPredictionAdapter,
)
from moduly.mereni.kalorimetry.prediction_backfill import (
    KalorimetryBackfillIdentifierHistory,
    build_kalorimetry_backfill_plan,
    calculate_kalorimetry_backfill_week,
)
from moduly.mereni.kalorimetry.prediction_backfill_workflow import (
    apply_kalorimetry_prediction_backfill,
    dry_run_kalorimetry_prediction_backfill,
    verify_kalorimetry_prediction_backfill,
)
from moduly.mereni.kalorimetry.production_dry_run import (
    InMemoryKalorimetryAdapter,
    required_kalorimetry_forecast_utc_hours,
)
from moduly.mereni.prediction import (
    PredictionTimeWindow,
    build_rolling_backtest_folds,
)
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_FORECAST_PERIOD_DEFINITION,
)


KALORIMETRY_CONTROLLED_BACKFILL_START = datetime(2025, 7, 28)
KALORIMETRY_CONTROLLED_BACKFILL_END = datetime(2026, 5, 18)
KALORIMETRY_CONTROLLED_BACKFILL_ARCHIVE_VERSION = 1
KALORIMETRY_CONTROLLED_BACKFILL_ARCHIVE_RUN_ID = (
    "kalorimetry-historical-backfill-20260729-v1"
)
PRAGUE_TIMEZONE = ZoneInfo("Europe/Prague")


@dataclass(frozen=True)
class KalorimetryControlledBackfillResult:
    plan_identifier_count: int
    plan_week_count: int
    plan_identifier_week_count: int
    observation_count: int
    weather_observation_count: int
    dry_run_absent_week_count: int
    dry_run_complete_week_count: int
    applied_week_count: int
    inserted_decision_count: int
    inserted_candidate_metric_count: int
    inserted_profile_point_count: int
    verified_complete_week_count: int
    verified_conflict_week_count: int
    weather_available_week_count: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "mode": "controlled_production_historical_backfill",
            **self.__dict__,
        }


def run_controlled_kalorimetry_backfill(
    *,
    confirm_apply: bool = False,
    max_weeks: int | None = None,
) -> KalorimetryControlledBackfillResult:
    if not confirm_apply:
        raise PermissionError(
            "Controlled kalorimetry backfill requires explicit confirmation."
        )
    session = get_session_pg()
    try:
        histories = _load_identifier_histories(session)
        plan = build_kalorimetry_backfill_plan(
            histories,
            start_date=KALORIMETRY_CONTROLLED_BACKFILL_START,
            end_date=KALORIMETRY_CONTROLLED_BACKFILL_END,
            archive_version=KALORIMETRY_CONTROLLED_BACKFILL_ARCHIVE_VERSION,
            max_weeks=max_weeks,
        )
        if not plan.items:
            raise RuntimeError("Controlled kalorimetry backfill plan is empty.")

        first_period = min(
            (item.forecast_period for item in plan.items),
            key=lambda period: period.start,
        )
        last_period = max(
            (item.forecast_period for item in plan.items),
            key=lambda period: period.start,
        )
        first_folds = build_rolling_backtest_folds(
            reference_end=first_period.start,
            fold_count=8,
            training_window_months=12,
            validation_period=KALORIMETRY_FORECAST_PERIOD_DEFINITION,
        )
        observation_window = PredictionTimeWindow(
            start=first_folds[0].train.start,
            end=last_period.start,
            label="controlled_historical_backfill",
        )
        source_adapter = KalorimetryPredictionAdapter()
        observations = tuple(
            source_adapter.load_observations(observation_window)
        )
        weather_observations = tuple(
            source_adapter.load_weather_observations(observation_window)
        )
        prepared_adapter = InMemoryKalorimetryAdapter(
            observations,
            weather_observations,
        )
        weather_available_weeks: set[datetime] = set()
        calculation_cache = {}

        def calculate_week(period, identifiers, archive_run_id, archive_version):
            cache_key = (
                period.start,
                identifiers,
                archive_run_id,
                archive_version,
            )
            if cache_key in calculation_cache:
                return calculation_cache[cache_key]
            issued_at, hdd = _load_historical_forecast_hdd_24h(
                session,
                period,
            )
            if hdd:
                weather_available_weeks.add(period.start)
            calculation = calculate_kalorimetry_backfill_week(
                forecast_period=period,
                identifiers=identifiers,
                observations=(),
                weather_observations=(),
                forecast_hdd_24h_by_utc_hour=hdd,
                forecast_issued_at=issued_at,
                archive_run_id=archive_run_id,
                archive_version=archive_version,
                prepared_adapter=prepared_adapter,
            )
            calculation_cache[cache_key] = calculation
            return calculation

        dry_run = dry_run_kalorimetry_prediction_backfill(
            plan,
            archive_run_id=KALORIMETRY_CONTROLLED_BACKFILL_ARCHIVE_RUN_ID,
            calculate_week=calculate_week,
            session=session,
        )
        if dry_run.conflict_week_count:
            raise RuntimeError(
                "Controlled kalorimetry backfill dry-run found conflicts."
            )
        apply_result = apply_kalorimetry_prediction_backfill(
            plan,
            archive_run_id=KALORIMETRY_CONTROLLED_BACKFILL_ARCHIVE_RUN_ID,
            calculate_week=calculate_week,
            session=session,
            confirm_apply=True,
        )
        verify = verify_kalorimetry_prediction_backfill(
            plan,
            archive_run_id=KALORIMETRY_CONTROLLED_BACKFILL_ARCHIVE_RUN_ID,
            calculate_week=calculate_week,
            session=session,
        )
        if (
            verify.conflict_week_count
            or verify.complete_week_count != plan.forecast_week_count
        ):
            raise RuntimeError(
                "Controlled kalorimetry backfill verification failed."
            )
        return KalorimetryControlledBackfillResult(
            plan_identifier_count=plan.identifier_count,
            plan_week_count=plan.forecast_week_count,
            plan_identifier_week_count=plan.identifier_week_count,
            observation_count=len(observations),
            weather_observation_count=len(weather_observations),
            dry_run_absent_week_count=dry_run.absent_week_count,
            dry_run_complete_week_count=dry_run.complete_week_count,
            applied_week_count=apply_result.complete_week_count,
            inserted_decision_count=sum(
                week.inserted_decision_count for week in apply_result.weeks
            ),
            inserted_candidate_metric_count=sum(
                week.inserted_candidate_metric_count
                for week in apply_result.weeks
            ),
            inserted_profile_point_count=sum(
                week.inserted_profile_point_count for week in apply_result.weeks
            ),
            verified_complete_week_count=verify.complete_week_count,
            verified_conflict_week_count=verify.conflict_week_count,
            weather_available_week_count=len(weather_available_weeks),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _load_identifier_histories(
    session,
) -> tuple[KalorimetryBackfillIdentifierHistory, ...]:
    rows = (
        session.execute(
            select(
                Mereni_kalorimetry.identifikace,
                func.min(Mereni_kalorimetry.date).label(
                    "first_measurement_at"
                ),
                func.max(Mereni_kalorimetry.date).label(
                    "last_measurement_at"
                ),
            )
            .where(
                Mereni_kalorimetry.platne.is_(True),
                Mereni_kalorimetry.reset_detected.is_(False),
                Mereni_kalorimetry.synthetic.is_(False),
                Mereni_kalorimetry.gap_detected.is_(False),
                Mereni_kalorimetry.delta.is_not(None),
                Mereni_kalorimetry.delta >= 0,
            )
            .group_by(Mereni_kalorimetry.identifikace)
            .order_by(Mereni_kalorimetry.identifikace)
        )
        .mappings()
        .all()
    )
    return tuple(
        KalorimetryBackfillIdentifierHistory(
            identifier=str(row["identifikace"]),
            first_measurement_at=row["first_measurement_at"],
            last_measurement_at=row["last_measurement_at"],
        )
        for row in rows
    )


def _load_historical_forecast_hdd_24h(
    session,
    forecast_period,
) -> tuple[datetime | None, Mapping[datetime, float]]:
    required_hours = required_kalorimetry_forecast_utc_hours(
        forecast_period
    )
    raw_start = required_hours[0] - timedelta(hours=23)
    raw_end = required_hours[-1] + timedelta(hours=1)
    period_start_utc = (
        forecast_period.start.replace(tzinfo=PRAGUE_TIMEZONE)
        .astimezone(UTC)
        .replace(tzinfo=None)
    )
    rows = (
        session.execute(
            select(
                MeteoForecastHourly.datetime_hour,
                MeteoForecastHourly.forecast_run_at,
                MeteoForecastHourly.heating_degree_hours,
            )
            .where(
                MeteoForecastHourly.datetime_hour >= raw_start,
                MeteoForecastHourly.datetime_hour < raw_end,
                MeteoForecastHourly.forecast_run_at < period_start_utc,
            )
            .order_by(
                MeteoForecastHourly.forecast_run_at.desc(),
                MeteoForecastHourly.datetime_hour,
            )
        )
        .mappings()
        .all()
    )
    by_run: dict[datetime, dict[datetime, float]] = {}
    for row in rows:
        by_run.setdefault(row["forecast_run_at"], {})[
            row["datetime_hour"]
        ] = float(row["heating_degree_hours"])
    for issued_at, raw in sorted(by_run.items(), reverse=True):
        trailing = {}
        for hour in required_hours:
            values = [
                raw.get(hour - timedelta(hours=offset))
                for offset in range(24)
            ]
            if any(value is None for value in values):
                break
            trailing[hour] = sum(values) / 24
        if len(trailing) == len(required_hours):
            return issued_at, trailing
    return None, {}
