from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from html import escape
from io import StringIO
from typing import Any

import pandas as pd
from decouple import config

from app.channels.email import send_email_outlook
from app.time_utils import prague_now_naive, prague_today
from moduly.mereni.vodomery.reporting._email_config import (
    filter_placeholder_recipients,
    load_report_recipients,
    sanitize_sender_alias,
)
from moduly.mereni.vodomery.reporting.daily_branch_report import (
    BILLING_CURVE_COLOR,
    BranchDeviceReportRow,
    DEFAULT_DAILY_BRANCH_REPORT_RECIPIENTS,
    DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS,
    _armex_logo_path,
    _build_device_table_html,
    _build_metric_card_html,
    _build_scheduler_admin_context,
    _format_datetime,
    _format_number,
    _format_percent,
    _format_percent_delta,
    _format_volume,
    _load_image_data_uri,
    _load_playwright_api,
    _prediction_delta_percent,
    _prepare_branch_device_rows,
    _safe_ratio_percent,
)
from services.api.services.vodomery import BRANCH_DASHBOARD_CONFIGS, load_branch_day_overview


DEFAULT_MONTHLY_BRANCH_REPORT_RECIPIENTS = DEFAULT_DAILY_BRANCH_REPORT_RECIPIENTS
DEFAULT_MONTHLY_BRANCH_REPORT_SENDER_ALIAS = DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS


class VodomeryMonthlyBranchReportError(RuntimeError):
    """Raised when the monthly branch report cannot be built or delivered."""


@dataclass(frozen=True)
class MonthlyBranchReportPeriod:
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
        return f"{self.period_start.strftime('%d.%m.%Y')} - {period_end_inclusive.strftime('%d.%m.%Y')}"

    @property
    def day_count(self) -> int:
        return (self.period_end.date() - self.period_start.date()).days


@dataclass(frozen=True)
class BranchMonthlyReportSection:
    key: str
    title: str
    billing_ident: str
    actual_total: float
    expected_total: float
    period_limit: float | None
    remaining_to_limit: float | None
    billing_total: float | None
    difference_vs_billing: float | None
    actual_vs_billing_percent: float | None
    device_rows: tuple[BranchDeviceReportRow, ...]
    chart_svg: str
    deviation_per_meter_day: float | None
    deviation_per_meter_hour: float | None


@dataclass(frozen=True)
class MonthlyBranchReport:
    generated_at: datetime
    period: MonthlyBranchReportPeriod
    branches: tuple[BranchMonthlyReportSection, ...]

    @property
    def total_branch_count(self) -> int:
        return len(self.branches)


def _load_recipients() -> tuple[str, ...]:
    return load_report_recipients(
        "VODOMERY_MONTHLY_BRANCH_REPORT_RECIPIENTS",
        default=DEFAULT_MONTHLY_BRANCH_REPORT_RECIPIENTS,
        error_cls=VodomeryMonthlyBranchReportError,
    )


def _resolve_sender_alias() -> str | None:
    return sanitize_sender_alias(
        config(
            "VODOMERY_MONTHLY_BRANCH_REPORT_SENDER_ALIAS",
            default=config(
                "VODOMERY_DAILY_BRANCH_REPORT_SENDER_ALIAS",
                default=config("O_EMAIL_UPOZORNENI", default=DEFAULT_MONTHLY_BRANCH_REPORT_SENDER_ALIAS),
            ),
        ),
        context_label="VODOMERY_MONTHLY_BRANCH_REPORT_SENDER_ALIAS",
    )


def _get_previous_month_period(reference_date: date | None = None) -> MonthlyBranchReportPeriod:
    base_date = reference_date or prague_today()
    current_month_start = base_date.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return MonthlyBranchReportPeriod(
        year=previous_month_start.year,
        month=previous_month_start.month,
        period_start=datetime.combine(previous_month_start, time.min),
        period_end=datetime.combine(current_month_start, time.min),
    )


def _iter_period_dates(period: MonthlyBranchReportPeriod) -> tuple[date, ...]:
    dates: list[date] = []
    current_date = period.period_start.date()
    while current_date < period.period_end.date():
        dates.append(current_date)
        current_date += timedelta(days=1)
    return tuple(dates)


