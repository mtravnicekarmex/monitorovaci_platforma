import datetime
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.plynomery import plynomery_prediction
from moduly.mereni.plynomery.plynomery_prediction import (
    MODEL_VERSION_BASELINE,
    MODEL_VERSION_WEATHER_ADJUSTED,
    ModelPerformanceSummary,
    build_plynomery_weekly_forecast_period,
    build_rebuild_windows,
    get_candidate_model_specs,
    get_candidate_model_versions,
    select_best_model_summary,
)


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSelectionSession:
    def __init__(self, selected_model_version):
        self.selected_model_version = selected_model_version

    def execute(self, statement):
        return FakeScalarResult(self.selected_model_version)


def test_plynomery_build_rebuild_windows_uses_one_month_validation_after_three_month_training():
    reference_time = datetime.datetime(2026, 4, 10, 6, 10, 5)

    windows = build_rebuild_windows(reference_time=reference_time)

    assert windows.deploy_end == reference_time
    assert windows.validation_end == reference_time
    assert windows.validation_start == datetime.datetime(2026, 3, 10, 6, 10, 5)
    assert windows.train_start == datetime.datetime(2025, 12, 10, 6, 10, 5)
    assert windows.train_end == windows.validation_start
    assert windows.deploy_start == windows.train_start


def test_plynomery_forecast_period_is_the_current_prague_calendar_week():
    period = build_plynomery_weekly_forecast_period(
        reference_time=datetime.datetime(2026, 7, 27, 6, 10, 5)
    )

    assert period.start == datetime.datetime(2026, 7, 27)
    assert period.end == datetime.datetime(2026, 8, 3)
    assert period.cadence.value == "weekly"
    assert period.label == "2026-07-27 - 2026-08-03"


def test_plynomery_forecast_period_keeps_the_same_week_for_midweek_rebuild():
    period = build_plynomery_weekly_forecast_period(
        reference_time=datetime.datetime(2026, 7, 30, 14, 25)
    )

    assert period.start == datetime.datetime(2026, 7, 27)
    assert period.end == datetime.datetime(2026, 8, 3)


def test_plynomery_candidate_model_versions_includes_weather_adjusted_candidate():
    assert get_candidate_model_versions() == (
        MODEL_VERSION_BASELINE,
        MODEL_VERSION_WEATHER_ADJUSTED,
    )


def test_plynomery_candidate_model_specs_expose_shared_prediction_metadata():
    specs = get_candidate_model_specs()

    assert [
        (
            spec.medium_key,
            spec.model_version,
            spec.model_key,
            spec.model_name,
            spec.training_window_months,
            spec.validation_window_months,
            spec.selection_enabled,
        )
        for spec in specs
    ] == [
        (
            "plynomery",
            MODEL_VERSION_BASELINE,
            "exact_fallback_baseline",
            "Model 1 - exact/fallback baseline",
            3,
            1,
            True,
        ),
        (
            "plynomery",
            MODEL_VERSION_WEATHER_ADJUSTED,
            "weather_adjusted_baseline",
            "Model 2 - weather adjusted baseline",
            3,
            1,
            True,
        ),
    ]


def test_plynomery_runtime_model_version_uses_latest_selection(monkeypatch):
    monkeypatch.setattr(plynomery_prediction, "ensure_prediction_tables", lambda: None)

    selected = plynomery_prediction.get_runtime_model_version(
        session=FakeSelectionSession(MODEL_VERSION_WEATHER_ADJUSTED)
    )

    assert selected == MODEL_VERSION_WEATHER_ADJUSTED


def test_plynomery_runtime_model_version_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(plynomery_prediction, "ensure_prediction_tables", lambda: None)

    selected = plynomery_prediction.get_runtime_model_version(
        session=FakeSelectionSession(None)
    )

    assert selected == MODEL_VERSION_BASELINE


