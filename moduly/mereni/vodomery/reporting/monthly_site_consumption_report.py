from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
import html
from typing import Callable

from decouple import config
from sqlalchemy import text

from app.channels.email import send_email_outlook
from app.time_utils import prague_today
from core.db.connect import ENGINE_MS, ENGINE_PG
from moduly.mereni.vodomery.reporting._email_config import (
    filter_placeholder_recipients,
    load_report_recipients,
    sanitize_sender_alias,
)


class MeterSource(str, Enum):
    VODOMER_PG = "vodomer_pg"
    KALORIMETR_PG = "kalorimetr_pg"
    ELEKTROMER_MS = "elektromer_ms"


@dataclass(frozen=True)
class MeterSpec:
    meter_type: str
    identifier: str
    unit: str
    source: MeterSource


@dataclass(frozen=True)
class SiteReportSpec:
    site_label: str
    recipient_env_key: str
    context_label: str
    meters: tuple[MeterSpec, ...]
    include_cutoff_measurement: bool = False
    recipient_fallback_env_keys: tuple[str, ...] = ()


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
        if self.period_start.time() != time.min or self.period_end.time() != time.min:
            return (
                f"{self.period_start.strftime('%d.%m.%Y %H:%M')} - "
                f"{self.period_end.strftime('%d.%m.%Y %H:%M')}"
            )
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


def send_monthly_site_consumption_report(
    spec: SiteReportSpec,
    reference_date: date | None = None,
    *,
    period_resolver: Callable[[date | None], ReportPeriod] | None = None,
) -> dict[str, object]:
    period = (
        period_resolver(reference_date)
        if period_resolver is not None
        else get_previous_month_period(reference_date)
    )
    recipients = filter_placeholder_recipients(
        load_site_report_recipients(spec),
        context_label=spec.context_label,
    )
    if not recipients:
        return {
            "title": build_subject(period, spec),
            "recipient_count": 0,
            "meter_count": 0,
            "period": period.month_label,
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }

    summaries = build_meter_summaries(period, spec)
    subject = build_subject(period, spec)
    body = build_html_body(period, summaries, spec)
    sender_alias = sanitize_sender_alias(
        config("O_EMAIL_UPOZORNENI", default=None),
        context_label="VODOMERY_MONTHLY_REPORT_SENDER_ALIAS",
    )

    for recipient in recipients:
        send_email_outlook(
            email_receiver=recipient,
            subject=subject,
            body=body,
            sender_alias=sender_alias,
            is_html=True,
        )

    return {
        "title": subject,
        "recipient_count": len(recipients),
        "meter_count": len(summaries),
        "period": period.month_label,
    }


def load_site_report_recipients(spec: SiteReportSpec) -> tuple[str, ...]:
    if spec.recipient_fallback_env_keys:
        return load_report_recipients(
            spec.recipient_env_key,
            fallback_env_keys=spec.recipient_fallback_env_keys,
        )
    return load_report_recipients(spec.recipient_env_key)


def get_previous_month_period(reference_date: date | None = None) -> ReportPeriod:
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


def build_meter_summaries(
    period: ReportPeriod,
    spec: SiteReportSpec,
) -> tuple[MeterConsumptionSummary, ...]:
    summaries: list[MeterConsumptionSummary] = []
    with ExitStack() as stack:
        pg_conn = None
        ms_conn = None
        for meter in spec.meters:
            if meter.source in (MeterSource.VODOMER_PG, MeterSource.KALORIMETR_PG):
                if pg_conn is None:
                    pg_conn = stack.enter_context(ENGINE_PG.connect())
                conn = pg_conn
            elif meter.source == MeterSource.ELEKTROMER_MS:
                if ms_conn is None:
                    ms_conn = stack.enter_context(ENGINE_MS.connect())
                conn = ms_conn
            else:
                raise ValueError(f"Nepodporovany zdroj meridla: {meter.source}")

            start_value = load_meter_value_before(
                conn,
                meter,
                period.period_start,
                include_cutoff=spec.include_cutoff_measurement,
            )
            end_value = load_meter_value_before(
                conn,
                meter,
                period.period_end,
                include_cutoff=spec.include_cutoff_measurement,
            )
            summaries.append(
                MeterConsumptionSummary(
                    meter_type=meter.meter_type,
                    identifier=meter.identifier,
                    unit=meter.unit,
                    start_value=start_value,
                    end_value=end_value,
                )
            )

    return tuple(summaries)


