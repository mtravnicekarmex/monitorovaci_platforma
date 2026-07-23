from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from services.api.routes import prediction as prediction_route
from services.api.schemas.prediction import PredictionPerformanceResponse
from services.api.services import prediction_performance


class _FakeMappingResult:
    def __init__(self, *, first_row=None, all_rows=None):
        self._first_row = first_row
        self._all_rows = list(all_rows or [])

    def first(self):
        return self._first_row

    def all(self):
        return self._all_rows


class _FakeResult:
    def __init__(self, *, scalar_value=None, first_row=None, all_rows=None):
        self._scalar_value = scalar_value
        self._mapping_result = _FakeMappingResult(
            first_row=first_row,
            all_rows=all_rows,
        )

    def scalar(self):
        return self._scalar_value

    def mappings(self):
        return self._mapping_result


class _FakePredictionSession:
    def __init__(self):
        self.closed = False
        self.tables = {
            "monitoring.vodomery_model_selection_runs",
            "monitoring.vodomery_model_selection_candidates",
            "monitoring.plynomery_model_selection_runs",
            "monitoring.plynomery_model_selection_candidates",
            "monitoring.prediction_selected_model_snapshots",
            "monitoring.prediction_profile_snapshots",
            "monitoring.prediction_backfill_candidate_metrics",
        }

    def execute(self, statement, params=None):
        params = params or {}
        statement_text = str(statement)

        if "to_regclass" in statement_text:
            return _FakeResult(scalar_value=params["table_name"] in self.tables)

        if "prediction_performance:latest_run:vodomery" in statement_text:
            return _FakeResult(
                first_row={
                    "selection_run_id": 33,
                    "selected_model_version": 3,
                    "selected_model_name": "Model 3 - recency weighted blend",
                    "train_start": datetime(2026, 4, 1),
                    "train_end": datetime(2026, 7, 1),
                    "validation_start": datetime(2026, 6, 1),
                    "validation_end": datetime(2026, 7, 1),
                    "deploy_start": datetime(2026, 4, 1),
                    "deploy_end": datetime(2026, 7, 1),
                    "created_at": datetime(2026, 7, 10, 12, 0),
                }
            )

        if "prediction_performance:latest_run:plynomery" in statement_text:
            return _FakeResult(
                first_row={
                    "selection_run_id": 14,
                    "selected_model_version": 2,
                    "selected_model_name": "Model 2 - weather adjusted baseline",
                    "train_start": datetime(2026, 4, 1),
                    "train_end": datetime(2026, 7, 1),
                    "validation_start": datetime(2026, 6, 1),
                    "validation_end": datetime(2026, 7, 1),
                    "deploy_start": datetime(2026, 4, 1),
                    "deploy_end": datetime(2026, 7, 1),
                    "created_at": datetime(2026, 7, 10, 12, 5),
                }
            )

        if "prediction_performance:candidates:vodomery" in statement_text:
            return _FakeResult(
                all_rows=[
                    {
                        "selection_run_id": 33,
                        "model_version": 3,
                        "model_key": "recency_weighted_blend",
                        "model_name": "Model 3 - recency weighted blend",
                        "training_window_months": 3,
                        "validation_window_months": 1,
                        "selection_enabled": True,
                        "selected": True,
                        "validation_total_count": 100,
                        "matched_validation_count": 95,
                        "coverage": 0.95,
                        "mae": 1.2,
                        "rmse": 2.3,
                        "bias": -0.1,
                        "wape": None,
                        "rolling_backtest_fold_count": 8,
                        "rolling_validation_total_count": 800,
                        "rolling_matched_validation_count": 760,
                        "rolling_coverage": 0.95,
                        "rolling_mae": 1.1,
                        "rolling_rmse": 2.2,
                        "rolling_bias": -0.2,
                        "rolling_wape": 3.9993,
                        "profile_count": 37800,
                        "created_at": datetime(2026, 7, 10, 12, 0),
                    }
                ]
            )

        if "prediction_performance:candidates:plynomery" in statement_text:
            return _FakeResult(
                all_rows=[
                    {
                        "selection_run_id": 14,
                        "model_version": 2,
                        "model_key": None,
                        "model_name": "Model 2 - weather adjusted baseline",
                        "training_window_months": None,
                        "validation_window_months": None,
                        "selection_enabled": True,
                        "selected": True,
                        "validation_total_count": 50,
                        "matched_validation_count": 45,
                        "coverage": 0.9,
                        "mae": 0.5,
                        "rmse": 0.7,
                        "bias": 0.05,
                        "wape": None,
                        "rolling_backtest_fold_count": 0,
                        "rolling_validation_total_count": None,
                        "rolling_matched_validation_count": None,
                        "rolling_coverage": None,
                        "rolling_mae": None,
                        "rolling_rmse": None,
                        "rolling_bias": None,
                        "rolling_wape": None,
                        "profile_count": 3360,
                        "created_at": datetime(2026, 7, 10, 12, 5),
                    }
                ]
            )

        if "prediction_performance:snapshot_summary" in statement_text:
            if params["medium_key"] != "vodomery":
                return _FakeResult(first_row=None)
            return _FakeResult(
                first_row={
                    "medium_key": "vodomery",
                    "selection_mode": "active",
                    "forecast_period_start": datetime(2026, 7, 13),
                    "forecast_period_end": datetime(2026, 7, 20),
                    "forecast_period_label": "2026-W29",
                    "forecast_cadence": "weekly",
                    "selection_run_id": 33,
                    "snapshot_count": 58,
                    "fallback_count": 3,
                    "selected_differs_from_global_count": 43,
                    "latest_created_at": datetime(2026, 7, 10, 12, 0),
                }
            )

        if "prediction_performance:model_distribution" in statement_text:
            return _FakeResult(
                all_rows=[
                    {
                        "selected_model_version": 2,
                        "selected_model_name": "Model 2 - adaptive strategy",
                        "row_count": 43,
                    },
                    {
                        "selected_model_version": 3,
                        "selected_model_name": "Model 3 - recency weighted blend",
                        "row_count": 15,
                    },
                ]
            )

        if "prediction_performance:fallback_distribution" in statement_text:
            return _FakeResult(
                all_rows=[
                    {"fallback_reason": "none", "row_count": 55},
                    {"fallback_reason": "no_identifier_metrics", "row_count": 3},
                ]
            )

        if "prediction_performance:snapshot_identity" in statement_text:
            if params["medium_key"] != "vodomery":
                return _FakeResult(first_row=None)
            return _FakeResult(
                first_row={
                    "medium_key": "vodomery",
                    "selection_mode": "active",
                    "forecast_period_start": datetime(2026, 7, 13),
                    "forecast_period_end": datetime(2026, 7, 20),
                    "forecast_cadence": "weekly",
                }
            )

        if "prediction_performance:worst_identifiers" in statement_text:
            return _FakeResult(
                all_rows=[
                    {
                        "medium_key": "vodomery",
                        "identifier": "V-001",
                        "selection_mode": "active",
                        "selection_run_id": 33,
                        "forecast_period_start": datetime(2026, 7, 13),
                        "forecast_period_end": datetime(2026, 7, 20),
                        "forecast_period_label": "2026-W29",
                        "selected_model_version": 3,
                        "selected_model_name": "Model 3 - recency weighted blend",
                        "global_model_version": 3,
                        "global_model_name": "Model 3 - recency weighted blend",
                        "uses_fallback": True,
                        "fallback_reason": "no_identifier_metrics",
                        "validation_total_count": 0,
                        "matched_validation_count": 0,
                        "coverage": 0.0,
                        "mae": None,
                        "rmse": None,
                        "bias": None,
                        "wape": None,
                        "created_at": datetime(2026, 7, 10, 12, 0),
                    }
                ]
            )

        if "prediction_performance:historical_candidates" in statement_text:
            if params["medium_key"] != "vodomery":
                return _FakeResult(all_rows=[])
            return _FakeResult(
                all_rows=[
                    {
                        "medium_key": "vodomery",
                        "archive_version": 1,
                        "model_version": 2,
                        "model_key": "adaptive_strategy",
                        "model_name": "Model 2 - adaptive strategy",
                        "selection_enabled": True,
                        "metric_row_count": 3042,
                        "forecast_period_count": 128,
                        "identifier_week_count": 3042,
                        "selected_metric_count": 1800,
                        "eligible_metric_count": 3042,
                        "avg_coverage": 0.96,
                        "avg_mae": 0.4,
                        "avg_rmse": 0.8,
                        "avg_bias": -0.02,
                        "avg_wape": 0.18,
                        "worst_wape": 0.72,
                        "first_forecast_period_start": datetime(2024, 2, 5),
                        "last_forecast_period_end": datetime(2026, 7, 20),
                        "latest_created_at": datetime(2026, 7, 23, 10, 0),
                    }
                ]
            )

        if "prediction_performance:historical_snapshot_coverage" in statement_text:
            if params["medium_key"] != "vodomery":
                return _FakeResult(all_rows=[])
            return _FakeResult(
                all_rows=[
                    {
                        "medium_key": "vodomery",
                        "archive_version": 1,
                        "forecast_period_start": datetime(2026, 7, 13),
                        "forecast_period_end": datetime(2026, 7, 20),
                        "forecast_period_label": "2026-07-13 - 2026-07-20",
                        "forecast_cadence": "weekly",
                        "selected_metric_pair_count": 58,
                        "profile_pair_count": 58,
                        "missing_profile_pair_count": 0,
                        "profile_row_count": 37800,
                        "latest_created_at": datetime(2026, 7, 23, 10, 0),
                    },
                    {
                        "medium_key": "vodomery",
                        "archive_version": 1,
                        "forecast_period_start": datetime(2026, 3, 2),
                        "forecast_period_end": datetime(2026, 3, 9),
                        "forecast_period_label": "2026-03-02 - 2026-03-09",
                        "forecast_cadence": "weekly",
                        "selected_metric_pair_count": 58,
                        "profile_pair_count": 57,
                        "missing_profile_pair_count": 1,
                        "profile_row_count": 37128,
                        "latest_created_at": datetime(2026, 7, 23, 10, 0),
                    },
                ]
            )

        raise AssertionError(f"Unexpected SQL: {statement_text}")

    def close(self):
        self.closed = True


