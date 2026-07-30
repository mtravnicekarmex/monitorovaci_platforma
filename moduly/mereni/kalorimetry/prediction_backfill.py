from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Mapping, Sequence

from moduly.mereni.kalorimetry.calendar_baseline import (
    KalorimetryCalendarBaselineCandidate,
)
from moduly.mereni.kalorimetry.deployable_catalog import (
    build_kalorimetry_deployable_candidate_catalog,
)
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_FORECAST_PERIOD_DEFINITION,
)
from moduly.mereni.kalorimetry.production_dry_run import (
    InMemoryKalorimetryAdapter,
)
from moduly.mereni.kalorimetry.rolling_backtest import (
    run_kalorimetry_candidate_rolling_backtest,
)
from moduly.mereni.kalorimetry.selection import (
    build_kalorimetry_dry_run_selection_decisions,
)
from moduly.mereni.kalorimetry.snapshot_persistence import (
    KalorimetrySnapshotPersistencePlan,
    build_kalorimetry_snapshot_persistence_plan,
)
from moduly.mereni.kalorimetry.weather_candidate import (
    KalorimetryWeatherCandidate,
)
from moduly.mereni.prediction import (
    ARCHIVE_SOURCE_HISTORICAL_BACKFILL,
    SELECTION_MODE_ACTIVE,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionObservation,
    PredictionTimeWindow,
    build_rolling_backtest_folds,
)


KALORIMETRY_BACKFILL_ARCHIVE_VERSION = 1
KALORIMETRY_BACKFILL_MODEL_VERSIONS = (1, 2)


@dataclass(frozen=True)
class KalorimetryBackfillIdentifierHistory:
    identifier: str
    first_measurement_at: datetime
    last_measurement_at: datetime


@dataclass(frozen=True)
class KalorimetryBackfillPlanItem:
    identifier: str
    forecast_period: PredictionForecastPeriod
    first_measurement_at: datetime


@dataclass(frozen=True)
class KalorimetryBackfillPlan:
    start_date: datetime
    end_date: datetime
    archive_version: int
    items: tuple[KalorimetryBackfillPlanItem, ...]
    skipped_counts: Mapping[str, int] = field(default_factory=dict)

    @property
    def identifier_count(self) -> int:
        return len({item.identifier for item in self.items})

    @property
    def forecast_week_count(self) -> int:
        return len({item.forecast_period.start for item in self.items})

    @property
    def identifier_week_count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class KalorimetryBackfillWeekCalculation:
    forecast_period: PredictionForecastPeriod
    planned_identifiers: tuple[str, ...]
    snapshot_plan: KalorimetrySnapshotPersistencePlan
    candidate_metric_rows: tuple[dict[str, object], ...]
    unavailable_reasons: Mapping[str, int]


def floor_kalorimetry_calendar_week(value: datetime) -> datetime:
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday())


def build_kalorimetry_backfill_period(
    week_start: datetime,
) -> PredictionForecastPeriod:
    start = floor_kalorimetry_calendar_week(week_start)
    end = start + timedelta(days=7)
    return PredictionForecastPeriod(
        start=start,
        end=end,
        cadence=PredictionForecastCadence.WEEKLY,
        label=f"{start:%Y-%m-%d} - {end:%Y-%m-%d}",
    )


