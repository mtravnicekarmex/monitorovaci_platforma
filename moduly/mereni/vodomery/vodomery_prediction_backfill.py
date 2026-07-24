from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Sequence

from sqlalchemy import text

from core.db.connect import get_session_pg
from moduly.mereni.prediction import (
    ARCHIVE_SOURCE_HISTORICAL_BACKFILL,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    add_months,
    persist_prediction_backfill_candidate_metrics,
    persist_prediction_profile_snapshots,
)
from moduly.mereni.vodomery import vodomery_prediction


BACKFILL_DEFAULT_START = datetime(2024, 1, 1)
BACKFILL_DEFAULT_ARCHIVE_VERSION = 1
BACKFILL_HISTORY_MONTHS_REQUIRED = 1
VODOMERY_BACKFILL_MODEL_VERSIONS = (1, 2, 3)


@dataclass(frozen=True)
class VodomeryBackfillIdentifierHistory:
    identifier: str
    first_measurement_at: datetime
    last_measurement_at: datetime


@dataclass(frozen=True)
class VodomeryBackfillPlanItem:
    identifier: str
    forecast_period: PredictionForecastPeriod
    first_measurement_at: datetime
    history_available_from: datetime


@dataclass(frozen=True)
class VodomeryBackfillPlan:
    start_date: datetime
    end_date: datetime
    archive_version: int
    model_versions: tuple[int, ...]
    items: tuple[VodomeryBackfillPlanItem, ...]
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

    @property
    def candidate_metric_row_estimate(self) -> int:
        return self.identifier_week_count * len(self.model_versions)


@dataclass(frozen=True)
class VodomeryBackfillDryRunWeekResult:
    forecast_period: PredictionForecastPeriod
    planned_identifier_count: int
    calculated_identifier_count: int
    candidate_metric_row_count: int
    selected_decision_count: int
    selected_profile_pair_count: int
    skipped_counts: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class VodomeryBackfillDryRunResult:
    archive_run_id: str
    plan: VodomeryBackfillPlan
    weeks: tuple[VodomeryBackfillDryRunWeekResult, ...]

    @property
    def calculated_week_count(self) -> int:
        return len(self.weeks)

    @property
    def candidate_metric_row_count(self) -> int:
        return sum(week.candidate_metric_row_count for week in self.weeks)

    @property
    def selected_decision_count(self) -> int:
        return sum(week.selected_decision_count for week in self.weeks)

    @property
    def selected_profile_pair_count(self) -> int:
        return sum(week.selected_profile_pair_count for week in self.weeks)


@dataclass(frozen=True)
class VodomeryBackfillWriteWeekResult(VodomeryBackfillDryRunWeekResult):
    inserted_candidate_metric_count: int = 0
    inserted_profile_snapshot_count: int = 0


@dataclass(frozen=True)
class VodomeryBackfillWriteResult:
    archive_run_id: str
    plan: VodomeryBackfillPlan
    weeks: tuple[VodomeryBackfillWriteWeekResult, ...]

    @property
    def committed_week_count(self) -> int:
        return len(self.weeks)

    @property
    def inserted_candidate_metric_count(self) -> int:
        return sum(week.inserted_candidate_metric_count for week in self.weeks)

    @property
    def inserted_profile_snapshot_count(self) -> int:
        return sum(week.inserted_profile_snapshot_count for week in self.weeks)


@dataclass(frozen=True)
class VodomeryBackfillVerifyProfileSource:
    archive_source: str
    archive_version: int | None
    profile_row_count: int
    identifier_count: int
    forecast_week_count: int
    identifier_week_count: int


@dataclass(frozen=True)
class VodomeryBackfillVerifyCandidateMetrics:
    archive_version: int
    metric_row_count: int
    identifier_count: int
    forecast_week_count: int
    identifier_week_count: int
    selected_metric_row_count: int


@dataclass(frozen=True)
class VodomeryBackfillVerifyResult:
    start_date: datetime
    end_date: datetime
    archive_version: int
    profile_sources: tuple[VodomeryBackfillVerifyProfileSource, ...]
    candidate_metrics: VodomeryBackfillVerifyCandidateMetrics
    missing_tables: tuple[str, ...] = ()

    @property
    def profile_row_count(self) -> int:
        return sum(source.profile_row_count for source in self.profile_sources)

    @property
    def profile_identifier_week_count(self) -> int:
        return sum(source.identifier_week_count for source in self.profile_sources)