def test_collect_prediction_performance_report_merges_media_runs_snapshots_and_catalog():
    session = _FakePredictionSession()

    response = prediction_performance.collect_prediction_performance_report(
        session_factory=lambda: session,
        reference_time=datetime(2026, 7, 10, 14, 30),
    )

    assert response.status == "ok"
    assert response.checked_at == datetime(2026, 7, 10, 14, 30)
    assert session.closed is True

    by_medium = {item.medium_key: item for item in response.media}
    assert set(by_medium) == {"vodomery", "plynomery", "elektromery"}

    vodomery = by_medium["vodomery"]
    assert vodomery.status == "ok"
    assert vodomery.latest_selection_run.selection_run_id == 33
    assert vodomery.snapshot_summary.snapshot_count == 58
    assert vodomery.snapshot_summary.fallback_count == 3
    assert vodomery.snapshot_summary.selected_differs_from_global_count == 43
    assert vodomery.snapshot_summary.model_distribution[0].count == 43
    assert vodomery.candidate_performance[0].rolling_wape == 3.9993
    assert vodomery.worst_identifier_selections[0].identifier == "V-001"
    assert vodomery.historical_candidate_performance[0].model_key == "adaptive_strategy"
    assert vodomery.historical_candidate_performance[0].identifier_week_count == 3042
    assert vodomery.historical_snapshot_coverage[0].profile_pair_count == 58
    assert vodomery.historical_snapshot_coverage[1].missing_profile_pair_count == 1

    plynomery = by_medium["plynomery"]
    assert plynomery.status == "ok"
    assert plynomery.latest_selection_run.selection_run_id == 14
    assert plynomery.candidate_performance[0].model_key == "weather_adjusted_baseline"
    assert plynomery.candidate_performance[0].training_window_months == 3
    assert plynomery.historical_candidate_performance == []

    elektromery = by_medium["elektromery"]
    assert elektromery.status == "not_run"
    assert elektromery.latest_selection_run is None
    assert len(elektromery.candidate_catalog) == 3
    assert elektromery.candidate_catalog[0].forecast_cadence == "monthly"


def test_prediction_performance_route_delegates_to_service(monkeypatch):
    expected = PredictionPerformanceResponse(
        status="ok",
        checked_at=datetime(2026, 7, 10, 14, 30),
        media=[],
    )
    monkeypatch.setattr(
        prediction_route,
        "collect_prediction_performance_report",
        lambda: expected,
    )

    response = prediction_route.get_prediction_performance(
        current_user=SimpleNamespace(is_admin=True)
    )

    assert response is expected
