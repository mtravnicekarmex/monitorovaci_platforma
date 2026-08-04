from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import math
from typing import Callable
from uuid import uuid4

from sqlalchemy import func, select, text

from core.db.connect import get_session_pg
from moduly.mereni.kalorimetry.calendar_baseline import (
    ensure_kalorimetry_prediction_tables,
)
from moduly.mereni.kalorimetry.database.models import (
    KalorimetryModelSelectionRun,
    KalorimetryModelValidationMetric,
    KalorimetryModelValidationRun,
)
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_FORECAST_PERIOD_DEFINITION,
    KALORIMETRY_PIPELINE_SETTINGS,
)
from moduly.mereni.kalorimetry.production_dry_run import (
    PRAGUE_TIMEZONE,
    KalorimetryProductionDryRunResult,
    run_kalorimetry_production_dry_run,
)
from moduly.mereni.kalorimetry.rolling_backtest import (
    persist_kalorimetry_rolling_metrics,
)
from moduly.mereni.kalorimetry.snapshot_persistence import (
    build_kalorimetry_snapshot_persistence_plan,
    persist_kalorimetry_snapshot_plan,
)
from moduly.mereni.prediction import (
    ARCHIVE_SOURCE_WEEKLY_REBUILD,
    SELECTION_MODE_ACTIVE,
    PredictionTimeWindow,
    build_rolling_backtest_folds,
    ensure_prediction_profile_snapshot_table,
    ensure_prediction_selected_model_snapshot_table,
)
from moduly.mereni.prediction.storage import (
    PredictionProfileSnapshot,
    PredictionSelectedModelSnapshot,
)


ACTIVATION_LOCK_KEY = "kalorimetry_current_snapshot_activation"


@dataclass(frozen=True)
class KalorimetryCurrentSnapshotActivationResult:
    forecast_period_start: datetime
    forecast_period_end: datetime
    selection_run_id: int
    validation_run_count: int
    validation_metric_count: int
    selected_model_snapshot_count: int
    profile_snapshot_count: int
    available_identifier_count: int
    unavailable_identifier_count: int
    winner_counts: dict[int, int]
    verified: bool

    def to_aggregate_dict(self) -> dict[str, object]:
        return {
            "mode": "controlled_current_snapshot_activation",
            "forecast_period_start": self.forecast_period_start,
            "forecast_period_end": self.forecast_period_end,
            "selection_run_id": self.selection_run_id,
            "validation_run_count": self.validation_run_count,
            "validation_metric_count": self.validation_metric_count,
            "selected_model_snapshot_count": self.selected_model_snapshot_count,
            "profile_snapshot_count": self.profile_snapshot_count,
            "available_identifier_count": self.available_identifier_count,
            "unavailable_identifier_count": self.unavailable_identifier_count,
            "winner_counts": dict(sorted(self.winner_counts.items())),
            "verified": self.verified,
        }