def _sum_billing_total(hourly_rows: list[dict[str, object]] | tuple[dict[str, object], ...]) -> float:
    if not hourly_rows:
        return 0.0
    hourly_df = pd.DataFrame(hourly_rows)
    if hourly_df.empty or "fakturacni_spotreba" not in hourly_df.columns:
        return 0.0
    return round(float(pd.to_numeric(hourly_df["fakturacni_spotreba"], errors="coerce").fillna(0.0).sum()), 3)


def _compute_normalized_deviation(
    difference_vs_billing: float | None,
    device_count: int,
    time_units: int,
) -> float | None:
    if difference_vs_billing is None or device_count <= 0 or time_units <= 0:
        return None
    return round(float(difference_vs_billing) / float(device_count) / float(time_units), 3)


def _build_monthly_branch_chart_svg(
    daily_rows: tuple[dict[str, object], ...],
    device_rows: tuple[BranchDeviceReportRow, ...],
    *,
    title: str,
) -> str:
    if not daily_rows:
        return "<div class='chart-empty'>Pro zvolené období nejsou k dispozici denní data pro vykreslení grafu.</div>"

    x_dates = [pd.Timestamp(row["date"]) for row in daily_rows]
    expected_values = [round(float(row.get("expected_total", 0.0) or 0.0), 3) for row in daily_rows]
    actual_totals = [round(float(row.get("actual_total", 0.0) or 0.0), 3) for row in daily_rows]
    billing_values = [round(float(row.get("billing_total", 0.0) or 0.0), 3) for row in daily_rows]

    chart_width = 930
    chart_height = 212
    margin_left = 48
    margin_right = 18
    margin_top = 12
    margin_bottom = 30
    plot_width = chart_width - margin_left - margin_right
    plot_height = chart_height - margin_top - margin_bottom
    y_max = max(actual_totals + expected_values + billing_values + [0.1]) * 1.12
    if y_max <= 0:
        y_max = 1.0

    def scale_x(position_index: int) -> float:
        if len(x_dates) == 1:
            return margin_left + plot_width / 2
        return margin_left + (plot_width * position_index / (len(x_dates) - 1))

    def scale_y(value: float) -> float:
        return margin_top + plot_height - (float(value) / y_max * plot_height)

    grid_lines = []
    axis_labels = []
    for tick_index in range(5):
        tick_value = y_max * tick_index / 4
        y = scale_y(tick_value)
        grid_lines.append(
            f"<line x1='{margin_left:.1f}' y1='{y:.1f}' x2='{chart_width - margin_right:.1f}' y2='{y:.1f}' "
            "stroke='#e2e8f0' stroke-width='1' />"
        )
        axis_labels.append(
            f"<text x='{margin_left - 8:.1f}' y='{y + 4:.1f}' text-anchor='end' class='chart-axis-label'>"
            f"{escape(_format_number(tick_value, digits=1))}</text>"
        )

    area_paths: list[str] = []
    cumulative_lower = [0.0] * len(x_dates)
    for row in device_rows:
        if row.spotreba <= 0:
            continue
        series_values = [
            round(float((daily_rows[index].get("device_values") or {}).get(row.identifikace, 0.0) or 0.0), 3)
            for index in range(len(daily_rows))
        ]
        upper = [lower + value for lower, value in zip(cumulative_lower, series_values)]
        top_points = " ".join(
            f"{scale_x(index):.1f},{scale_y(value):.1f}"
            for index, value in enumerate(upper)
        )
        bottom_points = " ".join(
            f"{scale_x(index):.1f},{scale_y(value):.1f}"
            for index, value in reversed(list(enumerate(cumulative_lower)))
        )
        area_paths.append(
            f"<polygon points='{top_points} {bottom_points}' fill='{row.color_hex}' fill-opacity='0.82' stroke='none' />"
        )
        cumulative_lower = upper

    expected_path = " ".join(
        f"{scale_x(index):.1f},{scale_y(value):.1f}"
        for index, value in enumerate(expected_values)
    )
    billing_path = " ".join(
        f"{scale_x(index):.1f},{scale_y(value):.1f}"
        for index, value in enumerate(billing_values)
    )

    x_labels = []
    label_step = max(1, len(x_dates) // 6)
    for index, timestamp in enumerate(x_dates):
        if len(x_dates) <= 8 or index in {0, len(x_dates) - 1} or index % label_step == 0:
            x = scale_x(index)
            x_labels.append(
                f"<text x='{x:.1f}' y='{chart_height - 12:.1f}' text-anchor='middle' class='chart-axis-label'>"
                f"{timestamp.strftime('%d.%m.')}</text>"
            )

    svg = StringIO()
    svg.write("<div class='branch-chart'>")
    svg.write(
        f"<svg viewBox='0 0 {chart_width} {chart_height}' role='img' aria-label='Měsíční graf spotřeby větve {escape(title)}'>"
    )
    svg.write(f"<rect x='0' y='0' width='{chart_width}' height='{chart_height}' rx='18' fill='#ffffff' />")
    for line in grid_lines:
        svg.write(line)
    svg.write(
        f"<line x1='{margin_left:.1f}' y1='{margin_top + plot_height:.1f}' x2='{chart_width - margin_right:.1f}' y2='{margin_top + plot_height:.1f}' stroke='#94a3b8' stroke-width='1.2' />"
    )
    svg.write(
        f"<line x1='{margin_left:.1f}' y1='{margin_top:.1f}' x2='{margin_left:.1f}' y2='{margin_top + plot_height:.1f}' stroke='#94a3b8' stroke-width='1.2' />"
    )
    for label in axis_labels:
        svg.write(label)
    for polygon in area_paths:
        svg.write(polygon)
    if expected_path:
        svg.write(
            f"<polyline points='{expected_path}' fill='none' stroke='#cbd5e1' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round' />"
        )
    if billing_path:
        svg.write(
            f"<polyline points='{billing_path}' fill='none' stroke='{BILLING_CURVE_COLOR}' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round' />"
        )
    for label in x_labels:
        svg.write(label)
    svg.write("</svg>")
    svg.write(
        "<div class='chart-line-legend'>"
        f"<span class='chart-line-legend-item'><span class='chart-line-legend-dot' style='background:{BILLING_CURVE_COLOR};'></span>SČVK</span>"
        "<span class='chart-line-legend-item'><span class='chart-line-legend-dot' style='background:#cbd5e1;'></span>Predikce</span>"
        "</div>"
    )
    svg.write("</div>")
    return svg.getvalue()


def build_monthly_vodomery_branch_report(
    *,
    reference_date: date | None = None,
    generated_at: datetime | None = None,
) -> MonthlyBranchReport:
    period = _get_previous_month_period(reference_date)
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

    sections: list[BranchMonthlyReportSection] = []
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
            BranchMonthlyReportSection(
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

    return MonthlyBranchReport(
        generated_at=resolved_generated_at,
        period=period,
        branches=tuple(sections),
    )


def _build_branch_section_html(section: BranchMonthlyReportSection, *, is_first: bool) -> str:
    main_value = _format_volume(section.difference_vs_billing, signed=True)
    main_detail = (
        f"{_format_volume(section.actual_total)} vs. {_format_volume(section.billing_total)} | "
        f"Pokrytí {_format_percent(section.actual_vs_billing_percent)}"
        if section.billing_total is not None
        else f"{_format_volume(section.actual_total)} vs. -"
    )
    section_class = "branch-section branch-section-first" if is_first else "branch-section"
    return (
        f"<section class='{section_class}'>"
        "<div class='branch-header'>"
        f"<div class='branch-title-block'><div class='branch-eyebrow'>Větev</div><h2>{escape(section.title)}</h2>"
        f"<div class='branch-meta'>Fakturační vodoměr: <strong>{escape(section.billing_ident)}</strong></div></div>"
        f"<div class='branch-summary-card'>{_build_metric_card_html('Součet spotřeby vs. fakturační vodoměr', main_value, main_detail, primary=True)}</div>"
        "</div>"
        "<div class='metric-grid'>"
        f"{_build_metric_card_html('Predikce období', _format_volume(section.expected_total), _format_percent_delta(_prediction_delta_percent(section.actual_total, section.expected_total)))}"
        f"{_build_metric_card_html('Součet spotřeby', _format_volume(section.actual_total))}"
        f"{_build_metric_card_html('SPOTŘEBA SČVK', _format_volume(section.billing_total))}"
        "</div>"
        "<div class='branch-chart-wrap'>"
        f"{section.chart_svg}"
        "</div>"
        "<div class='branch-table-wrap'>"
        f"{_build_device_table_html(section.device_rows)}"
        "</div>"
        "<div class='branch-deviation-wrap'>"
        "<div class='branch-subtitle'>Odchylky</div>"
        "<div class='branch-deviation-grid'>"
        f"{_build_metric_card_html('Na 1 vodoměr / den', _format_volume(section.deviation_per_meter_day, signed=True))}"
        f"{_build_metric_card_html('Na 1 vodoměr / hodinu', _format_volume(section.deviation_per_meter_hour, signed=True))}"
        "</div>"
        "</div>"
        "</section>"
    )


def build_monthly_vodomery_branch_report_html(report: MonthlyBranchReport) -> str:
    branch_sections_html = "".join(
        _build_branch_section_html(section, is_first=index == 0)
        for index, section in enumerate(report.branches)
    )

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Vodoměry | měsíční report fakturačních vodoměrů</title>
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
      display: none;
    }}
    .report-content {{
      margin-top: 0;
    }}
    .title-eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #64748b;
      font-size: 10px;
      margin-bottom: 4px;
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
    .branch-section {{
      break-before: page;
      break-inside: avoid-page;
      page-break-inside: avoid;
      padding-top: 11mm;
    }}
    .branch-section-first {{
      break-before: auto;
      padding-top: 11mm;
    }}
    .branch-header {{
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(300px, 0.8fr);
      gap: 8px;
      align-items: stretch;
      margin-bottom: 8px;
    }}
    .branch-title-block {{
      padding: 4px 0;
    }}
    .branch-summary-card {{
      align-self: end;
      margin-top: 7mm;
    }}
    .branch-eyebrow {{
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: #64748b;
      font-size: 10px;
      margin-bottom: 3px;
    }}
    .branch-header h2 {{
      margin: 0;
      font-size: 20px;
      color: #0f4c81;
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
    .branch-summary-card .metric-card {{
      height: 100%;
      box-sizing: border-box;
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
    .metric-card-alert {{
      background: linear-gradient(180deg, #fff1f2 0%, #ffe4e6 100%);
      border-color: #fca5a5;
      color: #7f1d1d;
      box-shadow: 0 6px 16px rgba(220, 38, 38, 0.12);
    }}
    .metric-card-alert .metric-label {{
      color: #991b1b;
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
    .metric-card-alert .metric-value {{
      color: #991b1b;
    }}
    .metric-detail {{
      margin-top: 4px;
      color: #52606d;
      font-size: 9px;
    }}
    .metric-card-primary .metric-detail {{
      color: rgba(255,255,255,0.85);
    }}
    .metric-card-alert .metric-detail {{
      color: #991b1b;
    }}
    .branch-chart-wrap, .branch-table-wrap, .branch-deviation-wrap {{
      border: 1px solid #d8e1eb;
      border-radius: 10px;
      background: #ffffff;
      padding: 6px 8px 7px;
      box-shadow: 0 3px 12px rgba(15, 76, 129, 0.05);
      break-inside: avoid-page;
      page-break-inside: avoid;
    }}
    .branch-chart-wrap {{
      margin-bottom: 8px;
    }}
    .branch-table-wrap {{
      margin-bottom: 8px;
    }}
    .branch-subtitle {{
      margin-bottom: 6px;
      font-size: 10px;
      font-weight: 700;
      color: #0f4c81;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .branch-deviation-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
    }}
    .branch-chart svg {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .chart-line-legend {{
      display: flex;
      align-items: center;
      gap: 14px;
      margin-top: 6px;
      color: #52606d;
      font-size: 9px;
    }}
    .chart-line-legend-item {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}
    .chart-line-legend-dot {{
      width: 8px;
      height: 8px;
      border-radius: 999px;
      display: inline-block;
      flex: 0 0 auto;
    }}
    .chart-axis-label {{
      fill: #64748b;
      font-size: 9.5px;
      font-family: "Segoe UI", Arial, sans-serif;
    }}
    .chart-empty, .empty-state {{
      padding: 8px 0;
      color: #64748b;
    }}
    .branch-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 9px;
      line-height: 1.2;
    }}
    .branch-table thead th {{
      text-align: left;
      padding: 5px 6px;
      background: #0f4c81;
      color: #ffffff;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      font-size: 7.6px;
    }}
    .branch-table thead th.numeric {{
      text-align: right;
    }}
    .branch-table tbody td {{
      padding: 4px 6px;
      border-bottom: 1px solid #e5e7eb;
      vertical-align: middle;
    }}
    .branch-table tbody tr:nth-child(even) {{
      background: #f8fafc;
    }}
    .branch-table tbody tr:last-child td {{
      border-bottom: none;
    }}
    .numeric {{
      text-align: right;
      white-space: nowrap;
    }}
    .row-ident {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }}
    .row-swatch {{
      width: 8px;
      height: 8px;
      border-radius: 999px;
      display: inline-block;
      flex: 0 0 auto;
    }}
  </style>
</head>
<body>
  <header class="page-header">
    <div>
      <div class="title-eyebrow">Monitoring platforma</div>
      <h1>Měsíční report fakturačních vodoměrů</h1>
    </div>
    <div class="page-logo">
      <img src="" alt="ARMEX">
    </div>
    <div class="page-meta">
      <strong>Období reportu:</strong> {escape(report.period.date_range_label)}
    </div>
  </header>

  <main class="report-content">
    {branch_sections_html}
  </main>
</body>
</html>"""


def _build_pdf_header_template(report: MonthlyBranchReport) -> str:
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
          <div class="pdf-header-title">Měsíční report<br>fakturačních vodoměrů</div>
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


def render_monthly_vodomery_branch_report_pdf(report: MonthlyBranchReport) -> bytes:
    sync_playwright = _load_playwright_api()
    html = build_monthly_vodomery_branch_report_html(report)
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


def _build_report_subject(report: MonthlyBranchReport) -> str:
    return f"Vodomery | mesicni report fakturacnich vodomeru | {report.period.month:02d}.{report.period.year}"


def _build_report_pdf_filename(report: MonthlyBranchReport) -> str:
    return f"vodomery_vetve_mesic_{report.period.year}{report.period.month:02d}.pdf"


def _build_report_email_body(report: MonthlyBranchReport, pdf_filename: str) -> str:
    summary_rows = "".join(
        (
            "<tr>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;'><strong>{escape(branch.title)}</strong></td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_volume(branch.actual_total))}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_volume(branch.billing_total))}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_volume(branch.difference_vs_billing, signed=True))}</td>"
            "</tr>"
        )
        for branch in report.branches
    )
    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        "<h2 style='margin:0 0 12px;'>Měsíční report fakturačních vodoměrů</h2>"
        "<p style='margin:0 0 12px;'>"
        "V příloze je měsíční PDF report s přehledem spotřeby jednotlivých větví, porovnáním "
        "součtu podružných vodoměrů s fakturačním vodoměrem a denním grafem za celé období."
        "</p>"
        f"<p style='margin:0 0 16px;'><strong>Období:</strong> {escape(report.period.date_range_label)}<br>"
        f"<strong>Vygenerováno:</strong> {escape(_format_datetime(report.generated_at))}<br>"
        f"<strong>Soubor:</strong> {escape(pdf_filename)}</p>"
        "<table style='border-collapse:collapse;font-size:14px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Větev</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Součet spotřeby</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Fakturační vodoměr</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Rozdíl</th>"
        "</tr>"
        f"{summary_rows}"
        "</table>"
        "</body></html>"
    )


def send_monthly_vodomery_branch_report(
    *,
    reference_date: date | None = None,
    recipients: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    period = _get_previous_month_period(reference_date)
    resolved_recipients = filter_placeholder_recipients(
        recipients if recipients is not None else _load_recipients(),
        context_label="send_monthly_vodomery_branch_report",
    )
    if not resolved_recipients:
        return {
            "title": f"Vodomery | mesicni report fakturacnich vodomeru | {period.month:02d}.{period.year}",
            "recipient_count": 0,
            "recipients": (),
            "period": period.month_label,
            "branch_count": 0,
            "pdf_filename": f"vodomery_vetve_mesic_{period.year}{period.month:02d}.pdf",
            "pdf_size_bytes": 0,
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }
    report = build_monthly_vodomery_branch_report(reference_date=reference_date)
    pdf_bytes = render_monthly_vodomery_branch_report_pdf(report)
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
        "period": report.period.month_label,
        "branch_count": report.total_branch_count,
        "pdf_filename": pdf_filename,
        "pdf_size_bytes": len(pdf_bytes),
    }
