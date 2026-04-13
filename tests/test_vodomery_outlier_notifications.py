import datetime
import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.alerting import outlier_notifications


def test_build_candidate_matches_generic_outlier_rule():
    rule = SimpleNamespace(
        id=7,
        rule_name="Outlier operator",
        recipient_email="alerts@example.com",
        enabled=True,
        identifikace=None,
        event_type="OUTLIER_REVIEW",
        severity_min="MEDIUM",
        min_duration_minutes=0,
        send_on="ACTIVE",
    )
    review = SimpleNamespace(
        id=101,
        identifikace="A_V1",
        date=datetime.datetime(2026, 4, 13, 8, 15, 0),
        zdroj="AREAL",
        interval_minutes=15,
        detection_kind="NORMAL_DELTA",
        candidate_delta=35.0,
        threshold_delta=12.0,
        current_objem=120.0,
        baseline_objem=85.0,
    )

    candidate = outlier_notifications._build_candidate(rule=rule, review=review)

    assert candidate is not None
    assert candidate["rule_id"] == 7
    assert candidate["recipient_email"] == "alerts@example.com"
    assert candidate["severity"] == "HIGH"
    assert candidate["delivery_key"] == (101, 7, "alerts@example.com")


def test_build_candidate_rejects_rule_for_other_event_type():
    rule = SimpleNamespace(
        id=7,
        rule_name="Spike only",
        recipient_email="alerts@example.com",
        enabled=True,
        identifikace=None,
        event_type="SPIKE",
        severity_min="LOW",
        min_duration_minutes=0,
        send_on="ACTIVE",
    )
    review = SimpleNamespace(
        id=101,
        identifikace="A_V1",
        date=datetime.datetime(2026, 4, 13, 8, 15, 0),
        zdroj="AREAL",
        interval_minutes=15,
        detection_kind="NORMAL_DELTA",
        candidate_delta=35.0,
        threshold_delta=12.0,
        current_objem=120.0,
        baseline_objem=85.0,
    )

    assert outlier_notifications._build_candidate(rule=rule, review=review) is None


def test_build_html_body_contains_rule_and_severity():
    body = outlier_notifications._build_html_body(
        [
            {
                "rule_name": "Outlier operator",
                "identifikace": "A_V1",
                "zdroj": "AREAL",
                "review_date": datetime.datetime(2026, 4, 13, 8, 15, 0),
                "severity": "HIGH",
                "detection_kind": "NORMAL_DELTA",
                "candidate_delta": 35.0,
                "threshold_delta": 12.0,
            }
        ]
    )

    assert "Outlier operator" in body
    assert "A_V1" in body
    assert "HIGH" in body
    assert "35.000" in body
