import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.reporting import _email_config as email_config


def test_load_report_recipients_filters_placeholder_domains(monkeypatch):
    values = {
        "VODOMERY_DAILY_BRANCH_REPORT_RECIPIENTS": "ops@example.com, real@armex.cz, real@armex.cz",
    }

    monkeypatch.setattr(
        email_config,
        "config",
        lambda key, default="": values.get(key, default),
    )

    recipients = email_config.load_report_recipients("VODOMERY_DAILY_BRANCH_REPORT_RECIPIENTS")

    assert recipients == ("real@armex.cz",)


def test_load_report_recipients_returns_empty_tuple_for_placeholder_only(monkeypatch):
    values = {
        "VODOMERY_DAILY_BRANCH_REPORT_RECIPIENTS": "ops@example.com, alerts@example.org",
    }

    monkeypatch.setattr(
        email_config,
        "config",
        lambda key, default="": values.get(key, default),
    )

    recipients = email_config.load_report_recipients("VODOMERY_DAILY_BRANCH_REPORT_RECIPIENTS")

    assert recipients == ()


def test_sanitize_sender_alias_ignores_placeholder_email_addresses():
    assert (
        email_config.sanitize_sender_alias(
            "Monitoring <upozorneni@example.com>",
            context_label="test",
        )
        is None
    )
    assert email_config.sanitize_sender_alias("Monitoring", context_label="test") == "Monitoring"