def build_kalorimetry_backfill_plan(
    histories: Sequence[KalorimetryBackfillIdentifierHistory],
    *,
    start_date: datetime,
    end_date: datetime,
    archive_version: int = KALORIMETRY_BACKFILL_ARCHIVE_VERSION,
    existing_periods: Sequence[tuple[str, datetime]] = (),
    max_identifiers: int | None = None,
    max_weeks: int | None = None,
) -> KalorimetryBackfillPlan:
    if end_date <= start_date:
        raise ValueError("Backfill end date must be after start date.")
    if archive_version <= 0:
        raise ValueError("Backfill archive version must be positive.")
    if max_identifiers is not None and max_identifiers <= 0:
        raise ValueError("Maximum identifier count must be positive.")
    if max_weeks is not None and max_weeks <= 0:
        raise ValueError("Maximum week count must be positive.")

    existing = set(existing_periods)
    skipped: Counter[str] = Counter()
    selected_histories = sorted(histories, key=lambda row: row.identifier)
    if max_identifiers is not None:
        selected_histories = selected_histories[:max_identifiers]
    first_week = floor_kalorimetry_calendar_week(start_date)
    items = []
    for history in selected_histories:
        week = first_week
        planned_week_count = 0
        last_week = floor_kalorimetry_calendar_week(
            history.last_measurement_at
        )
        while week < end_date and week <= last_week:
            if max_weeks is not None and planned_week_count >= max_weeks:
                break
            if (history.identifier, week) in existing:
                skipped["existing_period"] += 1
            else:
                items.append(
                    KalorimetryBackfillPlanItem(
                        identifier=history.identifier,
                        forecast_period=build_kalorimetry_backfill_period(week),
                        first_measurement_at=history.first_measurement_at,
                    )
                )
            planned_week_count += 1
            week += timedelta(days=7)
    return KalorimetryBackfillPlan(
        start_date=start_date,
        end_date=end_date,
        archive_version=archive_version,
        items=tuple(items),
        skipped_counts=dict(skipped),
    )


def calculate_kalorimetry_backfill_week(
    *,
    forecast_period: PredictionForecastPeriod,
    identifiers: Sequence[str],
    observations: Sequence[PredictionObservation],
    weather_observations: Sequence[PredictionObservation],
    forecast_hdd_24h_by_utc_hour: Mapping[datetime, float],
    forecast_issued_at: datetime | None,
    archive_run_id: str,
    archive_version: int = KALORIMETRY_BACKFILL_ARCHIVE_VERSION,
    prepared_adapter: InMemoryKalorimetryAdapter | None = None,
) -> KalorimetryBackfillWeekCalculation:
    if not archive_run_id.strip():
        raise ValueError("Backfill archive run id must not be empty.")
    planned_identifiers = tuple(
        sorted({str(identifier) for identifier in identifiers})
    )
    if not planned_identifiers:
        raise ValueError("Backfill week needs at least one identifier.")
    if forecast_period.cadence is not PredictionForecastCadence.WEEKLY:
        raise ValueError("Kalorimetry backfill requires weekly periods.")
    if forecast_hdd_24h_by_utc_hour and forecast_issued_at is None:
        raise ValueError(
            "Historical weather profiles require forecast issue provenance."
        )
    if (
        forecast_issued_at is not None
        and forecast_issued_at >= forecast_period.start
    ):
        raise ValueError(
            "Historical forecast must be issued before the forecast week."
        )

    if prepared_adapter is None:
        safe_observations = tuple(
            row
            for row in observations
            if row.identifier in planned_identifiers
            and row.timestamp < forecast_period.start
        )
        safe_weather_observations = tuple(
            row
            for row in weather_observations
            if row.identifier in planned_identifiers
            and row.timestamp < forecast_period.start
        )
        adapter = InMemoryKalorimetryAdapter(
            safe_observations,
            safe_weather_observations,
        )
    else:
        adapter = prepared_adapter
    candidates = (
        KalorimetryCalendarBaselineCandidate(),
        KalorimetryWeatherCandidate(),
    )
    candidate_results = tuple(
        run_kalorimetry_candidate_rolling_backtest(
            adapter=adapter,
            candidate=candidate,
            reference_end=forecast_period.start,
        )
        for candidate in candidates
    )
    folds = build_rolling_backtest_folds(
        reference_end=forecast_period.start,
        fold_count=8,
        training_window_months=12,
        validation_period=KALORIMETRY_FORECAST_PERIOD_DEFINITION,
    )
    deploy_train_window = PredictionTimeWindow(
        start=folds[-1].train.start,
        end=forecast_period.start,
        label="historical_backfill_deploy_train",
    )
    deployable_catalog = build_kalorimetry_deployable_candidate_catalog(
        baseline_observations=adapter.load_observations(
            deploy_train_window,
            identifiers=planned_identifiers,
        ),
        weather_observations=adapter.load_weather_observations(
            deploy_train_window,
            identifiers=planned_identifiers,
        ),
        forecast_period=forecast_period,
        hdd_24h_by_utc_hour=forecast_hdd_24h_by_utc_hour,
    )
    decisions = tuple(
        replace(
            decision,
            metadata={
                **dict(decision.metadata),
                "selection_mode": "historical_backfill_dry_run",
                "archive_source": ARCHIVE_SOURCE_HISTORICAL_BACKFILL,
                "archive_version": archive_version,
                "archive_run_id": archive_run_id,
                "forecast_issued_at": (
                    None
                    if forecast_issued_at is None
                    else forecast_issued_at.isoformat()
                ),
            },
        )
        for decision in build_kalorimetry_dry_run_selection_decisions(
            candidate_results=candidate_results,
            deployable_catalog=deployable_catalog,
        )
    )
    decision_by_identifier = {
        decision.identifier: decision for decision in decisions
    }
    unavailable_reasons = Counter()
    for identifier in planned_identifiers:
        decision = decision_by_identifier.get(identifier)
        if decision is None:
            unavailable_reasons["no_identifier_metrics"] += 1
        elif not decision.available:
            unavailable_reasons[decision.fallback_reason] += 1

    snapshot_plan = build_kalorimetry_snapshot_persistence_plan(
        dry_run_decisions=decisions,
        deployable_catalog=deployable_catalog,
        global_candidate=candidates[0].spec,
        selection_run_id=None,
        archive_run_id=archive_run_id,
        selection_mode=SELECTION_MODE_ACTIVE,
        archive_source=ARCHIVE_SOURCE_HISTORICAL_BACKFILL,
        archive_version=archive_version,
        training_window=deploy_train_window,
        validation_window=folds[-1].validation,
    )
    candidate_metric_rows = _build_candidate_metric_rows(
        candidate_results=candidate_results,
        decisions=decisions,
        forecast_period=forecast_period,
        archive_run_id=archive_run_id,
        archive_version=archive_version,
        folds=folds,
    )
    return KalorimetryBackfillWeekCalculation(
        forecast_period=forecast_period,
        planned_identifiers=planned_identifiers,
        snapshot_plan=snapshot_plan,
        candidate_metric_rows=candidate_metric_rows,
        unavailable_reasons=dict(sorted(unavailable_reasons.items())),
    )


