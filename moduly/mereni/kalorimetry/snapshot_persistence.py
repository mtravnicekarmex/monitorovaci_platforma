from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from moduly.mereni.kalorimetry.deployable_catalog import (
    KalorimetryDeployableCandidateCatalog,
    validate_deployable_kalorimetry_profiles,
)
from moduly.mereni.kalorimetry.kalorimetry_prediction import (
    KALORIMETRY_MEDIUM_KEY,
)
from moduly.mereni.kalorimetry.selection import (
    FALLBACK_NONE,
    KalorimetryCandidateSelectionAudit,
    KalorimetryDryRunSelectionDecision,
)
from moduly.mereni.prediction import (
    ARCHIVE_SOURCE_WEEKLY_REBUILD,
    SELECTION_MODE_DRY_RUN,
    PredictionCandidateSpec,
    PredictionSelectedModelDecision,
    PredictionSelectionFallbackReason,
    PredictionTimeWindow,
    normalize_archive_source,
    normalize_selection_mode,
    persist_prediction_profile_snapshots,
    persist_selected_model_decisions,
)


@dataclass(frozen=True)
class KalorimetrySnapshotPersistencePlan:
    decisions: tuple[PredictionSelectedModelDecision, ...]
    profile_rows: tuple[dict[str, object], ...]
    unavailable_identifiers: tuple[str, ...]

    @property
    def available_identifier_count(self) -> int:
        return len(self.decisions)

    @property
    def profile_point_count(self) -> int:
        return len(self.profile_rows)


@dataclass(frozen=True)
class KalorimetrySnapshotPersistenceResult:
    selected_model_snapshot_count: int
    profile_snapshot_count: int
    available_identifier_count: int
    unavailable_identifier_count: int


def build_kalorimetry_snapshot_persistence_plan(
    *,
    dry_run_decisions: Sequence[KalorimetryDryRunSelectionDecision],
    deployable_catalog: KalorimetryDeployableCandidateCatalog,
    global_candidate: PredictionCandidateSpec,
    selection_run_id: int | None,
    archive_run_id: str,
    selection_mode: str = SELECTION_MODE_DRY_RUN,
    archive_source: str = ARCHIVE_SOURCE_WEEKLY_REBUILD,
    archive_version: int = 1,
    training_window: PredictionTimeWindow | None = None,
    validation_window: PredictionTimeWindow | None = None,
    created_at: datetime | None = None,
) -> KalorimetrySnapshotPersistencePlan:
    if global_candidate.medium_key != KALORIMETRY_MEDIUM_KEY:
        raise ValueError("Global candidate must belong to kalorimetry.")
    if selection_run_id is not None and selection_run_id <= 0:
        raise ValueError("Selection run id must be positive.")
    if not str(archive_run_id).strip():
        raise ValueError("Archive run id must not be empty.")
    if archive_version <= 0:
        raise ValueError("Archive version must be positive.")

    normalized_selection_mode = normalize_selection_mode(selection_mode)
    normalized_archive_source = normalize_archive_source(archive_source)
    if (
        selection_run_id is None
        and normalized_archive_source != "historical_backfill"
    ):
        raise ValueError(
            "A missing selection run id is reserved for historical backfill."
        )
    period = deployable_catalog.forecast_period
    identifiers = [decision.identifier for decision in dry_run_decisions]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Kalorimetry snapshot batch contains duplicate identifiers.")

    shared_decisions: list[PredictionSelectedModelDecision] = []
    profile_rows: list[dict[str, object]] = []
    unavailable_identifiers: list[str] = []
    for decision in sorted(dry_run_decisions, key=lambda item: item.identifier):
        if (
            decision.forecast_period_start != period.start
            or decision.forecast_period_end != period.end
        ):
            raise ValueError(
                "Kalorimetry selection and deployable catalog periods differ."
            )
        if not decision.available:
            _validate_unavailable_decision(decision)
            unavailable_identifiers.append(decision.identifier)
            continue

        selected_model_version = _require_selected_value(
            decision.selected_model_version,
            "model version",
        )
        selected_model_key = str(
            _require_selected_value(decision.selected_model_key, "model key")
        )
        selected_model_name = str(
            _require_selected_value(decision.selected_model_name, "model name")
        )
        entry = deployable_catalog.get(
            identifier=decision.identifier,
            model_version=int(selected_model_version),
        )
        if entry is None or not entry.available or not entry.profiles:
            raise RuntimeError(
                "Available kalorimetry selection is missing its deployable profile "
                f"for identifier {decision.identifier!r}."
            )
        if entry.model_key != selected_model_key:
            raise RuntimeError(
                "Selected kalorimetry model key differs from deployable profile."
            )
        validate_deployable_kalorimetry_profiles(
            entry.profiles,
            expected_identifier=decision.identifier,
            expected_model_version=int(selected_model_version),
        )

        fallback_reason = (
            PredictionSelectionFallbackReason.NONE
            if decision.fallback_reason == FALLBACK_NONE
            else PredictionSelectionFallbackReason.MISSING_PROFILE
        )
        metadata = {
            **dict(decision.metadata),
            "prediction_available": True,
            "availability_reason": None,
            "selection_fallback_detail": decision.fallback_reason,
            "candidate_audit": [
                _candidate_audit_to_dict(audit)
                for audit in decision.candidate_audits
            ],
        }
        shared_decision = PredictionSelectedModelDecision(
            medium_key=KALORIMETRY_MEDIUM_KEY,
            identifier=decision.identifier,
            forecast_period=period,
            selection_run_id=selection_run_id,
            selected_model_version=int(selected_model_version),
            selected_model_key=selected_model_key,
            selected_model_name=selected_model_name,
            global_model_version=global_candidate.model_version,
            global_model_key=global_candidate.model_key,
            global_model_name=global_candidate.model_name,
            fallback_reason=fallback_reason,
            metrics=decision.selected_metrics,
            created_at=created_at,
            metadata=metadata,
        )
        shared_decisions.append(shared_decision)
        profile_rows.extend(
            _profile_snapshot_rows(
                decision=shared_decision,
                profiles=entry.profiles,
                archive_run_id=archive_run_id,
                archive_source=normalized_archive_source,
                archive_version=archive_version,
                selection_mode=normalized_selection_mode,
                training_window=training_window,
                validation_window=validation_window,
                fallback_detail=decision.fallback_reason,
                created_at=created_at,
            )
        )

    expected_profile_count = 672 * len(shared_decisions)
    if len(profile_rows) != expected_profile_count:
        raise RuntimeError(
            "Kalorimetry snapshot batch is incomplete: expected "
            f"{expected_profile_count} profile points, got {len(profile_rows)}."
        )
    return KalorimetrySnapshotPersistencePlan(
        decisions=tuple(shared_decisions),
        profile_rows=tuple(profile_rows),
        unavailable_identifiers=tuple(sorted(unavailable_identifiers)),
    )


