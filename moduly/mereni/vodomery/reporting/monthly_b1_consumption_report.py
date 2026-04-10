from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import html

from decouple import config
from sqlalchemy import text

from app.channels.email import send_email_outlook
from app.time_utils import prague_today
from core.db.connect import ENGINE_MS, ENGINE_PG

ELEKTROMER_IDENTIFIERS: tuple[str, ...] = ("B1", "B1-EPS")


@dataclass(frozen=True)
class ReportPeriod:
    year: int
    month: int
    period_start: datetime
    period_end: datetime

    @property
    def month_label(self) -> str:
        return f"{self.month:02d}/{self.year}"

    @property
    def date_range_label(self) -> str:
        period_end_inclusive = self.period_end - timedelta(days=1)
        return (
            f"{self.period_start.strftime('%d.%m.%Y')} - "
            f"{period_end_inclusive.strftime('%d.%m.%Y')}"
        )


@dataclass(frozen=True)
class MeterConsumptionSummary:
    meter_type: str
    identifier: str
    unit: str
    start_value: float | None
    end_value: float | None

    @property
    def consumption(self) -> float | None:
        if self.start_value is None or self.end_value is None or self.end_value < self.start_value:
            return None
        return round(self.end_value - self.start_value, 3)


def send_monthly_b1_consumption_report(reference_date: date | None = None) -> dict[str, object]:
    recipients = _load_recipients()
    period = _get_previous_month_period(reference_date)
    summaries = _build_meter_summaries(period)
    subject = _build_subject(period)
    body = _build_html_body(period, summaries)

    for recipient in recipients:
        send_email_outlook(
            email_receiver=recipient,
            subject=subject,
            body=body,
            sender_alias=config("O_EMAIL_UPOZORNENI", default=None),
            is_html=True,
        )

    return {
        "title": subject,
        "recipient_count": len(recipients),
        "meter_count": len(summaries),
        "period": period.month_label,
    }


def _load_recipients() -> list[str]:
    raw_recipients = config("VODOMERY_MONTHLY_REPORT_RECIPIENTS", default="")
    recipients = [item.strip() for item in raw_recipients.split(",") if item.strip()]
    if not recipients:
        raise ValueError("Neni nastavena promenna VODOMERY_MONTHLY_REPORT_RECIPIENTS.")
    return recipients


def _get_previous_month_period(reference_date: date | None = None) -> ReportPeriod:
    base_date = reference_date or prague_today()
    current_month_start = base_date.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return ReportPeriod(
        year=previous_month_start.year,
        month=previous_month_start.month,
        period_start=datetime.combine(previous_month_start, time.min),
        period_end=datetime.combine(current_month_start, time.min),
    )


def _build_meter_summaries(period: ReportPeriod) -> tuple[MeterConsumptionSummary, ...]:
    water_summary = _build_vodomer_summary(period)
    electricity_summaries = _build_elektromer_summaries(period)
    return (water_summary, *electricity_summaries)


def _build_vodomer_summary(period: ReportPeriod) -> MeterConsumptionSummary:
    with ENGINE_PG.connect() as conn:
        start_value = _load_last_valid_vodomer_value_before(conn, "SCVK_B1", period.period_start)
        end_value = _load_last_valid_vodomer_value_before(conn, "SCVK_B1", period.period_end)

    return MeterConsumptionSummary(
        meter_type="Vodoměr",
        identifier="SCVK_B1",
        unit="m3",
        start_value=start_value,
        end_value=end_value,
    )


def _build_elektromer_summaries(period: ReportPeriod) -> tuple[MeterConsumptionSummary, ...]:
    with ENGINE_MS.connect() as conn:
        summaries = []
        for identifier in ELEKTROMER_IDENTIFIERS:
            start_value = _load_last_valid_elektromer_total_before(conn, identifier, period.period_start)
            end_value = _load_last_valid_elektromer_total_before(conn, identifier, period.period_end)
            summaries.append(
                MeterConsumptionSummary(
                    meter_type="Elektroměr",
                    identifier=identifier,
                    unit="kWh",
                    start_value=start_value,
                    end_value=end_value,
                )
            )

    return tuple(summaries)


def _build_subject(period: ReportPeriod) -> str:
    elektriky = ", ".join(ELEKTROMER_IDENTIFIERS)
    return f"Spotřeba B1 - {period.month_label}"


def _build_report_heading(period: ReportPeriod) -> str:
    return f"Spotřeba B1 - {period.month_label}"


def _load_last_valid_vodomer_value_before(conn, identifier: str, cutoff: datetime) -> float | None:
    row = conn.execute(
        text(
            """
            SELECT objem
            FROM monitoring."Mereni_vodomery_vse"
            WHERE identifikace = :identifier
              AND date < :cutoff
              AND platne = TRUE
              AND objem IS NOT NULL
            ORDER BY date DESC, id DESC
            LIMIT 1
            """
        ),
        {
            "identifier": identifier,
            "cutoff": cutoff,
        },
    ).first()
    return _to_rounded_float(row[0]) if row else None


def _load_last_valid_elektromer_total_before(conn, identifier: str, cutoff: datetime) -> float | None:
    row = conn.execute(
        text(
            """
            SELECT TOP 1 total
            FROM dbo.Mereni_elektromery
            WHERE identifikace = :identifier
              AND date < :cutoff
              AND total IS NOT NULL
            ORDER BY date DESC, recid DESC
            """
        ),
        {
            "identifier": identifier,
            "cutoff": cutoff,
        },
    ).first()
    return _to_rounded_float(row[0]) if row else None


def _to_rounded_float(value: object) -> float | None:
    if value is None:
        return None
    return round(float(value), 3)


def _build_html_body(
    period: ReportPeriod,
    summaries: tuple[MeterConsumptionSummary, ...],
) -> str:
    row_html = "".join(
        (
            "<tr>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;'>{html.escape(summary.meter_type)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;'>{html.escape(summary.identifier)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_value(summary.start_value)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_value(summary.end_value)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{_format_value(summary.consumption)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;'>{html.escape(summary.unit)}</td>"
            "</tr>"
        )
        for summary in summaries
    )

    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        f"<h2 style='margin:0 0 12px;'>{html.escape(_build_report_heading(period))}</h2>"
        # f"<p style='margin:0 0 6px;'><strong>Měsíc reportu:</strong> {html.escape(period.month_label)}</p>"
        f"<p style='margin:0 0 16px;'><strong>Období:</strong> {html.escape(period.date_range_label)}</p>"
        "<table style='border-collapse:collapse;font-size:14px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Typ měřidla</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Identifikace</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Počáteční stav</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Konečný stav</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Spotřeba</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Jednotka</th>"
        "</tr>"
        f"{row_html}"
        "</table>"
        "</body></html>"
    )


def _format_value(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}".replace(".", ",")
