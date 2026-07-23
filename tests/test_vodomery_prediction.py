import datetime
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery import vodomery_prediction
from moduly.mereni.vodomery.vodomery_prediction import (
    CandidateModelDefinition,
    ModelPerformanceSummary,
    build_rebuild_windows,
    get_candidate_model_specs,
    get_candidate_model_versions,
    select_best_model_summary,
)


def test_build_rebuild_windows_uses_one_month_validation_after_three_month_training():
    reference_time = datetime.datetime(2026, 4, 10, 6, 10, 5)

    windows = build_rebuild_windows(reference_time=reference_time)

    assert windows.deploy_end == reference_time
    assert windows.validation_end == reference_time
    assert windows.validation_start == datetime.datetime(2026, 3, 10, 6, 10, 5)
    assert windows.train_start == datetime.datetime(2025, 12, 10, 6, 10, 5)
    assert windows.train_end == windows.validation_start
    assert windows.deploy_start == windows.train_start


def test_build_vodomery_weekly_forecast_period_uses_calendar_week():
    reference_time = datetime.datetime(2026, 7, 13, 4, 10, 5)

    period = vodomery_prediction.build_vodomery_weekly_forecast_period(
        reference_time=reference_time,
    )

    assert period.start == datetime.datetime(2026, 7, 13)
    assert period.end == datetime.datetime(2026, 7, 20)
    assert period.cadence.value == "weekly"
    assert period.label == "2026-07-13 - 2026-07-20"


def test_get_candidate_model_versions_default_excludes_measured_only_candidate():
    assert get_candidate_model_versions() == (1, 2, 3)
    assert get_candidate_model_versions(include_measured_only=True) == (1, 2, 3, 4, 5)


def test_candidate_model_specs_expose_shared_prediction_metadata():
    specs = get_candidate_model_specs()

    assert [
        (
            spec.model_version,
            spec.model_key,
            spec.model_name,
            spec.training_window_months,
            spec.selection_enabled,
        )
        for spec in specs
    ] == [
        (1, "baseline_mad", "Model 1 - baseline MAD", 3, True),
        (2, "adaptive_strategy", "Model 2 - adaptive strategy", 3, True),
        (3, "recency_weighted_blend", "Model 3 - recency weighted blend", 3, True),
        (4, "seasonal_yearly_blend", "Model 4 - seasonal yearly blend", 12, False),
        (5, "recency_weighted_long_blend", "Model 5 - long recency weighted blend", 12, False),
    ]
    assert {spec.medium_key for spec in specs} == {"vodomery"}
    assert [spec.model_version for spec in get_candidate_model_specs(include_measured_only=False)] == [
        1,
        2,
        3,
    ]


def test_rebuild_candidate_model_dispatches_through_candidate_plugin(monkeypatch):
    windows = build_rebuild_windows(reference_time=datetime.datetime(2026, 4, 10, 6, 10, 5))
    calls = []

    def fake_rebuild(session, *, definition, windows):
        calls.append((session, definition, windows))
        return ModelPerformanceSummary(
            model_version=definition.model_version,
            model_name=definition.model_name,
            validation_total_count=10,
            matched_validation_count=9,
            coverage=0.9,
            mae=0.1,
            rmse=0.2,
            bias=0.0,
            profile_count=42,
        )

    monkeypatch.setattr(vodomery_prediction, "_rebuild_model_1_candidate", fake_rebuild)
    definition = CandidateModelDefinition(
        model_version=1,
        model_key="baseline_mad",
        model_name="Model 1 - baseline MAD",
    )

    summary = vodomery_prediction._rebuild_candidate_model(
        object(),
        definition=definition,
        windows=windows,
    )

    assert summary.profile_count == 42
    assert calls[0][1].to_prediction_spec().model_key == "baseline_mad"
    assert calls[0][2] == windows


def test_rebuild_single_measured_only_candidate_uses_candidate_training_window(monkeypatch):
    reference_time = datetime.datetime(2026, 7, 8, 6, 10, 5)
    captured = {}

    class FakeSession:
        def commit(self):
            captured["committed"] = True

        def close(self):
            captured["closed"] = True

    def fake_rebuild(session, *, definition, windows):
        captured["session"] = session
        captured["definition"] = definition
        captured["windows"] = windows
        return ModelPerformanceSummary(
            model_version=definition.model_version,
            model_name=definition.model_name,
            model_key=definition.model_key,
            training_window_months=definition.training_window_months,
            validation_window_months=definition.validation_window_months,
            selection_enabled=definition.selection_enabled,
            validation_total_count=10,
            matched_validation_count=10,
            coverage=1.0,
            mae=0.1,
            rmse=0.2,
            bias=0.0,
            profile_count=99,
        )

    monkeypatch.setattr(vodomery_prediction, "ensure_vodomery_model_validation_tables", lambda: None)
    monkeypatch.setattr(vodomery_prediction, "drop_legacy_identifikace_fk", lambda table_name: None)
    monkeypatch.setattr(vodomery_prediction, "get_session_pg", lambda: FakeSession())
    monkeypatch.setattr(vodomery_prediction, "_rebuild_candidate_model", fake_rebuild)

    result = vodomery_prediction.rebuild_profiles(
        model_version=4,
        reference_time=reference_time,
    )

    assert result["model_version"] == 4
    assert result["profile_count"] == 99
    assert captured["definition"].selection_enabled is False
    assert captured["windows"].validation_start == datetime.datetime(2026, 6, 8, 6, 10, 5)
    assert captured["windows"].train_start == datetime.datetime(2025, 6, 8, 6, 10, 5)
    assert captured["committed"] is True
    assert captured["closed"] is True