@dataclass(frozen=True)
class _BackfillWeekCalculation:
    summary: VodomeryBackfillDryRunWeekResult
    selected_decisions: tuple[object, ...]
    candidate_metric_rows: tuple[dict[str, object], ...]
    selected_profile_snapshot_rows: tuple[dict[str, object], ...] = ()


def floor_calendar_week_start(value: datetime) -> datetime:
    midnight = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday())


def ceil_calendar_week_start(value: datetime) -> datetime:
    week_start = floor_calendar_week_start(value)
    if value == week_start:
        return week_start
    return week_start + timedelta(days=7)


def build_calendar_week_period(start: datetime) -> PredictionForecastPeriod:
    normalized_start = floor_calendar_week_start(start)
    end = normalized_start + timedelta(days=7)
    return PredictionForecastPeriod(
        start=normalized_start,
        end=end,
        cadence=PredictionForecastCadence.WEEKLY,
        label=f"{normalized_start:%Y-%m-%d} - {end:%Y-%m-%d}",
    )


def load_vodomery_backfill_identifier_history(
    session,
    *,
    start_date: datetime = BACKFILL_DEFAULT_START,
    identifiers: Sequence[str] | None = None,
) -> tuple[VodomeryBackfillIdentifierHistory, ...]:
    params: dict[str, object] = {"start_date": start_date}
    identifier_filter = ""
    if identifiers:
        identifier_filter = "AND identifikace = ANY(:identifiers)"
        params["identifiers"] = list(identifiers)

    rows = (
        session.execute(
            text(
                f"""
                SELECT
                    identifikace,
                    MIN(date) AS first_measurement_at,
                    MAX(date) AS last_measurement_at
                FROM monitoring."Mereni_vodomery_vse"
                WHERE
                    synthetic = FALSE
                    AND platne = TRUE
                    AND reset_detected = FALSE
                    AND delta IS NOT NULL
                    AND date >= :start_date
                    {identifier_filter}
                GROUP BY identifikace
                ORDER BY identifikace
                """
            ),
            params,
        )
        .mappings()
        .all()
    )
    return tuple(
        VodomeryBackfillIdentifierHistory(
            identifier=str(row["identifikace"]),
            first_measurement_at=row["first_measurement_at"],
            last_measurement_at=row["last_measurement_at"],
        )
        for row in rows
    )


def build_vodomery_backfill_plan(
    histories: Iterable[VodomeryBackfillIdentifierHistory],
    *,
    start_date: datetime = BACKFILL_DEFAULT_START,
    end_date: datetime,
    archive_version: int = BACKFILL_DEFAULT_ARCHIVE_VERSION,
    model_versions: Sequence[int] = VODOMERY_BACKFILL_MODEL_VERSIONS,
    existing_weekly_rebuild_periods: Iterable[tuple[str, datetime]] = (),
    max_identifiers: int | None = None,
    max_weeks: int | None = None,
) -> VodomeryBackfillPlan:
    if end_date <= start_date:
        raise ValueError("Backfill end date must be after start date.")
    if archive_version <= 0:
        raise ValueError("Backfill archive version must be positive.")

    normalized_models = tuple(sorted({int(model) for model in model_versions}))
    if not normalized_models:
        raise ValueError("Backfill needs at least one candidate model version.")

    skipped: Counter[str] = Counter()
    existing_weekly_rebuild = set(existing_weekly_rebuild_periods)
    items: list[VodomeryBackfillPlanItem] = []
    selected_histories = sorted(histories, key=lambda item: item.identifier)
    if max_identifiers is not None:
        selected_histories = selected_histories[:max_identifiers]

    global_first_week = ceil_calendar_week_start(start_date)
    for history in selected_histories:
        history_available_from = add_months(
            history.first_measurement_at,
            BACKFILL_HISTORY_MONTHS_REQUIRED,
        )
        first_week = max(global_first_week, ceil_calendar_week_start(history_available_from))
        last_week = floor_calendar_week_start(history.last_measurement_at)
        week_start = first_week
        planned_weeks = 0
        if week_start >= end_date or week_start > last_week:
            skipped["outside_date_range"] += 1
            continue

        while week_start < end_date and week_start <= last_week:
            if max_weeks is not None and planned_weeks >= max_weeks:
                break
            if (history.identifier, week_start) in existing_weekly_rebuild:
                skipped["weekly_rebuild_exists"] += 1
            else:
                items.append(
                    VodomeryBackfillPlanItem(
                        identifier=history.identifier,
                        forecast_period=build_calendar_week_period(week_start),
                        first_measurement_at=history.first_measurement_at,
                        history_available_from=history_available_from,
                    )
                )
            planned_weeks += 1
            week_start += timedelta(days=7)

    return VodomeryBackfillPlan(
        start_date=start_date,
        end_date=end_date,
        archive_version=archive_version,
        model_versions=normalized_models,
        items=tuple(items),
        skipped_counts=dict(skipped),
    )


