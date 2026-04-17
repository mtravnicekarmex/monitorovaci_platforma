from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any

import pandas as pd
from decouple import config

from app.channels.email import send_email_outlook
from app.time_utils import prague_now_naive, prague_today
from moduly.mereni.vodomery.reporting.daily_branch_report import (
    DEFAULT_DAILY_BRANCH_REPORT_RECIPIENTS,
    DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS,
    _build_scheduler_admin_context,
    _format_datetime,
    _format_volume,
    _load_playwright_api,
    _prepare_branch_device_rows,
    _safe_ratio_percent,
)
from moduly.mereni.vodomery.reporting.monthly_branch_report import (
    BranchMonthlyReportSection as BranchWeeklyReportSection,
    _build_pdf_header_template as _build_monthly_pdf_header_template,
    _build_report_email_body as _build_monthly_report_email_body,
    _iter_period_dates,
    _sum_billing_total,
    build_monthly_vodomery_branch_report_html as _build_monthly_vodomery_branch_report_html,
    _build_monthly_branch_chart_svg,
    _compute_normalized_deviation,
)
from services.api.services.vodomery import BRANCH_DASHBOARD_CONFIGS, load_branch_day_overview


DEFAULT_WEEKLY_BRANCH_REPORT_RECIPIENTS = DEFAULT_DAILY_BRANCH_REPORT_RECIPIENTS
DEFAULT_WEEKLY_BRANCH_REPORT_SENDER_ALIAS = DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS


class VodomeryWeeklyBranchReportError(RuntimeError):
    """Raised when the weekly branch report cannot be built or delivered."""


@dataclass(frozen=True)
class WeeklyBranchReportPeriod:
    iso_year: int
    iso_week: int
    period_start: datetime
    period_end: datetime

    @property
    def week_label(self) -> str:
        return f"{self.iso_year}-W{self.iso_week:02d}"

    @property
    def date_range_label(self) -> str:
        period_end_inclusive = self.period_end - timedelta(days=1)
        return f"{self.period_start.strftime('%d.%m.%Y')} - {period_end_inclusive.strftime('%d.%m.%Y')}"

    @property
    def day_count(self) -> int:
        return (self.period_end.date() - self.period_start.date()).days


@dataclass(frozen=True)
class WeeklyBranchReport:
    generated_at: datetime
    period: WeeklyBranchReportPeriod
    branches: tuple[BranchWeeklyReportSection, ...]

    @property
    def total_branch_count(self) -> int:
        return len(self.branches)


def _load_recipients() -> tuple[str, ...]:
    raw_recipients = config(
        "VODOMERY_WEEKLY_BRANCH_REPORT_RECIPIENTS",
        default=config(
            "VODOMERY_DAILY_BRANCH_REPORT_RECIPIENTS",
            default=DEFAULT_WEEKLY_BRANCH_REPORT_RECIPIENTS,
        ),
    )
    recipients = tuple(item.strip() for item in raw_recipients.split(",") if item.strip())
    if not recipients:
        raise VodomeryWeeklyBranchReportError(
            "Neni nastavena promenna VODOMERY_WEEKLY_BRANCH_REPORT_RECIPIENTS."
        )
    return recipients


def _resolve_sender_alias() -> str | None:
    sender_alias = config(
        "VODOMERY_WEEKLY_BRANCH_REPORT_SENDER_ALIAS",
        default=config(
            "VODOMERY_DAILY_BRANCH_REPORT_SENDER_ALIAS",
            default=config("O_EMAIL_UPOZORNENI", default=DEFAULT_WEEKLY_BRANCH_REPORT_SENDER_ALIAS),
        ),
    ).strip()
    return sender_alias or None


def _get_previous_week_period(reference_date: date | None = None) -> WeeklyBranchReportPeriod:
    base_date = reference_date or prague_today()
    current_week_start = base_date - timedelta(days=base_date.weekday())
    previous_week_start = current_week_start - timedelta(days=7)
    iso_year, iso_week, _ = previous_week_start.isocalendar()
    return WeeklyBranchReportPeriod(
        iso_year=iso_year,
        iso_week=iso_week,
        period_start=datetime.combine(previous_week_start, time.min),
        period_end=datetime.combine(current_week_start, time.min),
    )