def test_rebuild_profiles_persists_active_selected_model_snapshots(monkeypatch):
    reference_time = datetime.datetime(2026, 7, 13, 4, 10, 5)
    captured = {"ensured_snapshot_table": False}

    class FakeSession:
        def commit(self):
            captured["committed"] = True

        def close(self):
            captured["closed"] = True

    class FakeSelectionRun:
        id = 91

    definitions = (
        CandidateModelDefinition(
            model_version=2,
            model_key="adaptive_strategy",
            model_name="Model 2 - adaptive strategy",
        ),
        CandidateModelDefinition(
            model_version=3,
            model_key="recency_weighted_blend",
            model_name="Model 3 - recency weighted blend",
        ),
    )

    def fake_rebuild(session, *, definition, windows):
        return ModelPerformanceSummary(
            model_version=definition.model_version,
            model_key=definition.model_key,
            model_name=definition.model_name,
            training_window_months=definition.training_window_months,
            validation_window_months=definition.validation_window_months,
            selection_enabled=definition.selection_enabled,
            validation_total_count=100,
            matched_validation_count=100,
            coverage=1.0,
            mae=0.2 if definition.model_version == 2 else 0.1,
            rmse=0.3 if definition.model_version == 2 else 0.2,
            bias=0.0,
            profile_count=1000,
        )

    def fake_rolling(session, *, definition, reference_end):
        return vodomery_prediction.CandidateRollingBacktestResult(
            metrics=vodomery_prediction.PredictionMetricSummary(
                validation_total_count=80,
                matched_validation_count=80,
                coverage=1.0,
                mae=0.1 if definition.model_version == 2 else 0.2,
                rmse=0.2 if definition.model_version == 2 else 0.3,
                bias=0.0,
                wape=0.1 if definition.model_version == 2 else 0.2,
            ),
            device_metrics=(
                vodomery_prediction.DeviceModelPerformanceSummary(
                    identifikace="L1_V1",
                    model_version=definition.model_version,
                    model_key=definition.model_key,
                    model_name=definition.model_name,
                    selection_enabled=True,
                    rolling_backtest_fold_count=8,
                    rolling_validation_total_count=80,
                    rolling_matched_validation_count=80,
                    rolling_coverage=1.0,
                    rolling_mae=0.1 if definition.model_version == 2 else 0.2,
                    rolling_rmse=0.2 if definition.model_version == 2 else 0.3,
                    rolling_bias=0.0,
                    rolling_wape=0.1 if definition.model_version == 2 else 0.2,
                ),
            ),
        )

    def fake_persist_snapshots(session, decisions, *, selection_mode):
        captured["selection_mode"] = selection_mode
        captured["decisions"] = tuple(decisions)
        return len(decisions)

    def fake_build_profile_snapshot_rows(session, decisions, **kwargs):
        captured["profile_snapshot_decisions"] = tuple(decisions)
        captured["profile_snapshot_kwargs"] = kwargs
        return (
            {"identifier": "L1_V1", "model_version": 2},
        )

    def fake_persist_profile_snapshots(session, rows):
        captured["profile_snapshot_rows"] = tuple(rows)
        return 42

    monkeypatch.setattr(vodomery_prediction, "ensure_vodomery_model_validation_tables", lambda: None)
    monkeypatch.setattr(
        vodomery_prediction,
        "ensure_prediction_selected_model_snapshot_table",
        lambda: captured.update({"ensured_snapshot_table": True}),
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "ensure_prediction_profile_snapshot_table",
        lambda: captured.update({"ensured_profile_snapshot_table": True}),
    )
    monkeypatch.setattr(vodomery_prediction, "drop_legacy_identifikace_fk", lambda table_name: None)
    monkeypatch.setattr(vodomery_prediction, "get_session_pg", lambda: FakeSession())
    monkeypatch.setattr(vodomery_prediction, "get_runtime_model_version", lambda *, session, default: 3)
    monkeypatch.setattr(vodomery_prediction, "get_candidate_model_definitions", lambda: definitions)
    monkeypatch.setattr(vodomery_prediction, "_rebuild_candidate_model", fake_rebuild)
    monkeypatch.setattr(
        vodomery_prediction,
        "_run_candidate_rolling_weekly_backtest_with_devices",
        fake_rolling,
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "_persist_selection_run",
        lambda *args, **kwargs: FakeSelectionRun(),
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "persist_selected_model_decisions",
        fake_persist_snapshots,
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "_build_selected_prediction_profile_snapshot_rows",
        fake_build_profile_snapshot_rows,
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "persist_prediction_profile_snapshots",
        fake_persist_profile_snapshots,
    )

    result = vodomery_prediction.rebuild_profiles(reference_time=reference_time)

    assert captured["ensured_snapshot_table"] is True
    assert captured["ensured_profile_snapshot_table"] is True
    assert captured["selection_mode"] == "active"
    assert len(captured["decisions"]) == 1
    assert captured["profile_snapshot_decisions"] == captured["decisions"]
    decision = captured["decisions"][0]
    assert decision.selection_run_id == 91
    assert decision.identifier == "L1_V1"
    assert decision.selected_model_version == 2
    assert decision.global_model_version == 3
    assert decision.metadata["selection_mode"] == "active"
    assert decision.forecast_period.start == datetime.datetime(2026, 7, 13)
    assert decision.forecast_period.end == datetime.datetime(2026, 7, 20)
    assert result["active_model_version"] == 3
    assert result["selected_model_snapshot_mode"] == "active"
    assert result["selected_model_snapshot_count"] == 1
    assert result["prediction_profile_snapshot_source"] == "weekly_rebuild"
    assert result["prediction_profile_snapshot_count"] == 42
    assert result["prediction_profile_snapshot_pair_count"] == 1
    assert result["prediction_profile_snapshot_missing_pair_count"] == 0
    assert captured["profile_snapshot_kwargs"]["require_all_pairs"] is False
    assert captured["profile_snapshot_rows"] == ({"identifier": "L1_V1", "model_version": 2},)
    assert result["selected_model_snapshots"][0]["identifier"] == "L1_V1"
    assert result["selected_model_snapshots"][0]["selected_model_version"] == 2
    assert result["selected_model_snapshots"][0]["global_model_version"] == 3
    assert result["selected_model_snapshots"][0]["uses_fallback"] is False
    assert result["rebuild_duration_seconds"] >= 0
    assert result["forecast_period"]["cadence"] == "weekly"
    assert captured["committed"] is True
    assert captured["closed"] is True


