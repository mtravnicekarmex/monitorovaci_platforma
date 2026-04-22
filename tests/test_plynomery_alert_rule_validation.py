import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.plynomery.database.alerting import EVENT_TYPE_OPTIONS
from services.api.core.plynomery_alert_rule_validation import normalize_alert_rule_payload


def test_expected_zero_usage_is_available_for_plynomery_alerting():
    assert "EXPECTED_ZERO_USAGE" in EVENT_TYPE_OPTIONS


def test_normalize_alert_rule_payload_accepts_expected_zero_usage():
    payload = normalize_alert_rule_payload(
        rule_name="Expected zero",
        recipient_email="alerts@example.com",
        severity_min="HIGH",
        min_duration_minutes=120,
        send_on="ACTIVE",
        identifikace=None,
        event_type="EXPECTED_ZERO_USAGE",
        enabled=True,
        note=None,
    )

    assert payload["event_type"] == "EXPECTED_ZERO_USAGE"
    assert payload["min_duration_minutes"] == 120