def persist_kalorimetry_snapshot_plan(
    session,
    plan: KalorimetrySnapshotPersistencePlan,
    *,
    selection_mode: str = SELECTION_MODE_DRY_RUN,
) -> KalorimetrySnapshotPersistenceResult:
    normalized_selection_mode = normalize_selection_mode(selection_mode)
    with session.begin_nested():
        selected_count = persist_selected_model_decisions(
            session,
            plan.decisions,
            selection_mode=normalized_selection_mode,
        )
        profile_count = persist_prediction_profile_snapshots(
            session,
            plan.profile_rows,
        )
        session.flush()
    return KalorimetrySnapshotPersistenceResult(
        selected_model_snapshot_count=selected_count,
        profile_snapshot_count=profile_count,
        available_identifier_count=plan.available_identifier_count,
        unavailable_identifier_count=len(plan.unavailable_identifiers),
    )


def _validate_unavailable_decision(
    decision: KalorimetryDryRunSelectionDecision,
) -> None:
    if any(
        value is not None
        for value in (
            decision.selected_model_version,
            decision.selected_model_key,
            decision.selected_model_name,
            decision.selected_metrics,
        )
    ):
        raise ValueError(
            "Unavailable kalorimetry decision must not identify a selected model."
        )
    if decision.fallback_reason == FALLBACK_NONE:
        raise ValueError(
            "Unavailable kalorimetry decision needs an availability reason."
        )


def _require_selected_value(value, label: str):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"Available kalorimetry decision needs selected {label}.")
    return value


def _candidate_audit_to_dict(
    audit: KalorimetryCandidateSelectionAudit,
) -> dict[str, object]:
    return {
        "model_version": audit.model_version,
        "model_key": audit.model_key,
        "metrics": None if audit.metrics is None else audit.metrics.to_dict(),
        "rolling_backtest_fold_count": audit.rolling_backtest_fold_count,
        "matched_fold_count": audit.matched_fold_count,
        "profile_available": audit.profile_available,
        "profile_reason": audit.profile_reason,
        "metric_eligible": audit.metric_eligible,
        "fold_eligible": audit.fold_eligible,
        "coverage_eligible": audit.coverage_eligible,
        "selectable": audit.selectable,
        "rank_by_policy": audit.rank_by_policy,
    }


def _profile_snapshot_rows(
    *,
    decision: PredictionSelectedModelDecision,
    profiles,
    archive_run_id: str,
    archive_source: str,
    archive_version: int,
    selection_mode: str,
    training_window: PredictionTimeWindow | None,
    validation_window: PredictionTimeWindow | None,
    fallback_detail: str,
    created_at: datetime | None,
) -> list[dict[str, object]]:
    rows = []
    for point in profiles:
        metadata = {
            **dict(point.features),
            "selection_fallback_detail": fallback_detail,
        }
        row = {
            "medium_key": decision.medium_key,
            "identifier": decision.identifier,
            "forecast_period_start": decision.forecast_period.start,
            "forecast_period_end": decision.forecast_period.end,
            "forecast_cadence": decision.forecast_period.cadence.value,
            "forecast_period_label": decision.forecast_period.label,
            "archive_source": archive_source,
            "archive_version": archive_version,
            "selection_mode": selection_mode,
            "selection_run_id": decision.selection_run_id,
            "archive_run_id": archive_run_id,
            "model_version": decision.selected_model_version,
            "model_key": decision.selected_model_key,
            "model_name": decision.selected_model_name,
            "global_model_version": decision.global_model_version,
            "global_model_key": decision.global_model_key,
            "global_model_name": decision.global_model_name,
            "uses_fallback": decision.uses_fallback,
            "fallback_reason": decision.fallback_reason.value,
            "interval_minutes": point.interval_minutes,
            "day_of_week": point.day_of_week,
            "slot": point.slot,
            "expected_mean": point.expected_mean,
            "expected_median": point.expected_median,
            "expected_p10": point.expected_p10,
            "expected_p90": point.expected_p90,
            "expected_std": point.expected_std,
            "sample_size": point.sample_size,
            "source_profile_created_at": None,
            "training_window_start": (
                None if training_window is None else training_window.start
            ),
            "training_window_end": (
                None if training_window is None else training_window.end
            ),
            "validation_window_start": (
                None if validation_window is None else validation_window.start
            ),
            "validation_window_end": (
                None if validation_window is None else validation_window.end
            ),
            "metadata_json": json.dumps(
                metadata,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        if created_at is not None:
            row["created_at"] = created_at
        rows.append(row)
    return rows