def test_rebuild_model_4_candidate_uses_last_year_for_deploy_profiles(monkeypatch):
    definition = CandidateModelDefinition(
        model_version=4,
        model_key="seasonal_yearly_blend",
        model_name="Model 4 - seasonal yearly blend",
        training_window_months=12,
        selection_enabled=False,
    )
    windows = build_rebuild_windows(
        reference_time=datetime.datetime(2026, 7, 8, 6, 10, 5),
        training_window_months=12,
    )
    profile_builds = []

    def fake_build_profiles(session, *, model_version, data_start, data_end, reference_end):
        profile_builds.append(
            {
                "model_version": model_version,
                "data_start": data_start,
                "data_end": data_end,
                "reference_end": reference_end,
            }
        )

    monkeypatch.setattr(vodomery_prediction, "_build_model_4_profiles", fake_build_profiles)
    monkeypatch.setattr(vodomery_prediction, "_delete_profiles", lambda session, model_version: None)
    monkeypatch.setattr(vodomery_prediction, "_count_profiles", lambda session, model_version: 123)
    monkeypatch.setattr(
        vodomery_prediction,
        "_evaluate_profiles_on_validation",
        lambda session, *, model_version, windows: vodomery_prediction.ValidationAggregate(
            validation_total_count=10,
            matched_validation_count=9,
            coverage=0.9,
            mae=0.1,
            rmse=0.2,
            bias=0.0,
        ),
    )

    summary = vodomery_prediction._rebuild_model_4_candidate(
        object(),
        definition=definition,
        windows=windows,
    )

    assert summary.model_version == 4
    assert summary.selection_enabled is False
    assert profile_builds[0]["model_version"] == 1004
    assert profile_builds[0]["data_start"] == datetime.datetime(2025, 6, 8, 6, 10, 5)
    assert profile_builds[0]["data_end"] == datetime.datetime(2026, 6, 8, 6, 10, 5)
    assert profile_builds[1]["model_version"] == 4
    assert profile_builds[1]["data_start"] == datetime.datetime(2025, 7, 8, 6, 10, 5)
    assert profile_builds[1]["data_end"] == datetime.datetime(2026, 7, 8, 6, 10, 5)


def test_rebuild_model_5_candidate_uses_long_recency_window(monkeypatch):
    definition = CandidateModelDefinition(
        model_version=5,
        model_key="recency_weighted_long_blend",
        model_name="Model 5 - long recency weighted blend",
        training_window_months=12,
        selection_enabled=False,
    )
    windows = build_rebuild_windows(
        reference_time=datetime.datetime(2026, 7, 8, 6, 10, 5),
        training_window_months=12,
    )
    profile_builds = []

    def fake_build_profiles(
        session,
        *,
        model_version,
        data_start,
        data_end,
        reference_end,
        half_life_days,
    ):
        profile_builds.append(
            {
                "model_version": model_version,
                "data_start": data_start,
                "data_end": data_end,
                "reference_end": reference_end,
                "half_life_days": half_life_days,
            }
        )

    monkeypatch.setattr(vodomery_prediction, "_build_model_3_profiles", fake_build_profiles)
    monkeypatch.setattr(vodomery_prediction, "_delete_profiles", lambda session, model_version: None)
    monkeypatch.setattr(vodomery_prediction, "_count_profiles", lambda session, model_version: 123)
    monkeypatch.setattr(
        vodomery_prediction,
        "_evaluate_profiles_on_validation",
        lambda session, *, model_version, windows: vodomery_prediction.ValidationAggregate(
            validation_total_count=10,
            matched_validation_count=9,
            coverage=0.9,
            mae=0.1,
            rmse=0.2,
            bias=0.0,
        ),
    )

    summary = vodomery_prediction._rebuild_model_5_candidate(
        object(),
        definition=definition,
        windows=windows,
    )

    assert summary.model_version == 5
    assert summary.selection_enabled is False
    assert profile_builds[0]["model_version"] == 1005
    assert profile_builds[0]["data_start"] == datetime.datetime(2025, 6, 8, 6, 10, 5)
    assert profile_builds[0]["data_end"] == datetime.datetime(2026, 6, 8, 6, 10, 5)
    assert profile_builds[0]["half_life_days"] == vodomery_prediction.MODEL_V5_RECENCY_HALF_LIFE_DAYS
    assert profile_builds[1]["model_version"] == 5
    assert profile_builds[1]["data_start"] == datetime.datetime(2025, 7, 8, 6, 10, 5)
    assert profile_builds[1]["data_end"] == datetime.datetime(2026, 7, 8, 6, 10, 5)
    assert profile_builds[1]["half_life_days"] == vodomery_prediction.MODEL_V5_RECENCY_HALF_LIFE_DAYS


