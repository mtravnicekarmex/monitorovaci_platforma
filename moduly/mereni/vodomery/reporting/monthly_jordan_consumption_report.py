from __future__ import annotations

from datetime import date

from moduly.mereni.vodomery.reporting import monthly_site_consumption_report as site_report


JORDAN_REPORT_SPEC = site_report.SiteReportSpec(
    site_label="JORDAN",
    recipient_env_key="MONTHLY_JORDAN_CONSUMPTION_REPORT_RECIPIENTS",
    context_label="send_monthly_jordan_consumption_report",
    meters=(
        site_report.MeterSpec(
            meter_type="Vodoměr",
            identifier="G_V2",
            unit="m3",
            source=site_report.MeterSource.VODOMER_PG,
        ),
        site_report.MeterSpec(
            meter_type="Kalorimetr",
            identifier="Gmt2",
            unit="kWh",
            source=site_report.MeterSource.KALORIMETR_PG,
        ),
        site_report.MeterSpec(
            meter_type="Elektroměr",
            identifier="G-2.3",
            unit="kWh",
            source=site_report.MeterSource.ELEKTROMER_MS,
        ),
    ),
)


def send_monthly_jordan_consumption_report(reference_date: date | None = None) -> dict[str, object]:
    return site_report.send_monthly_site_consumption_report(JORDAN_REPORT_SPEC, reference_date)


def _load_recipients() -> list[str]:
    return list(site_report.load_report_recipients(JORDAN_REPORT_SPEC.recipient_env_key))
