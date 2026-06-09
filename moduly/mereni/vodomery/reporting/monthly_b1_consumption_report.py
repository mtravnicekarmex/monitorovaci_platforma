from __future__ import annotations

from datetime import date, datetime

from moduly.mereni.vodomery.reporting import monthly_site_consumption_report as site_report


ELEKTROMER_IDENTIFIERS: tuple[str, ...] = ("B1", "B1-EPS")

B1_REPORT_SPEC = site_report.SiteReportSpec(
    site_label="B1",
    recipient_env_key="MONTHLY_B1_CONSUMPTION_REPORT_RECIPIENTS",
    context_label="send_monthly_b1_consumption_report",
    meters=(
        site_report.MeterSpec(
            meter_type="Vodoměr",
            identifier="SCVK_B1",
            unit="m3",
            source=site_report.MeterSource.VODOMER_PG,
        ),
        site_report.MeterSpec(
            meter_type="Elektroměr",
            identifier=ELEKTROMER_IDENTIFIERS[0],
            unit="kWh",
            source=site_report.MeterSource.ELEKTROMER_MS,
        ),
        site_report.MeterSpec(
            meter_type="Elektroměr",
            identifier=ELEKTROMER_IDENTIFIERS[1],
            unit="kWh",
            source=site_report.MeterSource.ELEKTROMER_MS,
        ),
    ),
)

ReportPeriod = site_report.ReportPeriod
MeterConsumptionSummary = site_report.MeterConsumptionSummary


def send_monthly_b1_consumption_report(reference_date: date | None = None) -> dict[str, object]:
    return site_report.send_monthly_site_consumption_report(B1_REPORT_SPEC, reference_date)


def _load_recipients() -> list[str]:
    return list(site_report.load_report_recipients(B1_REPORT_SPEC.recipient_env_key))


def _get_previous_month_period(reference_date: date | None = None) -> ReportPeriod:
    return site_report.get_previous_month_period(reference_date)


def _build_meter_summaries(period: ReportPeriod) -> tuple[MeterConsumptionSummary, ...]:
    return site_report.build_meter_summaries(period, B1_REPORT_SPEC)


def _build_subject(period: ReportPeriod) -> str:
    return site_report.build_subject(period, B1_REPORT_SPEC)


def _build_report_heading(period: ReportPeriod) -> str:
    return site_report.build_subject(period, B1_REPORT_SPEC)


def _load_last_valid_vodomer_value_before(conn, identifier: str, cutoff: datetime) -> float | None:
    return site_report.load_last_valid_vodomer_value_before(conn, identifier, cutoff)


def _load_last_valid_elektromer_total_before(conn, identifier: str, cutoff: datetime) -> float | None:
    return site_report.load_last_valid_elektromer_total_before(conn, identifier, cutoff)


def _to_rounded_float(value: object) -> float | None:
    return site_report.to_rounded_float(value)


def _build_html_body(
    period: ReportPeriod,
    summaries: tuple[MeterConsumptionSummary, ...],
) -> str:
    return site_report.build_html_body(period, summaries, B1_REPORT_SPEC)


def _format_value(value: float | None) -> str:
    return site_report.format_value(value)