def rebuild_current_kalorimetry_snapshots(
    *,
    reference_time: datetime | None = None,
    dry_run_fn: Callable[..., KalorimetryProductionDryRunResult] = (
        run_kalorimetry_production_dry_run
    ),
    session_factory: Callable[[], object] = get_session_pg,
    ensure_kalorimetry_tables_fn: Callable[[], None] = (
        ensure_kalorimetry_prediction_tables
    ),
    ensure_selected_snapshot_table_fn: Callable[[], None] = (
        ensure_prediction_selected_model_snapshot_table
    ),
    ensure_profile_snapshot_table_fn: Callable[[], None] = (
        ensure_prediction_profile_snapshot_table
    ),
) -> dict[str, object]:
    """Build the current weekly snapshots or verify an exact prior rebuild."""
    resolved_reference = reference_time or datetime.now()
    dry_run = dry_run_fn(
        reference_time=resolved_reference,
        session_factory=session_factory,
    )
    period = dry_run.deployable_catalog.forecast_period
    available = [decision for decision in dry_run.decisions if decision.available]
    unavailable = [
        decision for decision in dry_run.decisions if not decision.available
    ]
    _validate_dry_run_for_activation(
        dry_run,
        expected_period_start=period.start,
        expected_period_end=period.end,
        expected_available_identifier_count=len(available),
        expected_unavailable_identifier_count=len(unavailable),
    )
    global_candidate = _select_global_candidate(dry_run)

    ensure_kalorimetry_tables_fn()
    ensure_selected_snapshot_table_fn()
    ensure_profile_snapshot_table_fn()

    existing = _verify_exact_period_matches_dry_run(
        session_factory=session_factory,
        dry_run=dry_run,
        global_model_version=int(global_candidate.model_version),
    )
    if existing is not None:
        return {
            "mode": "scheduled_current_snapshot_rebuild",
            "action": "verified_existing",
            "forecast_period_start": period.start,
            "forecast_period_end": period.end,
            **existing,
            "available_identifier_count": len(available),
            "unavailable_identifier_count": len(unavailable),
            "verified": True,
        }

    result = activate_kalorimetry_current_snapshots(
        reference_time=resolved_reference,
        expected_period_start=period.start,
        expected_period_end=period.end,
        expected_available_identifier_count=len(available),
        expected_unavailable_identifier_count=len(unavailable),
        confirm_activation=True,
        dry_run_fn=lambda **_kwargs: dry_run,
        session_factory=session_factory,
        ensure_kalorimetry_tables_fn=ensure_kalorimetry_tables_fn,
        ensure_selected_snapshot_table_fn=ensure_selected_snapshot_table_fn,
        ensure_profile_snapshot_table_fn=ensure_profile_snapshot_table_fn,
    )
    return {
        **result.to_aggregate_dict(),
        "mode": "scheduled_current_snapshot_rebuild",
        "action": "created",
    }


