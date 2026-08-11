import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.database.alerting import EVENT_TYPE_OPTIONS
from services.api.core.vodomery_alert_rule_validation import normalize_alert_rule_payload


def test_vodomery_alert_rule_options_include_sustained_high_usage():
    assert "SUSTAINED_HIGH_USAGE" in EVENT_TYPE_OPTIONS


def test_normalize_alert_rule_payload_forces_zero_duration_for_outlier_review():
    payload = normalize_alert_rule_payload(
        rule_name="Outlier email",
        recipient_email="alerts@example.com",
        severity_min="HIGH",
        min_duration_minutes=120,
        send_on="ACTIVE",
        identifikace=None,
        event_type="OUTLIER_REVIEW",
        enabled=True,
        note=None,
    )

    assert payload["event_type"] == "OUTLIER_REVIEW"
    assert payload["min_duration_minutes"] == 0


def test_normalize_alert_rule_payload_accepts_sustained_high_usage():
    payload = normalize_alert_rule_payload(
        rule_name="Sustained high usage",
        recipient_email="alerts@example.com",
        severity_min="HIGH",
        min_duration_minutes=60,
        send_on="ACTIVE",
        identifikace="E_V1",
        event_type="sustained_high_usage",
        enabled=True,
        note=None,
    )

    assert payload["event_type"] == "SUSTAINED_HIGH_USAGE"
    assert payload["min_duration_minutes"] == 60