def load_meter_value_before(
    conn,
    meter: MeterSpec,
    cutoff: datetime,
    *,
    include_cutoff: bool = False,
) -> float | None:
    if meter.source == MeterSource.VODOMER_PG:
        return load_last_valid_vodomer_value_before(
            conn,
            meter.identifier,
            cutoff,
            include_cutoff=include_cutoff,
        )
    if meter.source == MeterSource.KALORIMETR_PG:
        return load_last_valid_kalorimetr_energy_before(
            conn,
            meter.identifier,
            cutoff,
            include_cutoff=include_cutoff,
        )
    if meter.source == MeterSource.ELEKTROMER_MS:
        return load_last_valid_elektromer_total_before(
            conn,
            meter.identifier,
            cutoff,
            include_cutoff=include_cutoff,
        )
    raise ValueError(f"Nepodporovany zdroj meridla: {meter.source}")


def build_subject(period: ReportPeriod, spec: SiteReportSpec) -> str:
    return f"Spotřeba {spec.site_label} - {period.month_label}"


def load_last_valid_vodomer_value_before(
    conn,
    identifier: str,
    cutoff: datetime,
    *,
    include_cutoff: bool = False,
) -> float | None:
    cutoff_operator = "<=" if include_cutoff else "<"
    row = conn.execute(
        text(
            f"""
            SELECT objem
            FROM monitoring."Mereni_vodomery_vse"
            WHERE identifikace = :identifier
              AND date {cutoff_operator} :cutoff
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
    return to_rounded_float(row[0]) if row else None


def load_last_valid_kalorimetr_energy_before(
    conn,
    identifier: str,
    cutoff: datetime,
    *,
    include_cutoff: bool = False,
) -> float | None:
    cutoff_operator = "<=" if include_cutoff else "<"
    row = conn.execute(
        text(
            f"""
            SELECT spotreba_energie
            FROM monitoring."Mereni_kalorimetry_vse"
            WHERE identifikace = :identifier
              AND date {cutoff_operator} :cutoff
              AND platne = TRUE
              AND spotreba_energie IS NOT NULL
            ORDER BY date DESC, id DESC
            LIMIT 1
            """
        ),
        {
            "identifier": identifier,
            "cutoff": cutoff,
        },
    ).first()
    return to_rounded_float(row[0]) if row else None


def load_last_valid_elektromer_total_before(
    conn,
    identifier: str,
    cutoff: datetime,
    *,
    include_cutoff: bool = False,
) -> float | None:
    cutoff_operator = "<=" if include_cutoff else "<"
    row = conn.execute(
        text(
            f"""
            SELECT TOP 1 total
            FROM dbo.Mereni_elektromery
            WHERE identifikace = :identifier
              AND date {cutoff_operator} :cutoff
              AND total IS NOT NULL
            ORDER BY date DESC, recid DESC
            """
        ),
        {
            "identifier": identifier,
            "cutoff": cutoff,
        },
    ).first()
    return to_rounded_float(row[0]) if row else None


def to_rounded_float(value: object) -> float | None:
    if value is None:
        return None
    return round(float(value), 3)


def build_html_body(
    period: ReportPeriod,
    summaries: tuple[MeterConsumptionSummary, ...],
    spec: SiteReportSpec,
) -> str:
    row_html = "".join(
        (
            "<tr>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;'>{html.escape(summary.meter_type)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;'>{html.escape(summary.identifier)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{format_value(summary.start_value)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{format_value(summary.end_value)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{format_value(summary.consumption)}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;'>{html.escape(summary.unit)}</td>"
            "</tr>"
        )
        for summary in summaries
    )

    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        f"<h2 style='margin:0 0 12px;'>{html.escape(build_subject(period, spec))}</h2>"
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


def format_value(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}".replace(".", ",")