def activate_kalorimetry_current_snapshots(
    *,
    reference_time: datetime,
    expected_period_start: datetime,
    expected_period_end: datetime,
    expected_available_identifier_count: int,
    expected_unavailable_identifier_count: int,
    confirm_activation: bool = False,
    dry_run_fn: Callable[..., KalorimetryProductionDryRunResult] = (
        run_kalorimetry_production_dry_run
    ),
    session_factory: Callable[[], object] = get_session_pg,
    ensure_kalorimetry_tables_fn: Callable[[], None] = (
        ensure_kalorimetry_prediction_tables
    ),
    ensure_selected_snapshot_table_fn: Callable[[], None] = (
        ensure_prediction_selected_model_snapshot_table
    ),
    ensure_profile_snapshot_table_fn: Callable[[], None] = (
        ensure_prediction_profile_snapshot_table
    ),
) -> KalorimetryCurrentSnapshotActivationResult:
    if not confirm_activation:
        raise PermissionError("Current snapshot activation requires confirmation.")

    dry_run = dry_run_fn(
        reference_time=reference_time,
        session_factory=session_factory,
    )
    _validate_dry_run_for_activation(
        dry_run,
        expected_period_start=expected_period_start,
        expected_period_end=expected_period_end,
        expected_available_identifier_count=expected_available_identifier_count,
        expected_unavailable_identifier_count=(
            expected_unavailable_identifier_count
        ),
    )
    global_candidate = _select_global_candidate(dry_run)
    training_window, validation_window = _build_audit_windows(dry_run)
    winner_counts = Counter(
        int(decision.selected_model_version)
        for decision in dry_run.decisions
        if decision.available and decision.selected_model_version is not None
    )

    _require_exact_period_absent(
        session_factory=session_factory,
        period_start=expected_period_start,
        period_end=expected_period_end,
    )

    ensure_kalorimetry_tables_fn()
    ensure_selected_snapshot_table_fn()
    ensure_profile_snapshot_table_fn()

    session = session_factory()
    try:
        with session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": ACTIVATION_LOCK_KEY},
            )
            _assert_exact_period_absent_in_session(
                session,
                period_start=expected_period_start,
                period_end=expected_period_end,
            )

            validation_run_ids: list[int] = []
            validation_metric_count = 0
            for candidate_result in dry_run.candidate_results:
                before_ids = set(
                    session.execute(
                        select(KalorimetryModelValidationRun.id).where(
                            KalorimetryModelValidationRun.model_version
                            == candidate_result.result.spec.model_version,
                            KalorimetryModelValidationRun.reference_end
                            == expected_period_start,
                        )
                    ).scalars()
                )
                inserted = persist_kalorimetry_rolling_metrics(
                    session,
                    candidate_result=candidate_result,
                    reference_end=expected_period_start,
                )
                expected_metrics = len(candidate_result.identifier_metrics)
                if inserted != expected_metrics:
                    raise RuntimeError(
                        "Kalorimetry validation metric insert count mismatch."
                    )
                validation_metric_count += inserted
                after_ids = set(
                    session.execute(
                        select(KalorimetryModelValidationRun.id).where(
                            KalorimetryModelValidationRun.model_version
                            == candidate_result.result.spec.model_version,
                            KalorimetryModelValidationRun.reference_end
                            == expected_period_start,
                        )
                    ).scalars()
                )
                created_ids = after_ids - before_ids
                if len(created_ids) != 1:
                    raise RuntimeError(
                        "Kalorimetry validation run identity is ambiguous."
                    )
                validation_run_ids.extend(created_ids)

            selection_run = KalorimetryModelSelectionRun(
                train_start=training_window.start,
                train_end=training_window.end,
                validation_start=validation_window.start,
                validation_end=validation_window.end,
                deploy_start=expected_period_start,
                deploy_end=expected_period_end,
                selected_model_version=global_candidate.model_version,
                selected_model_name=global_candidate.model_name,
            )
            session.add(selection_run)
            session.flush()
            selection_run_id = int(selection_run.id)

            archive_run_id = (
                f"kalorimetry-selection-{selection_run_id}-"
                f"{uuid4().hex[:12]}"
            )
            plan = build_kalorimetry_snapshot_persistence_plan(
                dry_run_decisions=dry_run.decisions,
                deployable_catalog=dry_run.deployable_catalog,
                global_candidate=global_candidate,
                selection_run_id=selection_run_id,
                archive_run_id=archive_run_id,
                selection_mode=SELECTION_MODE_ACTIVE,
                archive_source=ARCHIVE_SOURCE_WEEKLY_REBUILD,
                archive_version=1,
                training_window=training_window,
                validation_window=validation_window,
            )
            expected_profile_count = 672 * expected_available_identifier_count
            if (
                plan.available_identifier_count
                != expected_available_identifier_count
                or len(plan.unavailable_identifiers)
                != expected_unavailable_identifier_count
                or plan.profile_point_count != expected_profile_count
            ):
                raise RuntimeError(
                    "Kalorimetry activation plan differs from approved counts."
                )

            persisted = persist_kalorimetry_snapshot_plan(
                session,
                plan,
                selection_mode=SELECTION_MODE_ACTIVE,
            )
            del persisted
            _assert_transaction_snapshot_counts(
                session,
                period_start=expected_period_start,
                period_end=expected_period_end,
                selection_run_id=selection_run_id,
                expected_decision_count=expected_available_identifier_count,
                expected_profile_count=expected_profile_count,
            )

        verified = _verify_persisted_activation(
            session_factory=session_factory,
            period_start=expected_period_start,
            period_end=expected_period_end,
            selection_run_id=selection_run_id,
            validation_run_ids=tuple(validation_run_ids),
            expected_available_identifier_count=(
                expected_available_identifier_count
            ),
            expected_profile_count=672 * expected_available_identifier_count,
            expected_validation_metric_count=validation_metric_count,
        )
        return KalorimetryCurrentSnapshotActivationResult(
            forecast_period_start=expected_period_start,
            forecast_period_end=expected_period_end,
            selection_run_id=selection_run_id,
            validation_run_count=len(validation_run_ids),
            validation_metric_count=validation_metric_count,
            selected_model_snapshot_count=expected_available_identifier_count,
            profile_snapshot_count=672 * expected_available_identifier_count,
            available_identifier_count=expected_available_identifier_count,
            unavailable_identifier_count=expected_unavailable_identifier_count,
            winner_counts=dict(winner_counts),
            verified=verified,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _validate_dry_run_for_activation(
    dry_run: KalorimetryProductionDryRunResult,
    *,
    expected_period_start: datetime,
    expected_period_end: datetime,
    expected_available_identifier_count: int,
    expected_unavailable_identifier_count: int,
) -> None:
    period = dry_run.deployable_catalog.forecast_period
    if (
        period.start != expected_period_start
        or period.end != expected_period_end
    ):
        raise RuntimeError("Kalorimetry dry-run period differs from approval.")
    if dry_run.forecast_run_at is None or dry_run.forecast_hdd_hour_count != 168:
        raise RuntimeError("Kalorimetry forecast coverage is incomplete.")
    period_start_utc = (
        period.start.replace(tzinfo=PRAGUE_TIMEZONE)
        .astimezone(UTC)
        .replace(tzinfo=None)
    )
    if dry_run.forecast_run_at >= period_start_utc:
        raise RuntimeError("Kalorimetry forecast was issued after week start.")
    if (
        dry_run.latest_observation_at is None
        or dry_run.latest_observation_at
        < expected_period_start - timedelta(minutes=15)
    ):
        raise RuntimeError("Kalorimetry observations are stale for activation.")

    available = [decision for decision in dry_run.decisions if decision.available]
    unavailable = [
        decision for decision in dry_run.decisions if not decision.available
    ]
    if (
        len(available) != expected_available_identifier_count
        or len(unavailable) != expected_unavailable_identifier_count
    ):
        raise RuntimeError("Kalorimetry availability counts changed after approval.")
    for decision in available:
        if decision.selected_metrics is None or not all(
            value is not None and math.isfinite(float(value))
            for value in (
                decision.selected_metrics.wape,
                decision.selected_metrics.mae,
                decision.selected_metrics.rmse,
                decision.selected_metrics.bias,
            )
        ):
            raise RuntimeError("Available kalorimetry decision lacks finite metrics.")
        selected_audit = next(
            (
                audit
                for audit in decision.candidate_audits
                if audit.model_version == decision.selected_model_version
            ),
            None,
        )
        if (
            selected_audit is None
            or selected_audit.matched_fold_count < 8
            or selected_audit.metrics is None
            or selected_audit.metrics.coverage < 0.85
            or not selected_audit.profile_available
        ):
            raise RuntimeError("Selected kalorimetry decision fails policy gates.")


def _select_global_candidate(dry_run: KalorimetryProductionDryRunResult):
    candidates = [
        candidate.result.spec
        for candidate in dry_run.candidate_results
        if candidate.result.metrics.wape is not None
        and candidate.result.metrics.mae is not None
        and candidate.result.metrics.rmse is not None
        and candidate.result.metrics.bias is not None
    ]
    metrics_by_version = {
        candidate.result.spec.model_version: candidate.result.metrics
        for candidate in dry_run.candidate_results
    }
    if not candidates:
        raise RuntimeError("No finite global kalorimetry candidate exists.")
    return min(
        candidates,
        key=lambda spec: (
            float(metrics_by_version[spec.model_version].wape),
            float(metrics_by_version[spec.model_version].mae),
            float(metrics_by_version[spec.model_version].rmse),
            abs(float(metrics_by_version[spec.model_version].bias)),
            spec.model_version,
        ),
    )


def _build_audit_windows(
    dry_run: KalorimetryProductionDryRunResult,
) -> tuple[PredictionTimeWindow, PredictionTimeWindow]:
    training_months = max(
        candidate.result.spec.training_window_months
        for candidate in dry_run.candidate_results
    )
    folds = build_rolling_backtest_folds(
        reference_end=dry_run.deployable_catalog.forecast_period.start,
        fold_count=KALORIMETRY_PIPELINE_SETTINGS.rolling_backtest_fold_count,
        training_window_months=training_months,
        validation_period=KALORIMETRY_FORECAST_PERIOD_DEFINITION,
    )
    return (
        PredictionTimeWindow(
            start=folds[-1].train.start,
            end=dry_run.deployable_catalog.forecast_period.start,
            label="current_snapshot_deploy_train",
        ),
        PredictionTimeWindow(
            start=min(fold.validation.start for fold in folds),
            end=max(fold.validation.end for fold in folds),
            label="current_snapshot_rolling_validation",
        ),
    )


def _require_exact_period_absent(
    *,
    session_factory: Callable[[], object],
    period_start: datetime,
    period_end: datetime,
) -> None:
    session = session_factory()
    try:
        session.execute(text("SET TRANSACTION READ ONLY"))
        _assert_exact_period_absent_in_session(
            session,
            period_start=period_start,
            period_end=period_end,
        )
    finally:
        session.rollback()
        session.close()


def _assert_exact_period_absent_in_session(
    session,
    *,
    period_start: datetime,
    period_end: datetime,
) -> None:
    decision_count = session.execute(
        text(
            """
            SELECT count(*)
            FROM monitoring.prediction_selected_model_snapshots
            WHERE medium_key='kalorimetry'
              AND selection_mode='active'
              AND forecast_period_start=:period_start
              AND forecast_period_end=:period_end
            """
        ),
        {"period_start": period_start, "period_end": period_end},
    ).scalar_one()
    profile_count = session.execute(
        text(
            """
            SELECT count(*)
            FROM monitoring.prediction_profile_snapshots
            WHERE medium_key='kalorimetry'
              AND selection_mode='active'
              AND archive_source='weekly_rebuild'
              AND forecast_period_start=:period_start
              AND forecast_period_end=:period_end
            """
        ),
        {"period_start": period_start, "period_end": period_end},
    ).scalar_one()
    if int(decision_count) != 0 or int(profile_count) != 0:
        raise RuntimeError("Current kalorimetry snapshot identity already exists.")


def _verify_exact_period_matches_dry_run(
    *,
    session_factory: Callable[[], object],
    dry_run: KalorimetryProductionDryRunResult,
    global_model_version: int,
) -> dict[str, int] | None:
    period = dry_run.deployable_catalog.forecast_period
    expected_models = {
        str(decision.identifier): int(decision.selected_model_version)
        for decision in dry_run.decisions
        if decision.available and decision.selected_model_version is not None
    }
    session = session_factory()
    try:
        session.execute(text("SET TRANSACTION READ ONLY"))
        decisions = session.execute(
            select(
                PredictionSelectedModelSnapshot.identifier,
                PredictionSelectedModelSnapshot.selected_model_version,
                PredictionSelectedModelSnapshot.global_model_version,
                PredictionSelectedModelSnapshot.selection_run_id,
            ).where(
                PredictionSelectedModelSnapshot.medium_key == "kalorimetry",
                PredictionSelectedModelSnapshot.selection_mode
                == SELECTION_MODE_ACTIVE,
                PredictionSelectedModelSnapshot.forecast_period_start
                == period.start,
                PredictionSelectedModelSnapshot.forecast_period_end == period.end,
            )
        ).all()
        profile_groups = session.execute(
            select(
                PredictionProfileSnapshot.identifier,
                PredictionProfileSnapshot.model_version,
                PredictionProfileSnapshot.global_model_version,
                PredictionProfileSnapshot.selection_run_id,
                PredictionProfileSnapshot.archive_source,
                PredictionProfileSnapshot.archive_version,
                PredictionProfileSnapshot.interval_minutes,
                func.count(PredictionProfileSnapshot.id).label("profile_count"),
            )
            .where(
                PredictionProfileSnapshot.medium_key == "kalorimetry",
                PredictionProfileSnapshot.selection_mode == SELECTION_MODE_ACTIVE,
                PredictionProfileSnapshot.forecast_period_start == period.start,
                PredictionProfileSnapshot.forecast_period_end == period.end,
            )
            .group_by(
                PredictionProfileSnapshot.identifier,
                PredictionProfileSnapshot.model_version,
                PredictionProfileSnapshot.global_model_version,
                PredictionProfileSnapshot.selection_run_id,
                PredictionProfileSnapshot.archive_source,
                PredictionProfileSnapshot.archive_version,
                PredictionProfileSnapshot.interval_minutes,
            )
        ).all()
        if not decisions and not profile_groups:
            return None
        if not decisions or not profile_groups:
            raise RuntimeError("Existing kalorimetry snapshot period is incomplete.")

        actual_models = {
            str(row.identifier): int(row.selected_model_version)
            for row in decisions
        }
        selection_run_ids = {row.selection_run_id for row in decisions}
        if (
            len(decisions) != len(expected_models)
            or actual_models != expected_models
            or len(selection_run_ids) != 1
            or None in selection_run_ids
            or any(
                int(row.global_model_version) != global_model_version
                for row in decisions
            )
        ):
            raise RuntimeError("Existing kalorimetry decisions conflict with dry-run.")

        selection_run_id = int(next(iter(selection_run_ids)))
        expected_profile_groups = {
            (identifier, model_version) for identifier, model_version in expected_models.items()
        }
        actual_profile_groups = {
            (str(row.identifier), int(row.model_version)) for row in profile_groups
        }
        if actual_profile_groups != expected_profile_groups or any(
            row.selection_run_id != selection_run_id
            or row.archive_source != ARCHIVE_SOURCE_WEEKLY_REBUILD
            or int(row.archive_version) != 1
            or int(row.interval_minutes) != 15
            or int(row.global_model_version) != global_model_version
            or int(row.profile_count) != 672
            for row in profile_groups
        ):
            raise RuntimeError("Existing kalorimetry profiles conflict with dry-run.")

        selection_run_count = session.execute(
            select(func.count(KalorimetryModelSelectionRun.id)).where(
                KalorimetryModelSelectionRun.id == selection_run_id,
                KalorimetryModelSelectionRun.deploy_start == period.start,
                KalorimetryModelSelectionRun.deploy_end == period.end,
                KalorimetryModelSelectionRun.selected_model_version
                == global_model_version,
            )
        ).scalar_one()
        if int(selection_run_count) != 1:
            raise RuntimeError("Existing kalorimetry selection run is inconsistent.")
        return {
            "selection_run_id": selection_run_id,
            "selected_model_snapshot_count": len(decisions),
            "profile_snapshot_count": 672 * len(profile_groups),
        }
    finally:
        session.rollback()
        session.close()


def _verify_persisted_activation(
    *,
    session_factory: Callable[[], object],
    period_start: datetime,
    period_end: datetime,
    selection_run_id: int,
    validation_run_ids: tuple[int, ...],
    expected_available_identifier_count: int,
    expected_profile_count: int,
    expected_validation_metric_count: int,
) -> bool:
    session = session_factory()
    try:
        session.execute(text("SET TRANSACTION READ ONLY"))
        decision_count = session.execute(
            text(
                """
                SELECT count(*)
                FROM monitoring.prediction_selected_model_snapshots
                WHERE medium_key='kalorimetry'
                  AND selection_mode='active'
                  AND forecast_period_start=:period_start
                  AND forecast_period_end=:period_end
                  AND selection_run_id=:selection_run_id
                """
            ),
            {
                "period_start": period_start,
                "period_end": period_end,
                "selection_run_id": selection_run_id,
            },
        ).scalar_one()
        profile_count = session.execute(
            text(
                """
                SELECT count(*)
                FROM monitoring.prediction_profile_snapshots
                WHERE medium_key='kalorimetry'
                  AND selection_mode='active'
                  AND archive_source='weekly_rebuild'
                  AND archive_version=1
                  AND forecast_period_start=:period_start
                  AND forecast_period_end=:period_end
                  AND selection_run_id=:selection_run_id
                """
            ),
            {
                "period_start": period_start,
                "period_end": period_end,
                "selection_run_id": selection_run_id,
            },
        ).scalar_one()
        incomplete_profiles = session.execute(
            text(
                """
                SELECT count(*)
                FROM (
                    SELECT identifier, model_version
                    FROM monitoring.prediction_profile_snapshots
                    WHERE medium_key='kalorimetry'
                      AND selection_mode='active'
                      AND archive_source='weekly_rebuild'
                      AND forecast_period_start=:period_start
                      AND forecast_period_end=:period_end
                      AND selection_run_id=:selection_run_id
                    GROUP BY identifier, model_version
                    HAVING count(*) <> 672
                ) AS incomplete
                """
            ),
            {
                "period_start": period_start,
                "period_end": period_end,
                "selection_run_id": selection_run_id,
            },
        ).scalar_one()
        validation_metric_count = session.execute(
            select(func.count(KalorimetryModelValidationMetric.id)).where(
                KalorimetryModelValidationMetric.run_id.in_(validation_run_ids)
            )
        ).scalar_one()
        selection_run_count = session.execute(
            select(func.count(KalorimetryModelSelectionRun.id)).where(
                KalorimetryModelSelectionRun.id == selection_run_id,
                KalorimetryModelSelectionRun.deploy_start == period_start,
                KalorimetryModelSelectionRun.deploy_end == period_end,
            )
        ).scalar_one()
        checks = (
            int(decision_count) == expected_available_identifier_count,
            int(profile_count) == expected_profile_count,
            int(incomplete_profiles) == 0,
            int(validation_metric_count) == expected_validation_metric_count,
            int(selection_run_count) == 1,
        )
        if not all(checks):
            raise RuntimeError("Persisted kalorimetry activation failed verification.")
        return True
    finally:
        session.rollback()
        session.close()


def _assert_transaction_snapshot_counts(
    session,
    *,
    period_start: datetime,
    period_end: datetime,
    selection_run_id: int,
    expected_decision_count: int,
    expected_profile_count: int,
) -> None:
    parameters = {
        "period_start": period_start,
        "period_end": period_end,
        "selection_run_id": selection_run_id,
    }
    decision_count = session.execute(
        text(
            """
            SELECT count(*)
            FROM monitoring.prediction_selected_model_snapshots
            WHERE medium_key='kalorimetry'
              AND selection_mode='active'
              AND forecast_period_start=:period_start
              AND forecast_period_end=:period_end
              AND selection_run_id=:selection_run_id
            """
        ),
        parameters,
    ).scalar_one()
    profile_count = session.execute(
        text(
            """
            SELECT count(*)
            FROM monitoring.prediction_profile_snapshots
            WHERE medium_key='kalorimetry'
              AND selection_mode='active'
              AND archive_source='weekly_rebuild'
              AND archive_version=1
              AND forecast_period_start=:period_start
              AND forecast_period_end=:period_end
              AND selection_run_id=:selection_run_id
            """
        ),
        parameters,
    ).scalar_one()
    if (
        int(decision_count) != expected_decision_count
        or int(profile_count) != expected_profile_count
    ):
        raise RuntimeError(
            "Kalorimetry transaction row counts differ from approved plan: "
            f"decisions={int(decision_count)}/{expected_decision_count}, "
            f"profiles={int(profile_count)}/{expected_profile_count}."
        )
