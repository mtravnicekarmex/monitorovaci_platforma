from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from moduly.mereni.kalorimetry.deployable_catalog import (
    PROFILE_INSUFFICIENT_HISTORY,
    KalorimetryDeployableCandidateCatalog,
)
from moduly.mereni.kalorimetry.rolling_backtest import (
    KalorimetryCandidateRollingBacktestResult,
    KalorimetryIdentifierRollingMetric,
)
from moduly.mereni.prediction import (
    PredictionCandidateSpec,
    PredictionMetricSummary,
)


KALORIMETRY_SELECTION_COVERAGE_THRESHOLD = 0.85
KALORIMETRY_SELECTION_MIN_FOLD_COUNT = 8
KALORIMETRY_SELECTION_MODE_DRY_RUN = "dry_run"

FALLBACK_NONE = "none"
FALLBACK_NO_IDENTIFIER_METRICS = "no_identifier_metrics"
FALLBACK_BELOW_FOLD_COUNT = "below_fold_count_threshold"
FALLBACK_BELOW_COVERAGE = "below_coverage_threshold"
FALLBACK_NO_DEPLOYABLE_PROFILE = "no_deployable_profile"
FALLBACK_INSUFFICIENT_HISTORY = "insufficient_history"


@dataclass(frozen=True)
class KalorimetryCandidateSelectionAudit:
    identifier: str
    model_version: int
    model_key: str
    metrics: PredictionMetricSummary | None
    rolling_backtest_fold_count: int
    matched_fold_count: int
    profile_available: bool
    profile_reason: str
    metric_eligible: bool
    fold_eligible: bool
    coverage_eligible: bool
    selectable: bool
    rank_by_policy: int | None = None


@dataclass(frozen=True)
class KalorimetryDryRunSelectionDecision:
    identifier: str
    forecast_period_start: object
    forecast_period_end: object
    available: bool
    selected_model_version: int | None
    selected_model_key: str | None
    selected_model_name: str | None
    fallback_reason: str
    selected_metrics: PredictionMetricSummary | None
    candidate_audits: tuple[KalorimetryCandidateSelectionAudit, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)


def build_kalorimetry_dry_run_selection_decisions(
    *,
    candidate_results: Sequence[KalorimetryCandidateRollingBacktestResult],
    deployable_catalog: KalorimetryDeployableCandidateCatalog,
    coverage_threshold: float = KALORIMETRY_SELECTION_COVERAGE_THRESHOLD,
    minimum_fold_count: int = KALORIMETRY_SELECTION_MIN_FOLD_COUNT,
) -> tuple[KalorimetryDryRunSelectionDecision, ...]:
    if not 0 <= coverage_threshold <= 1:
        raise ValueError("Coverage threshold must be between zero and one.")
    if minimum_fold_count <= 0:
        raise ValueError("Minimum fold count must be positive.")

    specs_by_version = {
        result.result.spec.model_version: result.result.spec
        for result in candidate_results
    }
    metrics_by_pair = {
        (metric.identifier, metric.model_version): metric
        for result in candidate_results
        for metric in result.identifier_metrics
    }
    identifiers = sorted(
        {
            entry.identifier for entry in deployable_catalog.entries
        }
        | {
            metric.identifier
            for result in candidate_results
            for metric in result.identifier_metrics
        }
    )

    decisions = []
    for identifier in identifiers:
        audits = [
            _build_candidate_audit(
                identifier=identifier,
                spec=spec,
                metric=metrics_by_pair.get(
                    (identifier, spec.model_version)
                ),
                deployable_catalog=deployable_catalog,
                coverage_threshold=coverage_threshold,
                minimum_fold_count=minimum_fold_count,
            )
            for spec in sorted(
                specs_by_version.values(),
                key=lambda item: item.model_version,
            )
        ]
        selectable = [audit for audit in audits if audit.selectable]
        ranked = sorted(selectable, key=_selection_key)
        rank_by_version = {
            audit.model_version: rank
            for rank, audit in enumerate(ranked, start=1)
        }
        ranked_audits = tuple(
            dataclass_replace_rank(
                audit,
                rank_by_version.get(audit.model_version),
            )
            for audit in audits
        )

        selected_audit = ranked[0] if ranked else None
        metric_winner = _metric_winner_ignoring_profile(audits)
        fallback_reason = _resolve_fallback_reason(
            audits=audits,
            selected=selected_audit,
            metric_winner=metric_winner,
        )
        selected_spec = (
            specs_by_version[selected_audit.model_version]
            if selected_audit is not None
            else None
        )
        decisions.append(
            KalorimetryDryRunSelectionDecision(
                identifier=identifier,
                forecast_period_start=deployable_catalog.forecast_period.start,
                forecast_period_end=deployable_catalog.forecast_period.end,
                available=selected_audit is not None,
                selected_model_version=(
                    selected_audit.model_version
                    if selected_audit is not None
                    else None
                ),
                selected_model_key=(
                    selected_audit.model_key
                    if selected_audit is not None
                    else None
                ),
                selected_model_name=(
                    selected_spec.model_name
                    if selected_spec is not None
                    else None
                ),
                fallback_reason=fallback_reason,
                selected_metrics=(
                    selected_audit.metrics
                    if selected_audit is not None
                    else None
                ),
                candidate_audits=ranked_audits,
                metadata={
                    "selection_mode": KALORIMETRY_SELECTION_MODE_DRY_RUN,
                    "selection_policy": (
                        "deployable_min_folds_coverage_wape_mae_rmse_bias"
                    ),
                    "coverage_threshold": coverage_threshold,
                    "minimum_fold_count": minimum_fold_count,
                    "metric_winner_model_version": (
                        metric_winner.model_version
                        if metric_winner is not None
                        else None
                    ),
                },
            )
        )
    return tuple(decisions)


