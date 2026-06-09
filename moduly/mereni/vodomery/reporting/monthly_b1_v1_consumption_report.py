from __future__ import annotations

from datetime import date, datetime, time

from app.czech_business_calendar import last_czech_business_day
from app.time_utils import prague_today
from moduly.mereni.vodomery.reporting import monthly_site_consumption_report as site_report


B1_V1_REPORT_SPEC = site_report.SiteReportSpec(
    site_label="B1_V1",
    recipient_env_key="MONTHLY_B1_V1_CONSUMPTION_REPORT_RECIPIENTS",
    context_label="send_monthly_b1_v1_consumption_report",
    meters=(
        site_report.MeterSpec(
            meter_type="Vodom\u011br",
            identifier="B1_V1",
            unit="m3",
            source=site_report.MeterSource.VODOMER_PG,
        ),
    ),
    include_cutoff_measurement=True,
    recipient_fallback_env_keys=("MONTHLY_B1_CONSUMPTION_REPORT_RECIPIENTS",),
)


def _previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def get_b1_v1_report_period(reference_date: date | None = None) -> site_report.ReportPeriod:
    base_date = reference_date or prague_today()
    report_year = base_date.year
    report_month = base_date.month
    current_month_end = last_czech_business_day(report_year, report_month)

    if base_date < current_month_end:
        report_year, report_month = _previous_month(report_year, report_month)

    period_end_date = last_czech_business_day(report_year, report_month)
    previous_year, previous_month = _previous_month(report_year, report_month)
    period_start_date = last_czech_business_day(previous_year, previous_month)

    return site_report.ReportPeriod(
        year=report_year,
        month=report_month,
        period_start=datetime.combine(period_start_date, time(13, 15, 59, 999999)),
        period_end=datetime.combine(period_end_date, time(13, 0, 59, 999999)),
    )


def send_monthly_b1_v1_consumption_report(
    reference_date: date | None = None,
) -> dict[str, object]:
    return site_report.send_monthly_site_consumption_report(
        B1_V1_REPORT_SPEC,
        reference_date,
        period_resolver=get_b1_v1_report_period,
    )


def _load_recipients() -> list[str]:
    return list(site_report.load_site_report_recipients(B1_V1_REPORT_SPEC))