def plan_vodomery_prediction_backfill(
    *,
    start_date: datetime = BACKFILL_DEFAULT_START,
    end_date: datetime,
    history_start_date: datetime | None = None,
    identifiers: Sequence[str] | None = None,
    archive_version: int = BACKFILL_DEFAULT_ARCHIVE_VERSION,
    max_identifiers: int | None = None,
    max_weeks: int | None = None,
) -> VodomeryBackfillPlan:
    resolved_history_start_date = history_start_date or start_date
    if resolved_history_start_date > start_date:
        raise ValueError("Backfill history start date must not be after start date.")

    session = get_session_pg()
    try:
        histories = load_vodomery_backfill_identifier_history(
            session,
            start_date=resolved_history_start_date,
            identifiers=identifiers,
        )
        return build_vodomery_backfill_plan(
            histories,
            start_date=start_date,
            end_date=end_date,
            archive_version=archive_version,
            max_identifiers=max_identifiers,
            max_weeks=max_weeks,
        )
    finally:
        session.close()


def verify_vodomery_prediction_backfill(
    *,
    start_date: datetime = BACKFILL_DEFAULT_START,
    end_date: datetime,
    archive_version: int = BACKFILL_DEFAULT_ARCHIVE_VERSION,
    identifiers: Sequence[str] | None = None,
    session=None,
) -> VodomeryBackfillVerifyResult:
    if end_date <= start_date:
        raise ValueError("Backfill verify end date must be after start date.")
    if archive_version <= 0:
        raise ValueError("Backfill verify archive version must be positive.")

    owns_session = session is None
    if session is None:
        session = get_session_pg()

    try:
        params: dict[str, object] = {
            "start_date": start_date,
            "end_date": end_date,
            "archive_version": archive_version,
        }
        identifier_filter = ""
        if identifiers:
            identifier_filter = "AND identifier = ANY(:identifiers)"
            params["identifiers"] = list(identifiers)

        table_state = (
            session.execute(
                text(
                    """
                    SELECT
                        to_regclass('monitoring.prediction_profile_snapshots')
                            AS profile_table,
                        to_regclass('monitoring.prediction_backfill_candidate_metrics')
                            AS metric_table
                    """
                )
            )
            .mappings()
            .one()
        )
        missing_tables = []
        profile_rows = []
        if table_state["profile_table"] is None:
            missing_tables.append("monitoring.prediction_profile_snapshots")
        else:
            profile_rows = (
                session.execute(
                    text(
                        f"""
                        SELECT
                            archive_source,
                            archive_version,
                            COUNT(*) AS profile_row_count,
                            COUNT(DISTINCT identifier) AS identifier_count,
                            COUNT(DISTINCT forecast_period_start) AS forecast_week_count,
                            COUNT(DISTINCT (identifier, forecast_period_start))
                                AS identifier_week_count
                        FROM monitoring.prediction_profile_snapshots
                        WHERE
                            medium_key = 'vodomery'
                            AND forecast_period_start >= :start_date
                            AND forecast_period_start < :end_date
                            AND (
                                archive_source = 'weekly_rebuild'
                                OR (
                                    archive_source = 'historical_backfill'
                                    AND archive_version = :archive_version
                                )
                            )
                            {identifier_filter}
                        GROUP BY archive_source, archive_version
                        ORDER BY archive_source, archive_version
                        """
                    ),
                    params,
                )
                .mappings()
                .all()
            )

        if table_state["metric_table"] is None:
            missing_tables.append("monitoring.prediction_backfill_candidate_metrics")
            metric_row = {
                "metric_row_count": 0,
                "identifier_count": 0,
                "forecast_week_count": 0,
                "identifier_week_count": 0,
                "selected_metric_row_count": 0,
            }
        else:
            metric_row = (
                session.execute(
                    text(
                        f"""
                        SELECT
                            COUNT(*) AS metric_row_count,
                            COUNT(DISTINCT identifier) AS identifier_count,
                            COUNT(DISTINCT forecast_period_start) AS forecast_week_count,
                            COUNT(DISTINCT (identifier, forecast_period_start))
                                AS identifier_week_count,
                            COUNT(*) FILTER (WHERE selected = TRUE)
                                AS selected_metric_row_count
                        FROM monitoring.prediction_backfill_candidate_metrics
                        WHERE
                            medium_key = 'vodomery'
                            AND archive_version = :archive_version
                            AND forecast_period_start >= :start_date
                            AND forecast_period_start < :end_date
                            {identifier_filter}
                        """
                    ),
                    params,
                )
                .mappings()
                .one()
            )

        return VodomeryBackfillVerifyResult(
            start_date=start_date,
            end_date=end_date,
            archive_version=archive_version,
            profile_sources=tuple(
                VodomeryBackfillVerifyProfileSource(
                    archive_source=str(row["archive_source"]),
                    archive_version=(
                        None
                        if row["archive_version"] is None
                        else int(row["archive_version"])
                    ),
                    profile_row_count=int(row["profile_row_count"] or 0),
                    identifier_count=int(row["identifier_count"] or 0),
                    forecast_week_count=int(row["forecast_week_count"] or 0),
                    identifier_week_count=int(row["identifier_week_count"] or 0),
                )
                for row in profile_rows
            ),
            candidate_metrics=VodomeryBackfillVerifyCandidateMetrics(
                archive_version=archive_version,
                metric_row_count=int(metric_row["metric_row_count"] or 0),
                identifier_count=int(metric_row["identifier_count"] or 0),
                forecast_week_count=int(metric_row["forecast_week_count"] or 0),
                identifier_week_count=int(metric_row["identifier_week_count"] or 0),
                selected_metric_row_count=int(
                    metric_row["selected_metric_row_count"] or 0
                ),
            ),
            missing_tables=tuple(missing_tables),
        )
    finally:
        if owns_session:
            session.close()