def _build_candidate_audit(
    *,
    identifier: str,
    spec: PredictionCandidateSpec,
    metric: KalorimetryIdentifierRollingMetric | None,
    deployable_catalog: KalorimetryDeployableCandidateCatalog,
    coverage_threshold: float,
    minimum_fold_count: int,
) -> KalorimetryCandidateSelectionAudit:
    profile = deployable_catalog.get(
        identifier=identifier,
        model_version=spec.model_version,
    )
    metric_summary = metric.metrics if metric is not None else None
    metric_eligible = bool(
        metric is not None
        and metric_summary is not None
        and metric_summary.validation_total_count > 0
        and metric_summary.matched_validation_count > 0
        and metric_summary.wape is not None
        and metric_summary.mae is not None
        and metric_summary.rmse is not None
        and metric_summary.bias is not None
    )
    fold_eligible = bool(
        metric_eligible
        and metric is not None
        and metric.rolling_backtest_fold_count >= minimum_fold_count
    )
    coverage_eligible = bool(
        fold_eligible
        and metric_summary is not None
        and metric_summary.coverage >= coverage_threshold
    )
    profile_available = bool(profile is not None and profile.available)
    return KalorimetryCandidateSelectionAudit(
        identifier=identifier,
        model_version=spec.model_version,
        model_key=spec.model_key,
        metrics=metric_summary,
        rolling_backtest_fold_count=(
            metric.rolling_backtest_fold_count if metric is not None else 0
        ),
        matched_fold_count=(
            metric.matched_fold_count if metric is not None else 0
        ),
        profile_available=profile_available,
        profile_reason=(
            profile.reason if profile is not None else PROFILE_INSUFFICIENT_HISTORY
        ),
        metric_eligible=metric_eligible,
        fold_eligible=fold_eligible,
        coverage_eligible=coverage_eligible,
        selectable=bool(
            spec.selection_enabled
            and coverage_eligible
            and profile_available
        ),
    )


def _selection_key(
    audit: KalorimetryCandidateSelectionAudit,
) -> tuple[float, float, float, float, int, int]:
    metrics = audit.metrics
    if metrics is None:
        raise ValueError("Selectable candidate needs metrics.")
    return (
        float(metrics.wape),
        float(metrics.mae),
        float(metrics.rmse),
        abs(float(metrics.bias)),
        -int(metrics.matched_validation_count),
        audit.model_version,
    )


def _metric_winner_ignoring_profile(
    audits: Sequence[KalorimetryCandidateSelectionAudit],
) -> KalorimetryCandidateSelectionAudit | None:
    eligible = [
        audit
        for audit in audits
        if audit.coverage_eligible
    ]
    return min(eligible, key=_selection_key) if eligible else None


def _resolve_fallback_reason(
    *,
    audits: Sequence[KalorimetryCandidateSelectionAudit],
    selected: KalorimetryCandidateSelectionAudit | None,
    metric_winner: KalorimetryCandidateSelectionAudit | None,
) -> str:
    if selected is not None:
        if (
            metric_winner is not None
            and metric_winner.model_version != selected.model_version
        ):
            return metric_winner.profile_reason
        return FALLBACK_NONE
    if not any(audit.metric_eligible for audit in audits):
        if audits and all(
            audit.profile_reason == PROFILE_INSUFFICIENT_HISTORY
            for audit in audits
        ):
            return FALLBACK_INSUFFICIENT_HISTORY
        return FALLBACK_NO_IDENTIFIER_METRICS
    if not any(audit.fold_eligible for audit in audits):
        return FALLBACK_BELOW_FOLD_COUNT
    if not any(audit.coverage_eligible for audit in audits):
        return FALLBACK_BELOW_COVERAGE
    if audits and all(
        audit.profile_reason == PROFILE_INSUFFICIENT_HISTORY
        for audit in audits
    ):
        return FALLBACK_INSUFFICIENT_HISTORY
    return FALLBACK_NO_DEPLOYABLE_PROFILE


def dataclass_replace_rank(
    audit: KalorimetryCandidateSelectionAudit,
    rank: int | None,
) -> KalorimetryCandidateSelectionAudit:
    return KalorimetryCandidateSelectionAudit(
        identifier=audit.identifier,
        model_version=audit.model_version,
        model_key=audit.model_key,
        metrics=audit.metrics,
        rolling_backtest_fold_count=audit.rolling_backtest_fold_count,
        matched_fold_count=audit.matched_fold_count,
        profile_available=audit.profile_available,
        profile_reason=audit.profile_reason,
        metric_eligible=audit.metric_eligible,
        fold_eligible=audit.fold_eligible,
        coverage_eligible=audit.coverage_eligible,
        selectable=audit.selectable,
        rank_by_policy=rank,
    )
