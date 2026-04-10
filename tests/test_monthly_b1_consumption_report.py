import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.reporting import monthly_b1_consumption_report as report_module


def test_send_monthly_b1_consumption_report_builds_html_email(monkeypatch):
    sent_messages = []
    period = report_module.ReportPeriod(
        year=2026,
        month=3,
        period_start=datetime.datetime(2026, 3, 1, 0, 0, 0),
        period_end=datetime.datetime(2026, 4, 1, 0, 0, 0),
    )
    summaries = (
        report_module.MeterConsumptionSummary(
            meter_type="Vodoměr",
            identifier="SCVK_B1",
            unit="m3",
            start_value=100.25,
            end_value=124.75,
        ),
        report_module.MeterConsumptionSummary(
            meter_type="Elektroměr",
            identifier="B1",
            unit="kWh",
            start_value=1000.0,
            end_value=1125.5,
        ),
        report_module.MeterConsumptionSummary(
            meter_type="Elektroměr",
            identifier="B1-EPS",
            unit="kWh",
            start_value=500.0,
            end_value=575.25,
        ),
    )

    monkeypatch.setattr(report_module, "_load_recipients", lambda: ["monthly@example.com"])
    monkeypatch.setattr(report_module, "_get_previous_month_period", lambda reference_date=None: period)
    monkeypatch.setattr(report_module, "_build_meter_summaries", lambda current_period: summaries)
    monkeypatch.setattr(report_module, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))

    def fake_config(key, default=None):
        if key == "O_EMAIL_UPOZORNENI":
            return "Monitoring"
        return default

    monkeypatch.setattr(report_module, "config", fake_config)

    result = report_module.send_monthly_b1_consumption_report(reference_date=datetime.date(2026, 4, 10))

    assert result == {
        "title": "Spotřeba B1 - 03/2026",
        "recipient_count": 1,
        "meter_count": 3,
        "period": "03/2026",
    }
    assert len(sent_messages) == 1
    assert sent_messages[0]["email_receiver"] == "monthly@example.com"
    assert sent_messages[0]["subject"] == "Spotřeba B1 - 03/2026"
    assert sent_messages[0]["sender_alias"] == "Monitoring"
    assert sent_messages[0]["is_html"] is True
    assert "Spotřeba B1 - 03/2026" in sent_messages[0]["body"]
    assert "01.03.2026 - 31.03.2026" in sent_messages[0]["body"]
    assert "SCVK_B1" in sent_messages[0]["body"]
    assert "B1" in sent_messages[0]["body"]
    assert "B1-EPS" in sent_messages[0]["body"]
    assert "100,250" in sent_messages[0]["body"]
    assert "24,500" in sent_messages[0]["body"]
    assert "125,500" in sent_messages[0]["body"]
    assert "75,250" in sent_messages[0]["body"]


def test_build_html_body_uses_dash_for_missing_values():
    period = report_module.ReportPeriod(
        year=2026,
        month=3,
        period_start=datetime.datetime(2026, 3, 1, 0, 0, 0),
        period_end=datetime.datetime(2026, 4, 1, 0, 0, 0),
    )
    summaries = (
        report_module.MeterConsumptionSummary(
            meter_type="Vodoměr",
            identifier="SCVK_B1",
            unit="m3",
            start_value=None,
            end_value=10.0,
        ),
    )

    body = report_module._build_html_body(period, summaries)

    assert body.count(">-<") == 2