def build_weekly_vodomery_branch_report(
    *,
    reference_date: date | None = None,
    generated_at: datetime | None = None,
) -> WeeklyBranchReport:
    period = _get_previous_week_period(reference_date)
    resolved_generated_at = generated_at or prague_now_naive()
    admin_context = _build_scheduler_admin_context()
    period_dates = _iter_period_dates(period)

    accumulators: dict[str, dict[str, Any]] = {
        config_item.key: {
            "title": config_item.title,
            "billing_ident": config_item.billing_ident,
            "actual_total": 0.0,
            "expected_total": 0.0,
            "billing_total": 0.0,
            "period_limit": 0.0 if config_item.daily_limit is not None else None,
            "device_map": {},
            "unique_devices": set(),
            "daily_rows": [],
        }
        for config_item in BRANCH_DASHBOARD_CONFIGS
    }

    for target_date in period_dates:
        branch_payload_by_key = {
            str(branch_payload["key"]): branch_payload
            for branch_payload in load_branch_day_overview(admin_context, target_date=target_date)
        }
        for config_item in BRANCH_DASHBOARD_CONFIGS:
            accumulator = accumulators[config_item.key]
            branch_payload = branch_payload_by_key.get(config_item.key)

            actual_total = round(float((branch_payload or {}).get("actual_total", 0.0) or 0.0), 3)
            expected_total = round(float((branch_payload or {}).get("expected_total", 0.0) or 0.0), 3)
            billing_total = _sum_billing_total((branch_payload or {}).get("hourly_rows") or ())
            daily_limit_value = (branch_payload or {}).get("daily_limit")
            if daily_limit_value is None:
                daily_limit_value = config_item.daily_limit

            if accumulator["period_limit"] is not None and daily_limit_value is not None:
                accumulator["period_limit"] = round(float(accumulator["period_limit"]) + float(daily_limit_value), 3)

            accumulator["actual_total"] = round(float(accumulator["actual_total"]) + actual_total, 3)
            accumulator["expected_total"] = round(float(accumulator["expected_total"]) + expected_total, 3)
            accumulator["billing_total"] = round(float(accumulator["billing_total"]) + billing_total, 3)

            active_devices = tuple(
                dict.fromkeys(
                    str(identifier)
                    for identifier in ((branch_payload or {}).get("active_devices") or ())
                    if identifier
                )
            )
            if not active_devices and branch_payload:
                active_devices = tuple(
                    dict.fromkeys(
                        str(row.get("identifikace"))
                        for row in ((branch_payload or {}).get("device_consumption_rows") or ())
                        if row.get("identifikace")
                    )
                )

            for identifier in active_devices:
                accumulator["unique_devices"].add(identifier)
                accumulator["device_map"].setdefault(
                    identifier,
                    {
                        "identifikace": identifier,
                        "spotreba": 0.0,
                        "ocekavana_spotreba": 0.0,
                    },
                )

            device_values: dict[str, float] = {}
            for row in ((branch_payload or {}).get("device_consumption_rows") or ()):
                identifier = str(row.get("identifikace") or "").strip()
                if not identifier:
                    continue
                actual_value = round(float(row.get("spotreba", 0.0) or 0.0), 3)
                expected_value = round(float(row.get("ocekavana_spotreba", 0.0) or 0.0), 3)
                accumulator["unique_devices"].add(identifier)
                device_stats = accumulator["device_map"].setdefault(
                    identifier,
                    {
                        "identifikace": identifier,
                        "spotreba": 0.0,
                        "ocekavana_spotreba": 0.0,
                    },
                )
                device_stats["spotreba"] = round(float(device_stats["spotreba"]) + actual_value, 3)
                device_stats["ocekavana_spotreba"] = round(float(device_stats["ocekavana_spotreba"]) + expected_value, 3)
                device_values[identifier] = actual_value

            accumulator["daily_rows"].append(
                {
                    "date": target_date,
                    "actual_total": actual_total,
                    "expected_total": expected_total,
                    "billing_total": billing_total,
                    "device_values": device_values,
                }
            )

    sections: list[BranchWeeklyReportSection] = []
    for config_item in BRANCH_DASHBOARD_CONFIGS:
        accumulator = accumulators[config_item.key]
        actual_total = round(float(accumulator["actual_total"]), 3)
        expected_total = round(float(accumulator["expected_total"]), 3)
        billing_total = round(float(accumulator["billing_total"]), 3)
        period_limit = (
            round(float(accumulator["period_limit"]), 3) if accumulator["period_limit"] is not None else None
        )
        remaining_to_limit = None if period_limit is None else round(period_limit - actual_total, 3)
        difference_vs_billing = round(actual_total - billing_total, 3)
        actual_vs_billing_percent = _safe_ratio_percent(actual_total, billing_total)

        device_rows_df = pd.DataFrame(accumulator["device_map"].values())
        if not device_rows_df.empty:
            device_rows_df["podil_procent"] = (
                device_rows_df["spotreba"] / actual_total * 100 if actual_total > 0 else 0.0
            )
            device_rows_df["podil_procent"] = pd.to_numeric(
                device_rows_df["podil_procent"],
                errors="coerce",
            ).fillna(0.0).round(1)
        prepared_device_rows = _prepare_branch_device_rows(device_rows_df)

        sections.append(
            BranchWeeklyReportSection(
                key=config_item.key,
                title=str(accumulator["title"]),
                billing_ident=str(accumulator["billing_ident"]),
                actual_total=actual_total,
                expected_total=expected_total,
                period_limit=period_limit,
                remaining_to_limit=remaining_to_limit,
                billing_total=billing_total,
                difference_vs_billing=difference_vs_billing,
                actual_vs_billing_percent=actual_vs_billing_percent,
                device_rows=prepared_device_rows,
                chart_svg=_build_monthly_branch_chart_svg(
                    tuple(accumulator["daily_rows"]),
                    prepared_device_rows,
                    title=str(accumulator["title"]),
                ),
                deviation_per_meter_day=_compute_normalized_deviation(
                    difference_vs_billing,
                    len(accumulator["unique_devices"]),
                    max(period.day_count, 1),
                ),
                deviation_per_meter_hour=_compute_normalized_deviation(
                    difference_vs_billing,
                    len(accumulator["unique_devices"]),
                    max(period.day_count * 24, 1),
                ),
            )
        )

    return WeeklyBranchReport(
        generated_at=resolved_generated_at,
        period=period,
        branches=tuple(sections),
    )


