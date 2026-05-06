from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from html import escape
from math import isfinite
from typing import Any

import pandas as pd
from decouple import config

from app.channels.email import send_email_outlook
from app.time_utils import prague_now_naive, prague_today
from moduly.mereni.vodomery.SCVK.cena_vody import cena_vody
from moduly.mereni.vodomery.SCVK.stocne import cena_stocne, stocne_odberna_mista, stocne_scvk
from moduly.mereni.vodomery.reporting._email_config import (
    filter_placeholder_recipients,
    load_report_recipients,
    sanitize_sender_alias,
)
from moduly.mereni.vodomery.reporting.daily_branch_report import (
    DEFAULT_DAILY_BRANCH_REPORT_RECIPIENTS,
    DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS,
    _armex_logo_path,
    _build_metric_card_html,
    _format_datetime,
    _format_percent,
    _format_volume,
    _load_image_data_uri,
    _load_playwright_api,
    build_daily_branch_report,
)
from moduly.mereni.vodomery.reporting.monthly_branch_report import build_monthly_vodomery_branch_report
from moduly.mereni.vodomery.reporting.weekly_branch_report import build_weekly_vodomery_branch_report


class VodomeryBillingSummaryReportError(RuntimeError):
    """Raised when the periodic SČVK billing summary report cannot be built or delivered."""


@dataclass(frozen=True)
class BillingSummaryReportPeriod:
    kind: str
    title_label: str
    period_start: datetime
    period_end: datetime

    @property
    def date_range_label(self) -> str:
        period_end_inclusive = self.period_end - timedelta(days=1)
        if self.period_start.date() == period_end_inclusive.date():
            return self.period_start.strftime("%d.%m.%Y")
        return f"{self.period_start.strftime('%d.%m.%Y')} - {period_end_inclusive.strftime('%d.%m.%Y')}"

    @property
    def start_date(self) -> date:
        return self.period_start.date()

    @property
    def end_date(self) -> date:
        return (self.period_end - timedelta(days=1)).date()


@dataclass(frozen=True)
class BillingSummaryBillingRow:
    branch_title: str
    billing_ident: str
    start_value: float | None
    end_value: float | None
    consumption: float
    share_percent: float | None
    adjusted_consumption: float | None
    price_amount: float | None
    sewerage_price_amount: float | None
    total_price_amount: float | None
    baseline_total_price_amount: float | None
    difference_amount: float | None


@dataclass(frozen=True)
class BillingSummarySubmeterRow:
    branch_title: str
    billing_ident: str
    identifikace: str
    start_value: float | None
    end_value: float | None
    consumption: float
    share_percent: float | None
    adjusted_consumption: float | None
    price_amount: float | None
    sewerage_price_amount: float | None
    total_price_amount: float | None
    baseline_total_price_amount: float | None
    difference_amount: float | None


@dataclass(frozen=True)
class BillingSummaryReport:
    generated_at: datetime
    period: BillingSummaryReportPeriod
    water_price_per_m3: float
    sewerage_price_per_m3: float
    billing_rows: tuple[BillingSummaryBillingRow, ...]
    submeter_rows: tuple[BillingSummarySubmeterRow, ...]
    total_billing_consumption: float
    total_submeter_consumption: float
    total_difference: float
    coverage_percent: float | None
    total_billing_price: float | None
    total_billing_sewerage_price: float | None
    total_billing_total_price: float | None
    total_submeter_baseline_price: float | None
    total_submeter_baseline_sewerage_price: float | None
    total_submeter_baseline_total_price: float | None
    total_adjusted_submeter_consumption: float | None
    total_adjusted_submeter_price: float | None
    total_adjusted_submeter_sewerage_price: float | None
    total_adjusted_submeter_total_price: float | None
    total_submeter_difference_amount: float | None


def _round_optional_float(value: object, *, digits: int = 3) -> float | None:
    if value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric_value):
        return None
    return round(numeric_value, digits)


def _format_currency(value: object) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value) or not isfinite(numeric_value):
        return "-"
    if abs(numeric_value) < 0.005:
        numeric_value = 0.0
    return f"{numeric_value:.2f} Kč"


def _safe_ratio_percent(numerator: object, denominator: object) -> float | None:
    try:
        numerator_value = float(numerator)
        denominator_value = float(denominator)
    except (TypeError, ValueError):
        return None
    if pd.isna(numerator_value) or pd.isna(denominator_value) or denominator_value <= 0:
        return None
    return round(numerator_value / denominator_value * 100, 1)


def _format_currency_delta(value: object) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value) or not isfinite(numeric_value):
        return "-"
    if abs(numeric_value) < 0.005:
        numeric_value = 0.0
    return f"{numeric_value:+.2f} Kč"


def _allocate_weighted_total(
    total: float,
    weights: tuple[float, ...],
    *,
    digits: int,
) -> tuple[float, ...]:
    if not weights:
        return ()

    normalized_weights = tuple(max(float(weight or 0.0), 0.0) for weight in weights)
    total_weight = sum(normalized_weights)
    if total_weight <= 0:
        return tuple(0.0 for _ in normalized_weights)

    rounded_values = [
        round(float(total) * weight / total_weight, digits)
        for weight in normalized_weights
    ]
    adjustment_index = max(
        index
        for index, weight in enumerate(normalized_weights)
        if weight > 0
    )
    rounded_values[adjustment_index] = round(
        rounded_values[adjustment_index] + round(float(total) - sum(rounded_values), digits),
        digits,
    )
    return tuple(rounded_values)


