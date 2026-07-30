from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
from math import isclose

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_PG
from core.scheduler.scheduler import (
    _release_process_lock,
    _try_acquire_process_lock,
)
from moduly.mereni.plynomery.database.outlier_review_apply import (
    _rebuild_events_for_ident,
    _rebuild_scores_for_ident,
)
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    PlynomeryAnomalyScore,
)
from moduly.mereni.plynomery.plynomery_anomaly import (
    PLYNOMERY_MEDIUM_KEY,
    _build_per_identifier_selected_score_rows,
)
from moduly.mereni.prediction.storage import (
    PredictionProfileSnapshot,
    PredictionSelectedModelSnapshot,
    SELECTION_MODE_ACTIVE,
)


EXPECTED_SELECTION_RUN_ID = 21
EXPECTED_PERIOD_START = datetime(2026, 7, 27)
EXPECTED_PERIOD_END = datetime(2026, 8, 3)
EXPECTED_DECISIONS = 18
EXPECTED_AVAILABLE_DECISIONS = 5
EXPECTED_UNAVAILABLE_DECISIONS = 13
EXPECTED_PROFILE_PAIRS = 5
EXPECTED_PROFILE_ROWS_PER_PAIR = 672
SCORE_FLOAT_FIELDS = (
    "actual_value",
    "expected_mean",
    "expected_std",
    "expected_median",
    "expected_p10",
    "expected_p90",
    "deviation",
    "z_score",
)


class ReconciliationScopeError(RuntimeError):
    """Raised when production state differs from the reviewed incident scope."""


class ReconciliationLockError(RuntimeError):
    """Raised when reconciliation would race the quarter-hour scheduler job."""


@dataclass(frozen=True)
class ReconciliationDryRunSummary:
    selection_run_id: int
    active_model_version: int
    decision_count: int
    available_decision_count: int
    unavailable_decision_count: int
    measured_identifier_count: int
    measured_identifiers_without_decision: int
    profile_pair_count: int
    profile_row_count: int
    missing_available_profile_pairs: int
    profiles_for_unavailable_decisions: int
    profile_period_model_mismatches: int
    eligible_measurement_count: int
    expected_score_count: int
    intentionally_unscored_count: int
    persisted_score_count: int
    missing_score_count: int
    unexpected_score_count: int
    unavailable_selection_score_count: int
    mismatched_score_count: int
    mismatched_processed_score_count: int
    anomaly_flag_change_count: int
    severity_change_count: int
    affected_identifier_count: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class ReconciliationApplySummary:
    before: ReconciliationDryRunSummary
    after: ReconciliationDryRunSummary
    rebuilt_identifier_count: int
    rebuilt_score_count: int
    processed_score_count: int
    created_event_count: int
    resolved_event_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "rebuilt_identifier_count": self.rebuilt_identifier_count,
            "rebuilt_score_count": self.rebuilt_score_count,
            "processed_score_count": self.processed_score_count,
            "created_event_count": self.created_event_count,
            "resolved_event_count": self.resolved_event_count,
        }


