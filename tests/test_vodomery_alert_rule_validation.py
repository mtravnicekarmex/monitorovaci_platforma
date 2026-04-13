import sys
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.api.core.vodomery_alert_rule_validation import normalize_alert_rule_payload


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