def test_backtest_dispatch_builds_model_5_with_long_half_life(monkeypatch):
    definition = CandidateModelDefinition(
        model_version=5,
        model_key="recency_weighted_long_blend",
        model_name="Model 5 - long recency weighted blend",
        training_window_months=12,
        selection_enabled=False,
    )
    windows = build_rebuild_windows(
        reference_time=datetime.datetime(2026, 7, 8, 6, 10, 5),
        training_window_months=12,
    )
    captured = {}

    def fake_build_profiles(
        session,
        *,
        model_version,
        data_start,
        data_end,
        reference_end,
        half_life_days,
    ):
        captured.update(
            {
                "model_version": model_version,
                "data_start": data_start,
                "data_end": data_end,
                "reference_end": reference_end,
                "half_life_days": half_life_days,
            }
        )

    monkeypatch.setattr(vodomery_prediction, "_build_model_3_profiles", fake_build_profiles)

    vodomery_prediction._build_candidate_profiles_for_backtest_fold(
        object(),
        definition=definition,
        model_version=2501,
        windows=windows,
    )

    assert captured == {
        "model_version": 2501,
        "data_start": datetime.datetime(2025, 6, 8, 6, 10, 5),
        "data_end": datetime.datetime(2026, 6, 8, 6, 10, 5),
        "reference_end": datetime.datetime(2026, 6, 8, 6, 10, 5),
        "half_life_days": vodomery_prediction.MODEL_V5_RECENCY_HALF_LIFE_DAYS,
    }


def test_run_candidate_rolling_weekly_backtest_aggregates_fold_metrics(monkeypatch):
    definition = CandidateModelDefinition(
        model_version=4,
        model_key="seasonal_yearly_blend",
        model_name="Model 4 - seasonal yearly blend",
        training_window_months=12,
        selection_enabled=False,
    )
    built_versions = []
    deleted_versions = []
    fold_results = [
        vodomery_prediction.ValidationAggregate(
            validation_total_count=10,
            matched_validation_count=8,
            coverage=0.8,
            mae=0.5,
            rmse=0.707106,
            bias=0.25,
            wape=0.2,
            abs_error_sum=4.0,
            squared_error_sum=4.0,
            error_sum=2.0,
            matched_actual_abs_sum=20.0,
        ),
        vodomery_prediction.ValidationAggregate(
            validation_total_count=5,
            matched_validation_count=2,
            coverage=0.4,
            mae=1.0,
            rmse=2.0,
            bias=-0.5,
            wape=0.2,
            abs_error_sum=2.0,
            squared_error_sum=8.0,
            error_sum=-1.0,
            matched_actual_abs_sum=10.0,
        ),
    ]

    def fake_build_profiles(session, *, definition, model_version, windows):
        built_versions.append((model_version, windows.train_start, windows.validation_start))

    def fake_evaluate(session, *, model_version, windows):
        return fold_results.pop(0)

    monkeypatch.setattr(
        vodomery_prediction,
        "_build_candidate_profiles_for_backtest_fold",
        fake_build_profiles,
    )
    monkeypatch.setattr(vodomery_prediction, "_evaluate_profiles_on_validation", fake_evaluate)
    monkeypatch.setattr(
        vodomery_prediction,
        "_delete_profiles",
        lambda session, model_version: deleted_versions.append(model_version),
    )

    metrics = vodomery_prediction._run_candidate_rolling_weekly_backtest(
        object(),
        definition=definition,
        reference_end=datetime.datetime(2026, 7, 8, 6, 10, 5),
        fold_count=2,
        validation_days=7,
    )

    assert [version for version, _, _ in built_versions] == [2401, 2402]
    assert deleted_versions == [2401, 2402]
    assert metrics.validation_total_count == 15
    assert metrics.matched_validation_count == 10
    assert metrics.coverage == 10 / 15
    assert metrics.mae == 0.6
    assert round(metrics.rmse, 6) == round((12.0 / 10) ** 0.5, 6)
    assert metrics.bias == 0.1
    assert metrics.wape == 0.2


def test_run_candidate_rolling_weekly_backtest_with_devices_aggregates_identifier_metrics(monkeypatch):
    definition = CandidateModelDefinition(
        model_version=3,
        model_key="recency_weighted_blend",
        model_name="Model 3 - recency weighted blend",
    )
    built_versions = []
    deleted_versions = []
    fold_results = [
        {
            "A1": vodomery_prediction.ValidationAggregate(
                validation_total_count=10,
                matched_validation_count=8,
                coverage=0.8,
                mae=0.5,
                rmse=0.707106,
                bias=0.25,
                wape=0.2,
                abs_error_sum=4.0,
                squared_error_sum=4.0,
                error_sum=2.0,
                matched_actual_abs_sum=20.0,
            ),
            "B1": vodomery_prediction.ValidationAggregate(
                validation_total_count=5,
                matched_validation_count=5,
                coverage=1.0,
                mae=0.4,
                rmse=0.632456,
                bias=-0.2,
                wape=0.1,
                abs_error_sum=2.0,
                squared_error_sum=2.0,
                error_sum=-1.0,
                matched_actual_abs_sum=20.0,
            ),
        },
        {
            "A1": vodomery_prediction.ValidationAggregate(
                validation_total_count=2,
                matched_validation_count=2,
                coverage=1.0,
                mae=0.5,
                rmse=1.0,
                bias=-0.5,
                wape=0.2,
                abs_error_sum=1.0,
                squared_error_sum=2.0,
                error_sum=-1.0,
                matched_actual_abs_sum=5.0,
            ),
        },
    ]

    def fake_build_profiles(session, *, definition, model_version, windows):
        built_versions.append(model_version)

    def fake_evaluate_by_identifikace(session, *, model_version, windows):
        return fold_results.pop(0)

    monkeypatch.setattr(
        vodomery_prediction,
        "_build_candidate_profiles_for_backtest_fold",
        fake_build_profiles,
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "_evaluate_profiles_on_validation_by_identifikace",
        fake_evaluate_by_identifikace,
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "_delete_profiles",
        lambda session, model_version: deleted_versions.append(model_version),
    )

    result = vodomery_prediction._run_candidate_rolling_weekly_backtest_with_devices(
        object(),
        definition=definition,
        reference_end=datetime.datetime(2026, 7, 8, 6, 10, 5),
        fold_count=2,
        validation_days=7,
    )

    assert built_versions == [2301, 2302]
    assert deleted_versions == [2301, 2302]
    assert result.metrics.validation_total_count == 17
    assert result.metrics.matched_validation_count == 15
    assert round(result.metrics.mae, 6) == round(7.0 / 15, 6)
    assert round(result.metrics.rmse, 6) == round((8.0 / 15) ** 0.5, 6)
    assert result.metrics.bias == 0.0
    assert round(result.metrics.wape, 6) == round(7.0 / 45.0, 6)

    by_ident = {row.identifikace: row for row in result.device_metrics}
    assert set(by_ident) == {"A1", "B1"}
    assert by_ident["A1"].rolling_backtest_fold_count == 2
    assert by_ident["A1"].rolling_validation_total_count == 12
    assert by_ident["A1"].rolling_matched_validation_count == 10
    assert by_ident["A1"].rolling_mae == 0.5
    assert round(by_ident["A1"].rolling_rmse, 6) == round((6.0 / 10) ** 0.5, 6)
    assert by_ident["A1"].rolling_bias == 0.1
    assert by_ident["A1"].rolling_wape == 0.2
    assert by_ident["B1"].rolling_validation_total_count == 5
    assert by_ident["B1"].rolling_mae == 0.4