def _build_monthly_compatible_report(report: WeeklyBranchReport) -> SimpleNamespace:
    return SimpleNamespace(
        generated_at=report.generated_at,
        period=SimpleNamespace(date_range_label=report.period.date_range_label),
        branches=report.branches,
    )


def _retitle_monthly_markup(markup: str) -> str:
    return (
        markup
        .replace(
            "Vodoměry | měsíční report fakturačních vodoměrů",
            "Vodoměry | týdenní report fakturačních vodoměrů",
        )
        .replace(
            "Měsíční report<br>fakturačních vodoměrů",
            "Týdenní report<br>fakturačních vodoměrů",
        )
        .replace(
            "Měsíční report fakturačních vodoměrů",
            "Týdenní report fakturačních vodoměrů",
        )
    )


def build_weekly_vodomery_branch_report_html(report: WeeklyBranchReport) -> str:
    monthly_html = _build_monthly_vodomery_branch_report_html(_build_monthly_compatible_report(report))
    return _retitle_monthly_markup(monthly_html)


def _build_pdf_header_template(report: WeeklyBranchReport) -> str:
    monthly_header = _build_monthly_pdf_header_template(_build_monthly_compatible_report(report))
    return _retitle_monthly_markup(monthly_header)


def render_weekly_vodomery_branch_report_pdf(report: WeeklyBranchReport) -> bytes:
    sync_playwright = _load_playwright_api()
    html = build_weekly_vodomery_branch_report_html(report)
    header_template = _build_pdf_header_template(report)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.emulate_media(media="screen")
            return page.pdf(
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template=header_template,
                footer_template="<div></div>",
                margin={"top": "38mm", "right": "8mm", "bottom": "10mm", "left": "8mm"},
            )
        finally:
            browser.close()


def _build_report_subject(report: WeeklyBranchReport) -> str:
    return f"Vodomery | tydenni report fakturacnich vodomeru | {report.period.date_range_label}"


def _build_report_pdf_filename(report: WeeklyBranchReport) -> str:
    end_date_inclusive = report.period.period_end - timedelta(days=1)
    return (
        f"vodomery_vetve_tyden_{report.period.period_start:%Y%m%d}_{end_date_inclusive:%Y%m%d}.pdf"
    )


def _build_report_email_body(report: WeeklyBranchReport, pdf_filename: str) -> str:
    monthly_body = _build_monthly_report_email_body(_build_monthly_compatible_report(report), pdf_filename)
    return (
        monthly_body
        .replace("Měsíční report fakturačních vodoměrů", "Týdenní report fakturačních vodoměrů")
        .replace("měsíční PDF report", "týdenní PDF report")
        .replace("denním grafem za celé období", "denním grafem za minulý týden")
    )


def send_weekly_vodomery_branch_report(
    *,
    reference_date: date | None = None,
    recipients: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_recipients = recipients or _load_recipients()
    report = build_weekly_vodomery_branch_report(reference_date=reference_date)
    pdf_bytes = render_weekly_vodomery_branch_report_pdf(report)
    pdf_filename = _build_report_pdf_filename(report)
    subject = _build_report_subject(report)
    body = _build_report_email_body(report, pdf_filename)
    sender_alias = _resolve_sender_alias()

    for recipient in resolved_recipients:
        send_email_outlook(
            email_receiver=recipient,
            subject=subject,
            body=body,
            sender_alias=sender_alias,
            is_html=True,
            attachments=[(pdf_filename, pdf_bytes, "application", "pdf")],
        )

    return {
        "title": subject,
        "recipient_count": len(resolved_recipients),
        "recipients": resolved_recipients,
        "period": report.period.week_label,
        "date_range": report.period.date_range_label,
        "branch_count": report.total_branch_count,
        "pdf_filename": pdf_filename,
        "pdf_size_bytes": len(pdf_bytes),
    }