def _get_daily_period(target_date: date | None = None) -> BillingSummaryReportPeriod:
    resolved_target_date = target_date or (prague_today() - timedelta(days=1))
    period_start = datetime.combine(resolved_target_date, time.min)
    return BillingSummaryReportPeriod(
        kind="day",
        title_label="Denní",
        period_start=period_start,
        period_end=period_start + timedelta(days=1),
    )


def _get_previous_week_period(reference_date: date | None = None) -> BillingSummaryReportPeriod:
    base_date = reference_date or prague_today()
    current_week_start = base_date - timedelta(days=base_date.weekday())
    previous_week_start = current_week_start - timedelta(days=7)
    return BillingSummaryReportPeriod(
        kind="week",
        title_label="Týdenní",
        period_start=datetime.combine(previous_week_start, time.min),
        period_end=datetime.combine(current_week_start, time.min),
    )


def _get_previous_month_period(reference_date: date | None = None) -> BillingSummaryReportPeriod:
    base_date = reference_date or prague_today()
    current_month_start = base_date.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return BillingSummaryReportPeriod(
        kind="month",
        title_label="Měsíční",
        period_start=datetime.combine(previous_month_start, time.min),
        period_end=datetime.combine(current_month_start, time.min),
    )


def _load_daily_recipients() -> tuple[str, ...]:
    return load_report_recipients(
        "VODOMERY_DAILY_BILLING_SUMMARY_REPORT_RECIPIENTS",
        default=DEFAULT_DAILY_BRANCH_REPORT_RECIPIENTS,
        fallback_env_keys=("VODOMERY_DAILY_BRANCH_REPORT_RECIPIENTS",),
        error_cls=VodomeryBillingSummaryReportError,
    )


def _load_weekly_recipients() -> tuple[str, ...]:
    return load_report_recipients(
        "VODOMERY_WEEKLY_BILLING_SUMMARY_REPORT_RECIPIENTS",
        fallback_env_keys=("VODOMERY_WEEKLY_BRANCH_REPORT_RECIPIENTS",),
        error_cls=VodomeryBillingSummaryReportError,
    )


def _load_monthly_recipients() -> tuple[str, ...]:
    return load_report_recipients(
        "VODOMERY_MONTHLY_BILLING_SUMMARY_REPORT_RECIPIENTS",
        fallback_env_keys=("VODOMERY_MONTHLY_BRANCH_REPORT_RECIPIENTS",),
        error_cls=VodomeryBillingSummaryReportError,
    )


def _resolve_daily_sender_alias() -> str | None:
    return sanitize_sender_alias(
        config(
            "VODOMERY_DAILY_BILLING_SUMMARY_REPORT_SENDER_ALIAS",
            default=config(
                "VODOMERY_DAILY_BRANCH_REPORT_SENDER_ALIAS",
                default=config("O_EMAIL_UPOZORNENI", default=DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS),
            ),
        ),
        context_label="VODOMERY_DAILY_BILLING_SUMMARY_REPORT_SENDER_ALIAS",
    )


def _resolve_weekly_sender_alias() -> str | None:
    return sanitize_sender_alias(
        config(
            "VODOMERY_WEEKLY_BILLING_SUMMARY_REPORT_SENDER_ALIAS",
            default=config(
                "VODOMERY_WEEKLY_BRANCH_REPORT_SENDER_ALIAS",
                default=config(
                    "VODOMERY_DAILY_BRANCH_REPORT_SENDER_ALIAS",
                    default=config("O_EMAIL_UPOZORNENI", default=DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS),
                ),
            ),
        ),
        context_label="VODOMERY_WEEKLY_BILLING_SUMMARY_REPORT_SENDER_ALIAS",
    )


def _resolve_monthly_sender_alias() -> str | None:
    return sanitize_sender_alias(
        config(
            "VODOMERY_MONTHLY_BILLING_SUMMARY_REPORT_SENDER_ALIAS",
            default=config(
                "VODOMERY_MONTHLY_BRANCH_REPORT_SENDER_ALIAS",
                default=config(
                    "VODOMERY_DAILY_BRANCH_REPORT_SENDER_ALIAS",
                    default=config("O_EMAIL_UPOZORNENI", default=DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS),
                ),
            ),
        ),
        context_label="VODOMERY_MONTHLY_BILLING_SUMMARY_REPORT_SENDER_ALIAS",
    )


def _load_branch_sections_for_period(period: BillingSummaryReportPeriod) -> tuple[Any, ...]:
    if period.kind == "day":
        return build_daily_branch_report(
            target_date=period.start_date,
            generated_at=period.period_end,
        ).branches
    if period.kind == "week":
        return build_weekly_vodomery_branch_report(
            reference_date=period.period_end.date(),
            generated_at=period.period_end,
        ).branches
    if period.kind == "month":
        return build_monthly_vodomery_branch_report(
            reference_date=period.period_end.date(),
            generated_at=period.period_end,
        ).branches
    raise VodomeryBillingSummaryReportError(f"Nepodporovany typ obdobi: {period.kind}")