def test_mark_best_device_models_marks_best_candidate_per_identifier():
    worse = vodomery_prediction.DeviceModelPerformanceSummary(
        identifikace="L1_V1",
        model_version=3,
        model_key="recency_weighted_blend",
        model_name="Model 3 - recency weighted blend",
        selection_enabled=True,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=80,
        rolling_matched_validation_count=80,
        rolling_coverage=1.0,
        rolling_mae=0.3,
        rolling_rmse=0.4,
        rolling_bias=0.0,
        rolling_wape=0.2,
    )
    better_measured_only = vodomery_prediction.DeviceModelPerformanceSummary(
        identifikace="L1_V1",
        model_version=4,
        model_key="seasonal_yearly_blend",
        model_name="Model 4 - seasonal yearly blend",
        selection_enabled=False,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=80,
        rolling_matched_validation_count=80,
        rolling_coverage=1.0,
        rolling_mae=0.2,
        rolling_rmse=0.3,
        rolling_bias=0.0,
        rolling_wape=0.1,
    )

    marked = vodomery_prediction._mark_best_device_models((worse, better_measured_only))

    assert [row.best_for_identifier for row in marked] == [False, True]


def test_build_selected_model_decisions_use_best_eligible_model():
    forecast_period = vodomery_prediction.build_vodomery_weekly_forecast_period(
        reference_time=datetime.datetime(2026, 7, 13, 4, 10, 5),
    )
    global_summary = ModelPerformanceSummary(
        model_version=3,
        model_name="Model 3 - recency weighted blend",
        model_key="recency_weighted_blend",
        validation_total_count=100,
        matched_validation_count=100,
        coverage=1.0,
        mae=0.1,
        rmse=0.2,
        bias=0.0,
        profile_count=1000,
    )
    eligible = vodomery_prediction.DeviceModelPerformanceSummary(
        identifikace="L1_V1",
        model_version=2,
        model_key="adaptive_strategy",
        model_name="Model 2 - adaptive strategy",
        selection_enabled=True,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=80,
        rolling_matched_validation_count=80,
        rolling_coverage=1.0,
        rolling_mae=0.2,
        rolling_rmse=0.3,
        rolling_bias=0.0,
        rolling_wape=0.2,
    )
    global_device = vodomery_prediction.DeviceModelPerformanceSummary(
        identifikace="L1_V1",
        model_version=3,
        model_key="recency_weighted_blend",
        model_name="Model 3 - recency weighted blend",
        selection_enabled=True,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=80,
        rolling_matched_validation_count=80,
        rolling_coverage=1.0,
        rolling_mae=0.3,
        rolling_rmse=0.4,
        rolling_bias=0.0,
        rolling_wape=0.3,
    )
    measured_only_winner = vodomery_prediction.DeviceModelPerformanceSummary(
        identifikace="L1_V1",
        model_version=4,
        model_key="seasonal_yearly_blend",
        model_name="Model 4 - seasonal yearly blend",
        selection_enabled=False,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=80,
        rolling_matched_validation_count=80,
        rolling_coverage=1.0,
        rolling_mae=0.1,
        rolling_rmse=0.2,
        rolling_bias=0.0,
        rolling_wape=0.1,
        best_for_identifier=True,
    )

    decisions = vodomery_prediction._build_selected_model_decisions(
        device_summaries=(eligible, global_device, measured_only_winner),
        selected_summary=global_summary,
        forecast_period=forecast_period,
        selection_run_id=91,
    )

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.selected_model_version == 2
    assert decision.selected_model_key == "adaptive_strategy"
    assert decision.global_model_version == 3
    assert decision.uses_fallback is False
    assert decision.metrics is not None
    assert decision.metrics.wape == 0.2
    assert decision.metadata["best_overall_model_version"] == 4
    assert decision.metadata["best_overall_selection_enabled"] is False
    assert decision.metadata["selection_mode"] == "active"
    assert decision.metadata["selected_from_device_metrics"] is True


