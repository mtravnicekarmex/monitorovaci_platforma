from __future__ import annotations

import html
from collections import Counter
from typing import Sequence

from moduly.mereni.kalorimetry.rolling_backtest import (
    KalorimetryCandidateRollingBacktestResult,
)
from moduly.mereni.kalorimetry.selection import (
    KalorimetryDryRunSelectionDecision,
)


KALORIMETRY_REBUILD_WORST_IDENTIFIER_LIMIT = 10


def build_kalorimetry_model_rebuild_report(
    *,
    candidate_results: Sequence[KalorimetryCandidateRollingBacktestResult],
    decisions: Sequence[KalorimetryDryRunSelectionDecision],
    worst_identifier_limit: int = KALORIMETRY_REBUILD_WORST_IDENTIFIER_LIMIT,
) -> dict[str, object]:
    if worst_identifier_limit <= 0:
        raise ValueError("Worst identifier limit must be positive.")

    winner_counts = Counter(
        int(decision.selected_model_version)
        for decision in decisions
        if decision.available and decision.selected_model_version is not None
    )
    fallback_counts = Counter(
        decision.fallback_reason
        for decision in decisions
        if decision.fallback_reason != "none"
    )
    candidate_rankings = sorted(
        (
            {
                "model_version": result.result.spec.model_version,
                "model_key": result.result.spec.model_key,
                "model_name": result.result.spec.model_name,
                "selection_enabled": result.result.spec.selection_enabled,
                "fold_count": len(result.result.folds),
                **result.result.metrics.to_dict(),
            }
            for result in candidate_results
        ),
        key=_candidate_ranking_key,
    )
    worst_identifiers = sorted(
        (
            {
                "identifier": decision.identifier,
                "selected_model_version": decision.selected_model_version,
                "selected_model_name": decision.selected_model_name,
                "fallback_reason": decision.fallback_reason,
                **decision.selected_metrics.to_dict(),
            }
            for decision in decisions
            if decision.available
            and decision.selected_metrics is not None
            and decision.selected_metrics.wape is not None
        ),
        key=lambda row: (
            -float(row["wape"]),
            str(row["identifier"]),
        ),
    )[:worst_identifier_limit]

    periods = {
        (
            decision.forecast_period_start,
            decision.forecast_period_end,
        )
        for decision in decisions
    }
    if len(periods) > 1:
        raise ValueError("Kalorimetry rebuild report mixes forecast periods.")
    period_start, period_end = next(iter(periods), (None, None))
    return {
        "medium_key": "kalorimetry",
        "selection_mode": "dry_run",
        "forecast_period_start": period_start,
        "forecast_period_end": period_end,
        "candidate_rankings": candidate_rankings,
        "winner_counts": dict(sorted(winner_counts.items())),
        "fallback_counts": dict(sorted(fallback_counts.items())),
        "identifier_count": len(decisions),
        "available_identifier_count": sum(
            1 for decision in decisions if decision.available
        ),
        "unavailable_identifier_count": sum(
            1 for decision in decisions if not decision.available
        ),
        "worst_identifiers": worst_identifiers,
    }


def render_kalorimetry_model_rebuild_report_html(
    report: dict[str, object],
) -> str:
    candidate_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('model_name') or '-'))}</td>"
        f"<td>v{int(row['model_version'])}</td>"
        f"<td>{_percent(row.get('coverage'))}</td>"
        f"<td>{_percent(row.get('wape'))}</td>"
        f"<td>{_metric(row.get('mae'))}</td>"
        f"<td>{_metric(row.get('rmse'))}</td>"
        f"<td>{_metric(row.get('bias'))}</td>"
        "</tr>"
        for row in report.get("candidate_rankings", [])
        if isinstance(row, dict)
    )
    worst_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('identifier') or '-'))}</td>"
        f"<td>v{int(row['selected_model_version'])}</td>"
        f"<td>{_percent(row.get('coverage'))}</td>"
        f"<td>{_percent(row.get('wape'))}</td>"
        f"<td>{html.escape(str(row.get('fallback_reason') or 'none'))}</td>"
        "</tr>"
        for row in report.get("worst_identifiers", [])
        if isinstance(row, dict)
    )
    winners = ", ".join(
        f"v{html.escape(str(version))}: {int(count)}"
        for version, count in dict(report.get("winner_counts") or {}).items()
    ) or "-"
    fallbacks = ", ".join(
        f"{html.escape(str(reason))}: {int(count)}"
        for reason, count in dict(report.get("fallback_counts") or {}).items()
    ) or "žádné"
    return (
        "<html><body>"
        "<h2>Kalorimetry – dry-run rebuild modelů</h2>"
        f"<p>Identifikátory: {int(report.get('identifier_count') or 0)}, "
        f"dostupné: {int(report.get('available_identifier_count') or 0)}, "
        f"nedostupné: {int(report.get('unavailable_identifier_count') or 0)}</p>"
        f"<p>Vítězné modely: {winners}<br>Fallbacky: {fallbacks}</p>"
        "<h3>Pořadí kandidátů</h3>"
        "<table><tr><th>Model</th><th>Verze</th><th>Coverage</th>"
        "<th>WAPE</th><th>MAE</th><th>RMSE</th><th>Bias</th></tr>"
        f"{candidate_rows}</table>"
        "<h3>Nejhorší identifikátory podle WAPE</h3>"
        "<table><tr><th>Identifikátor</th><th>Model</th><th>Coverage</th>"
        "<th>WAPE</th><th>Fallback</th></tr>"
        f"{worst_rows}</table>"
        "</body></html>"
    )


def _candidate_ranking_key(row: dict[str, object]) -> tuple:
    return (
        float("inf") if row.get("wape") is None else float(row["wape"]),
        float("inf") if row.get("mae") is None else float(row["mae"]),
        float("inf") if row.get("rmse") is None else float(row["rmse"]),
        (
            float("inf")
            if row.get("bias") is None
            else abs(float(row["bias"]))
        ),
        int(row["model_version"]),
    )


def _percent(value: object) -> str:
    return "-" if value is None else f"{float(value) * 100:.1f} %"


def _metric(value: object) -> str:
    return "-" if value is None else f"{float(value):.4f}"
