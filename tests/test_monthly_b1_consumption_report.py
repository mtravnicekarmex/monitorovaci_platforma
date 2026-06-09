import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.mereni.vodomery.reporting import monthly_b1_consumption_report as report_module
from moduly.mereni.vodomery.reporting import monthly_jordan_consumption_report as jordan_report
from moduly.mereni.vodomery.reporting import monthly_site_consumption_report as site_report


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

    monkeypatch.setattr(site_report, "load_report_recipients", lambda env_key: ("monthly@armex.cz",))
    monkeypatch.setattr(site_report, "get_previous_month_period", lambda reference_date=None: period)
    monkeypatch.setattr(site_report, "build_meter_summaries", lambda current_period, spec: summaries)
    monkeypatch.setattr(site_report, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))

    def fake_config(key, default=None):
        if key == "O_EMAIL_UPOZORNENI":
            return "Monitoring"
        return default

    monkeypatch.setattr(site_report, "config", fake_config)

    result = report_module.send_monthly_b1_consumption_report(reference_date=datetime.date(2026, 4, 10))

    assert result == {
        "title": "Spotřeba B1 - 03/2026",
        "recipient_count": 1,
        "meter_count": 3,
        "period": "03/2026",
    }
    assert len(sent_messages) == 1
    assert sent_messages[0]["email_receiver"] == "monthly@armex.cz"
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


def test_jordan_report_spec_uses_requested_devices():
    assert jordan_report.JORDAN_REPORT_SPEC.recipient_env_key == (
        "MONTHLY_JORDAN_CONSUMPTION_REPORT_RECIPIENTS"
    )
    assert [
        (meter.meter_type, meter.identifier, meter.unit, meter.source)
        for meter in jordan_report.JORDAN_REPORT_SPEC.meters
    ] == [
        ("Vodoměr", "G_V2", "m3", site_report.MeterSource.VODOMER_PG),
        ("Kalorimetr", "Gmt2", "kWh", site_report.MeterSource.KALORIMETR_PG),
        ("Elektroměr", "G-2.3", "kWh", site_report.MeterSource.ELEKTROMER_MS),
    ]


def test_send_monthly_jordan_consumption_report_builds_html_email(monkeypatch):
    sent_messages = []
    period = site_report.ReportPeriod(
        year=2026,
        month=5,
        period_start=datetime.datetime(2026, 5, 1, 0, 0, 0),
        period_end=datetime.datetime(2026, 6, 1, 0, 0, 0),
    )
    summaries = (
        site_report.MeterConsumptionSummary("Vodoměr", "G_V2", "m3", 100.0, 112.5),
        site_report.MeterConsumptionSummary("Kalorimetr", "Gmt2", "kWh", 200.0, 208.25),
        site_report.MeterConsumptionSummary("Elektroměr", "G-2.3", "kWh", 300.0, 340.75),
    )

    monkeypatch.setattr(site_report, "load_report_recipients", lambda env_key: ("jordan@armex.cz",))
    monkeypatch.setattr(site_report, "get_previous_month_period", lambda reference_date=None: period)
    monkeypatch.setattr(site_report, "build_meter_summaries", lambda current_period, spec: summaries)
    monkeypatch.setattr(site_report, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))
    monkeypatch.setattr(site_report, "config", lambda key, default=None: "Monitoring")

    result = jordan_report.send_monthly_jordan_consumption_report(
        reference_date=datetime.date(2026, 6, 8)
    )

    assert result == {
        "title": "Spotřeba JORDAN - 05/2026",
        "recipient_count": 1,
        "meter_count": 3,
        "period": "05/2026",
    }
    assert sent_messages[0]["email_receiver"] == "jordan@armex.cz"
    assert sent_messages[0]["subject"] == "Spotřeba JORDAN - 05/2026"
    assert "01.05.2026 - 31.05.2026" in sent_messages[0]["body"]
    assert "G_V2" in sent_messages[0]["body"]
    assert "Gmt2" in sent_messages[0]["body"]
    assert "G-2.3" in sent_messages[0]["body"]
    assert "12,500" in sent_messages[0]["body"]
    assert "8,250" in sent_messages[0]["body"]
    assert "40,750" in sent_messages[0]["body"]


def test_load_last_valid_kalorimetr_energy_uses_normalized_pg_table():
    calls = []

    class FakeResult:
        @staticmethod
        def first():
            return (123.4567,)

    class FakeConnection:
        @staticmethod
        def execute(statement, params):
            calls.append((str(statement), params))
            return FakeResult()

    cutoff = datetime.datetime(2026, 6, 1)
    value = site_report.load_last_valid_kalorimetr_energy_before(
        FakeConnection(),
        "Gmt2",
        cutoff,
    )

    assert value == 123.457
    assert 'monitoring."Mereni_kalorimetry_vse"' in calls[0][0]
    assert "spotreba_energie" in calls[0][0]
    assert "platne = TRUE" in calls[0][0]
    assert calls[0][1] == {"identifier": "Gmt2", "cutoff": cutoff}