def test_build_selected_model_decisions_fallbacks_below_coverage():
    forecast_period = vodomery_prediction.build_vodomery_weekly_forecast_period(
        reference_time=datetime.datetime(2026, 7, 13, 4, 10, 5),
    )
    global_summary = ModelPerformanceSummary(
        model_version=3,
        model_name="Model 3 - recency weighted blend",
        model_key="recency_weighted_blend",
        validation_total_count=100,
        matched_validation_count=100,
        coverage=1.0,
        mae=0.1,
        rmse=0.2,
        bias=0.0,
        profile_count=1000,
    )
    low_coverage = vodomery_prediction.DeviceModelPerformanceSummary(
        identifikace="L1_V1",
        model_version=2,
        model_key="adaptive_strategy",
        model_name="Model 2 - adaptive strategy",
        selection_enabled=True,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=80,
        rolling_matched_validation_count=40,
        rolling_coverage=0.5,
        rolling_mae=0.1,
        rolling_rmse=0.2,
        rolling_bias=0.0,
        rolling_wape=0.1,
    )
    global_device = vodomery_prediction.DeviceModelPerformanceSummary(
        identifikace="L1_V1",
        model_version=3,
        model_key="recency_weighted_blend",
        model_name="Model 3 - recency weighted blend",
        selection_enabled=True,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=80,
        rolling_matched_validation_count=48,
        rolling_coverage=0.6,
        rolling_mae=0.2,
        rolling_rmse=0.3,
        rolling_bias=0.0,
        rolling_wape=0.2,
    )

    decisions = vodomery_prediction._build_selected_model_decisions(
        device_summaries=(low_coverage, global_device),
        selected_summary=global_summary,
        forecast_period=forecast_period,
        selection_run_id=91,
    )

    decision = decisions[0]
    assert decision.selected_model_version == 3
    assert decision.uses_fallback is True
    assert decision.fallback_reason is vodomery_prediction.PredictionSelectionFallbackReason.BELOW_COVERAGE_THRESHOLD
    assert decision.metrics is not None
    assert decision.metrics.wape == 0.2


def test_persist_selected_prediction_profile_snapshots_writes_selected_models(monkeypatch):
    forecast_period = vodomery_prediction.build_vodomery_weekly_forecast_period(
        reference_time=datetime.datetime(2026, 7, 13, 4, 10, 5),
    )
    decisions = (
        vodomery_prediction.PredictionSelectedModelDecision(
            medium_key="vodomery",
            identifier="L1_V1",
            forecast_period=forecast_period,
            selection_run_id=91,
            selected_model_version=2,
            selected_model_key="adaptive_strategy",
            selected_model_name="Model 2 - adaptive strategy",
            global_model_version=3,
            global_model_key="recency_weighted_blend",
            global_model_name="Model 3 - recency weighted blend",
        ),
        vodomery_prediction.PredictionSelectedModelDecision(
            medium_key="vodomery",
            identifier="B_V4",
            forecast_period=forecast_period,
            selection_run_id=91,
            selected_model_version=3,
            selected_model_key="recency_weighted_blend",
            selected_model_name="Model 3 - recency weighted blend",
            global_model_version=3,
            global_model_key="recency_weighted_blend",
            global_model_name="Model 3 - recency weighted blend",
            fallback_reason=(
                vodomery_prediction.PredictionSelectionFallbackReason.NO_IDENTIFIER_METRICS
            ),
        ),
    )
    profiles = [
        SimpleNamespace(
            identifikace="L1_V1",
            model_version=2,
            interval_minutes=60,
            day_of_week=0,
            slot=8,
            mean=0.25,
            median=0.2,
            p10=0.05,
            p90=0.5,
            std=0.1,
            sample_size=12,
            created_at=datetime.datetime(2026, 7, 13, 4, 12),
        ),
        SimpleNamespace(
            identifikace="L1_V1",
            model_version=3,
            interval_minutes=60,
            day_of_week=0,
            slot=8,
            mean=9.99,
            median=9.99,
            p10=9.99,
            p90=9.99,
            std=9.99,
            sample_size=1,
            created_at=datetime.datetime(2026, 7, 13, 4, 12),
        ),
        SimpleNamespace(
            identifikace="B_V4",
            model_version=3,
            interval_minutes=60,
            day_of_week=0,
            slot=8,
            mean=0.4,
            median=0.35,
            p10=0.1,
            p90=0.8,
            std=0.12,
            sample_size=10,
            created_at=datetime.datetime(2026, 7, 13, 4, 13),
        ),
    ]

    class FakeScalars:
        def all(self):
            return profiles

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    class FakeSession:
        def execute(self, statement):
            return FakeResult()

    captured = {}

    def fake_persist(session, rows):
        captured["session"] = session
        captured["rows"] = rows
        return len(rows)

    monkeypatch.setattr(
        vodomery_prediction,
        "persist_prediction_profile_snapshots",
        fake_persist,
    )

    count = vodomery_prediction._persist_selected_prediction_profile_snapshots(
        FakeSession(),
        decisions,
    )

    assert count == 2
    rows = captured["rows"]
    assert {row["identifier"] for row in rows} == {"L1_V1", "B_V4"}
    assert {row["model_version"] for row in rows} == {2, 3}
    assert all(row["archive_source"] == "weekly_rebuild" for row in rows)
    assert all(row["archive_version"] == 1 for row in rows)
    assert rows[0]["forecast_period_start"] == forecast_period.start
    l1_row = next(row for row in rows if row["identifier"] == "L1_V1")
    assert l1_row["model_version"] == 2
    assert l1_row["expected_mean"] == 0.25
    fallback_row = next(row for row in rows if row["identifier"] == "B_V4")
    assert fallback_row["uses_fallback"] is True
    assert fallback_row["fallback_reason"] == "no_identifier_metrics"