def build_periodic_vodomery_billing_summary_report(
    period: BillingSummaryReportPeriod,
    *,
    generated_at: datetime | None = None,
) -> BillingSummaryReport:
    branch_sections = _load_branch_sections_for_period(period)
    water_price_per_m3 = round(float(cena_vody), 2)
    sewerage_price_per_m3 = round(float(cena_stocne), 2)

    billing_rows = tuple(
        BillingSummaryBillingRow(
            branch_title=str(getattr(section, "title", "-")),
            billing_ident=str(getattr(section, "billing_ident", "-")),
            start_value=_round_optional_float(getattr(getattr(section, "billing_row", None), "start_value", None)),
            end_value=_round_optional_float(getattr(getattr(section, "billing_row", None), "end_value", None)),
            consumption=round(
                float(
                    getattr(getattr(section, "billing_row", None), "spotreba", None)
                    or getattr(section, "billing_total", 0.0)
                    or 0.0
                ),
                3,
            ),
            share_percent=None,
            adjusted_consumption=None,
            price_amount=None,
            sewerage_price_amount=None,
            total_price_amount=None,
            baseline_total_price_amount=None,
            difference_amount=None,
        )
        for section in branch_sections
    )
    submeter_rows = tuple(
        BillingSummarySubmeterRow(
            branch_title=str(getattr(section, "title", "-")),
            billing_ident=str(getattr(section, "billing_ident", "-")),
            identifikace=str(getattr(row, "identifikace", "-")),
            start_value=_round_optional_float(getattr(row, "start_value", None)),
            end_value=_round_optional_float(getattr(row, "end_value", None)),
            consumption=round(float(getattr(row, "spotreba", 0.0) or 0.0), 3),
            share_percent=None,
            adjusted_consumption=None,
            price_amount=None,
            sewerage_price_amount=None,
            total_price_amount=None,
            baseline_total_price_amount=None,
            difference_amount=None,
        )
        for section in branch_sections
        for row in tuple(getattr(section, "device_rows", ()) or ())
    )
    total_billing_consumption = round(sum(row.consumption for row in billing_rows), 3)
    total_submeter_consumption = round(sum(row.consumption for row in submeter_rows), 3)
    total_difference = round(total_billing_consumption - total_submeter_consumption, 3)
    coverage_percent = _safe_ratio_percent(total_submeter_consumption, total_billing_consumption)
    billing_rows = tuple(
        BillingSummaryBillingRow(
            branch_title=row.branch_title,
            billing_ident=row.billing_ident,
            start_value=row.start_value,
            end_value=row.end_value,
            consumption=row.consumption,
            share_percent=_safe_ratio_percent(row.consumption, total_billing_consumption),
            adjusted_consumption=row.consumption,
            price_amount=round(row.consumption * water_price_per_m3, 2),
            sewerage_price_amount=(
                round(row.consumption * sewerage_price_per_m3, 2)
                if row.billing_ident in stocne_scvk
                else 0.0
            ),
            total_price_amount=round(
                (round(row.consumption * water_price_per_m3, 2))
                + (
                    round(row.consumption * sewerage_price_per_m3, 2)
                    if row.billing_ident in stocne_scvk
                    else 0.0
                ),
                2,
            ),
            baseline_total_price_amount=round(
                (round(row.consumption * water_price_per_m3, 2))
                + (
                    round(row.consumption * sewerage_price_per_m3, 2)
                    if row.billing_ident in stocne_scvk
                    else 0.0
                ),
                2,
            ),
            difference_amount=0.0,
        )
        for row in billing_rows
    )
    total_billing_price = round(sum(row.price_amount or 0.0 for row in billing_rows), 2)
    total_billing_sewerage_price = round(sum(row.sewerage_price_amount or 0.0 for row in billing_rows), 2)
    total_billing_total_price = round(sum(row.total_price_amount or 0.0 for row in billing_rows), 2)
    adjusted_consumption_differences = _allocate_weighted_total(
        total_difference,
        tuple(row.consumption for row in submeter_rows),
        digits=3,
    )
    submeter_rows = tuple(
        BillingSummarySubmeterRow(
            branch_title=row.branch_title,
            billing_ident=row.billing_ident,
            identifikace=row.identifikace,
            start_value=row.start_value,
            end_value=row.end_value,
            consumption=row.consumption,
            share_percent=_safe_ratio_percent(row.consumption, total_submeter_consumption),
            adjusted_consumption=round(row.consumption + adjusted_consumption_difference, 3),
            price_amount=round(round(row.consumption + adjusted_consumption_difference, 3) * water_price_per_m3, 2),
            sewerage_price_amount=(
                round(round(row.consumption + adjusted_consumption_difference, 3) * sewerage_price_per_m3, 2)
                if row.identifikace in stocne_odberna_mista
                else 0.0
            ),
            total_price_amount=round(
                (round(round(row.consumption + adjusted_consumption_difference, 3) * water_price_per_m3, 2))
                + (
                    round(round(row.consumption + adjusted_consumption_difference, 3) * sewerage_price_per_m3, 2)
                    if row.identifikace in stocne_odberna_mista
                    else 0.0
                ),
                2,
            ),
            baseline_total_price_amount=round(
                (round(row.consumption * water_price_per_m3, 2))
                + (
                    round(row.consumption * sewerage_price_per_m3, 2)
                    if row.identifikace in stocne_odberna_mista
                    else 0.0
                ),
                2,
            ),
            difference_amount=None,
        )
        for row, adjusted_consumption_difference in zip(submeter_rows, adjusted_consumption_differences)
    )
    submeter_rows = tuple(
        BillingSummarySubmeterRow(
            branch_title=row.branch_title,
            billing_ident=row.billing_ident,
            identifikace=row.identifikace,
            start_value=row.start_value,
            end_value=row.end_value,
            consumption=row.consumption,
            share_percent=row.share_percent,
            adjusted_consumption=row.adjusted_consumption,
            price_amount=row.price_amount,
            sewerage_price_amount=row.sewerage_price_amount,
            total_price_amount=row.total_price_amount,
            baseline_total_price_amount=row.baseline_total_price_amount,
            difference_amount=round((row.total_price_amount or 0.0) - (row.baseline_total_price_amount or 0.0), 2),
        )
        for row in submeter_rows
    )
    total_submeter_baseline_price = round(
        sum(round(row.consumption * water_price_per_m3, 2) for row in submeter_rows),
        2,
    )
    total_submeter_baseline_sewerage_price = round(
        sum(
            round(row.consumption * sewerage_price_per_m3, 2)
            if row.identifikace in stocne_odberna_mista
            else 0.0
            for row in submeter_rows
        ),
        2,
    )
    total_submeter_baseline_total_price = round(sum(row.baseline_total_price_amount or 0.0 for row in submeter_rows), 2)
    total_adjusted_submeter_consumption = round(sum(row.adjusted_consumption or 0.0 for row in submeter_rows), 3)
    total_adjusted_submeter_price = round(sum(row.price_amount or 0.0 for row in submeter_rows), 2)
    total_adjusted_submeter_sewerage_price = round(sum(row.sewerage_price_amount or 0.0 for row in submeter_rows), 2)
    total_adjusted_submeter_total_price = round(sum(row.total_price_amount or 0.0 for row in submeter_rows), 2)
    total_submeter_difference_amount = round(sum(row.difference_amount or 0.0 for row in submeter_rows), 2)

    return BillingSummaryReport(
        generated_at=generated_at or prague_now_naive(),
        period=period,
        water_price_per_m3=water_price_per_m3,
        sewerage_price_per_m3=sewerage_price_per_m3,
        billing_rows=billing_rows,
        submeter_rows=submeter_rows,
        total_billing_consumption=total_billing_consumption,
        total_submeter_consumption=total_submeter_consumption,
        total_difference=total_difference,
        coverage_percent=coverage_percent,
        total_billing_price=total_billing_price,
        total_billing_sewerage_price=total_billing_sewerage_price,
        total_billing_total_price=total_billing_total_price,
        total_submeter_baseline_price=total_submeter_baseline_price,
        total_submeter_baseline_sewerage_price=total_submeter_baseline_sewerage_price,
        total_submeter_baseline_total_price=total_submeter_baseline_total_price,
        total_adjusted_submeter_consumption=total_adjusted_submeter_consumption,
        total_adjusted_submeter_price=total_adjusted_submeter_price,
        total_adjusted_submeter_sewerage_price=total_adjusted_submeter_sewerage_price,
        total_adjusted_submeter_total_price=total_adjusted_submeter_total_price,
        total_submeter_difference_amount=total_submeter_difference_amount,
    )


