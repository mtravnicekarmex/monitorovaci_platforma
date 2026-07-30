from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVENTORY = (
    PROJECT_ROOT
    / "agents"
    / "inventories"
    / "KALORIMETRY_CONSUMER_INVENTORY.md"
)


def test_inventory_classifies_every_required_consumer_category():
    source = INVENTORY.read_text(encoding="utf-8")
    for classification in (
        "prediction-bearing",
        "actual-only",
        "anomaly/event",
        "model rebuild",
        "device/inventory",
    ):
        assert classification in source


def test_inventory_owns_user_facing_and_direct_profile_consumers():
    source = INVENTORY.read_text(encoding="utf-8")
    required_paths = (
        "pages/11_kalorimetry.py",
        "pages/12_kalorimetry_detail.py",
        "pages/33_kalorimetry_seznam.py",
        "pages/0_overview.py",
        "monthly_jordan_consumption_report.py",
        "services/api/services/kalorimetry.py",
        "active_profile.py",
        "kalorimetry_anomaly.py",
        "outlier_review_apply.py",
        "events.py",
        "reconciliation.py",
        "prediction_adapter.py",
        "prediction_performance.py",
    )
    for path in required_paths:
        assert path in source


def test_jordan_report_remains_explicitly_actual_only():
    source = INVENTORY.read_text(encoding="utf-8")
    assert "JORDAN monthly email" in source
    assert "actual-only" in source
    assert "do not add prediction without separate approval" in source


def test_inventory_prohibits_direct_candidate_profile_dashboard_reads():
    source = INVENTORY.read_text(encoding="utf-8")
    normalized = " ".join(source.split())
    assert "kalorimetry_anomaly_profiles" in source
    assert "kalorimetry_weather_model_profiles" in source
    assert (
        "No user-facing dashboard, consumption report, or prediction-series "
        "path reads those candidate tables directly."
    ) in normalized
