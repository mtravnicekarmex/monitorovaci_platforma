from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from sqlalchemy import text

from moduly.mereni.kalorimetry.prediction_backfill import (
    KalorimetryBackfillPlan,
    KalorimetryBackfillPlanItem,
    KalorimetryBackfillWeekCalculation,
)
from moduly.mereni.prediction import (
    SELECTION_MODE_ACTIVE,
    persist_prediction_backfill_candidate_metrics,
    persist_prediction_profile_snapshots,
    persist_selected_model_decisions,
)


BACKFILL_STATE_ABSENT = "absent"
BACKFILL_STATE_COMPLETE = "complete"
BACKFILL_STATE_CONFLICT = "conflict"


@dataclass(frozen=True)
class KalorimetryBackfillIdentityState:
    decision_models: tuple[tuple[str, int], ...] = ()
    candidate_models: tuple[tuple[str, int], ...] = ()
    selected_candidate_models: tuple[tuple[str, int], ...] = ()
    profile_point_counts: tuple[tuple[str, int, int], ...] = ()
    invalid_decision_run_count: int = 0
    invalid_profile_source_count: int = 0
    missing_tables: tuple[str, ...] = ()
    decision_fingerprints: tuple[str, ...] = ()
    candidate_fingerprints: tuple[str, ...] = ()
    profile_fingerprints: tuple[str, ...] = ()

    @property
    def row_count(self) -> int:
        return (
            len(self.decision_models)
            + len(self.candidate_models)
            + sum(count for _, _, count in self.profile_point_counts)
        )


@dataclass(frozen=True)
class KalorimetryBackfillWeekWorkflowResult:
    forecast_period_start: object
    identifier_count: int
    state: str
    decision_count: int
    candidate_metric_count: int
    profile_point_count: int
    inserted_decision_count: int = 0
    inserted_candidate_metric_count: int = 0
    inserted_profile_point_count: int = 0


@dataclass(frozen=True)
class KalorimetryBackfillWorkflowResult:
    mode: str
    archive_run_id: str
    archive_version: int
    weeks: tuple[KalorimetryBackfillWeekWorkflowResult, ...]

    @property
    def complete_week_count(self) -> int:
        return sum(week.state == BACKFILL_STATE_COMPLETE for week in self.weeks)

    @property
    def absent_week_count(self) -> int:
        return sum(week.state == BACKFILL_STATE_ABSENT for week in self.weeks)

    @property
    def conflict_week_count(self) -> int:
        return sum(week.state == BACKFILL_STATE_CONFLICT for week in self.weeks)


WeekCalculator = Callable[
    [object, tuple[str, ...], str, int],
    KalorimetryBackfillWeekCalculation,
]
StateLoader = Callable[
    [object, object, tuple[str, ...], int],
    KalorimetryBackfillIdentityState,
]


def dry_run_kalorimetry_prediction_backfill(
    plan: KalorimetryBackfillPlan,
    *,
    archive_run_id: str,
    calculate_week: WeekCalculator,
    session,
    load_state: StateLoader | None = None,
) -> KalorimetryBackfillWorkflowResult:
    return _run_read_only_workflow(
        mode="dry_run",
        plan=plan,
        archive_run_id=archive_run_id,
        calculate_week=calculate_week,
        session=session,
        load_state=load_state or load_kalorimetry_backfill_identity_state,
    )


def verify_kalorimetry_prediction_backfill(
    plan: KalorimetryBackfillPlan,
    *,
    archive_run_id: str,
    calculate_week: WeekCalculator,
    session,
    load_state: StateLoader | None = None,
) -> KalorimetryBackfillWorkflowResult:
    return _run_read_only_workflow(
        mode="verify",
        plan=plan,
        archive_run_id=archive_run_id,
        calculate_week=calculate_week,
        session=session,
        load_state=load_state or load_kalorimetry_backfill_identity_state,
    )


