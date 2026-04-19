import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.reporting import _email_config as email_config
from moduly.mereni.vodomery.reporting import model_rebuild_report
from moduly.mereni.vodomery.reporting import monthly_b1_consumption_report
from moduly.mereni.vodomery.reporting import monthly_branch_report
from moduly.mereni.vodomery.reporting import monthly_consumption_report
from moduly.mereni.vodomery.reporting import weekly_branch_report


def test_monthly_consumption_report_uses_dedicated_recipient_env(monkeypatch):
    values = {
        "VODOMERY_MONTHLY_CONSUMPTION_REPORT_RECIPIENTS": "spotreba@armex.cz",
        "VODOMERY_MONTHLY_B1_CONSUMPTION_REPORT_RECIPIENTS": "b1@armex.cz",
    }
    monkeypatch.setattr(email_config, "config", lambda key, default="": values.get(key, default))

    assert monthly_consumption_report._load_recipients() == ["spotreba@armex.cz"]


def test_monthly_b1_report_uses_dedicated_recipient_env(monkeypatch):
    values = {
        "VODOMERY_MONTHLY_CONSUMPTION_REPORT_RECIPIENTS": "spotreba@armex.cz",
        "VODOMERY_MONTHLY_B1_CONSUMPTION_REPORT_RECIPIENTS": "b1@armex.cz",
    }
    monkeypatch.setattr(email_config, "config", lambda key, default="": values.get(key, default))

    assert monthly_b1_consumption_report._load_recipients() == ["b1@armex.cz"]


def test_model_rebuild_report_does_not_fallback_to_monthly_consumption_recipients(monkeypatch):
    values = {
        "VODOMERY_MONTHLY_CONSUMPTION_REPORT_RECIPIENTS": "spotreba@armex.cz",
    }
    monkeypatch.setattr(email_config, "config", lambda key, default="": values.get(key, default))

    with pytest.raises(ValueError, match="VODOMERY_MODEL_REBUILD_REPORT_RECIPIENTS"):
        model_rebuild_report._load_recipients()


def test_weekly_branch_report_does_not_fallback_to_daily_branch_recipients(monkeypatch):
    values = {
        "VODOMERY_DAILY_BRANCH_REPORT_RECIPIENTS": "denni@armex.cz",
    }
    monkeypatch.setattr(email_config, "config", lambda key, default="": values.get(key, default))

    assert weekly_branch_report._load_recipients() == ()


def test_monthly_branch_report_does_not_fallback_to_daily_branch_recipients(monkeypatch):
    values = {
        "VODOMERY_DAILY_BRANCH_REPORT_RECIPIENTS": "denni@armex.cz",
    }
    monkeypatch.setattr(email_config, "config", lambda key, default="": values.get(key, default))

    assert monthly_branch_report._load_recipients() == ()
