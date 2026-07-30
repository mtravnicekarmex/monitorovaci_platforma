from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from core.db.connect import get_session_pg
from moduly.apps.meteo.database.models import MeteoForecastHourly
from moduly.mereni.kalorimetry.calendar_baseline import (
    KalorimetryCalendarBaselineCandidate,
)
from moduly.mereni.kalorimetry.deployable_catalog import (
    KalorimetryDeployableCandidateCatalog,
    build_kalorimetry_deployable_candidate_catalog,
)
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_FORECAST_PERIOD_DEFINITION,
    KALORIMETRY_PIPELINE_SETTINGS,
    build_kalorimetry_weekly_forecast_period,
)
from moduly.mereni.kalorimetry.prediction_adapter import (
    KalorimetryPredictionAdapter,
)
from moduly.mereni.kalorimetry.reporting.model_rebuild_report import (
    build_kalorimetry_model_rebuild_report,
)
from moduly.mereni.kalorimetry.rolling_backtest import (
    KalorimetryCandidateRollingBacktestResult,
    run_kalorimetry_candidate_rolling_backtest,
)
from moduly.mereni.kalorimetry.selection import (
    KalorimetryDryRunSelectionDecision,
    build_kalorimetry_dry_run_selection_decisions,
)
from moduly.mereni.kalorimetry.weather_candidate import (
    KalorimetryWeatherCandidate,
)
from moduly.mereni.prediction import (
    PredictionObservation,
    PredictionTimeWindow,
    build_rolling_backtest_folds,
)


PRAGUE_TIMEZONE = ZoneInfo("Europe/Prague")


@dataclass(frozen=True)
class KalorimetryProductionDryRunResult:
    reference_time: datetime
    observation_window: PredictionTimeWindow
    observation_count: int
    weather_observation_count: int
    latest_observation_at: datetime | None
    forecast_run_at: datetime | None
    forecast_hdd_hour_count: int
    candidate_results: tuple[KalorimetryCandidateRollingBacktestResult, ...]
    deployable_catalog: KalorimetryDeployableCandidateCatalog
    decisions: tuple[KalorimetryDryRunSelectionDecision, ...]
    aggregate_report: dict[str, object]

    def to_aggregate_dict(self) -> dict[str, object]:
        return {
            "medium_key": "kalorimetry",
            "mode": "production_read_only_dry_run",
            "reference_time": self.reference_time,
            "observation_window_start": self.observation_window.start,
            "observation_window_end": self.observation_window.end,
            "observation_count": self.observation_count,
            "weather_observation_count": self.weather_observation_count,
            "latest_observation_at": self.latest_observation_at,
            "forecast_run_at": self.forecast_run_at,
            "forecast_hdd_hour_count": self.forecast_hdd_hour_count,
            "deployable_available_pair_count": sum(
                1 for entry in self.deployable_catalog.entries if entry.available
            ),
            "deployable_unavailable_reasons": _count_reasons(
                entry.reason
                for entry in self.deployable_catalog.entries
                if not entry.available
            ),
            **self.aggregate_report,
        }


class InMemoryKalorimetryAdapter:
    def __init__(
        self,
        observations: Sequence[PredictionObservation],
        weather_observations: Sequence[PredictionObservation],
    ) -> None:
        self._observations = tuple(
            sorted(observations, key=lambda row: row.timestamp)
        )
        self._observation_times = tuple(
            row.timestamp for row in self._observations
        )
        self._weather_observations = tuple(
            sorted(weather_observations, key=lambda row: row.timestamp)
        )
        self._weather_observation_times = tuple(
            row.timestamp for row in self._weather_observations
        )

    def load_observations(
        self,
        window: PredictionTimeWindow,
        *,
        identifiers: Sequence[str] | None = None,
    ) -> tuple[PredictionObservation, ...]:
        return _slice_observations(
            self._observations,
            self._observation_times,
            window,
            identifiers=identifiers,
        )

    def load_weather_observations(
        self,
        window: PredictionTimeWindow,
        *,
        identifiers: Sequence[str] | None = None,
    ) -> tuple[PredictionObservation, ...]:
        return _slice_observations(
            self._weather_observations,
            self._weather_observation_times,
            window,
            identifiers=identifiers,
        )


