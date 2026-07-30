from __future__ import annotations

import datetime

import pytest

from moduly.mereni.kalorimetry.calendar_baseline import (
    KalorimetryCalendarBaselineCandidate,
)
from moduly.mereni.kalorimetry.deployable_catalog import (
    PROFILE_MISSING_FORECAST_WEATHER,
    build_kalorimetry_deployable_candidate_catalog,
)
from moduly.mereni.kalorimetry.rolling_backtest import (
    KalorimetryCandidateRollingBacktestResult,
    KalorimetryIdentifierRollingMetric,
)
from moduly.mereni.kalorimetry.selection import (
    FALLBACK_BELOW_COVERAGE,
    FALLBACK_BELOW_FOLD_COUNT,
    FALLBACK_INSUFFICIENT_HISTORY,
    FALLBACK_NONE,
    FALLBACK_NO_IDENTIFIER_METRICS,
    build_kalorimetry_dry_run_selection_decisions,
)
from moduly.mereni.kalorimetry.weather_candidate import (
    KalorimetryWeatherCandidate,
)
from moduly.mereni.prediction import (
    PredictionBacktestResult,
    PredictionCandidateSpec,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionMetricSummary,
    PredictionObservation,
)


def observation(
    *,
    weather: bool,
    day: int,
    slot: int,
    sample: int,
) -> PredictionObservation:
    return PredictionObservation(
        identifier="K1",
        timestamp=datetime.datetime(2026, 1, 5)
        + datetime.timedelta(days=day, minutes=slot * 15),
        actual_value=1.0 + sample,
        interval_minutes=15,
        day_of_week=day,
        slot=slot,
        features={"hdd_24h": float(sample)} if weather else {},
    )


def complete_observations(*, weather: bool):
    return tuple(
        observation(
            weather=weather,
            day=day,
            slot=slot,
            sample=sample,
        )
        for day in range(7)
        for slot in range(96)
        for sample in range(2)
    )


def period():
    return PredictionForecastPeriod(
        start=datetime.datetime(2026, 7, 27),
        end=datetime.datetime(2026, 8, 3),
        cadence=PredictionForecastCadence.WEEKLY,
    )


def complete_weather():
    start = datetime.datetime(2026, 7, 26, 22)
    return {
        start + datetime.timedelta(hours=offset): 4.0
        for offset in range(168)
    }


def catalog(*, weather_available: bool = True, history_available: bool = True):
    weather = complete_weather()
    if not weather_available:
        del weather[sorted(weather)[10]]
    baseline_rows = (
        complete_observations(weather=False)
        if history_available
        else ()
    )
    weather_rows = (
        complete_observations(weather=True)
        if history_available
        else ()
    )
    return build_kalorimetry_deployable_candidate_catalog(
        baseline_observations=baseline_rows,
        weather_observations=weather_rows,
        forecast_period=period(),
        hdd_24h_by_utc_hour=weather,
        baseline_candidate=KalorimetryCalendarBaselineCandidate(
            minimum_slot_samples=2
        ),
        weather_candidate=KalorimetryWeatherCandidate(
            minimum_slot_samples=2
        ),
    )


def candidate_result(
    *,
    model_version: int,
    model_key: str,
    wape: float | None,
    coverage: float = 1.0,
    folds: int = 8,
    matched: int = 100,
) -> KalorimetryCandidateRollingBacktestResult:
    spec = PredictionCandidateSpec(
        medium_key="kalorimetry",
        model_version=model_version,
        model_key=model_key,
        model_name=f"Model {model_version}",
        training_window_months=12,
    )
    metrics = PredictionMetricSummary(
        validation_total_count=100,
        matched_validation_count=matched,
        coverage=coverage,
        mae=None if wape is None else 2.0,
        rmse=None if wape is None else 3.0,
        bias=None if wape is None else 0.5,
        wape=wape,
    )
    return KalorimetryCandidateRollingBacktestResult(
        result=PredictionBacktestResult(
            spec=spec,
            folds=(),
            metrics=metrics,
        ),
        identifier_metrics=(
            KalorimetryIdentifierRollingMetric(
                identifier="K1",
                model_version=model_version,
                model_key=model_key,
                rolling_backtest_fold_count=folds,
                matched_fold_count=folds if matched else 0,
                metrics=metrics,
            ),
        ),
    )


def test_weather_wins_when_metrics_and_both_profiles_are_eligible():
    decisions = build_kalorimetry_dry_run_selection_decisions(
        candidate_results=(
            candidate_result(
                model_version=1,
                model_key="baseline",
                wape=0.4,
            ),
            candidate_result(
                model_version=2,
                model_key="weather",
                wape=0.2,
            ),
        ),
        deployable_catalog=catalog(),
    )

    decision = decisions[0]
    assert decision.available is True
    assert decision.selected_model_version == 2
    assert decision.selected_model_name == "Model 2"
    assert decision.fallback_reason == FALLBACK_NONE
    assert decision.metadata["selection_mode"] == "dry_run"
    assert {
        audit.model_version: audit.rank_by_policy
        for audit in decision.candidate_audits
    } == {1: 2, 2: 1}