def apply_kalorimetry_prediction_backfill(
    plan: KalorimetryBackfillPlan,
    *,
    archive_run_id: str,
    calculate_week: WeekCalculator,
    session,
    confirm_apply: bool = False,
    load_state: StateLoader | None = None,
) -> KalorimetryBackfillWorkflowResult:
    _validate_workflow_identity(plan, archive_run_id)
    if not confirm_apply:
        raise PermissionError(
            "Kalorimetry historical backfill apply requires explicit confirmation."
        )
    resolved_load_state = (
        load_state or load_kalorimetry_backfill_identity_state
    )
    results = []
    for period, items in _group_plan_items_by_week(plan):
        identifiers = tuple(item.identifier for item in items)
        calculation = calculate_week(
            period,
            identifiers,
            archive_run_id,
            plan.archive_version,
        )
        expected = build_expected_kalorimetry_backfill_identity_state(
            calculation
        )
        existing = resolved_load_state(
            session,
            period,
            identifiers,
            plan.archive_version,
        )
        if existing.missing_tables:
            session.rollback()
            raise RuntimeError(
                "Kalorimetry backfill apply requires all shared snapshot "
                "and candidate metric tables."
            )
        state = classify_kalorimetry_backfill_identity(
            existing=existing,
            expected=expected,
        )
        if state == BACKFILL_STATE_CONFLICT:
            session.rollback()
            raise RuntimeError(
                "Kalorimetry backfill conflict for forecast week "
                f"{period.start:%Y-%m-%d}; no rows were written."
            )
        if state == BACKFILL_STATE_COMPLETE:
            results.append(
                _week_result(calculation, state=BACKFILL_STATE_COMPLETE)
            )
            continue

        try:
            with session.begin_nested():
                decision_count = persist_selected_model_decisions(
                    session,
                    calculation.snapshot_plan.decisions,
                    selection_mode=SELECTION_MODE_ACTIVE,
                )
                candidate_count = (
                    persist_prediction_backfill_candidate_metrics(
                        session,
                        calculation.candidate_metric_rows,
                    )
                )
                profile_count = persist_prediction_profile_snapshots(
                    session,
                    calculation.snapshot_plan.profile_rows,
                )
                session.flush()
                written = resolved_load_state(
                    session,
                    period,
                    identifiers,
                    plan.archive_version,
                )
                if classify_kalorimetry_backfill_identity(
                    existing=written,
                    expected=expected,
                ) != BACKFILL_STATE_COMPLETE:
                    raise RuntimeError(
                        "Kalorimetry backfill post-insert verification failed; "
                        "the weekly transaction must be rolled back."
                    )
                decision_count = len(
                    calculation.snapshot_plan.decisions
                )
                candidate_count = len(calculation.candidate_metric_rows)
                profile_count = len(calculation.snapshot_plan.profile_rows)
            session.commit()
        except Exception:
            session.rollback()
            raise
        results.append(
            _week_result(
                calculation,
                state=BACKFILL_STATE_COMPLETE,
                inserted_decision_count=decision_count,
                inserted_candidate_metric_count=candidate_count,
                inserted_profile_point_count=profile_count,
            )
        )
    return KalorimetryBackfillWorkflowResult(
        mode="apply",
        archive_run_id=archive_run_id,
        archive_version=plan.archive_version,
        weeks=tuple(results),
    )


