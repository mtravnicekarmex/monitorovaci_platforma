import datetime

from pathlib import Path

from moduly.mereni.plynomery import reporting
from moduly.mereni.plynomery.reporting import monthly_billing_report
from moduly.mereni.plynomery.reporting.model_rebuild_report import _build_email_body


def _selection_result():
    return {
        "selection_run_id": 18,
        "selection_mode": "active",
        "active_model_version": 2,
        "active_model_name": "Model 2",
        "previous_active_model_version": 2,
        "previous_active_model_name": "Model 2",
        "windows": {
            "train_start": datetime.datetime(2026, 4, 1),
            "train_end": datetime.datetime(2026, 6, 1),
            "validation_start": datetime.datetime(2026, 6, 1),
            "validation_end": datetime.datetime(2026, 7, 1),
            "deploy_start": datetime.datetime(2026, 4, 1),
            "deploy_end": datetime.datetime(2026, 7, 1),
        },
        "candidates": [
            {
                "model_version": 2,
                "model_name": "Model 2",
                "selected": True,
                "validation_total_count": 100,
                "matched_validation_count": 90,
                "coverage": 0.9,
                "mae": 1.0,
                "rmse": 1.2,
                "bias": 0.1,
                "rolling_coverage": 0.88,
                "rolling_wape": 0.15,
                "profile_count": 100,
            }
        ],
        "dry_run_winner_counts": {1: 2, 2: 3},
        "dry_run_unavailable_count": 13,
        "dry_run_selected_models": [
            {
                "identifier": "P_A1<script>",
                "selected_model_version": 2,
                "fallback_reason": "none",
                "metrics": {"coverage": 0.9, "wape": 0.2},
            },
            {
                "identifier": "P_A2",
                "selected_model_version": 1,
                "fallback_reason": "below_coverage_threshold",
                "metrics": {"coverage": 0.8, "wape": 0.3},
            },
        ],
        "deployable_profile_pair_count": 10,
        "deployable_profile_count": 6720,
    }


def test_plynomery_reporting_surface_exports_only_model_rebuild_delivery_report():
    assert reporting.__all__ == ["send_plynomery_model_rebuild_report"]

    reporting_directory = Path(reporting.__file__).resolve().parent
    report_modules = sorted(
        path.name
        for path in reporting_directory.glob("*.py")
        if path.name != "__init__.py"
    )
    assert report_modules == ["model_rebuild_report.py", "monthly_billing_report.py"]

    monthly_exported_send_functions = [
        name
        for name in dir(monthly_billing_report)
        if name.startswith("send_")
    ]
    assert monthly_exported_send_functions == []


def test_plynomery_rebuild_report_contains_selection_aggregates_and_rolling_metrics():
    body = _build_email_body(_selection_result())

    assert "Aktivni per-identifier vyber" in body
    assert "v1: 2, v2: 3" in body
    assert "below_coverage_threshold: 1" in body
    assert "Rolling coverage" in body
    assert "Rolling WAPE" in body
    assert "Deployable dvojice/profily: 10 / 6720" in body
    assert "Predikce nedostupna (nedostatecna historie): 13" in body


def test_plynomery_rebuild_report_escapes_identifier_labels():
    body = _build_email_body(_selection_result())

    assert "P_A1&lt;script&gt;" in body
    assert "P_A1<script>" not in body