def build_daily_vodomery_billing_summary_report(
    *,
    target_date: date | None = None,
    generated_at: datetime | None = None,
) -> BillingSummaryReport:
    return build_periodic_vodomery_billing_summary_report(
        _get_daily_period(target_date),
        generated_at=generated_at,
    )


def build_weekly_vodomery_billing_summary_report(
    *,
    reference_date: date | None = None,
    generated_at: datetime | None = None,
) -> BillingSummaryReport:
    return build_periodic_vodomery_billing_summary_report(
        _get_previous_week_period(reference_date),
        generated_at=generated_at,
    )


def build_monthly_vodomery_billing_summary_report(
    *,
    reference_date: date | None = None,
    generated_at: datetime | None = None,
) -> BillingSummaryReport:
    return build_periodic_vodomery_billing_summary_report(
        _get_previous_month_period(reference_date),
        generated_at=generated_at,
    )


def _build_billing_rows_html(report: BillingSummaryReport) -> str:
    rows_html = "".join(
        (
            "<tr>"
            f"<td class='column-device'>{escape(row.billing_ident)}</td>"
            f"<td class='numeric'>{escape(_format_volume(row.consumption))}</td>"
            f"<td class='numeric'>{escape(_format_percent(row.share_percent))}</td>"
            f"<td class='numeric'>{escape(_format_volume(row.adjusted_consumption))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.price_amount))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.sewerage_price_amount))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.total_price_amount))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.baseline_total_price_amount))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.difference_amount))}</td>"
            "</tr>"
        )
        for row in report.billing_rows
    )
    total_row_html = (
        "<tr class='balance-total-row'>"
        "<td><strong>Celkem</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_volume(report.total_billing_consumption))}</strong></td>"
        "<td class='numeric'><strong>100.0 %</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_volume(report.total_billing_consumption))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_currency(report.total_billing_price))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_currency(report.total_billing_sewerage_price))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_currency(report.total_billing_total_price))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_currency(report.total_billing_total_price))}</strong></td>"
        "<td class='numeric'><strong>0.00 Kč</strong></td>"
        "</tr>"
    )
    return (
        "<table class='branch-table'>"
        "<thead><tr>"
        "<th class='column-device'>Odběrné místo</th>"
        "<th class='numeric'>Spotřeba</th>"
        "<th class='numeric'>Podíl</th>"
        "<th class='numeric'>Upravená spotřeba</th>"
        "<th class='numeric'>Cena vody</th>"
        "<th class='numeric'>Cena stočné</th>"
        "<th class='numeric'>Cena celkem</th>"
        "<th class='numeric'>Cena bez odchylky</th>"
        "<th class='numeric'>Rozdíl</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}{total_row_html}</tbody>"
        "</table>"
    )