def reconciliation_approval_sha256(
    summary: ReconciliationDryRunSummary,
) -> str:
    payload = json.dumps(
        summary.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def run_active_period_reconciliation_dry_run() -> ReconciliationDryRunSummary:
    with ENGINE_PG.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            session = Session(
                bind=connection,
                autoflush=False,
                expire_on_commit=False,
            )
            try:
                return build_active_period_reconciliation_dry_run(session)
            finally:
                session.close()
        finally:
            transaction.rollback()


def build_active_period_reconciliation_dry_run(
    session: Session,
) -> ReconciliationDryRunSummary:
    summary, _affected_identifiers = _build_active_period_reconciliation_audit(
        session
    )
    return summary


def _build_active_period_reconciliation_audit(
    session: Session,
) -> tuple[ReconciliationDryRunSummary, frozenset[str]]:
    snapshots = session.execute(
        select(PredictionSelectedModelSnapshot).where(
            PredictionSelectedModelSnapshot.medium_key == PLYNOMERY_MEDIUM_KEY,
            PredictionSelectedModelSnapshot.selection_mode == SELECTION_MODE_ACTIVE,
            PredictionSelectedModelSnapshot.selection_run_id
            == EXPECTED_SELECTION_RUN_ID,
            PredictionSelectedModelSnapshot.forecast_period_start
            == EXPECTED_PERIOD_START,
            PredictionSelectedModelSnapshot.forecast_period_end
            == EXPECTED_PERIOD_END,
        )
    ).scalars().all()
    _require(len(snapshots) == EXPECTED_DECISIONS, "decision_count")

    decision_by_identifier = {str(row.identifier): row for row in snapshots}
    _require(len(decision_by_identifier) == len(snapshots), "duplicate_decision")
    available_identifiers = {
        identifier
        for identifier, row in decision_by_identifier.items()
        if str(row.fallback_reason) != "insufficient_history"
    }
    unavailable_identifiers = set(decision_by_identifier) - available_identifiers
    _require(
        len(available_identifiers) == EXPECTED_AVAILABLE_DECISIONS,
        "available_decision_count",
    )
    _require(
        len(unavailable_identifiers) == EXPECTED_UNAVAILABLE_DECISIONS,
        "unavailable_decision_count",
    )

    profile_rows = session.execute(
        select(PredictionProfileSnapshot).where(
            PredictionProfileSnapshot.medium_key == PLYNOMERY_MEDIUM_KEY,
            PredictionProfileSnapshot.selection_mode == SELECTION_MODE_ACTIVE,
            PredictionProfileSnapshot.selection_run_id
            == EXPECTED_SELECTION_RUN_ID,
            PredictionProfileSnapshot.forecast_period_start
            == EXPECTED_PERIOD_START,
            PredictionProfileSnapshot.forecast_period_end == EXPECTED_PERIOD_END,
        )
    ).scalars().all()
    profile_counts: dict[tuple[str, int], int] = {}
    profile_period_model_mismatches = 0
    profiles_for_unavailable = 0
    for row in profile_rows:
        identifier = str(row.identifier)
        pair = (identifier, int(row.model_version))
        profile_counts[pair] = profile_counts.get(pair, 0) + 1
        decision = decision_by_identifier.get(identifier)
        if identifier in unavailable_identifiers:
            profiles_for_unavailable += 1
        if (
            decision is None
            or int(decision.selected_model_version) != int(row.model_version)
        ):
            profile_period_model_mismatches += 1

    expected_pairs = {
        (identifier, int(decision_by_identifier[identifier].selected_model_version))
        for identifier in available_identifiers
    }
    missing_profile_pairs = len(expected_pairs - set(profile_counts))
    complete_profile_pairs = sum(
        profile_counts.get(pair) == EXPECTED_PROFILE_ROWS_PER_PAIR
        for pair in expected_pairs
    )
    _require(complete_profile_pairs == EXPECTED_PROFILE_PAIRS, "profile_pair_count")
    _require(missing_profile_pairs == 0, "missing_available_profile_pair")
    _require(profiles_for_unavailable == 0, "profile_for_unavailable_decision")
    _require(profile_period_model_mismatches == 0, "profile_model_mismatch")

    measurements = session.execute(
        select(Mereni_plynomery)
        .where(
            Mereni_plynomery.date >= EXPECTED_PERIOD_START,
            Mereni_plynomery.date < EXPECTED_PERIOD_END,
            Mereni_plynomery.synthetic.is_(False),
            Mereni_plynomery.platne.is_(True),
            Mereni_plynomery.reset_detected.is_(False),
            Mereni_plynomery.delta.is_not(None),
        )
        .order_by(Mereni_plynomery.id.asc())
    ).scalars().all()
    measured_identifiers = {str(row.identifikace) for row in measurements}
    missing_decisions = measured_identifiers - set(decision_by_identifier)
    _require(not missing_decisions, "measured_identifier_without_decision")

    active_model_version = _load_runtime_model_version_read_only(session)
    _require(
        {int(row.global_model_version) for row in snapshots}
        == {active_model_version},
        "active_model_identity",
    )
    expected_rows = _build_per_identifier_selected_score_rows(
        session,
        measurements=measurements,
        output_model_version=active_model_version,
        selection_mode=SELECTION_MODE_ACTIVE,
    )
    expected_by_measurement = {
        int(row["measurement_id"]): row for row in expected_rows
    }
    _require(
        len(expected_by_measurement) == len(expected_rows),
        "duplicate_expected_score",
    )

    persisted_scores = session.execute(
        select(PlynomeryAnomalyScore).where(
            PlynomeryAnomalyScore.model_version == active_model_version,
            PlynomeryAnomalyScore.date >= EXPECTED_PERIOD_START,
            PlynomeryAnomalyScore.date < EXPECTED_PERIOD_END,
        )
    ).scalars().all()
    persisted_by_measurement = {
        int(row.measurement_id): row for row in persisted_scores
    }
    _require(
        len(persisted_by_measurement) == len(persisted_scores),
        "duplicate_persisted_score",
    )

    expected_ids = set(expected_by_measurement)
    persisted_ids = set(persisted_by_measurement)
    missing_ids = expected_ids - persisted_ids
    unexpected_ids = persisted_ids - expected_ids
    measurement_by_id = {int(row.id): row for row in measurements}
    unavailable_score_count = sum(
        str(measurement_by_id[measurement_id].identifikace)
        in unavailable_identifiers
        for measurement_id in unexpected_ids
        if measurement_id in measurement_by_id
    )
    _require(unavailable_score_count == 0, "score_for_unavailable_decision")
    _require(
        all(measurement_id in measurement_by_id for measurement_id in unexpected_ids),
        "unexpected_score_outside_eligible_measurements",
    )

    mismatched_ids: set[int] = set()
    anomaly_changes = 0
    severity_changes = 0
    processed_mismatches = 0
    for measurement_id in expected_ids & persisted_ids:
        expected = expected_by_measurement[measurement_id]
        persisted = persisted_by_measurement[measurement_id]
        numeric_mismatch = any(
            not _floats_match(expected[field], getattr(persisted, field))
            for field in SCORE_FLOAT_FIELDS
        )
        anomaly_changed = bool(expected["is_anomaly"]) != bool(persisted.is_anomaly)
        severity_changed = expected["severity"] != persisted.severity
        if numeric_mismatch or anomaly_changed or severity_changed:
            mismatched_ids.add(measurement_id)
            processed_mismatches += int(bool(persisted.processed))
        anomaly_changes += int(anomaly_changed)
        severity_changes += int(severity_changed)

    affected_ids = mismatched_ids | missing_ids | unexpected_ids
    affected_identifiers = {
        str(measurement_by_id[measurement_id].identifikace)
        for measurement_id in affected_ids
        if measurement_id in measurement_by_id
    }
    summary = ReconciliationDryRunSummary(
        selection_run_id=EXPECTED_SELECTION_RUN_ID,
        active_model_version=active_model_version,
        decision_count=len(snapshots),
        available_decision_count=len(available_identifiers),
        unavailable_decision_count=len(unavailable_identifiers),
        measured_identifier_count=len(measured_identifiers),
        measured_identifiers_without_decision=len(missing_decisions),
        profile_pair_count=complete_profile_pairs,
        profile_row_count=len(profile_rows),
        missing_available_profile_pairs=missing_profile_pairs,
        profiles_for_unavailable_decisions=profiles_for_unavailable,
        profile_period_model_mismatches=profile_period_model_mismatches,
        eligible_measurement_count=len(measurements),
        expected_score_count=len(expected_rows),
        intentionally_unscored_count=len(measurements) - len(expected_rows),
        persisted_score_count=len(persisted_scores),
        missing_score_count=len(missing_ids),
        unexpected_score_count=len(unexpected_ids),
        unavailable_selection_score_count=unavailable_score_count,
        mismatched_score_count=len(mismatched_ids),
        mismatched_processed_score_count=processed_mismatches,
        anomaly_flag_change_count=anomaly_changes,
        severity_change_count=severity_changes,
        affected_identifier_count=len(affected_identifiers),
    )
    return summary, frozenset(affected_identifiers)


def run_active_period_reconciliation_apply(
    *,
    approved_dry_run_sha256: str,
) -> ReconciliationApplySummary:
    lock_handle = _try_acquire_process_lock("quarter_hour_job")
    if lock_handle is None:
        raise ReconciliationLockError(
            "Reconciliation apply stopped: quarter_hour_job lock is busy."
        )

    try:
        with ENGINE_PG.connect() as connection:
            transaction = connection.begin()
            session = Session(
                bind=connection,
                autoflush=False,
                expire_on_commit=False,
            )
            try:
                before, affected_identifiers = (
                    _build_active_period_reconciliation_audit(session)
                )
                _require(
                    reconciliation_approval_sha256(before)
                    == str(approved_dry_run_sha256).lower(),
                    "approved_dry_run_sha256",
                )
                _require(
                    before.mismatched_score_count > 0,
                    "mismatched_score_count",
                )
                _require(
                    before.affected_identifier_count
                    == len(affected_identifiers),
                    "affected_identifier_count",
                )

                rebuilt_score_count = 0
                processed_score_count = 0
                created_event_count = 0
                resolved_event_count = 0
                for identifier in sorted(affected_identifiers):
                    score_summary = _rebuild_scores_for_ident(
                        session,
                        identifikace=identifier,
                        model_version=before.active_model_version,
                        start_date=EXPECTED_PERIOD_START,
                        use_per_identifier_selection=True,
                    )
                    event_summary = _rebuild_events_for_ident(
                        session,
                        identifikace=identifier,
                        model_version=before.active_model_version,
                        ensure_schema=False,
                    )
                    rebuilt_score_count += int(
                        score_summary["inserted_scores"]
                    )
                    processed_score_count += int(
                        event_summary["processed_scores"]
                    )
                    created_event_count += int(
                        event_summary["created_events"]
                    )
                    resolved_event_count += int(
                        event_summary["resolved_events"]
                    )

                session.flush()
                after, remaining_identifiers = (
                    _build_active_period_reconciliation_audit(session)
                )
                _require(after.mismatched_score_count == 0, "post_apply_mismatch")
                _require(after.missing_score_count == 0, "post_apply_missing_score")
                _require(
                    after.unexpected_score_count == 0,
                    "post_apply_unexpected_score",
                )
                _require(
                    after.unavailable_selection_score_count == 0,
                    "post_apply_unavailable_score",
                )
                _require(
                    not remaining_identifiers,
                    "post_apply_affected_identifier",
                )

                result = ReconciliationApplySummary(
                    before=before,
                    after=after,
                    rebuilt_identifier_count=len(affected_identifiers),
                    rebuilt_score_count=rebuilt_score_count,
                    processed_score_count=processed_score_count,
                    created_event_count=created_event_count,
                    resolved_event_count=resolved_event_count,
                )
                transaction.commit()
                return result
            except Exception:
                transaction.rollback()
                raise
            finally:
                session.close()
    finally:
        _release_process_lock(lock_handle)


def _floats_match(left: object, right: object) -> bool:
    try:
        return isclose(
            float(left),
            float(right),
            rel_tol=1e-9,
            abs_tol=1e-9,
        )
    except (TypeError, ValueError):
        return left is None and right is None


def _load_runtime_model_version_read_only(session: Session) -> int:
    value = session.execute(
        text(
            """
            SELECT selected_model_version
            FROM monitoring.plynomery_model_selection_runs
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        )
    ).scalar_one_or_none()
    if value is None:
        raise ReconciliationScopeError(
            "Reconciliation dry-run stopped: active_model_identity is missing."
        )
    return int(value)


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReconciliationScopeError(
            f"Reconciliation dry-run stopped: {reason} differs from approved scope."
        )
