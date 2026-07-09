import datetime

from moduly.mereni.vodomery.reporting import model_rebuild_report


def test_model_rebuild_report_body_shows_eligibility_and_rolling_metrics():
    body = model_rebuild_report._build_email_body(
        {
            "selection_run_id": 7,
            "active_model_version": 2,
            "active_model_name": "Model 2 - adaptive strategy",
            "previous_active_model_version": 1,
            "previous_active_model_name": "Model 1 - baseline MAD",
            "rebuild_duration_seconds": 125.4,
            "windows": {
                "train_start": datetime.datetime(2026, 3, 1, 0, 0),
                "train_end": datetime.datetime(2026, 6, 1, 0, 0),
                "validation_start": datetime.datetime(2026, 6, 1, 0, 0),
                "validation_end": datetime.datetime(2026, 7, 1, 0, 0),
                "deploy_start": datetime.datetime(2026, 3, 1, 0, 0),
                "deploy_end": datetime.datetime(2026, 7, 1, 0, 0),
            },
            "forecast_period": {
                "start": datetime.datetime(2026, 7, 13, 4, 10, 5),
                "end": datetime.datetime(2026, 7, 20, 4, 10, 5),
                "cadence": "weekly",
                "label": "2026-07-13 04:10 - 2026-07-20 04:10",
            },
            "candidates": [
                {
                    "model_version": 2,
                    "model_name": "Model 2 - adaptive strategy",
                    "selection_enabled": True,
                    "validation_total_count": 100,
                    "matched_validation_count": 95,
                    "coverage": 0.95,
                    "mae": 0.2,
                    "rmse": 0.3,
                    "bias": 0.01,
                    "rolling_backtest_fold_count": 8,
                    "rolling_coverage": 0.94,
                    "rolling_wape": 0.12,
                    "rolling_mae": 0.21,
                    "rolling_rmse": 0.32,
                    "rolling_bias": 0.02,
                    "profile_count": 500,
                    "selected_device_count": 40,
                    "selected": True,
                },
                {
                    "model_version": 4,
                    "model_name": "Model 4 - seasonal yearly blend",
                    "selection_enabled": False,
                    "validation_total_count": 100,
                    "matched_validation_count": 98,
                    "coverage": 0.98,
                    "mae": 0.18,
                    "rmse": 0.28,
                    "bias": -0.02,
                    "rolling_backtest_fold_count": 8,
                    "rolling_coverage": 0.97,
                    "rolling_wape": 0.1,
                    "rolling_mae": 0.19,
                    "rolling_rmse": 0.29,
                    "rolling_bias": -0.01,
                    "profile_count": 700,
                    "selected_device_count": None,
                    "selected": False,
                },
            ],
            "device_candidates": [
                {
                    "identifikace": "L1_V1",
                    "model_version": 2,
                    "model_name": "Model 2 - adaptive strategy",
                    "selection_enabled": True,
                    "best_for_identifier": True,
                    "rolling_backtest_fold_count": 8,
                    "rolling_validation_total_count": 80,
                    "rolling_matched_validation_count": 76,
                    "rolling_coverage": 0.95,
                    "rolling_wape": 0.22,
                    "rolling_mae": 0.32,
                    "rolling_rmse": 0.5,
                    "rolling_bias": 0.03,
                },
                {
                    "identifikace": "L2_V1",
                    "model_version": 4,
                    "model_name": "Model 4 - seasonal yearly blend",
                    "selection_enabled": False,
                    "best_for_identifier": True,
                    "rolling_backtest_fold_count": 8,
                    "rolling_validation_total_count": 80,
                    "rolling_matched_validation_count": 78,
                    "rolling_coverage": 0.975,
                    "rolling_wape": 0.08,
                    "rolling_mae": 0.12,
                    "rolling_rmse": 0.2,
                    "rolling_bias": -0.01,
                },
                {
                    "identifikace": "L3_V1",
                    "model_version": 3,
                    "model_name": "Model 3 - recency weighted blend",
                    "selection_enabled": True,
                    "best_for_identifier": True,
                    "rolling_backtest_fold_count": 8,
                    "rolling_validation_total_count": 80,
                    "rolling_matched_validation_count": 77,
                    "rolling_coverage": 0.9625,
                    "rolling_wape": 0.31,
                    "rolling_mae": 0.42,
                    "rolling_rmse": 0.7,
                    "rolling_bias": 0.05,
                },
            ],
            "selected_model_snapshot_mode": "active",
            "selected_model_snapshot_count": 3,
            "selected_model_snapshots": [
                {
                    "medium_key": "vodomery",
                    "identifier": "L1_V1",
                    "forecast_period": {
                        "start": datetime.datetime(2026, 7, 13, 4, 10, 5),
                        "end": datetime.datetime(2026, 7, 20, 4, 10, 5),
                        "cadence": "weekly",
                        "label": "2026-07-13 04:10 - 2026-07-20 04:10",
                    },
                    "selection_run_id": 7,
                    "selected_model_version": 2,
                    "selected_model_key": "adaptive_strategy",
                    "selected_model_name": "Model 2 - adaptive strategy",
                    "global_model_version": 2,
                    "global_model_key": "adaptive_strategy",
                    "global_model_name": "Model 2 - adaptive strategy",
                    "fallback_reason": "none",
                    "uses_fallback": False,
                    "metrics": {
                        "validation_total_count": 80,
                        "matched_validation_count": 76,
                        "coverage": 0.95,
                        "mae": 0.32,
                        "rmse": 0.5,
                        "bias": 0.03,
                        "wape": 0.22,
                    },
                    "metadata": {"selected_from_device_metrics": True},
                },
                {
                    "medium_key": "vodomery",
                    "identifier": "L2_V1",
                    "forecast_period": {
                        "start": datetime.datetime(2026, 7, 13, 4, 10, 5),
                        "end": datetime.datetime(2026, 7, 20, 4, 10, 5),
                        "cadence": "weekly",
                        "label": "2026-07-13 04:10 - 2026-07-20 04:10",
                    },
                    "selection_run_id": 7,
                    "selected_model_version": 2,
                    "selected_model_key": "adaptive_strategy",
                    "selected_model_name": "Model 2 - adaptive strategy",
                    "global_model_version": 2,
                    "global_model_key": "adaptive_strategy",
                    "global_model_name": "Model 2 - adaptive strategy",
                    "fallback_reason": "no_eligible_candidate",
                    "uses_fallback": True,
                    "metrics": {
                        "validation_total_count": 80,
                        "matched_validation_count": 70,
                        "coverage": 0.875,
                        "mae": 0.55,
                        "rmse": 0.8,
                        "bias": 0.1,
                        "wape": 0.4,
                    },
                    "metadata": {"selected_from_device_metrics": False},
                },
                {
                    "medium_key": "vodomery",
                    "identifier": "L3_V1",
                    "forecast_period": {
                        "start": datetime.datetime(2026, 7, 13, 4, 10, 5),
                        "end": datetime.datetime(2026, 7, 20, 4, 10, 5),
                        "cadence": "weekly",
                        "label": "2026-07-13 04:10 - 2026-07-20 04:10",
                    },
                    "selection_run_id": 7,
                    "selected_model_version": 3,
                    "selected_model_key": "recency_weighted_blend",
                    "selected_model_name": "Model 3 - recency weighted blend",
                    "global_model_version": 2,
                    "global_model_key": "adaptive_strategy",
                    "global_model_name": "Model 2 - adaptive strategy",
                    "fallback_reason": "none",
                    "uses_fallback": False,
                    "metrics": {
                        "validation_total_count": 80,
                        "matched_validation_count": 77,
                        "coverage": 0.9625,
                        "mae": 0.42,
                        "rmse": 0.7,
                        "bias": 0.05,
                        "wape": 0.31,
                    },
                    "metadata": {"selected_from_device_metrics": True},
                },
            ],
        }
    )

    assert "Eligibility" in body
    assert "Rebuild duration" in body
    assert "2 min 5.4 s" in body
    assert "Rolling WAPE" in body
    assert "Popis sloupcu tabulky Model" in body
    assert "Per-odberne misto rolling backtest" in body
    assert "Odberna mista" in body
    assert "Model 4 - seasonal yearly blend (v4) - measured only" in body
    assert ">measured only</td>" in body
    assert "10.0 %" in body
    assert "L1_V1" in body
    assert "Model 4 - seasonal yearly blend (v4) - measured only" in body
    assert "22.0 %" in body
    assert "Detail nize obsahuje vsechna odberna mista" in body
    assert "Popis tabulek per-odberne misto" in body
    assert "Aktivni vyber modelu pro dalsi obdobi" in body
    assert "produkcni scoring v dalsim forecast obdobi" in body
    assert "Odberna mista s navrhem" in body
    assert "Navrh jiny nez globalni model" in body
    assert "Proc nektera mista zustala na globalnim modelu" in body
    assert "no eligible candidate" in body
    assert "Measured-only modely, ktere by historicky vyhraly" in body
    assert "Kontrola nejhorsich navrzenych vyberu podle WAPE" in body
    assert "Co znamenaji souhrnne active udaje" in body
    assert "L3_V1" in body
    assert "Model 3 - recency weighted blend (v3)" in body
    assert "31.0 %" in body