def dry_run_vodomery_prediction_backfill(
    plan: VodomeryBackfillPlan,
    *,
    archive_run_id: str,
    session=None,
) -> VodomeryBackfillDryRunResult:
    if not archive_run_id:
        raise ValueError("Backfill dry-run needs an archive run id.")

    owns_session = session is None
    if session is None:
        session = get_session_pg()

    try:
        week_results = []
        for forecast_start, items in _group_plan_items_by_week(plan):
            try:
                week_results.append(
                    _calculate_vodomery_backfill_week(
                        session,
                        forecast_start=forecast_start,
                        items=items,
                        archive_run_id=archive_run_id,
                        archive_version=plan.archive_version,
                        model_versions=plan.model_versions,
                        include_profile_snapshot_rows=True,
                    ).summary
                )
            finally:
                session.rollback()
        return VodomeryBackfillDryRunResult(
            archive_run_id=archive_run_id,
            plan=plan,
            weeks=tuple(week_results),
        )
    finally:
        if owns_session:
            session.close()


def write_vodomery_prediction_backfill(
    plan: VodomeryBackfillPlan,
    *,
    archive_run_id: str,
    session=None,
) -> VodomeryBackfillWriteResult:
    if not archive_run_id:
        raise ValueError("Backfill write needs an archive run id.")

    owns_session = session is None
    if session is None:
        session = get_session_pg()

    try:
        week_results = []
        for forecast_start, items in _group_plan_items_by_week(plan):
            try:
                calculation = _calculate_vodomery_backfill_week(
                    session,
                    forecast_start=forecast_start,
                    items=items,
                    archive_run_id=archive_run_id,
                    archive_version=plan.archive_version,
                    model_versions=plan.model_versions,
                    include_profile_snapshot_rows=True,
                )
                session.rollback()
                inserted_candidate_metric_count = (
                    persist_prediction_backfill_candidate_metrics(
                        session,
                        calculation.candidate_metric_rows,
                    )
                )
                inserted_profile_snapshot_count = (
                    persist_prediction_profile_snapshots(
                        session,
                        calculation.selected_profile_snapshot_rows,
                    )
                )
                session.commit()
                week_results.append(
                    VodomeryBackfillWriteWeekResult(
                        forecast_period=calculation.summary.forecast_period,
                        planned_identifier_count=(
                            calculation.summary.planned_identifier_count
                        ),
                        calculated_identifier_count=(
                            calculation.summary.calculated_identifier_count
                        ),
                        candidate_metric_row_count=(
                            calculation.summary.candidate_metric_row_count
                        ),
                        selected_decision_count=(
                            calculation.summary.selected_decision_count
                        ),
                        selected_profile_pair_count=(
                            calculation.summary.selected_profile_pair_count
                        ),
                        skipped_counts=calculation.summary.skipped_counts,
                        inserted_candidate_metric_count=(
                            inserted_candidate_metric_count
                        ),
                        inserted_profile_snapshot_count=inserted_profile_snapshot_count,
                    )
                )
            except Exception:
                session.rollback()
                raise

        return VodomeryBackfillWriteResult(
            archive_run_id=archive_run_id,
            plan=plan,
            weeks=tuple(week_results),
        )
    finally:
        if owns_session:
            session.close()