def _build_submeter_rows_html(report: BillingSummaryReport) -> str:
    rows_html = "".join(
        (
            "<tr>"
            f"<td class='column-device'>{escape(row.identifikace)}</td>"
            f"<td class='numeric'>{escape(_format_volume(row.consumption))}</td>"
            f"<td class='numeric'>{escape(_format_percent(row.share_percent))}</td>"
            f"<td class='numeric'>{escape(_format_volume(row.adjusted_consumption))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.price_amount))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.sewerage_price_amount))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.total_price_amount))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.baseline_total_price_amount))}</td>"
            f"<td class='numeric'>{escape(_format_currency(row.difference_amount))}</td>"
            "</tr>"
        )
        for row in report.submeter_rows
    )
    total_row_html = (
        "<tr class='balance-total-row'>"
        "<td><strong>Celkem</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_volume(report.total_submeter_consumption))}</strong></td>"
        "<td class='numeric'><strong>100.0 %</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_volume(report.total_adjusted_submeter_consumption))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_currency(report.total_adjusted_submeter_price))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_currency(report.total_adjusted_submeter_sewerage_price))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_currency(report.total_adjusted_submeter_total_price))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_currency(report.total_submeter_baseline_total_price))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_currency(report.total_submeter_difference_amount))}</strong></td>"
        "</tr>"
    )
    return (
        "<table class='branch-table'>"
        "<thead><tr>"
        "<th class='column-device'>Odběrné místo</th>"
        "<th class='numeric'>Spotřeba</th>"
        "<th class='numeric'>Podíl</th>"
        "<th class='numeric'>Upravená spotřeba</th>"
        "<th class='numeric'>Cena vody</th>"
        "<th class='numeric'>Cena stočné</th>"
        "<th class='numeric'>Cena celkem</th>"
        "<th class='numeric'>Cena bez odchylky</th>"
        "<th class='numeric'>Rozdíl</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}{total_row_html}</tbody>"
        "</table>"
    )


def _build_balance_section_html(report: BillingSummaryReport) -> str:
    total_price_difference = None
    if report.total_billing_total_price is not None and report.total_submeter_baseline_total_price is not None:
        total_price_difference = round(report.total_billing_total_price - report.total_submeter_baseline_total_price, 2)
    displayed_total_difference = None if report.total_difference is None else round(-report.total_difference, 3)
    displayed_price_difference = None if total_price_difference is None else round(-total_price_difference, 2)

    return (
        "<section class='balance-section'>"
        "<div class='balance-hero'>"
        "<div class='balance-title-block'>"
        "<div class='title-eyebrow'>Souhrn reportu</div>"
        f"<h2>{escape(report.period.title_label)} report SČVK vs. odběrná místa</h2>"
        f"<div class='branch-meta'><strong>Období reportu:</strong> {escape(report.period.date_range_label)}</div>"
        "<div class='balance-description'>"
        "Souhrn je sestaven přímo z existujících periodických reportů větví. "
        "První tabulka obsahuje všechny fakturační vodoměry SČVK a druhá všechny "
        "podřazené vodoměry převzaté z jednotlivých větví. U odběrných míst se navíc "
        "dopočítává upravená spotřeba z rozdílu mezi součtem odběrných míst a součtem SČVK vodoměrů."
        "</div>"
        "</div>"
        "<div class='balance-summary-card'>"
        f"{_build_metric_card_html('Celková bilance podružných vs. SČVK', _format_volume(displayed_total_difference, signed=True), f'Odběrná místa {_format_volume(report.total_submeter_consumption)} vs. SČVK {_format_volume(report.total_billing_consumption)} | Pokrytí {_format_percent(report.coverage_percent)}\nRozdíl cen {_format_currency_delta(displayed_price_difference)}', primary=True)}"
        "</div>"
        "</div>"
        "<div class='metric-grid balance-metric-grid'>"
        f"{_build_metric_card_html('Součet odběrných míst', _format_volume(report.total_submeter_consumption))}"
        f"{_build_metric_card_html('Součet spotřeby SČVK vodoměrů', _format_volume(report.total_billing_consumption))}"
        f"{_build_metric_card_html('Cena vody', _format_currency(report.water_price_per_m3).replace(' Kč', ' Kč/m³'))}"
        f"{_build_metric_card_html('Cena stočné', _format_currency(report.sewerage_price_per_m3).replace(' Kč', ' Kč/m³'))}"
        "</div>"
        "</section>"
    )