def _build_candidate_metric_rows(
    *,
    candidate_results,
    decisions,
    forecast_period,
    archive_run_id,
    archive_version,
    folds,
) -> tuple[dict[str, object], ...]:
    specs_by_version = {
        result.result.spec.model_version: result.result.spec
        for result in candidate_results
    }
    rows = []
    for decision in decisions:
        for audit in decision.candidate_audits:
            spec = specs_by_version[audit.model_version]
            metrics = audit.metrics
            rows.append(
                {
                    "medium_key": "kalorimetry",
                    "identifier": decision.identifier,
                    "forecast_period_start": forecast_period.start,
                    "forecast_period_end": forecast_period.end,
                    "forecast_cadence": forecast_period.cadence.value,
                    "forecast_period_label": forecast_period.label,
                    "archive_version": archive_version,
                    "archive_run_id": archive_run_id,
                    "model_version": spec.model_version,
                    "model_key": spec.model_key,
                    "model_name": spec.model_name,
                    "selection_enabled": spec.selection_enabled,
                    "selected": bool(
                        decision.available
                        and decision.selected_model_version
                        == spec.model_version
                    ),
                    "eligible": audit.selectable,
                    "rank_by_policy": audit.rank_by_policy,
                    "fallback_reason": decision.fallback_reason,
                    **(
                        {
                            "validation_total_count": 0,
                            "matched_validation_count": 0,
                            "coverage": 0.0,
                            "mae": None,
                            "rmse": None,
                            "bias": None,
                            "wape": None,
                        }
                        if metrics is None
                        else metrics.to_dict()
                    ),
                    "training_window_start": folds[0].train.start,
                    "training_window_end": folds[-1].train.end,
                    "validation_window_start": folds[0].validation.start,
                    "validation_window_end": folds[-1].validation.end,
                    "metadata_json": None,
                }
            )
    return tuple(rows)