def _group_plan_items_by_week(
    plan: VodomeryBackfillPlan,
) -> tuple[tuple[datetime, tuple[VodomeryBackfillPlanItem, ...]], ...]:
    grouped: dict[datetime, list[VodomeryBackfillPlanItem]] = {}
    for item in plan.items:
        grouped.setdefault(item.forecast_period.start, []).append(item)
    return tuple(
        (forecast_start, tuple(sorted(items, key=lambda item: item.identifier)))
        for forecast_start, items in sorted(grouped.items())
    )


def _calculate_vodomery_backfill_week(
    session,
    *,
    forecast_start: datetime,
    items: Sequence[VodomeryBackfillPlanItem],
    archive_run_id: str,
    archive_version: int,
    model_versions: Sequence[int],
    include_profile_snapshot_rows: bool = False,
) -> _BackfillWeekCalculation:
    forecast_period = build_calendar_week_period(forecast_start)
    planned_identifiers = {item.identifier for item in items}
    summaries = []
    device_summaries = []

    for model_version in model_versions:
        definition = vodomery_prediction._get_candidate_model_definition(model_version)
        if definition is None:
            raise ValueError(f"Unknown vodomery candidate model version: {model_version}")
        windows = vodomery_prediction._build_windows_for_definition(
            definition,
            reference_time=forecast_period.start,
        )
        summary = vodomery_prediction._rebuild_candidate_model(
            session,
            definition=definition,
            windows=windows,
        )
        rolling_result = (
            vodomery_prediction._run_candidate_rolling_weekly_backtest_with_devices(
                session,
                definition=definition,
                reference_end=forecast_period.start,
            )
        )
        summaries.append(
            vodomery_prediction._summary_with_rolling_backtest(
                summary,
                fold_count=vodomery_prediction.MODEL_ROLLING_BACKTEST_FOLD_COUNT,
                metrics=rolling_result.metrics,
            )
        )
        device_summaries.extend(
            summary
            for summary in rolling_result.device_metrics
            if summary.identifikace in planned_identifiers
        )

    device_summaries = list(vodomery_prediction._mark_best_device_models(device_summaries))
    selected_summary = vodomery_prediction.select_best_model_summary(summaries)
    if selected_summary is None:
        selected_summary = summaries[0]

    selected_decisions = vodomery_prediction._build_selected_model_decisions(
        device_summaries=device_summaries,
        selected_summary=selected_summary,
        forecast_period=forecast_period,
        selection_run_id=None,
        selection_mode="historical_backfill_dry_run",
        deployable_profile_pairs=vodomery_prediction._load_deployable_profile_pairs(
            session,
            device_summaries,
        ),
    )
    candidate_metric_rows = _build_backfill_candidate_metric_rows(
        device_summaries,
        selected_decisions=selected_decisions,
        forecast_period=forecast_period,
        archive_version=archive_version,
        archive_run_id=archive_run_id,
    )
    selected_profile_snapshot_rows = ()
    if include_profile_snapshot_rows:
        selected_profile_snapshot_rows = (
            vodomery_prediction._build_selected_prediction_profile_snapshot_rows(
                session,
                selected_decisions,
                archive_source=ARCHIVE_SOURCE_HISTORICAL_BACKFILL,
                archive_version=archive_version,
                archive_run_id=archive_run_id,
                require_all_pairs=False,
            )
        )
    selected_profile_pair_count = (
        vodomery_prediction._count_profile_snapshot_pairs(
            selected_profile_snapshot_rows,
        )
        if include_profile_snapshot_rows
        else len(selected_decisions)
    )
    calculated_identifiers = {summary.identifikace for summary in device_summaries}
    skipped = Counter()
    skipped["no_candidate_metrics"] = len(planned_identifiers - calculated_identifiers)

    return _BackfillWeekCalculation(
        summary=VodomeryBackfillDryRunWeekResult(
            forecast_period=forecast_period,
            planned_identifier_count=len(planned_identifiers),
            calculated_identifier_count=len(calculated_identifiers),
            candidate_metric_row_count=len(candidate_metric_rows),
            selected_decision_count=len(selected_decisions),
            selected_profile_pair_count=selected_profile_pair_count,
            skipped_counts={key: value for key, value in skipped.items() if value},
        ),
        selected_decisions=tuple(selected_decisions),
        candidate_metric_rows=candidate_metric_rows,
        selected_profile_snapshot_rows=selected_profile_snapshot_rows,
    )