def run_kalorimetry_production_dry_run(
    *,
    reference_time: datetime | None = None,
    adapter: KalorimetryPredictionAdapter | None = None,
    session_factory: Callable[[], object] = get_session_pg,
) -> KalorimetryProductionDryRunResult:
    resolved_reference = reference_time or datetime.now()
    forecast_period = build_kalorimetry_weekly_forecast_period(
        resolved_reference
    )
    candidates = (
        KalorimetryCalendarBaselineCandidate(),
        KalorimetryWeatherCandidate(),
    )
    folds = build_rolling_backtest_folds(
        reference_end=forecast_period.start,
        fold_count=KALORIMETRY_PIPELINE_SETTINGS.rolling_backtest_fold_count,
        training_window_months=max(
            candidate.spec.training_window_months
            for candidate in candidates
        ),
        validation_period=KALORIMETRY_FORECAST_PERIOD_DEFINITION,
    )
    observation_window = PredictionTimeWindow(
        start=min(fold.train.start for fold in folds),
        end=forecast_period.start,
        label="production_dry_run_observations",
    )
    source_adapter = adapter or KalorimetryPredictionAdapter()
    observations = tuple(source_adapter.load_observations(observation_window))
    weather_observations = tuple(
        source_adapter.load_weather_observations(observation_window)
    )
    memory_adapter = InMemoryKalorimetryAdapter(
        observations,
        weather_observations,
    )
    candidate_results = tuple(
        run_kalorimetry_candidate_rolling_backtest(
            adapter=memory_adapter,
            candidate=candidate,
            reference_end=forecast_period.start,
        )
        for candidate in candidates
    )
    deploy_train_window = PredictionTimeWindow(
        start=folds[-1].train.start,
        end=forecast_period.start,
        label="production_dry_run_deploy_train",
    )
    deploy_observations = memory_adapter.load_observations(deploy_train_window)
    deploy_weather_observations = memory_adapter.load_weather_observations(
        deploy_train_window
    )
    forecast_run_at, forecast_hdd = load_latest_forecast_hdd_24h(
        forecast_period=forecast_period,
        session_factory=session_factory,
    )
    deployable_catalog = build_kalorimetry_deployable_candidate_catalog(
        baseline_observations=deploy_observations,
        weather_observations=deploy_weather_observations,
        forecast_period=forecast_period,
        hdd_24h_by_utc_hour=forecast_hdd,
    )
    decisions = build_kalorimetry_dry_run_selection_decisions(
        candidate_results=candidate_results,
        deployable_catalog=deployable_catalog,
    )
    aggregate_report = build_kalorimetry_model_rebuild_report(
        candidate_results=candidate_results,
        decisions=decisions,
    )
    return KalorimetryProductionDryRunResult(
        reference_time=resolved_reference,
        observation_window=observation_window,
        observation_count=len(observations),
        weather_observation_count=len(weather_observations),
        latest_observation_at=max(
            (observation.timestamp for observation in observations),
            default=None,
        ),
        forecast_run_at=forecast_run_at,
        forecast_hdd_hour_count=len(forecast_hdd),
        candidate_results=candidate_results,
        deployable_catalog=deployable_catalog,
        decisions=decisions,
        aggregate_report=aggregate_report,
    )


def load_latest_forecast_hdd_24h(
    *,
    forecast_period,
    session_factory: Callable[[], object] = get_session_pg,
) -> tuple[datetime | None, dict[datetime, float]]:
    required_hours = required_kalorimetry_forecast_utc_hours(forecast_period)
    if not required_hours:
        return None, {}
    raw_start = required_hours[0] - timedelta(hours=23)
    raw_end = required_hours[-1] + timedelta(hours=1)
    session = session_factory()
    try:
        period_start_utc = (
            forecast_period.start.replace(tzinfo=PRAGUE_TIMEZONE)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
        forecast_run_at = session.execute(
            select(func.max(MeteoForecastHourly.forecast_run_at)).where(
                MeteoForecastHourly.forecast_run_at < period_start_utc
            )
        ).scalar_one_or_none()
        if forecast_run_at is None:
            return None, {}
        rows = (
            session.execute(
                select(
                    MeteoForecastHourly.datetime_hour,
                    MeteoForecastHourly.heating_degree_hours,
                )
                .where(
                    MeteoForecastHourly.forecast_run_at == forecast_run_at,
                    MeteoForecastHourly.datetime_hour >= raw_start,
                    MeteoForecastHourly.datetime_hour < raw_end,
                )
                .order_by(MeteoForecastHourly.datetime_hour)
            )
            .all()
        )
    finally:
        session.close()

    raw = {
        row.datetime_hour: float(row.heating_degree_hours)
        for row in rows
        if row.heating_degree_hours is not None
    }
    trailing = {}
    for hour in required_hours:
        values = [
            raw.get(hour - timedelta(hours=offset))
            for offset in reversed(range(24))
        ]
        if all(value is not None for value in values):
            trailing[hour] = sum(values) / 24
    return forecast_run_at, trailing


def required_kalorimetry_forecast_utc_hours(
    forecast_period,
) -> tuple[datetime, ...]:
    hours = set()
    cursor = forecast_period.start
    while cursor < forecast_period.end:
        aware = cursor.replace(tzinfo=PRAGUE_TIMEZONE)
        hours.add(
            aware.astimezone(UTC).replace(
                tzinfo=None,
                minute=0,
                second=0,
                microsecond=0,
            )
        )
        cursor += timedelta(minutes=15)
    return tuple(sorted(hours))


def _slice_observations(
    observations: Sequence[PredictionObservation],
    timestamps: Sequence[datetime],
    window: PredictionTimeWindow,
    *,
    identifiers: Sequence[str] | None,
) -> tuple[PredictionObservation, ...]:
    identifier_set = (
        None
        if not identifiers
        else {str(identifier) for identifier in identifiers}
    )
    start_index = bisect_left(timestamps, window.start)
    end_index = bisect_left(timestamps, window.end)
    return tuple(
        observation
        for observation in observations[start_index:end_index]
        if (
            identifier_set is None
            or observation.identifier in identifier_set
        )
    )


def _count_reasons(reasons) -> dict[str, int]:
    result: dict[str, int] = {}
    for reason in reasons:
        result[str(reason)] = result.get(str(reason), 0) + 1
    return dict(sorted(result.items()))