def build_expected_kalorimetry_backfill_identity_state(
    calculation: KalorimetryBackfillWeekCalculation,
) -> KalorimetryBackfillIdentityState:
    return KalorimetryBackfillIdentityState(
        decision_models=tuple(
            sorted(
                (
                    decision.identifier,
                    int(decision.selected_model_version),
                )
                for decision in calculation.snapshot_plan.decisions
            )
        ),
        candidate_models=tuple(
            sorted(
                (
                    str(row["identifier"]),
                    int(row["model_version"]),
                )
                for row in calculation.candidate_metric_rows
            )
        ),
        selected_candidate_models=tuple(
            sorted(
                (
                    str(row["identifier"]),
                    int(row["model_version"]),
                )
                for row in calculation.candidate_metric_rows
                if bool(row["selected"])
            )
        ),
        profile_point_counts=_profile_counts(
            calculation.snapshot_plan.profile_rows
        ),
        decision_fingerprints=tuple(
            sorted(
                _fingerprint(
                    {
                        "identifier": decision.identifier,
                        "selected_model_version": (
                            decision.selected_model_version
                        ),
                        "selected_model_key": getattr(
                            decision,
                            "selected_model_key",
                            None,
                        ),
                        "global_model_version": getattr(
                            decision,
                            "global_model_version",
                            None,
                        ),
                        "fallback_reason": getattr(
                            getattr(decision, "fallback_reason", None),
                            "value",
                            getattr(decision, "fallback_reason", None),
                        ),
                        "metrics": (
                            None
                            if getattr(decision, "metrics", None) is None
                            else {
                                "validation_total_count": (
                                    decision.metrics.validation_total_count
                                ),
                                "matched_validation_count": (
                                    decision.metrics.matched_validation_count
                                ),
                                "coverage": decision.metrics.coverage,
                                "mae": decision.metrics.mae,
                                "rmse": decision.metrics.rmse,
                                "bias": decision.metrics.bias,
                                "wape": decision.metrics.wape,
                            }
                        ),
                    }
                )
                for decision in calculation.snapshot_plan.decisions
            )
        ),
        candidate_fingerprints=tuple(
            sorted(
                _fingerprint(
                    _selected_mapping(
                        row,
                        (
                            "identifier",
                            "model_version",
                            "model_key",
                            "selected",
                            "eligible",
                            "rank_by_policy",
                            "fallback_reason",
                            "validation_total_count",
                            "matched_validation_count",
                            "coverage",
                            "mae",
                            "rmse",
                            "bias",
                            "wape",
                        ),
                    )
                )
                for row in calculation.candidate_metric_rows
            )
        ),
        profile_fingerprints=tuple(
            sorted(
                _fingerprint(
                    _selected_mapping(
                        row,
                        (
                            "identifier",
                            "model_version",
                            "model_key",
                            "interval_minutes",
                            "day_of_week",
                            "slot",
                            "expected_mean",
                            "expected_median",
                            "expected_p10",
                            "expected_p90",
                            "expected_std",
                            "sample_size",
                        ),
                    )
                )
                for row in calculation.snapshot_plan.profile_rows
            )
        ),
    )


def classify_kalorimetry_backfill_identity(
    *,
    existing: KalorimetryBackfillIdentityState,
    expected: KalorimetryBackfillIdentityState,
) -> str:
    if existing.row_count == 0:
        if existing.missing_tables and len(existing.missing_tables) != 3:
            return BACKFILL_STATE_CONFLICT
        return BACKFILL_STATE_ABSENT
    if existing == expected:
        return BACKFILL_STATE_COMPLETE
    return BACKFILL_STATE_CONFLICT