def test_persist_selected_prediction_profile_snapshots_fails_missing_profiles():
    forecast_period = vodomery_prediction.build_vodomery_weekly_forecast_period(
        reference_time=datetime.datetime(2026, 7, 13, 4, 10, 5),
    )
    decision = vodomery_prediction.PredictionSelectedModelDecision(
        medium_key="vodomery",
        identifier="L1_V1",
        forecast_period=forecast_period,
        selection_run_id=91,
        selected_model_version=2,
        selected_model_key="adaptive_strategy",
        selected_model_name="Model 2 - adaptive strategy",
        global_model_version=3,
        global_model_key="recency_weighted_blend",
        global_model_name="Model 3 - recency weighted blend",
    )

    class EmptyScalars:
        def all(self):
            return []

    class EmptyResult:
        def scalars(self):
            return EmptyScalars()

    class FakeSession:
        def execute(self, statement):
            return EmptyResult()

    try:
        vodomery_prediction._persist_selected_prediction_profile_snapshots(
            FakeSession(),
            (decision,),
        )
    except RuntimeError as exc:
        assert "missing source profiles" in str(exc)
    else:
        raise AssertionError("missing selected profiles should fail the rebuild")


def test_build_selected_prediction_profile_snapshot_rows_can_skip_missing_profiles():
    forecast_period = vodomery_prediction.build_vodomery_weekly_forecast_period(
        reference_time=datetime.datetime(2026, 7, 13, 4, 10, 5),
    )
    decisions = (
        vodomery_prediction.PredictionSelectedModelDecision(
            medium_key="vodomery",
            identifier="L1_V1",
            forecast_period=forecast_period,
            selection_run_id=91,
            selected_model_version=2,
            selected_model_key="adaptive_strategy",
            selected_model_name="Model 2 - adaptive strategy",
            global_model_version=3,
            global_model_key="recency_weighted_blend",
            global_model_name="Model 3 - recency weighted blend",
        ),
        vodomery_prediction.PredictionSelectedModelDecision(
            medium_key="vodomery",
            identifier="B_V4",
            forecast_period=forecast_period,
            selection_run_id=91,
            selected_model_version=3,
            selected_model_key="recency_weighted_blend",
            selected_model_name="Model 3 - recency weighted blend",
            global_model_version=3,
            global_model_key="recency_weighted_blend",
            global_model_name="Model 3 - recency weighted blend",
        ),
    )
    profiles = [
        SimpleNamespace(
            identifikace="L1_V1",
            model_version=2,
            interval_minutes=60,
            day_of_week=0,
            slot=8,
            mean=0.25,
            median=0.2,
            p10=0.05,
            p90=0.5,
            std=0.1,
            sample_size=12,
            created_at=datetime.datetime(2026, 7, 13, 4, 12),
        )
    ]

    class FakeScalars:
        def all(self):
            return profiles

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    class FakeSession:
        def execute(self, statement):
            return FakeResult()

    rows = vodomery_prediction._build_selected_prediction_profile_snapshot_rows(
        FakeSession(),
        decisions,
        archive_source="historical_backfill",
        require_all_pairs=False,
    )

    assert len(rows) == 1
    assert rows[0]["identifier"] == "L1_V1"
    assert rows[0]["archive_source"] == "historical_backfill"


def test_summary_with_rolling_backtest_serializes_new_metrics():
    summary = ModelPerformanceSummary(
        model_version=4,
        model_name="Model 4 - seasonal yearly blend",
        model_key="seasonal_yearly_blend",
        training_window_months=12,
        validation_window_months=1,
        selection_enabled=False,
        validation_total_count=100,
        matched_validation_count=90,
        coverage=0.9,
        mae=0.3,
        rmse=0.4,
        bias=-0.1,
        profile_count=700,
    )

    updated = vodomery_prediction._summary_with_rolling_backtest(
        summary,
        fold_count=8,
        metrics=vodomery_prediction.PredictionMetricSummary(
            validation_total_count=800,
            matched_validation_count=760,
            coverage=0.95,
            mae=0.22,
            rmse=0.33,
            bias=0.04,
            wape=0.18,
        ),
    )

    assert updated.to_dict(selected=False) == {
        "model_version": 4,
        "model_key": "seasonal_yearly_blend",
        "model_name": "Model 4 - seasonal yearly blend",
        "training_window_months": 12,
        "validation_window_months": 1,
        "selection_enabled": False,
        "rolling_backtest_fold_count": 8,
        "rolling_validation_total_count": 800,
        "rolling_matched_validation_count": 760,
        "rolling_coverage": 0.95,
        "rolling_mae": 0.22,
        "rolling_rmse": 0.33,
        "rolling_bias": 0.04,
        "rolling_wape": 0.18,
        "validation_total_count": 100,
        "matched_validation_count": 90,
        "coverage": 0.9,
        "mae": 0.3,
        "rmse": 0.4,
        "bias": -0.1,
        "profile_count": 700,
        "selected_device_count": None,
        "validation_candidate_count": None,
        "selected": False,
    }


