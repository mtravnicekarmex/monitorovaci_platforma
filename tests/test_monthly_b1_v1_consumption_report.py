import datetime

from app.czech_business_calendar import (
    czech_public_holidays,
    is_last_czech_business_day,
    last_czech_business_day,
)
from moduly.mereni.vodomery.reporting import monthly_b1_v1_consumption_report as report
from moduly.mereni.vodomery.reporting import monthly_site_consumption_report as site_report


def test_czech_business_calendar_includes_easter_holidays():
    holidays = czech_public_holidays(2026)

    assert datetime.date(2026, 4, 3) in holidays
    assert datetime.date(2026, 4, 6) in holidays


def test_last_czech_business_day_handles_weekend_and_easter():
    assert last_czech_business_day(2026, 5) == datetime.date(2026, 5, 29)
    assert last_czech_business_day(2024, 3) == datetime.date(2024, 3, 28)
    assert is_last_czech_business_day(datetime.date(2024, 3, 28)) is True
    assert is_last_czech_business_day(datetime.date(2024, 3, 29)) is False


def test_b1_v1_period_uses_requested_business_day_times():
    period = report.get_b1_v1_report_period(datetime.date(2026, 6, 30))

    assert period.year == 2026
    assert period.month == 6
    assert period.period_start == datetime.datetime(2026, 5, 29, 13, 15, 59, 999999)
    assert period.period_end == datetime.datetime(2026, 6, 30, 13, 0, 59, 999999)
    assert period.date_range_label == "29.05.2026 13:15 - 30.06.2026 13:00"


def test_b1_v1_period_uses_last_completed_month_before_current_month_end():
    period = report.get_b1_v1_report_period(datetime.date(2026, 6, 9))

    assert period.year == 2026
    assert period.month == 5
    assert period.period_start == datetime.datetime(2026, 4, 30, 13, 15, 59, 999999)
    assert period.period_end == datetime.datetime(2026, 5, 29, 13, 0, 59, 999999)


def test_b1_v1_report_builds_email_with_single_water_meter(monkeypatch):
    sent_messages = []
    period = site_report.ReportPeriod(
        year=2026,
        month=6,
        period_start=datetime.datetime(2026, 5, 29, 13, 15, 59, 999999),
        period_end=datetime.datetime(2026, 6, 30, 13, 0, 59, 999999),
    )
    summaries = (
        site_report.MeterConsumptionSummary(
            meter_type="Vodom\u011br",
            identifier="B1_V1",
            unit="m3",
            start_value=100.25,
            end_value=124.75,
        ),
    )

    monkeypatch.setattr(
        site_report,
        "load_report_recipients",
        lambda env_key, **kwargs: ("b1-v1@armex.cz",),
    )
    monkeypatch.setattr(report, "get_b1_v1_report_period", lambda reference_date=None: period)
    monkeypatch.setattr(site_report, "build_meter_summaries", lambda current_period, spec: summaries)
    monkeypatch.setattr(site_report, "send_email_outlook", lambda **kwargs: sent_messages.append(kwargs))
    monkeypatch.setattr(site_report, "config", lambda key, default=None: "Monitoring")

    result = report.send_monthly_b1_v1_consumption_report(
        reference_date=datetime.date(2026, 6, 30)
    )

    assert result == {
        "title": "Spot\u0159eba B1_V1 - 06/2026",
        "recipient_count": 1,
        "meter_count": 1,
        "period": "06/2026",
    }
    assert sent_messages[0]["email_receiver"] == "b1-v1@armex.cz"
    assert sent_messages[0]["subject"] == "Spot\u0159eba B1_V1 - 06/2026"
    assert "29.05.2026 13:15 - 30.06.2026 13:00" in sent_messages[0]["body"]
    assert "B1_V1" in sent_messages[0]["body"]
    assert "100,250" in sent_messages[0]["body"]
    assert "124,750" in sent_messages[0]["body"]
    assert "24,500" in sent_messages[0]["body"]


def test_b1_v1_water_value_query_includes_exact_cutoff():
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

    cutoff = datetime.datetime(2026, 6, 30, 13, 0, 59, 999999)
    value = site_report.load_last_valid_vodomer_value_before(
        FakeConnection(),
        "B1_V1",
        cutoff,
        include_cutoff=True,
    )

    assert value == 123.457
    assert "date <= :cutoff" in calls[0][0]
    assert calls[0][1] == {"identifier": "B1_V1", "cutoff": cutoff}