def test_plynomery_select_best_model_summary_prefers_coverage_before_lower_error():
    low_coverage = ModelPerformanceSummary(
        model_version=MODEL_VERSION_BASELINE,
        model_name="Model 1",
        validation_total_count=100,
        matched_validation_count=40,
        coverage=0.4,
        mae=0.1,
        rmse=0.2,
        bias=0.01,
        profile_count=500,
    )
    high_coverage = ModelPerformanceSummary(
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
        model_name="Model 2",
        validation_total_count=100,
        matched_validation_count=95,
        coverage=0.95,
        mae=0.15,
        rmse=0.25,
        bias=0.02,
        profile_count=520,
    )

    selected = select_best_model_summary((low_coverage, high_coverage))

    assert selected == high_coverage


def test_plynomery_combines_per_identifier_rolling_metrics_with_wape():
    definition = plynomery_prediction.get_candidate_model_definitions()[0]
    aggregates = {
        "P_A1": [
            plynomery_prediction.ValidationAggregate(
                validation_total_count=10,
                matched_validation_count=8,
                coverage=0.8,
                mae=1.0,
                rmse=1.0,
                bias=0.5,
                wape=0.2,
                abs_error_sum=8.0,
                squared_error_sum=8.0,
                error_sum=4.0,
                matched_actual_abs_sum=40.0,
            ),
            plynomery_prediction.ValidationAggregate(
                validation_total_count=10,
                matched_validation_count=10,
                coverage=1.0,
                mae=0.4,
                rmse=0.4,
                bias=-0.2,
                wape=0.1,
                abs_error_sum=4.0,
                squared_error_sum=1.6,
                error_sum=-2.0,
                matched_actual_abs_sum=40.0,
            ),
        ]
    }

    rows = plynomery_prediction._combine_device_rolling_metrics(
        definition,
        fold_count=2,
        device_fold_results=aggregates,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.rolling_backtest_fold_count == 2
    assert row.rolling_validation_total_count == 20
    assert row.rolling_matched_validation_count == 18
    assert row.rolling_coverage == 0.9
    assert row.rolling_mae == 12.0 / 18.0
    assert row.rolling_rmse == (9.6 / 18.0) ** 0.5
    assert row.rolling_bias == 2.0 / 18.0
    assert row.rolling_wape == 0.15


def test_plynomery_rolling_folds_end_on_completed_calendar_week(monkeypatch):
    definition = plynomery_prediction.get_candidate_model_definitions()[0]
    built_windows = []
    deleted_versions = []

    def fake_replace_profiles(
        session,
        *,
        model_version,
        data_start,
        data_end,
    ):
        built_windows.append((model_version, data_start, data_end))

    def fake_evaluate(session, *, model_version, windows):
        return {
            "P_A1": plynomery_prediction.ValidationAggregate(
                validation_total_count=10,
                matched_validation_count=10,
                coverage=1.0,
                mae=0.1,
                rmse=0.2,
                bias=0.0,
                wape=0.1,
                abs_error_sum=1.0,
                squared_error_sum=0.4,
                error_sum=0.0,
                matched_actual_abs_sum=10.0,
            )
        }

    monkeypatch.setattr(plynomery_prediction, "_replace_profiles", fake_replace_profiles)
    monkeypatch.setattr(
        plynomery_prediction,
        "_evaluate_profiles_on_validation_by_identifikace",
        fake_evaluate,
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_delete_profiles",
        lambda session, model_version: deleted_versions.append(model_version),
    )

    result = plynomery_prediction._run_candidate_rolling_weekly_backtest_with_devices(
        object(),
        definition=definition,
        reference_end=datetime.datetime(2026, 7, 27),
        fold_count=2,
    )

    assert [item[2] for item in built_windows] == [
        datetime.datetime(2026, 7, 13),
        datetime.datetime(2026, 7, 20),
    ]
    assert deleted_versions == [2101, 2102]
    assert result.metrics.validation_total_count == 20
    assert result.device_metrics[0].rolling_backtest_fold_count == 2


def test_plynomery_rebuild_exposes_per_identifier_rolling_candidates(monkeypatch):
    definitions = plynomery_prediction.get_candidate_model_definitions()
    transaction_calls = []
    session = SimpleNamespace(
        commit=lambda: transaction_calls.append("commit"),
        rollback=lambda: transaction_calls.append("rollback"),
        close=lambda: None,
    )

    monkeypatch.setattr(plynomery_prediction, "ensure_prediction_tables", lambda: None)
    monkeypatch.setattr(
        plynomery_prediction,
        "ensure_prediction_selected_model_snapshot_table",
        lambda: None,
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "ensure_prediction_profile_snapshot_table",
        lambda: None,
    )
    monkeypatch.setattr(plynomery_prediction, "get_session_pg", lambda: session)
    monkeypatch.setattr(
        plynomery_prediction,
        "get_runtime_model_version",
        lambda **kwargs: MODEL_VERSION_BASELINE,
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_build_windows_for_definition",
        lambda definition, reference_time: build_rebuild_windows(reference_time),
    )

    def fake_rolling(session, *, definition, reference_end):
        metrics = plynomery_prediction.PredictionMetricSummary(
            validation_total_count=100,
            matched_validation_count=90,
            coverage=0.9,
            mae=float(definition.model_version),
            rmse=float(definition.model_version) + 0.1,
            bias=0.0,
            wape=0.1 * definition.model_version,
        )
        return plynomery_prediction.CandidateRollingBacktestResult(
            metrics=metrics,
            device_metrics=(
                plynomery_prediction.DeviceModelPerformanceSummary(
                    identifikace="P_A1",
                    model_version=definition.model_version,
                    model_key=definition.model_key,
                    model_name=definition.model_name,
                    selection_enabled=True,
                    rolling_backtest_fold_count=8,
                    rolling_validation_total_count=100,
                    rolling_matched_validation_count=90,
                    rolling_coverage=0.9,
                    rolling_mae=metrics.mae,
                    rolling_rmse=metrics.rmse,
                    rolling_bias=metrics.bias,
                    rolling_wape=metrics.wape,
                ),
            ),
        )

    monkeypatch.setattr(
        plynomery_prediction,
        "_run_candidate_rolling_weekly_backtest_with_devices",
        fake_rolling,
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_rebuild_candidate_model",
        lambda session, *, definition, windows: ModelPerformanceSummary(
            model_version=definition.model_version,
            model_name=definition.model_name,
            model_key=definition.model_key,
            validation_total_count=100,
            matched_validation_count=90,
            coverage=0.9,
            mae=float(definition.model_version),
            rmse=float(definition.model_version) + 0.1,
            bias=0.0,
            profile_count=10,
        ),
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_persist_selection_run",
        lambda *args, **kwargs: SimpleNamespace(id=18),
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_load_deployable_profile_catalog",
        lambda session, device_summaries: {
            ("P_A1", MODEL_VERSION_BASELINE): (
                plynomery_prediction.PredictionProfilePoint(
                    identifier="P_A1",
                    interval_minutes=15,
                    day_of_week=1,
                    slot=1,
                    expected_mean=1.0,
                    expected_median=1.0,
                    expected_p10=0.5,
                    expected_p90=1.5,
                    expected_std=0.2,
                    sample_size=10,
                    model_version=MODEL_VERSION_BASELINE,
                    features={"profile_kind": "static"},
                ),
            ),
            ("P_A1", MODEL_VERSION_WEATHER_ADJUSTED): (
                plynomery_prediction.PredictionProfilePoint(
                    identifier="P_A1",
                    interval_minutes=15,
                    day_of_week=1,
                    slot=1,
                    expected_mean=1.0,
                    expected_median=1.0,
                    expected_p10=0.5,
                    expected_p90=1.5,
                    expected_std=0.2,
                    sample_size=10,
                    model_version=MODEL_VERSION_WEATHER_ADJUSTED,
                    features={"profile_kind": "weather_adjusted"},
                ),
            ),
        },
    )
    persisted_selection_modes = []

    def fake_persist_decisions(session, decisions, selection_mode):
        transaction_calls.append("selected_models")
        persisted_selection_modes.append(selection_mode)
        return len(decisions)

    def fake_persist_profiles(session, rows):
        transaction_calls.append("profiles")
        persisted_selection_modes.extend(
            sorted({row["selection_mode"] for row in rows})
        )
        return len(rows)

    monkeypatch.setattr(
        plynomery_prediction,
        "persist_selected_model_decisions",
        fake_persist_decisions,
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "persist_prediction_profile_snapshots",
        fake_persist_profiles,
    )

    result = plynomery_prediction.rebuild_profiles(
        reference_time=datetime.datetime(2026, 7, 27, 6, 10, 5)
    )

    assert len(result["candidates"]) == len(definitions)
    assert all(row["rolling_backtest_fold_count"] == 8 for row in result["candidates"])
    assert [row["model_version"] for row in result["per_identifier_candidates"]] == [
        MODEL_VERSION_BASELINE,
        MODEL_VERSION_WEATHER_ADJUSTED,
    ]
    assert result["deployable_profile_pair_count"] == 2
    assert result["deployable_profile_count"] == 2
    assert len(result["dry_run_selected_models"]) == 1
    assert result["dry_run_selected_models"][0]["selected_model_version"] == 1
    assert result["dry_run_fallback_count"] == 0
    assert result["dry_run_unavailable_count"] == 0
    assert result["dry_run_winner_counts"] == {MODEL_VERSION_BASELINE: 1}
    assert result["dry_run_selected_model_snapshot_count"] == 1
    assert result["dry_run_profile_snapshot_count"] == 1
    assert result["dry_run_profile_snapshot_pair_count"] == 1
    assert result["selection_mode"] == "active"
    assert result["selected_models"][0]["metadata"]["selection_mode"] == "active"
    assert persisted_selection_modes == ["active", "active"]
    assert transaction_calls == ["selected_models", "profiles", "commit"]


def test_weather_profile_catalog_preserves_deployable_coefficients():
    profile = SimpleNamespace(
        identifikace="P_A1",
        interval_minutes=15,
        day_of_week=2,
        slot=40,
        base_mean=1.0,
        hdd_slope=0.5,
        hdd_24h_mean=4.0,
        residual_mean=0.0,
        residual_median=0.1,
        residual_p10=-0.2,
        residual_p90=0.4,
        residual_std=0.3,
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
        sample_size=12,
    )

    point = plynomery_prediction._weather_profile_to_prediction_point(profile)

    assert point.expected_mean == 3.0
    assert point.expected_median == 3.1
    assert point.expected_p10 == 2.8
    assert point.expected_p90 == 3.4
    assert point.features == {
        "profile_kind": "weather_adjusted",
        "base_mean": 1.0,
        "hdd_slope": 0.5,
        "hdd_24h_mean": 4.0,
        "residual_mean": 0.0,
        "residual_median": 0.1,
        "residual_p10": -0.2,
        "residual_p90": 0.4,
        "residual_std": 0.3,
    }


def test_deployable_profile_rejects_non_finite_weather_coefficient():
    profile = SimpleNamespace(
        identifikace="P_A1",
        interval_minutes=15,
        day_of_week=2,
        slot=40,
        base_mean=1.0,
        hdd_slope=float("nan"),
        hdd_24h_mean=4.0,
        residual_mean=0.0,
        residual_median=0.1,
        residual_p10=-0.2,
        residual_p90=0.4,
        residual_std=0.3,
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
        sample_size=12,
    )

    with pytest.raises(RuntimeError, match="Unusable deployable"):
        plynomery_prediction._weather_profile_to_prediction_point(profile)


def test_deployable_profile_catalog_groups_static_and_weather_profiles():
    static_profile = SimpleNamespace(
        identifikace="P_A1",
        interval_minutes=15,
        day_of_week=1,
        slot=2,
        mean=1.0,
        median=0.9,
        p10=0.2,
        p90=1.5,
        std=0.25,
        model_version=MODEL_VERSION_BASELINE,
        sample_size=10,
    )
    weather_profile = SimpleNamespace(
        identifikace="P_A1",
        interval_minutes=15,
        day_of_week=1,
        slot=2,
        base_mean=0.8,
        hdd_slope=0.2,
        hdd_24h_mean=3.0,
        residual_mean=0.0,
        residual_median=0.0,
        residual_p10=-0.2,
        residual_p90=0.3,
        residual_std=0.2,
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
        sample_size=10,
    )

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return self

        def all(self):
            return self.rows

    class Session:
        def __init__(self):
            self.calls = 0

        def execute(self, statement):
            self.calls += 1
            return Result([static_profile] if self.calls == 1 else [weather_profile])

    summaries = (
        plynomery_prediction.DeviceModelPerformanceSummary(
            identifikace="P_A1",
            model_version=MODEL_VERSION_BASELINE,
            model_name="Model 1",
            rolling_backtest_fold_count=8,
            rolling_validation_total_count=10,
            rolling_matched_validation_count=10,
            rolling_coverage=1.0,
            rolling_mae=0.1,
            rolling_rmse=0.2,
            rolling_bias=0.0,
            rolling_wape=0.1,
        ),
        plynomery_prediction.DeviceModelPerformanceSummary(
            identifikace="P_A1",
            model_version=MODEL_VERSION_WEATHER_ADJUSTED,
            model_name="Model 2",
            rolling_backtest_fold_count=8,
            rolling_validation_total_count=10,
            rolling_matched_validation_count=10,
            rolling_coverage=1.0,
            rolling_mae=0.1,
            rolling_rmse=0.2,
            rolling_bias=0.0,
            rolling_wape=0.1,
        ),
    )

    catalog = plynomery_prediction._load_deployable_profile_catalog(
        Session(),
        summaries,
    )

    assert set(catalog) == {
        ("P_A1", MODEL_VERSION_BASELINE),
        ("P_A1", MODEL_VERSION_WEATHER_ADJUSTED),
    }
    assert catalog[("P_A1", MODEL_VERSION_BASELINE)][0].features == {
        "profile_kind": "static"
    }


def _selection_summary(
    model_version,
    *,
    coverage=0.9,
    fold_count=8,
    wape=0.2,
    selection_enabled=True,
):
    return plynomery_prediction.DeviceModelPerformanceSummary(
        identifikace="P_A1",
        model_version=model_version,
        model_key=f"model_{model_version}",
        model_name=f"Model {model_version}",
        selection_enabled=selection_enabled,
        rolling_backtest_fold_count=fold_count,
        rolling_validation_total_count=100,
        rolling_matched_validation_count=90,
        rolling_coverage=coverage,
        rolling_mae=1.0 + model_version / 10,
        rolling_rmse=1.5 + model_version / 10,
        rolling_bias=0.1,
        rolling_wape=wape,
    )


def _global_summary(model_version=MODEL_VERSION_BASELINE):
    return ModelPerformanceSummary(
        model_version=model_version,
        model_key=f"model_{model_version}",
        model_name=f"Model {model_version}",
        validation_total_count=100,
        matched_validation_count=90,
        coverage=0.9,
        mae=1.0,
        rmse=1.5,
        bias=0.1,
        profile_count=10,
    )


def test_dry_run_selection_chooses_lowest_wape_deployable_candidate():
    decisions = plynomery_prediction._build_dry_run_selected_model_decisions(
        device_summaries=(
            _selection_summary(MODEL_VERSION_BASELINE, wape=0.2),
            _selection_summary(MODEL_VERSION_WEATHER_ADJUSTED, wape=0.1),
        ),
        selected_summary=_global_summary(),
        forecast_period=build_plynomery_weekly_forecast_period(
            datetime.datetime(2026, 7, 27, 6, 10)
        ),
        selection_run_id=18,
        deployable_profile_catalog={
            ("P_A1", MODEL_VERSION_BASELINE): (object(),),
            ("P_A1", MODEL_VERSION_WEATHER_ADJUSTED): (object(),),
        },
    )

    assert decisions[0].selected_model_version == MODEL_VERSION_WEATHER_ADJUSTED
    assert decisions[0].fallback_reason.value == "none"
    assert decisions[0].metadata["selection_mode"] == "dry_run"


def test_dry_run_selection_uses_next_deployable_candidate_when_metric_winner_has_no_profile():
    decisions = plynomery_prediction._build_dry_run_selected_model_decisions(
        device_summaries=(
            _selection_summary(MODEL_VERSION_BASELINE, wape=0.2),
            _selection_summary(MODEL_VERSION_WEATHER_ADJUSTED, wape=0.1),
        ),
        selected_summary=_global_summary(),
        forecast_period=build_plynomery_weekly_forecast_period(
            datetime.datetime(2026, 7, 27, 6, 10)
        ),
        selection_run_id=18,
        deployable_profile_catalog={
            ("P_A1", MODEL_VERSION_BASELINE): (object(),),
        },
    )

    assert decisions[0].selected_model_version == MODEL_VERSION_BASELINE
    assert decisions[0].fallback_reason.value == "missing_profile"


@pytest.mark.parametrize(
    ("coverage", "fold_count", "expected_reason"),
    [
        (0.8, 8, "below_coverage_threshold"),
        (0.9, 7, "below_fold_count_threshold"),
    ],
)
def test_dry_run_selection_falls_back_to_global_with_precise_reason(
    coverage,
    fold_count,
    expected_reason,
):
    decisions = plynomery_prediction._build_dry_run_selected_model_decisions(
        device_summaries=(
            _selection_summary(
                MODEL_VERSION_BASELINE,
                coverage=coverage,
                fold_count=fold_count,
            ),
        ),
        selected_summary=_global_summary(),
        forecast_period=build_plynomery_weekly_forecast_period(
            datetime.datetime(2026, 7, 27, 6, 10)
        ),
        selection_run_id=18,
        deployable_profile_catalog={
            ("P_A1", MODEL_VERSION_BASELINE): (object(),),
        },
    )

    assert decisions[0].selected_model_version == MODEL_VERSION_BASELINE
    assert decisions[0].fallback_reason.value == expected_reason


def test_dry_run_selection_marks_identifier_without_history_as_unavailable():
    decisions = plynomery_prediction._build_dry_run_selected_model_decisions(
        device_summaries=(_selection_summary(MODEL_VERSION_BASELINE),),
        selected_summary=_global_summary(),
        forecast_period=build_plynomery_weekly_forecast_period(
            datetime.datetime(2026, 7, 27, 6, 10)
        ),
        selection_run_id=18,
        deployable_profile_catalog={},
    )

    assert decisions[0].fallback_reason.value == "insufficient_history"
    assert decisions[0].selected_model_version == MODEL_VERSION_BASELINE
    assert decisions[0].metadata["prediction_available"] is False
    assert decisions[0].metadata["availability_reason"] == "insufficient_history"
    assert decisions[0].metadata["deployable_profile_required"] is False


def test_dry_run_selection_records_no_identifier_metrics_for_undefined_wape():
    summary = replace(
        _selection_summary(MODEL_VERSION_BASELINE),
        rolling_wape=None,
    )

    decisions = plynomery_prediction._build_dry_run_selected_model_decisions(
        device_summaries=(summary,),
        selected_summary=_global_summary(),
        forecast_period=build_plynomery_weekly_forecast_period(
            datetime.datetime(2026, 7, 27, 6, 10)
        ),
        selection_run_id=18,
        deployable_profile_catalog={
            ("P_A1", MODEL_VERSION_BASELINE): (object(),),
        },
    )

    assert decisions[0].fallback_reason.value == "no_identifier_metrics"


def test_dry_run_profile_snapshot_rows_preserve_weather_metadata():
    decision = plynomery_prediction._build_dry_run_selected_model_decisions(
        device_summaries=(
            _selection_summary(MODEL_VERSION_WEATHER_ADJUSTED, wape=0.1),
        ),
        selected_summary=_global_summary(MODEL_VERSION_WEATHER_ADJUSTED),
        forecast_period=build_plynomery_weekly_forecast_period(
            datetime.datetime(2026, 7, 27, 6, 10)
        ),
        selection_run_id=18,
        deployable_profile_catalog={
            ("P_A1", MODEL_VERSION_WEATHER_ADJUSTED): (object(),),
        },
    )[0]
    point = plynomery_prediction.PredictionProfilePoint(
        identifier="P_A1",
        interval_minutes=15,
        day_of_week=2,
        slot=40,
        expected_mean=3.0,
        expected_median=3.1,
        expected_p10=2.8,
        expected_p90=3.4,
        expected_std=0.3,
        sample_size=12,
        model_version=MODEL_VERSION_WEATHER_ADJUSTED,
        features={
            "profile_kind": "weather_adjusted",
            "base_mean": 1.0,
            "hdd_slope": 0.5,
            "hdd_24h_mean": 4.0,
        },
    )
    windows = build_rebuild_windows(
        reference_time=datetime.datetime(2026, 7, 27, 6, 10)
    )

    rows = plynomery_prediction._build_dry_run_profile_snapshot_rows(
        (decision,),
        deployable_profile_catalog={
            ("P_A1", MODEL_VERSION_WEATHER_ADJUSTED): (point,),
        },
        windows=windows,
        archive_run_id="plynomery-selection-18",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["selection_mode"] == "dry_run"
    assert row["archive_source"] == "weekly_rebuild"
    assert row["archive_run_id"] == "plynomery-selection-18"
    assert row["model_version"] == MODEL_VERSION_WEATHER_ADJUSTED
    assert row["training_window_start"] == windows.train_start
    assert '"hdd_slope":0.5' in row["metadata_json"]


def test_dry_run_profile_snapshot_rows_fail_before_insert_when_pair_is_missing():
    decision = plynomery_prediction.PredictionSelectedModelDecision(
        medium_key="plynomery",
        identifier="P_A1",
        forecast_period=build_plynomery_weekly_forecast_period(
            datetime.datetime(2026, 7, 27, 6, 10)
        ),
        selection_run_id=18,
        selected_model_version=MODEL_VERSION_BASELINE,
        selected_model_key="model_1",
        selected_model_name="Model 1",
        global_model_version=MODEL_VERSION_BASELINE,
        global_model_key="model_1",
        global_model_name="Model 1",
    )

    with pytest.raises(RuntimeError, match="missing deployable profiles"):
        plynomery_prediction._build_dry_run_profile_snapshot_rows(
            (decision,),
            deployable_profile_catalog={},
            windows=build_rebuild_windows(
                reference_time=datetime.datetime(2026, 7, 27, 6, 10)
            ),
        )


def test_dry_run_profile_snapshot_rows_intentionally_skip_unavailable_identifier():
    decision = plynomery_prediction.PredictionSelectedModelDecision(
        medium_key="plynomery",
        identifier="P_NEW",
        forecast_period=build_plynomery_weekly_forecast_period(
            datetime.datetime(2026, 7, 27, 6, 10)
        ),
        selection_run_id=18,
        selected_model_version=MODEL_VERSION_BASELINE,
        selected_model_key="model_1",
        selected_model_name="Model 1",
        global_model_version=MODEL_VERSION_BASELINE,
        global_model_key="model_1",
        global_model_name="Model 1",
        fallback_reason="insufficient_history",
        metadata={
            "prediction_available": False,
            "availability_reason": "insufficient_history",
        },
    )

    rows = plynomery_prediction._build_dry_run_profile_snapshot_rows(
        (decision,),
        deployable_profile_catalog={},
        windows=build_rebuild_windows(
            reference_time=datetime.datetime(2026, 7, 27, 6, 10)
        ),
    )

    assert rows == ()


def test_plynomery_selection_candidate_persists_rolling_metadata():
    added = []

    class Session:
        def add(self, row):
            added.append(row)
            if isinstance(row, plynomery_prediction.PlynomeryModelSelectionRun):
                row.id = 18

        def flush(self):
            pass

    summary = replace(
        _global_summary(MODEL_VERSION_WEATHER_ADJUSTED),
        model_key="weather_adjusted_baseline",
        training_window_months=3,
        validation_window_months=1,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=400,
        rolling_matched_validation_count=360,
        rolling_coverage=0.9,
        rolling_mae=0.45,
        rolling_rmse=0.65,
        rolling_bias=0.03,
        rolling_wape=0.14,
    )
    windows = build_rebuild_windows(
        reference_time=datetime.datetime(2026, 7, 27, 6, 10)
    )

    plynomery_prediction._persist_selection_run(
        Session(),
        windows=windows,
        summaries=(summary,),
        selected_summary=summary,
    )

    candidate = next(
        row
        for row in added
        if isinstance(row, plynomery_prediction.PlynomeryModelSelectionCandidate)
    )
    assert candidate.model_key == "weather_adjusted_baseline"
    assert candidate.training_window_months == 3
    assert candidate.validation_window_months == 1
    assert candidate.rolling_backtest_fold_count == 8
    assert candidate.rolling_validation_total_count == 400
    assert candidate.rolling_wape == 0.14