def load_kalorimetry_backfill_identity_state(
    session,
    forecast_period,
    identifiers: tuple[str, ...],
    archive_version: int,
) -> KalorimetryBackfillIdentityState:
    table_names = (
        "monitoring.prediction_selected_model_snapshots",
        "monitoring.prediction_backfill_candidate_metrics",
        "monitoring.prediction_profile_snapshots",
    )
    table_row = (
        session.execute(
            text(
                """
                SELECT
                    to_regclass(:decision_table) AS decision_table,
                    to_regclass(:metric_table) AS metric_table,
                    to_regclass(:profile_table) AS profile_table
                """
            ),
            {
                "decision_table": table_names[0],
                "metric_table": table_names[1],
                "profile_table": table_names[2],
            },
        )
        .mappings()
        .one()
    )
    missing_tables = tuple(
        table_name
        for key, table_name in zip(
            ("decision_table", "metric_table", "profile_table"),
            table_names,
        )
        if table_row[key] is None
    )
    if missing_tables:
        return KalorimetryBackfillIdentityState(
            missing_tables=missing_tables,
        )

    params = {
        "medium_key": "kalorimetry",
        "period_start": forecast_period.start,
        "period_end": forecast_period.end,
        "cadence": forecast_period.cadence.value,
        "identifiers": list(identifiers),
        "archive_version": archive_version,
    }
    decision_rows = (
        session.execute(
            text(
                """
                SELECT identifier, selected_model_version, selected_model_key,
                       global_model_version, fallback_reason,
                       validation_total_count, matched_validation_count,
                       coverage, mae, rmse, bias, wape, selection_run_id
                FROM monitoring.prediction_selected_model_snapshots
                WHERE medium_key = :medium_key
                  AND forecast_period_start = :period_start
                  AND forecast_period_end = :period_end
                  AND forecast_cadence = :cadence
                  AND selection_mode = 'active'
                  AND identifier = ANY(:identifiers)
                ORDER BY identifier
                """
            ),
            params,
        )
        .mappings()
        .all()
    )
    metric_rows = (
        session.execute(
            text(
                """
                SELECT identifier, model_version, model_key, selected,
                       eligible, rank_by_policy, fallback_reason,
                       validation_total_count, matched_validation_count,
                       coverage, mae, rmse, bias, wape
                FROM monitoring.prediction_backfill_candidate_metrics
                WHERE medium_key = :medium_key
                  AND forecast_period_start = :period_start
                  AND forecast_period_end = :period_end
                  AND forecast_cadence = :cadence
                  AND archive_version = :archive_version
                  AND identifier = ANY(:identifiers)
                ORDER BY identifier, model_version
                """
            ),
            params,
        )
        .mappings()
        .all()
    )
    profile_rows = (
        session.execute(
            text(
                """
                SELECT identifier, model_version, model_key, archive_source,
                       selection_run_id, interval_minutes, day_of_week, slot,
                       expected_mean, expected_median, expected_p10,
                       expected_p90, expected_std, sample_size
                FROM monitoring.prediction_profile_snapshots
                WHERE medium_key = :medium_key
                  AND forecast_period_start = :period_start
                  AND forecast_period_end = :period_end
                  AND forecast_cadence = :cadence
                  AND selection_mode = 'active'
                  AND archive_version = :archive_version
                  AND identifier = ANY(:identifiers)
                ORDER BY identifier, model_version, interval_minutes,
                         day_of_week, slot
                """
            ),
            params,
        )
        .mappings()
        .all()
    )
    return KalorimetryBackfillIdentityState(
        decision_models=tuple(
            sorted(
                (
                    str(row["identifier"]),
                    int(row["selected_model_version"]),
                )
                for row in decision_rows
            )
        ),
        candidate_models=tuple(
            sorted(
                (
                    str(row["identifier"]),
                    int(row["model_version"]),
                )
                for row in metric_rows
            )
        ),
        selected_candidate_models=tuple(
            sorted(
                (
                    str(row["identifier"]),
                    int(row["model_version"]),
                )
                for row in metric_rows
                if bool(row["selected"])
            )
        ),
        profile_point_counts=_profile_counts(profile_rows),
        invalid_decision_run_count=sum(
            row["selection_run_id"] is not None for row in decision_rows
        ),
        invalid_profile_source_count=sum(
            row["archive_source"] != "historical_backfill"
            or row["selection_run_id"] is not None
            for row in profile_rows
        ),
        decision_fingerprints=tuple(
            sorted(
                _fingerprint(
                    {
                        "identifier": str(row["identifier"]),
                        "selected_model_version": int(
                            row["selected_model_version"]
                        ),
                        "selected_model_key": row["selected_model_key"],
                        "global_model_version": row["global_model_version"],
                        "fallback_reason": row["fallback_reason"],
                        "metrics": (
                            None
                            if row["validation_total_count"] is None
                            else {
                                "validation_total_count": int(
                                    row["validation_total_count"]
                                ),
                                "matched_validation_count": int(
                                    row["matched_validation_count"] or 0
                                ),
                                "coverage": float(row["coverage"] or 0),
                                "mae": row["mae"],
                                "rmse": row["rmse"],
                                "bias": row["bias"],
                                "wape": row["wape"],
                            }
                        ),
                    }
                )
                for row in decision_rows
            )
        ),
        candidate_fingerprints=tuple(
            sorted(
                _fingerprint(
                    _selected_mapping(
                        row,
                        (
                            "identifier",
                            "model_version",
                            "model_key",
                            "selected",
                            "eligible",
                            "rank_by_policy",
                            "fallback_reason",
                            "validation_total_count",
                            "matched_validation_count",
                            "coverage",
                            "mae",
                            "rmse",
                            "bias",
                            "wape",
                        ),
                    )
                )
                for row in metric_rows
            )
        ),
        profile_fingerprints=tuple(
            sorted(
                _fingerprint(
                    _selected_mapping(
                        row,
                        (
                            "identifier",
                            "model_version",
                            "model_key",
                            "interval_minutes",
                            "day_of_week",
                            "slot",
                            "expected_mean",
                            "expected_median",
                            "expected_p10",
                            "expected_p90",
                            "expected_std",
                            "sample_size",
                        ),
                    )
                )
                for row in profile_rows
            )
        ),
    )