def build_vodomery_billing_summary_report_html(report: BillingSummaryReport) -> str:
    armex_logo_data_uri = _load_image_data_uri(_armex_logo_path())
    balance_section_html = _build_balance_section_html(report)
    billing_table_html = _build_billing_rows_html(report)
    submeter_table_html = _build_submeter_rows_html(report)

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Vodoměry | {escape(report.period.title_label.lower())} report SČVK vs. odběrná místa</title>
  <style>
    @page {{
      size: A4;
      margin: 10mm 8mm 10mm;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      color: #16202a;
      background: #ffffff;
      font-size: 10.2px;
      line-height: 1.35;
    }}
    .page-header {{
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) auto minmax(180px, 1fr);
      align-items: center;
      gap: 14px;
      padding: 0 0 10px;
      border-bottom: 1.5px solid #0f4c81;
      margin-bottom: 10px;
    }}
    .page-header h1 {{
      margin: 0;
      font-size: 24px;
      color: #0f4c81;
      line-height: 1.08;
    }}
    .page-logo {{
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 52px;
    }}
    .page-logo img {{
      display: block;
      max-width: 160px;
      max-height: 42px;
      width: auto;
      height: auto;
    }}
    .page-meta {{
      text-align: right;
      color: #52606d;
      font-size: 11px;
    }}
    .report-content {{
      margin-top: 0;
    }}
    .balance-section {{
      padding-top: 2px;
      margin-bottom: 8px;
    }}
    .balance-hero {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(300px, 0.85fr);
      gap: 8px;
      align-items: stretch;
      margin-bottom: 8px;
    }}
    .balance-title-block {{
      padding: 4px 0;
    }}
    .balance-title-block h2 {{
      margin: 0;
      font-size: 20px;
      color: #0f4c81;
    }}
    .balance-description {{
      margin-top: 6px;
      color: #52606d;
      max-width: 680px;
    }}
    .balance-summary-card .metric-card {{
      height: 100%;
      box-sizing: border-box;
    }}
    .balance-summary-card .metric-detail {{
      white-space: pre-line;
    }}
    .balance-metric-grid {{
      grid-template-columns: repeat(4, 1fr);
      margin-bottom: 8px;
    }}
    .title-eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #64748b;
      font-size: 10px;
      margin-bottom: 4px;
    }}
    .branch-meta {{
      margin-top: 3px;
      color: #52606d;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-bottom: 8px;
    }}
    .metric-card {{
      border: 1px solid #d8e1eb;
      border-radius: 12px;
      background: linear-gradient(180deg, #ffffff 0%, #f8fbfd 100%);
      padding: 8px 10px;
      box-shadow: 0 4px 14px rgba(15, 76, 129, 0.06);
    }}
    .metric-card-primary {{
      grid-column: span 2;
      background: linear-gradient(135deg, #0f4c81 0%, #1d6fa5 100%);
      border-color: #0f4c81;
      color: #ffffff;
      box-shadow: 0 8px 20px rgba(15, 76, 129, 0.16);
    }}
    .metric-label {{
      font-size: 8px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #6b7280;
      margin-bottom: 4px;
    }}
    .metric-card-primary .metric-label {{
      color: rgba(255,255,255,0.8);
    }}
    .metric-value {{
      font-size: 16px;
      font-weight: 700;
      line-height: 1.2;
      color: #111827;
    }}
    .metric-card-primary .metric-value {{
      color: #ffffff;
    }}
    .metric-detail {{
      margin-top: 4px;
      color: #52606d;
      font-size: 9px;
    }}
    .metric-card-primary .metric-detail {{
      color: rgba(255,255,255,0.85);
    }}
    .report-section {{
      margin-bottom: 8px;
    }}
    .branch-table-wrap {{
      border: 1px solid #d8e1eb;
      border-radius: 10px;
      background: #ffffff;
      padding: 6px 8px 7px;
      box-shadow: 0 3px 12px rgba(15, 76, 129, 0.05);
      margin-bottom: 8px;
      break-inside: auto;
      page-break-inside: auto;
    }}
    .branch-subtitle {{
      margin-bottom: 6px;
      font-size: 10px;
      font-weight: 700;
      color: #0f4c81;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .branch-note {{
      margin-top: 6px;
      color: #52606d;
      font-size: 9px;
    }}
    .branch-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 9.2px;
    }}
    .branch-table th,
    .branch-table td {{
      border: 1px solid #d8e1eb;
      padding: 6px 7px;
      vertical-align: top;
    }}
    .branch-table .column-device {{
      width: 104px;
      max-width: 104px;
    }}
    .branch-table th {{
      background: #f8fbfd;
      color: #0f4c81;
      text-align: left;
    }}
    .branch-table td.numeric,
    .branch-table th.numeric {{
      text-align: right;
      white-space: nowrap;
    }}
    .balance-total-row td {{
      background: #eef5fb;
    }}
  </style>
