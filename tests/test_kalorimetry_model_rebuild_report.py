import datetime

from moduly.mereni.kalorimetry.calendar_baseline import (
    KalorimetryCalendarBaselineCandidate,
)
from moduly.mereni.kalorimetry.reporting.model_rebuild_report import (
    build_kalorimetry_model_rebuild_report,
    render_kalorimetry_model_rebuild_report_html,
)
from moduly.mereni.kalorimetry.rolling_backtest import (
    KalorimetryCandidateRollingBacktestResult,
)
from moduly.mereni.kalorimetry.selection import (
    KalorimetryDryRunSelectionDecision,
)
from moduly.mereni.kalorimetry.weather_candidate import (
    KalorimetryWeatherCandidate,
)
from moduly.mereni.prediction import (
    PredictionBacktestResult,
    PredictionMetricSummary,
)


def _metrics(*, wape, coverage=0.9):
    return PredictionMetricSummary(
        validation_total_count=100,
        matched_validation_count=int(100 * coverage),
        coverage=coverage,
        mae=1.0,
        rmse=2.0,
        bias=-0.2,
        wape=wape,
    )


def _candidate(candidate, *, wape):
    return KalorimetryCandidateRollingBacktestResult(
        result=PredictionBacktestResult(
            spec=candidate.spec,
            folds=(),
            metrics=_metrics(wape=wape),
        ),
        identifier_metrics=(),
    )


def _decision(identifier, *, model_version=1, wape=0.2, fallback="none"):
    candidate = (
        KalorimetryCalendarBaselineCandidate()
        if model_version == 1
        else KalorimetryWeatherCandidate()
    )
    return KalorimetryDryRunSelectionDecision(
        identifier=identifier,
        forecast_period_start=datetime.datetime(2026, 7, 27),
        forecast_period_end=datetime.datetime(2026, 8, 3),
        available=True,
        selected_model_version=candidate.spec.model_version,
        selected_model_key=candidate.spec.model_key,
        selected_model_name=candidate.spec.model_name,
        fallback_reason=fallback,
        selected_metrics=_metrics(wape=wape),
        candidate_audits=(),
    )


def test_report_contains_rankings_winners_fallbacks_and_worst_identifiers():
    report = build_kalorimetry_model_rebuild_report(
        candidate_results=(
            _candidate(KalorimetryCalendarBaselineCandidate(), wape=0.25),
            _candidate(KalorimetryWeatherCandidate(), wape=0.15),
        ),
        decisions=(
            _decision("K1", model_version=2, wape=0.1),
            _decision(
                "K2",
                model_version=1,
                wape=0.5,
                fallback="missing_forecast_weather",
            ),
        ),
    )

    assert report["candidate_rankings"][0]["model_version"] == 2
    assert report["winner_counts"] == {1: 1, 2: 1}
    assert report["fallback_counts"] == {"missing_forecast_weather": 1}
    assert report["worst_identifiers"][0]["identifier"] == "K2"
    assert "actual_value" not in repr(report)


def test_report_counts_unavailable_without_fabricating_winner():
    unavailable = KalorimetryDryRunSelectionDecision(
        identifier="K3",
        forecast_period_start=datetime.datetime(2026, 7, 27),
        forecast_period_end=datetime.datetime(2026, 8, 3),
        available=False,
        selected_model_version=None,
        selected_model_key=None,
        selected_model_name=None,
        fallback_reason="insufficient_history",
        selected_metrics=None,
        candidate_audits=(),
    )

    report = build_kalorimetry_model_rebuild_report(
        candidate_results=(),
        decisions=(unavailable,),
    )

    assert report["winner_counts"] == {}
    assert report["unavailable_identifier_count"] == 1
    assert report["worst_identifiers"] == []


def test_html_escapes_identifier_and_contains_only_aggregate_sections():
    report = build_kalorimetry_model_rebuild_report(
        candidate_results=(
            _candidate(KalorimetryCalendarBaselineCandidate(), wape=0.25),
        ),
        decisions=(_decision("<K1>", wape=0.2),),
    )

    body = render_kalorimetry_model_rebuild_report_html(report)

    assert "&lt;K1&gt;" in body
    assert "Pořadí kandidátů" in body
    assert "Nejhorší identifikátory" in body
    assert "actual_value" not in body