def _build_backfill_candidate_metric_rows(
    device_summaries: Sequence[object],
    *,
    selected_decisions: Sequence[object],
    forecast_period: PredictionForecastPeriod,
    archive_version: int,
    archive_run_id: str,
) -> tuple[dict[str, object], ...]:
    selected_model_by_identifier = {
        decision.identifier: int(decision.selected_model_version)
        for decision in selected_decisions
    }
    fallback_by_identifier = {
        decision.identifier: decision.fallback_reason.value
        for decision in selected_decisions
        if decision.uses_fallback
    }
    rank_by_identifier = _rank_device_summaries_by_policy(device_summaries)
    rows = []
    for summary in device_summaries:
        rank = rank_by_identifier.get((summary.identifikace, int(summary.model_version)))
        selected = (
            selected_model_by_identifier.get(summary.identifikace)
            == int(summary.model_version)
        )
        rows.append(
            {
                "medium_key": vodomery_prediction.VODOMERY_MEDIUM_KEY,
                "identifier": summary.identifikace,
                "forecast_period_start": forecast_period.start,
                "forecast_period_end": forecast_period.end,
                "forecast_cadence": forecast_period.cadence.value,
                "forecast_period_label": forecast_period.label,
                "archive_version": archive_version,
                "archive_run_id": archive_run_id,
                "model_version": int(summary.model_version),
                "model_key": vodomery_prediction._device_model_key(summary),
                "model_name": summary.model_name,
                "selection_enabled": bool(summary.selection_enabled),
                "selected": selected,
                "eligible": rank is not None,
                "rank_by_policy": rank,
                "fallback_reason": (
                    fallback_by_identifier.get(summary.identifikace) if selected else None
                ),
                "validation_total_count": int(summary.rolling_validation_total_count),
                "matched_validation_count": int(summary.rolling_matched_validation_count),
                "coverage": float(summary.rolling_coverage),
                "mae": summary.rolling_mae,
                "rmse": summary.rolling_rmse,
                "bias": summary.rolling_bias,
                "wape": summary.rolling_wape,
            }
        )
    return tuple(rows)


def _rank_device_summaries_by_policy(
    device_summaries: Sequence[object],
) -> dict[tuple[str, int], int]:
    grouped: dict[str, list[object]] = {}
    for summary in device_summaries:
        if (
            bool(summary.selection_enabled)
            and vodomery_prediction._device_summary_has_selection_metrics(summary)
            and summary.rolling_coverage >= vodomery_prediction.MODEL_SELECTION_COVERAGE_THRESHOLD
        ):
            grouped.setdefault(summary.identifikace, []).append(summary)

    ranks: dict[tuple[str, int], int] = {}
    for identifikace, summaries in grouped.items():
        for rank, summary in enumerate(
            sorted(summaries, key=vodomery_prediction._device_summary_selection_key),
            start=1,
        ):
            ranks[(identifikace, int(summary.model_version))] = rank
    return ranks