</head>
<body>
  <header class="page-header">
    <div>
      <div class="title-eyebrow">Monitoring platforma</div>
      <h1>{escape(report.period.title_label)} report SČVK vs. odběrná místa</h1>
    </div>
    <div class="page-logo">
      <img src="{armex_logo_data_uri}" alt="ARMEX">
    </div>
    <div class="page-meta">
      <strong>Období reportu:</strong> {escape(report.period.date_range_label)}
    </div>
  </header>
  <main class="report-content">
    {balance_section_html}
    <section class="report-section">
      <div class="branch-table-wrap">
        <div class="branch-subtitle">Souhrn spotřeby SČVK vodoměrů</div>
        {billing_table_html}
        <div class="branch-note">
          Podíl v tabulce SČVK vodoměrů je počítán vůči součtu spotřeby všech SČVK vodoměrů.
          Upravená spotřeba je u SČVK vodoměrů shodná se spotřebou. Cena vody a cena stočné jsou
          proto počítány z téže spotřeby, cena bez odchylky je shodná s cenou celkem a rozdíl je nulový.
        </div>
      </div>
    </section>
    <section class="report-section">
      <div class="branch-table-wrap">
        <div class="branch-subtitle">Souhrn spotřeby odběrných míst</div>
        {submeter_table_html}
        <div class="branch-note">
          Podíl v tabulce odběrných míst je počítán vůči součtu spotřeby všech odběrných míst.
          Upravená spotřeba vzniká přičtením podílu odběrného místa z rozdílu mezi součtem odběrných míst
          a součtem SČVK vodoměrů. Cena vody a cena stočné jsou počítány z upravené spotřeby, cena bez
          odchylky z původní spotřeby a rozdíl je dán jako cena celkem mínus cena bez odchylky.
        </div>
      </div>
    </section>
  </main>