def test_metric_winning_weather_without_forecast_selects_baseline_and_audits_reason():
    decision = build_kalorimetry_dry_run_selection_decisions(
        candidate_results=(
            candidate_result(
                model_version=1,
                model_key="baseline",
                wape=0.4,
            ),
            candidate_result(
                model_version=2,
                model_key="weather",
                wape=0.2,
            ),
        ),
        deployable_catalog=catalog(weather_available=False),
    )[0]

    assert decision.available is True
    assert decision.selected_model_version == 1
    assert decision.fallback_reason == PROFILE_MISSING_FORECAST_WEATHER
    weather_audit = next(
        audit
        for audit in decision.candidate_audits
        if audit.model_version == 2
    )
    assert weather_audit.coverage_eligible is True
    assert weather_audit.profile_available is False
    assert weather_audit.profile_reason == PROFILE_MISSING_FORECAST_WEATHER
    assert weather_audit.selectable is False


def test_below_coverage_candidate_is_not_selectable():
    decision = build_kalorimetry_dry_run_selection_decisions(
        candidate_results=(
            candidate_result(
                model_version=1,
                model_key="baseline",
                wape=0.4,
                coverage=0.5,
            ),
            candidate_result(
                model_version=2,
                model_key="weather",
                wape=0.2,
                coverage=0.4,
            ),
        ),
        deployable_catalog=catalog(),
    )[0]

    assert decision.available is False
    assert decision.fallback_reason == FALLBACK_BELOW_COVERAGE


def test_below_fold_count_is_explicit():
    decision = build_kalorimetry_dry_run_selection_decisions(
        candidate_results=(
            candidate_result(
                model_version=1,
                model_key="baseline",
                wape=0.4,
                folds=7,
            ),
            candidate_result(
                model_version=2,
                model_key="weather",
                wape=0.2,
                folds=6,
            ),
        ),
        deployable_catalog=catalog(),
    )[0]

    assert decision.available is False
    assert decision.fallback_reason == FALLBACK_BELOW_FOLD_COUNT


def test_missing_metrics_is_explicit_even_when_profiles_exist():
    decision = build_kalorimetry_dry_run_selection_decisions(
        candidate_results=(
            candidate_result(
                model_version=1,
                model_key="baseline",
                wape=None,
                matched=0,
            ),
            candidate_result(
                model_version=2,
                model_key="weather",
                wape=None,
                matched=0,
            ),
        ),
        deployable_catalog=catalog(),
    )[0]

    assert decision.available is False
    assert decision.fallback_reason == FALLBACK_NO_IDENTIFIER_METRICS


def test_no_history_is_explicitly_unavailable():
    empty_catalog = build_kalorimetry_deployable_candidate_catalog(
        baseline_observations=(
            observation(weather=False, day=0, slot=0, sample=0),
        ),
        weather_observations=(
            observation(weather=True, day=0, slot=0, sample=0),
        ),
        forecast_period=period(),
        hdd_24h_by_utc_hour=complete_weather(),
        baseline_candidate=KalorimetryCalendarBaselineCandidate(
            minimum_slot_samples=2
        ),
        weather_candidate=KalorimetryWeatherCandidate(
            minimum_slot_samples=2
        ),
    )
    decision = build_kalorimetry_dry_run_selection_decisions(
        candidate_results=(
            candidate_result(
                model_version=1,
                model_key="baseline",
                wape=None,
                matched=0,
            ),
            candidate_result(
                model_version=2,
                model_key="weather",
                wape=None,
                matched=0,
            ),
        ),
        deployable_catalog=empty_catalog,
    )[0]

    assert decision.available is False
    assert decision.selected_model_version is None
    assert decision.fallback_reason == FALLBACK_INSUFFICIENT_HISTORY


def test_tie_break_is_stable_by_model_version():
    decision = build_kalorimetry_dry_run_selection_decisions(
        candidate_results=(
            candidate_result(
                model_version=2,
                model_key="weather",
                wape=0.2,
            ),
            candidate_result(
                model_version=1,
                model_key="baseline",
                wape=0.2,
            ),
        ),
        deployable_catalog=catalog(),
    )[0]

    assert decision.selected_model_version == 1


@pytest.mark.parametrize(
    ("coverage", "folds", "message"),
    [
        (-0.1, 8, "Coverage"),
        (1.1, 8, "Coverage"),
        (0.85, 0, "fold"),
    ],
)
def test_selection_thresholds_are_validated(coverage, folds, message):
    with pytest.raises(ValueError, match=message):
        build_kalorimetry_dry_run_selection_decisions(
            candidate_results=(),
            deployable_catalog=catalog(),
            coverage_threshold=coverage,
            minimum_fold_count=folds,
        )