def test_persist_selection_run_stores_eligibility_and_rolling_metrics():
    captured = {}

    class FakeSession:
        def add(self, value):
            captured["selection_run"] = value

        def flush(self):
            captured["selection_run"].id = 77

        def execute(self, statement, rows):
            captured["rows"] = rows

    windows = build_rebuild_windows(reference_time=datetime.datetime(2026, 7, 8, 6, 10, 5))
    summary = ModelPerformanceSummary(
        model_version=4,
        model_name="Model 4 - seasonal yearly blend",
        model_key="seasonal_yearly_blend",
        training_window_months=12,
        validation_window_months=1,
        selection_enabled=False,
        validation_total_count=100,
        matched_validation_count=90,
        coverage=0.9,
        mae=0.3333333,
        rmse=0.4444444,
        bias=-0.0555555,
        profile_count=700,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=800,
        rolling_matched_validation_count=760,
        rolling_coverage=0.95,
        rolling_mae=0.2222222,
        rolling_rmse=0.3333333,
        rolling_bias=0.0444444,
        rolling_wape=0.1888888,
    )

    vodomery_prediction._persist_selection_run(
        FakeSession(),
        windows=windows,
        summaries=[summary],
        selected_summary=summary,
    )

    row = captured["rows"][0]
    assert row["selection_run_id"] == 77
    assert row["model_key"] == "seasonal_yearly_blend"
    assert row["training_window_months"] == 12
    assert row["validation_window_months"] == 1
    assert row["selection_enabled"] is False
    assert row["rolling_backtest_fold_count"] == 8
    assert row["rolling_validation_total_count"] == 800
    assert row["rolling_matched_validation_count"] == 760
    assert row["rolling_coverage"] == 0.95
    assert row["rolling_mae"] == 0.222222
    assert row["rolling_rmse"] == 0.333333
    assert row["rolling_bias"] == 0.044444
    assert row["rolling_wape"] == 0.188889


def test_persist_selection_run_stores_device_candidate_metrics():
    captured = {"execute_calls": []}

    class FakeSession:
        def add(self, value):
            captured["selection_run"] = value

        def flush(self):
            captured["selection_run"].id = 77

        def execute(self, statement, rows):
            captured["execute_calls"].append(rows)

    windows = build_rebuild_windows(reference_time=datetime.datetime(2026, 7, 8, 6, 10, 5))
    summary = ModelPerformanceSummary(
        model_version=3,
        model_name="Model 3 - recency weighted blend",
        model_key="recency_weighted_blend",
        training_window_months=3,
        validation_window_months=1,
        selection_enabled=True,
        validation_total_count=100,
        matched_validation_count=90,
        coverage=0.9,
        mae=0.3,
        rmse=0.4,
        bias=-0.05,
        profile_count=700,
    )
    device_summary = vodomery_prediction.DeviceModelPerformanceSummary(
        identifikace="L1_V1",
        model_version=3,
        model_key="recency_weighted_blend",
        model_name="Model 3 - recency weighted blend",
        selection_enabled=True,
        rolling_backtest_fold_count=8,
        rolling_validation_total_count=80,
        rolling_matched_validation_count=76,
        rolling_coverage=0.95,
        rolling_mae=0.2222222,
        rolling_rmse=0.3333333,
        rolling_bias=0.0444444,
        rolling_wape=0.1888888,
        best_for_identifier=True,
    )

    vodomery_prediction._persist_selection_run(
        FakeSession(),
        windows=windows,
        summaries=[summary],
        selected_summary=summary,
        device_summaries=[device_summary],
    )

    assert len(captured["execute_calls"]) == 2
    row = captured["execute_calls"][1][0]
    assert row["selection_run_id"] == 77
    assert row["identifikace"] == "L1_V1"
    assert row["model_key"] == "recency_weighted_blend"
    assert row["selection_enabled"] is True
    assert row["rolling_backtest_fold_count"] == 8
    assert row["rolling_validation_total_count"] == 80
    assert row["rolling_matched_validation_count"] == 76
    assert row["rolling_coverage"] == 0.95
    assert row["rolling_mae"] == 0.222222
    assert row["rolling_rmse"] == 0.333333
    assert row["rolling_bias"] == 0.044444
    assert row["rolling_wape"] == 0.188889
    assert row["best_for_identifier"] is True


def test_select_best_model_summary_prefers_coverage_before_lower_error():
    low_coverage = ModelPerformanceSummary(
        model_version=1,
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
        model_version=2,
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


def test_select_best_model_summary_ignores_measured_only_candidate():
    selectable = ModelPerformanceSummary(
        model_version=2,
        model_name="Model 2",
        validation_total_count=100,
        matched_validation_count=90,
        coverage=0.9,
        mae=1.0,
        rmse=1.1,
        bias=0.0,
        profile_count=500,
        selection_enabled=True,
    )
    measured_only = ModelPerformanceSummary(
        model_version=4,
        model_name="Model 4",
        validation_total_count=100,
        matched_validation_count=100,
        coverage=1.0,
        mae=0.01,
        rmse=0.02,
        bias=0.0,
        profile_count=700,
        selection_enabled=False,
    )

    selected = select_best_model_summary((selectable, measured_only))

    assert selected == selectable


def test_build_model_4_profiles_uses_seasonal_window_and_fallback_blend():
    class FakeSession:
        def __init__(self):
            self.calls = []

        def execute(self, statement, params=None):
            self.calls.append((str(statement), params or {}))

    session = FakeSession()
    vodomery_prediction._build_model_4_profiles(
        session,
        model_version=4,
        data_start=datetime.datetime(2025, 6, 8, 6, 10, 5),
        data_end=datetime.datetime(2026, 6, 8, 6, 10, 5),
        reference_end=datetime.datetime(2026, 6, 8, 6, 10, 5),
    )

    delete_sql, delete_params = session.calls[0]
    insert_sql, insert_params = session.calls[1]

    assert "DELETE FROM monitoring.vodomery_anomaly_profiles" in delete_sql
    assert delete_params["model_version"] == 4
    assert "seasonal_dow_slot_stats" in insert_sql
    assert "season_distance_days <= :season_window_days" in insert_sql
    assert "seasonal_trust" in insert_sql
    assert "workday_trust" in insert_sql
    assert insert_params["season_window_days"] == vodomery_prediction.MODEL_V4_SEASON_WINDOW_DAYS
    assert insert_params["model_version"] == 4