</body>
</html>"""


def _build_pdf_header_template(report: BillingSummaryReport) -> str:
    armex_logo_data_uri = _load_image_data_uri(_armex_logo_path())
    return f"""
    <style>
      .pdf-header {{
        width: 100%;
        box-sizing: border-box;
        padding: 0 8mm 0;
        font-family: "Segoe UI", Arial, sans-serif;
        color: #16202a;
      }}
      .pdf-header-table {{
        width: 100%;
        border-collapse: collapse;
      }}
      .pdf-header-table td {{
        vertical-align: middle;
      }}
      .pdf-header-left {{
        width: 38%;
      }}
      .pdf-header-center {{
        width: 28%;
        text-align: center;
      }}
      .pdf-header-right {{
        width: 34%;
        text-align: right;
      }}
      .pdf-header-eyebrow {{
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #64748b;
        font-size: 8px;
        margin-bottom: 2px;
      }}
      .pdf-header-title {{
        margin: 0;
        font-size: 18px;
        line-height: 1.0;
        color: #0f4c81;
        font-weight: 700;
      }}
      .pdf-header-logo {{
        display: block;
        margin: 0 auto;
        max-width: 140px;
        max-height: 30px;
        width: auto;
        height: auto;
      }}
      .pdf-header-meta {{
        color: #52606d;
        font-size: 9px;
        white-space: nowrap;
      }}
      .pdf-header-rule {{
        margin-top: 1.5mm;
        border-bottom: 1.5px solid #0f4c81;
      }}
    </style>
    <div class="pdf-header">
      <table class="pdf-header-table" role="presentation">
        <tr>
          <td class="pdf-header-left">
            <div>
              <div class="pdf-header-eyebrow">Monitoring platforma</div>
              <div class="pdf-header-title">{escape(report.period.title_label)} report<br>SČVK vs. odběrná místa</div>
            </div>
          </td>
          <td class="pdf-header-center">
            <img class="pdf-header-logo" src="{armex_logo_data_uri}" alt="ARMEX">
          </td>
          <td class="pdf-header-right">
            <div class="pdf-header-meta">
              <strong>Období reportu:</strong> {escape(report.period.date_range_label)}
            </div>
          </td>
        </tr>
      </table>
      <div class="pdf-header-rule"></div>
    </div>
    """


def render_vodomery_billing_summary_report_pdf(report: BillingSummaryReport) -> bytes:
    sync_playwright = _load_playwright_api()
    html = build_vodomery_billing_summary_report_html(report)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.emulate_media(media="screen")
            return page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "10mm", "right": "8mm", "bottom": "10mm", "left": "8mm"},
            )
        finally:
            browser.close()


def _build_report_subject(report: BillingSummaryReport) -> str:
    if report.period.kind == "day":
        return f"Vodomery | denni souhrn SCVK vs odberna mista | {report.period.date_range_label}"
    if report.period.kind == "week":
        return f"Vodomery | tydenni souhrn SCVK vs odberna mista | {report.period.date_range_label}"
    return f"Vodomery | mesicni souhrn SCVK vs odberna mista | {report.period.period_start:%m.%Y}"


def _build_report_pdf_filename(report: BillingSummaryReport) -> str:
    if report.period.kind == "day":
        return f"Denni souhrn SCVK vodomeru - {report.period.date_range_label}.pdf"
    if report.period.kind == "week":
        return f"Tydenni souhrn SCVK vodomeru - {report.period.date_range_label}.pdf"
    return f"Mesicni souhrn SCVK vodomeru - {report.period.period_start:%m.%Y}.pdf"


def _build_report_email_body(report: BillingSummaryReport, pdf_filename: str) -> str:
    report_label = report.period.title_label
    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        f"<h2 style='margin:0 0 12px;'>{escape(report_label)} report SČVK vs. odběrná místa</h2>"
        "<p style='margin:0 0 12px;'>"
        "V příloze je PDF report se souhrnem všech fakturačních SČVK vodoměrů a všech "
        "podřazených vodoměrů převzatých z periodických reportů jednotlivých větví."
        "</p>"
        f"<p style='margin:0 0 16px;'><strong>Období reportu:</strong> {escape(report.period.date_range_label)}<br>"
        f"<strong>Vygenerováno:</strong> {escape(_format_datetime(report.generated_at))}<br>"
        f"<strong>Cena vody:</strong> {escape(_format_currency(report.water_price_per_m3).replace(' Kč', ' Kč/m³'))}<br>"
        f"<strong>Cena stočné:</strong> {escape(_format_currency(report.sewerage_price_per_m3).replace(' Kč', ' Kč/m³'))}<br>"
        f"<strong>Soubor:</strong> {escape(pdf_filename)}</p>"
        "<table style='border-collapse:collapse;font-size:14px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Kategorie</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Spotřeba</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Cena celkem</th>"
        "</tr>"
        "<tr>"
        "<td style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;'><strong>SČVK vodoměry</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_volume(report.total_billing_consumption))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_currency(report.total_billing_total_price))}</td>"
        "</tr>"
        "<tr>"
        "<td style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;'><strong>Odběrná místa bez odchylky</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_volume(report.total_submeter_consumption))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_currency(report.total_submeter_baseline_total_price))}</td>"
        "</tr>"
        "<tr>"
        "<td style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;'><strong>Odběrná místa upravená</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_volume(report.total_adjusted_submeter_consumption))}</td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_currency(report.total_adjusted_submeter_total_price))}</td>"
        "</tr>"
        "<tr>"
        "<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;'><strong>Rozdíl</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;text-align:right;'><strong>{escape(_format_volume(report.total_difference, signed=True))}</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;text-align:right;'><strong>{escape(_format_currency(report.total_submeter_difference_amount))}</strong></td>"
        "</tr>"
        "</table>"
        "</body></html>"
    )


def send_daily_vodomery_billing_summary_report(
    *,
    target_date: date | None = None,
    recipients: tuple[str, ...] | None = None,
) -> dict[str, object]:
    period = _get_daily_period(target_date)
    resolved_recipients = filter_placeholder_recipients(
        recipients if recipients is not None else _load_daily_recipients(),
        context_label="send_daily_vodomery_billing_summary_report",
    )
    if not resolved_recipients:
        return {
            "title": f"Vodomery | denni souhrn SCVK vs odberna mista | {period.date_range_label}",
            "recipient_count": 0,
            "recipients": (),
            "period": period.date_range_label,
            "pdf_filename": f"Denni souhrn SCVK vodomeru - {period.date_range_label}.pdf",
            "pdf_size_bytes": 0,
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }
    report = build_daily_vodomery_billing_summary_report(target_date=target_date)
    pdf_bytes = render_vodomery_billing_summary_report_pdf(report)
    pdf_filename = _build_report_pdf_filename(report)
    subject = _build_report_subject(report)
    body = _build_report_email_body(report, pdf_filename)
    sender_alias = _resolve_daily_sender_alias()

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
        "period": report.period.date_range_label,
        "pdf_filename": pdf_filename,
        "pdf_size_bytes": len(pdf_bytes),
    }


def send_weekly_vodomery_billing_summary_report(
    *,
    reference_date: date | None = None,
    recipients: tuple[str, ...] | None = None,
) -> dict[str, object]:
    period = _get_previous_week_period(reference_date)
    resolved_recipients = filter_placeholder_recipients(
        recipients if recipients is not None else _load_weekly_recipients(),
        context_label="send_weekly_vodomery_billing_summary_report",
    )
    if not resolved_recipients:
        return {
            "title": f"Vodomery | tydenni souhrn SCVK vs odberna mista | {period.date_range_label}",
            "recipient_count": 0,
            "recipients": (),
            "period": period.date_range_label,
            "pdf_filename": f"Tydenni souhrn SCVK vodomeru - {period.date_range_label}.pdf",
            "pdf_size_bytes": 0,
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }
    report = build_weekly_vodomery_billing_summary_report(reference_date=reference_date)
    pdf_bytes = render_vodomery_billing_summary_report_pdf(report)
    pdf_filename = _build_report_pdf_filename(report)
    subject = _build_report_subject(report)
    body = _build_report_email_body(report, pdf_filename)
    sender_alias = _resolve_weekly_sender_alias()

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
        "period": report.period.date_range_label,
        "pdf_filename": pdf_filename,
        "pdf_size_bytes": len(pdf_bytes),
    }


def send_monthly_vodomery_billing_summary_report(
    *,
    reference_date: date | None = None,
    recipients: tuple[str, ...] | None = None,
) -> dict[str, object]:
    period = _get_previous_month_period(reference_date)
    resolved_recipients = filter_placeholder_recipients(
        recipients if recipients is not None else _load_monthly_recipients(),
        context_label="send_monthly_vodomery_billing_summary_report",
    )
    if not resolved_recipients:
        return {
            "title": f"Vodomery | mesicni souhrn SCVK vs odberna mista | {period.period_start:%m.%Y}",
            "recipient_count": 0,
            "recipients": (),
            "period": period.date_range_label,
            "pdf_filename": f"Mesicni souhrn SCVK vodomeru - {period.period_start:%m.%Y}.pdf",
            "pdf_size_bytes": 0,
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }
    report = build_monthly_vodomery_billing_summary_report(reference_date=reference_date)
    pdf_bytes = render_vodomery_billing_summary_report_pdf(report)
    pdf_filename = _build_report_pdf_filename(report)
    subject = _build_report_subject(report)
    body = _build_report_email_body(report, pdf_filename)
    sender_alias = _resolve_monthly_sender_alias()

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
        "period": report.period.date_range_label,
        "pdf_filename": pdf_filename,
        "pdf_size_bytes": len(pdf_bytes),
    }