def _run_read_only_workflow(
    *,
    mode: str,
    plan: KalorimetryBackfillPlan,
    archive_run_id: str,
    calculate_week: WeekCalculator,
    session,
    load_state: StateLoader,
) -> KalorimetryBackfillWorkflowResult:
    _validate_workflow_identity(plan, archive_run_id)
    results = []
    for period, items in _group_plan_items_by_week(plan):
        identifiers = tuple(item.identifier for item in items)
        calculation = calculate_week(
            period,
            identifiers,
            archive_run_id,
            plan.archive_version,
        )
        expected = build_expected_kalorimetry_backfill_identity_state(
            calculation
        )
        existing = load_state(
            session,
            period,
            identifiers,
            plan.archive_version,
        )
        state = classify_kalorimetry_backfill_identity(
            existing=existing,
            expected=expected,
        )
        results.append(_week_result(calculation, state=state))
    return KalorimetryBackfillWorkflowResult(
        mode=mode,
        archive_run_id=archive_run_id,
        archive_version=plan.archive_version,
        weeks=tuple(results),
    )


def _validate_workflow_identity(
    plan: KalorimetryBackfillPlan,
    archive_run_id: str,
) -> None:
    if not archive_run_id.strip():
        raise ValueError("Backfill workflow needs an archive run id.")
    if plan.archive_version <= 0:
        raise ValueError("Backfill archive version must be positive.")


def _group_plan_items_by_week(
    plan: KalorimetryBackfillPlan,
) -> tuple[
    tuple[object, tuple[KalorimetryBackfillPlanItem, ...]],
    ...,
]:
    grouped: dict[object, list[KalorimetryBackfillPlanItem]] = {}
    for item in plan.items:
        grouped.setdefault(item.forecast_period, []).append(item)
    return tuple(
        (
            period,
            tuple(sorted(items, key=lambda item: item.identifier)),
        )
        for period, items in sorted(
            grouped.items(),
            key=lambda pair: pair[0].start,
        )
    )


def _profile_counts(
    rows: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, int, int], ...]:
    counts: dict[tuple[str, int], int] = {}
    for row in rows:
        key = (str(row["identifier"]), int(row["model_version"]))
        counts[key] = counts.get(key, 0) + 1
    return tuple(
        sorted(
            (identifier, model_version, count)
            for (identifier, model_version), count in counts.items()
        )
    )


def _selected_mapping(
    row: Mapping[str, object],
    keys: Sequence[str],
) -> dict[str, object]:
    return {key: row.get(key) for key in keys}


def _fingerprint(value: Mapping[str, object]) -> str:
    payload = json.dumps(
        value,
        default=str,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _week_result(
    calculation: KalorimetryBackfillWeekCalculation,
    *,
    state: str,
    inserted_decision_count: int = 0,
    inserted_candidate_metric_count: int = 0,
    inserted_profile_point_count: int = 0,
) -> KalorimetryBackfillWeekWorkflowResult:
    return KalorimetryBackfillWeekWorkflowResult(
        forecast_period_start=calculation.forecast_period.start,
        identifier_count=len(calculation.planned_identifiers),
        state=state,
        decision_count=len(calculation.snapshot_plan.decisions),
        candidate_metric_count=len(calculation.candidate_metric_rows),
        profile_point_count=len(calculation.snapshot_plan.profile_rows),
        inserted_decision_count=inserted_decision_count,
        inserted_candidate_metric_count=inserted_candidate_metric_count,
        inserted_profile_point_count=inserted_profile_point_count,
    )
