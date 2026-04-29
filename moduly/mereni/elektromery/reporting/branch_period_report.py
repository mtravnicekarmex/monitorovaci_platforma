from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from html import escape
from io import StringIO
from math import isfinite
import mimetypes
from pathlib import Path
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
from services.api.services.elektromery import load_branch_period_overview


DEFAULT_BRANCH_REPORT_RECIPIENTS = "ops@example.com"
DEFAULT_BRANCH_REPORT_SENDER_ALIAS = "upozorneni@example.com"
LEGACY_DAILY_RECIPIENT_ENV = "ELEKTROMERY_DAILY_BRANCH_REPORT_RECIPIENTS"
LEGACY_DAILY_SENDER_ENV = "ELEKTROMERY_DAILY_BRANCH_REPORT_SENDER_ALIAS"
PALETTE = (
    "#4c78a8",
    "#f58518",
    "#e45756",
    "#72b7b2",
    "#54a24b",
    "#eeca3b",
    "#b279a2",
    "#ff9da6",
    "#9d755d",
    "#bab0ac",
)


class ElektromeryBranchReportError(RuntimeError):
    """Raised when an electrometer branch report cannot be built or delivered."""


@dataclass(frozen=True)
class BranchReportPeriod:
    kind: str
    title_prefix: str
    file_prefix: str
    period_start: datetime
    period_end: datetime
    label: str

    @property
    def date_range_label(self) -> str:
        period_end_inclusive = self.period_end - timedelta(days=1)
        return f"{self.period_start.strftime('%d.%m.%Y')} - {period_end_inclusive.strftime('%d.%m.%Y')}"

    @property
    def day_count(self) -> int:
        return (self.period_end.date() - self.period_start.date()).days


@dataclass(frozen=True)
class BranchDeviceReportRow:
    identifikace: str
    start_value: float | None
    end_value: float | None
    spotreba: float
    spotreba_vt: float | None
    spotreba_nt: float | None
    podil_procent: float | None
    active_days: int
    color_hex: str


@dataclass(frozen=True)
class BranchPeriodReportSection:
    key: str
    title: str
    actual_total: float
    vt_total: float | None
    nt_total: float | None
    last_actual_timestamp: datetime | None
    device_rows: tuple[BranchDeviceReportRow, ...]
    daily_rows: tuple[dict[str, object], ...]
    chart_svg: str


@dataclass(frozen=True)
class BranchPeriodReport:
    generated_at: datetime
    period: BranchReportPeriod
    branches: tuple[BranchPeriodReportSection, ...]

    @property
    def total_branch_count(self) -> int:
        return len(self.branches)


def _get_previous_week_period(reference_date: date | None = None) -> BranchReportPeriod:
    base_date = reference_date or prague_today()
    current_week_start = base_date - timedelta(days=base_date.weekday())
    previous_week_start = current_week_start - timedelta(days=7)
    iso_year, iso_week, _ = previous_week_start.isocalendar()
    return BranchReportPeriod(
        kind="weekly",
        title_prefix="Týdenní",
        file_prefix="Tydenni",
        period_start=datetime.combine(previous_week_start, time.min),
        period_end=datetime.combine(current_week_start, time.min),
        label=f"{iso_year}-W{iso_week:02d}",
    )


def _get_previous_month_period(reference_date: date | None = None) -> BranchReportPeriod:
    base_date = reference_date or prague_today()
    current_month_start = base_date.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    return BranchReportPeriod(
        kind="monthly",
        title_prefix="Měsíční",
        file_prefix="Mesicni",
        period_start=datetime.combine(previous_month_start, time.min),
        period_end=datetime.combine(current_month_start, time.min),
        label=f"{previous_month_start.month:02d}/{previous_month_start.year}",
    )


def _load_weekly_recipients() -> tuple[str, ...]:
    return load_report_recipients(
        "ELEKTROMERY_WEEKLY_BRANCH_REPORT_RECIPIENTS",
        default=DEFAULT_BRANCH_REPORT_RECIPIENTS,
        fallback_env_keys=(LEGACY_DAILY_RECIPIENT_ENV,),
        error_cls=ElektromeryBranchReportError,
    )


def _load_monthly_recipients() -> tuple[str, ...]:
    return load_report_recipients(
        "ELEKTROMERY_MONTHLY_BRANCH_REPORT_RECIPIENTS",
        default=DEFAULT_BRANCH_REPORT_RECIPIENTS,
        fallback_env_keys=(LEGACY_DAILY_RECIPIENT_ENV,),
        error_cls=ElektromeryBranchReportError,
    )


def _resolve_weekly_sender_alias() -> str | None:
    return sanitize_sender_alias(
        config(
            "ELEKTROMERY_WEEKLY_BRANCH_REPORT_SENDER_ALIAS",
            default=config(
                LEGACY_DAILY_SENDER_ENV,
                default=config("O_EMAIL_UPOZORNENI", default=DEFAULT_BRANCH_REPORT_SENDER_ALIAS),
            ),
        ),
        context_label="ELEKTROMERY_WEEKLY_BRANCH_REPORT_SENDER_ALIAS",
    )


def _resolve_monthly_sender_alias() -> str | None:
    return sanitize_sender_alias(
        config(
            "ELEKTROMERY_MONTHLY_BRANCH_REPORT_SENDER_ALIAS",
            default=config(
                LEGACY_DAILY_SENDER_ENV,
                default=config("O_EMAIL_UPOZORNENI", default=DEFAULT_BRANCH_REPORT_SENDER_ALIAS),
            ),
        ),
        context_label="ELEKTROMERY_MONTHLY_BRANCH_REPORT_SENDER_ALIAS",
    )


def _load_playwright_api():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ElektromeryBranchReportError(
            "Playwright je vyzadovan pro render PDF reportu elektromeru."
        ) from exc
    return sync_playwright


def _format_energy(value: object, *, signed: bool = False) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value):
        return "-"
    if abs(numeric_value) < 0.0005:
        numeric_value = 0.0
    format_spec = "+.3f" if signed else ".3f"
    return f"{numeric_value:{format_spec}} kWh"


def _format_number(value: object, *, digits: int = 3) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value):
        return "-"
    if abs(numeric_value) < 0.0005:
        numeric_value = 0.0
    return f"{numeric_value:.{digits}f}"


def _format_percent(value: object, *, digits: int = 1) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value) or not isfinite(numeric_value):
        return "-"
    if abs(numeric_value) < 0.05:
        numeric_value = 0.0
    return f"{numeric_value:.{digits}f} %"


def _format_datetime(value: datetime | None) -> str:
    return "-" if value is None else value.strftime("%d.%m.%Y %H:%M")


def _sum_energy_column(values: tuple[object, ...]) -> float:
    total = 0.0
    for value in values:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        if pd.isna(numeric_value) or not isfinite(numeric_value):
            continue
        total += numeric_value
    return round(total, 3)


def _load_image_data_uri(image_path: Path) -> str:
    if not image_path.exists():
        raise ElektromeryBranchReportError(f"Logo file was not found: {image_path}")
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _armex_logo_path() -> Path:
    return Path.cwd() / "data" / "ARMEX" / "logo_ARMEX.png"


def _prepare_branch_device_rows(device_consumption_df: pd.DataFrame) -> tuple[BranchDeviceReportRow, ...]:
    if device_consumption_df.empty:
        return ()

    rows = device_consumption_df.copy()
    for column in ("start_value", "end_value", "spotreba", "spotreba_vt", "spotreba_nt", "podil_procent", "active_days"):
        if column not in rows.columns:
            rows[column] = 0 if column == "active_days" else 0.0
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    rows["spotreba"] = rows["spotreba"].fillna(0.0)
    rows["podil_procent"] = rows["podil_procent"].fillna(0.0)
    rows["active_days"] = rows["active_days"].fillna(0)
    rows = rows.sort_values(["spotreba", "identifikace"], ascending=[False, True]).reset_index(drop=True)

    prepared_rows: list[BranchDeviceReportRow] = []
    for index, row in enumerate(rows.itertuples(index=False)):
        prepared_rows.append(
            BranchDeviceReportRow(
                identifikace=str(row.identifikace),
                start_value=None if pd.isna(row.start_value) else round(float(row.start_value), 3),
                end_value=None if pd.isna(row.end_value) else round(float(row.end_value), 3),
                spotreba=round(float(row.spotreba), 3),
                spotreba_vt=None if pd.isna(row.spotreba_vt) else round(float(row.spotreba_vt), 3),
                spotreba_nt=None if pd.isna(row.spotreba_nt) else round(float(row.spotreba_nt), 3),
                podil_procent=round(float(row.podil_procent), 1),
                active_days=int(row.active_days),
                color_hex=PALETTE[index % len(PALETTE)],
            )
        )
    return tuple(prepared_rows)


def _build_branch_chart_svg(
    daily_rows: tuple[dict[str, object], ...],
    device_rows: tuple[BranchDeviceReportRow, ...],
    *,
    title: str,
) -> str:
    if not daily_rows:
        return "<div class='chart-empty'>Pro zvolené období nejsou k dispozici denní data pro vykreslení grafu.</div>"

    x_dates = [pd.Timestamp(row["date"]) for row in daily_rows]
    actual_totals = [round(float(row.get("actual_total", 0.0) or 0.0), 3) for row in daily_rows]
    chart_width = 930
    chart_height = 212
    margin_left = 48
    margin_right = 18
    margin_top = 12
    margin_bottom = 30
    plot_width = chart_width - margin_left - margin_right
    plot_height = chart_height - margin_top - margin_bottom
    y_max = max(actual_totals + [0.1]) * 1.12
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
        f"<svg viewBox='0 0 {chart_width} {chart_height}' role='img' aria-label='Graf spotřeby větve {escape(title)}'>"
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
    for label in x_labels:
        svg.write(label)
    svg.write("</svg>")
    svg.write("</div>")
    return svg.getvalue()


def _build_report(period: BranchReportPeriod, *, generated_at: datetime | None = None) -> BranchPeriodReport:
    resolved_generated_at = generated_at or prague_now_naive()
    raw_branches = load_branch_period_overview(
        period_start=period.period_start,
        period_end=period.period_end,
    )

    sections: list[BranchPeriodReportSection] = []
    for branch in raw_branches:
        device_rows = _prepare_branch_device_rows(pd.DataFrame(branch.get("device_consumption_rows", [])))
        daily_rows = tuple(branch.get("daily_rows", []) or ())
        last_actual_timestamp = branch.get("last_actual_timestamp")
        if isinstance(last_actual_timestamp, str):
            parsed_last_actual = pd.to_datetime(last_actual_timestamp, errors="coerce")
            last_actual_timestamp = None if pd.isna(parsed_last_actual) else parsed_last_actual.to_pydatetime()

        sections.append(
            BranchPeriodReportSection(
                key=str(branch["key"]),
                title=str(branch["title"]),
                actual_total=round(float(branch.get("actual_total", 0.0) or 0.0), 3),
                vt_total=None if branch.get("vt_total") is None else round(float(branch.get("vt_total") or 0.0), 3),
                nt_total=None if branch.get("nt_total") is None else round(float(branch.get("nt_total") or 0.0), 3),
                last_actual_timestamp=last_actual_timestamp,
                device_rows=device_rows,
                daily_rows=daily_rows,
                chart_svg=_build_branch_chart_svg(daily_rows, device_rows, title=str(branch["title"])),
            )
        )

    return BranchPeriodReport(
        generated_at=resolved_generated_at,
        period=period,
        branches=tuple(sections),
    )


def build_weekly_elektromery_branch_report(
    *,
    reference_date: date | None = None,
    generated_at: datetime | None = None,
) -> BranchPeriodReport:
    return _build_report(_get_previous_week_period(reference_date), generated_at=generated_at)


def build_monthly_elektromery_branch_report(
    *,
    reference_date: date | None = None,
    generated_at: datetime | None = None,
) -> BranchPeriodReport:
    return _build_report(_get_previous_month_period(reference_date), generated_at=generated_at)


def _build_metric_card_html(
    label: str,
    value: str,
    detail: str | None = None,
    *,
    primary: bool = False,
) -> str:
    card_class = "metric-card metric-card-primary" if primary else "metric-card"
    detail_html = f"<div class='metric-detail'>{escape(detail)}</div>" if detail else ""
    return (
        f"<div class='{card_class}'>"
        f"<div class='metric-label'>{escape(label)}</div>"
        f"<div class='metric-value'>{escape(value)}</div>"
        f"{detail_html}"
        "</div>"
    )


def _build_report_balance_section_html(report: BranchPeriodReport) -> str:
    total_actual = _sum_energy_column(tuple(branch.actual_total for branch in report.branches))
    total_vt = _sum_energy_column(tuple(branch.vt_total for branch in report.branches))
    total_nt = _sum_energy_column(tuple(branch.nt_total for branch in report.branches))
    total_devices = sum(len(branch.device_rows) for branch in report.branches)

    rows_html = []
    for branch in report.branches:
        rows_html.append(
            "<tr>"
            f"<td><strong>{escape(branch.title)}</strong></td>"
            f"<td class='numeric'>{escape(_format_energy(branch.actual_total))}</td>"
            f"<td class='numeric'>{escape(_format_energy(branch.vt_total))}</td>"
            f"<td class='numeric'>{escape(_format_energy(branch.nt_total))}</td>"
            f"<td class='numeric'>{len(branch.device_rows)}</td>"
            "</tr>"
        )

    total_row_html = (
        "<tr class='balance-total-row'>"
        "<td><strong>Celkem</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_energy(total_actual))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_energy(total_vt))}</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_energy(total_nt))}</strong></td>"
        f"<td class='numeric'><strong>{total_devices}</strong></td>"
        "</tr>"
    )

    return (
        "<section class='balance-section'>"
        "<div class='balance-hero'>"
        "<div class='balance-title-block'>"
        "<div class='title-eyebrow'>Souhrn reportu</div>"
        "<h2>Celková spotřeba trafostanic</h2>"
        f"<div class='branch-meta'><strong>Období reportu:</strong> {escape(report.period.date_range_label)}</div>"
        "<div class='balance-description'>"
        "Souhrn spotřeby odběrných míst rozdělených podle trafostanic TS1-TS3."
        "</div>"
        "</div>"
        "<div class='balance-summary-card'>"
        f"{_build_metric_card_html('Celková spotřeba', _format_energy(total_actual), f'VT {_format_energy(total_vt)} | NT {_format_energy(total_nt)}', primary=True)}"
        "</div>"
        "</div>"
        "<div class='metric-grid balance-metric-grid'>"
        f"{_build_metric_card_html('Spotřeba VT', _format_energy(total_vt))}"
        f"{_build_metric_card_html('Spotřeba NT', _format_energy(total_nt))}"
        f"{_build_metric_card_html('Počet odběrných míst', str(total_devices))}"
        "</div>"
        "<div class='branch-table-wrap balance-table-wrap'>"
        "<div class='branch-subtitle'>Bilance po větvích</div>"
        "<table class='branch-table balance-table'>"
        "<thead><tr>"
        "<th>Větev</th>"
        "<th class='numeric'>Spotřeba</th>"
        "<th class='numeric'>VT</th>"
        "<th class='numeric'>NT</th>"
        "<th class='numeric'>Odběrná místa</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}{total_row_html}</tbody>"
        "</table>"
        "</div>"
        "</section>"
    )


def _build_device_table_row_html(row: BranchDeviceReportRow) -> str:
    return (
        "<tr>"
        f"<td><span class='row-ident'><span class='row-swatch' style='background:{escape(row.color_hex)};'></span>{escape(row.identifikace)}</span></td>"
        f"<td class='numeric'>{escape(_format_energy(row.start_value))}</td>"
        f"<td class='numeric'>{escape(_format_energy(row.end_value))}</td>"
        f"<td class='numeric'>{escape(_format_energy(row.spotreba))}</td>"
        f"<td class='numeric'>{escape(_format_energy(row.spotreba_vt))}</td>"
        f"<td class='numeric'>{escape(_format_energy(row.spotreba_nt))}</td>"
        f"<td class='numeric'>{escape(_format_percent(row.podil_procent))}</td>"
        f"<td class='numeric'>{row.active_days}</td>"
        "</tr>"
    )


def _build_device_table_html(device_rows: tuple[BranchDeviceReportRow, ...]) -> str:
    if not device_rows:
        return "<p class='empty-state'>Pro tuto větev nejsou k dispozici žádná odběrná místa.</p>"

    rows_html = "".join(_build_device_table_row_html(row) for row in device_rows)
    return (
        "<table class='branch-table'>"
        "<thead><tr>"
        "<th>Odběrné místo</th>"
        "<th class='numeric'>Počáteční stav</th>"
        "<th class='numeric'>Konečný stav</th>"
        "<th class='numeric'>Spotřeba</th>"
        "<th class='numeric'>VT</th>"
        "<th class='numeric'>NT</th>"
        "<th class='numeric'>Podíl na větvi</th>"
        "<th class='numeric'>Dny</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )


def _build_branch_section_html(section: BranchPeriodReportSection, *, is_first: bool) -> str:
    section_class = "branch-section branch-section-first" if is_first else "branch-section"
    average_daily = round(section.actual_total / len(section.daily_rows), 3) if section.daily_rows else None
    return (
        f"<section class='{section_class}'>"
        "<div class='branch-header'>"
        f"<div class='branch-title-block'><div class='branch-eyebrow'>Větev</div><h2>{escape(section.title)}</h2>"
        f"<div class='branch-meta'>Poslední měření: <strong>{escape(_format_datetime(section.last_actual_timestamp))}</strong></div></div>"
        f"<div class='branch-summary-card'>{_build_metric_card_html('Součet spotřeby odběrných míst', _format_energy(section.actual_total), f'VT {_format_energy(section.vt_total)} | NT {_format_energy(section.nt_total)}', primary=True)}</div>"
        "</div>"
        "<div class='metric-grid'>"
        f"{_build_metric_card_html('Spotřeba VT', _format_energy(section.vt_total))}"
        f"{_build_metric_card_html('Spotřeba NT', _format_energy(section.nt_total))}"
        f"{_build_metric_card_html('Průměr na den', _format_energy(average_daily))}"
        f"{_build_metric_card_html('Počet odběrných míst', str(len(section.device_rows)))}"
        "</div>"
        "<div class='branch-chart-wrap'>"
        f"{section.chart_svg}"
        "</div>"
        "<div class='branch-table-wrap'>"
        f"{_build_device_table_html(section.device_rows)}"
        "</div>"
        "</section>"
    )


def build_elektromery_branch_report_html(report: BranchPeriodReport) -> str:
    armex_logo_data_uri = _load_image_data_uri(_armex_logo_path())
    balance_section_html = _build_report_balance_section_html(report)
    branch_sections_html = "".join(
        _build_branch_section_html(section, is_first=index == 0)
        for index, section in enumerate(report.branches)
    )

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Elektroměry | {escape(report.period.title_prefix.lower())} report spotřeby</title>
  <style>
    @page {{
      size: A4;
      margin: 9mm 8mm 10mm;
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
    .title-eyebrow, .branch-eyebrow {{
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
    .balance-section {{
      break-after: page;
      page-break-after: always;
      padding-top: 2px;
    }}
    .balance-hero, .branch-header {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(300px, 0.85fr);
      gap: 8px;
      align-items: stretch;
      margin-bottom: 8px;
    }}
    .balance-title-block, .branch-title-block {{
      padding: 4px 0;
    }}
    .balance-title-block h2, .branch-header h2 {{
      margin: 0;
      font-size: 20px;
      color: #0f4c81;
    }}
    .balance-description, .branch-meta {{
      margin-top: 5px;
      color: #52606d;
    }}
    .branch-section {{
      break-before: page;
      break-inside: avoid-page;
      page-break-inside: avoid;
      padding-top: 2px;
    }}
    .branch-section-first {{
      break-before: auto;
    }}
    .metric-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 8px;
      margin-bottom: 8px;
    }}
    .balance-metric-grid {{
      grid-template-columns: repeat(3, 1fr);
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
    .branch-summary-card .metric-card, .balance-summary-card .metric-card {{
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
    .branch-chart-wrap, .branch-table-wrap {{
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
    .branch-subtitle {{
      margin-bottom: 6px;
      font-size: 10px;
      font-weight: 700;
      color: #0f4c81;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .branch-chart svg {{
      width: 100%;
      height: auto;
      display: block;
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
    .balance-total-row td {{
      background: #e8edf3 !important;
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
      <h1>{escape(report.period.title_prefix)} report spotřeby elektroměrů</h1>
    </div>
    <div class="page-logo">
      <img src="{armex_logo_data_uri}" alt="ARMEX">
    </div>
    <div class="page-meta">
      <strong>Období:</strong> {escape(report.period.date_range_label)}
    </div>
  </header>

  {balance_section_html}
  {branch_sections_html}
</body>
</html>"""


def render_elektromery_branch_report_pdf(report: BranchPeriodReport) -> bytes:
    sync_playwright = _load_playwright_api()
    html = build_elektromery_branch_report_html(report)

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


def _build_report_subject(report: BranchPeriodReport) -> str:
    return f"Elektromery | {report.period.title_prefix.lower()} report spotreby | {report.period.date_range_label}"


def _build_report_pdf_filename(report: BranchPeriodReport) -> str:
    return f"{report.period.file_prefix} report elektromeru - {report.period.date_range_label}.pdf"


def _build_report_email_body(report: BranchPeriodReport, pdf_filename: str) -> str:
    total_actual = _sum_energy_column(tuple(branch.actual_total for branch in report.branches))
    total_vt = _sum_energy_column(tuple(branch.vt_total for branch in report.branches))
    total_nt = _sum_energy_column(tuple(branch.nt_total for branch in report.branches))
    summary_rows = "".join(
        (
            "<tr>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;'><strong>{escape(branch.title)}</strong></td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_energy(branch.actual_total))}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_energy(branch.vt_total))}</td>"
            f"<td style='padding:8px 10px;border:1px solid #d0d7de;text-align:right;'>{escape(_format_energy(branch.nt_total))}</td>"
            "</tr>"
        )
        for branch in report.branches
    )
    total_row = (
        "<tr>"
        "<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;'><strong>Celkem</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;text-align:right;'><strong>{escape(_format_energy(total_actual))}</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;text-align:right;'><strong>{escape(_format_energy(total_vt))}</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;text-align:right;'><strong>{escape(_format_energy(total_nt))}</strong></td>"
        "</tr>"
    )
    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        f"<h2 style='margin:0 0 12px;'>{escape(report.period.title_prefix)} report spotřeby elektroměrů</h2>"
        "<p style='margin:0 0 12px;'>"
        "V příloze je PDF report s přehledem spotřeby odběrných míst po trafostanicích."
        "</p>"
        f"<p style='margin:0 0 16px;'><strong>Období reportu:</strong> {escape(report.period.date_range_label)}<br>"
        f"<strong>Vygenerováno:</strong> {escape(_format_datetime(report.generated_at))}<br>"
        f"<strong>Soubor:</strong> {escape(pdf_filename)}</p>"
        "<table style='border-collapse:collapse;font-size:14px;'>"
        "<tr>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:left;'>Větev</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>Spotřeba</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>VT</th>"
        "<th style='padding:8px 10px;border:1px solid #d0d7de;background:#f6f8fa;text-align:right;'>NT</th>"
        "</tr>"
        f"{summary_rows}"
        f"{total_row}"
        "</table>"
        "</body></html>"
    )


def _send_report(
    report: BranchPeriodReport,
    *,
    recipients: tuple[str, ...] | None,
    default_recipients_loader,
    sender_alias_resolver,
) -> dict[str, Any]:
    resolved_recipients = filter_placeholder_recipients(
        recipients if recipients is not None else default_recipients_loader(),
        context_label=f"send_{report.period.kind}_elektromery_branch_report",
    )
    pdf_filename = _build_report_pdf_filename(report)
    subject = _build_report_subject(report)
    if not resolved_recipients:
        return {
            "title": subject,
            "recipient_count": 0,
            "recipients": (),
            "period": report.period.date_range_label,
            "branch_count": 0,
            "pdf_filename": pdf_filename,
            "pdf_size_bytes": 0,
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }

    pdf_bytes = render_elektromery_branch_report_pdf(report)
    body = _build_report_email_body(report, pdf_filename)
    sender_alias = sender_alias_resolver()

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
        "branch_count": report.total_branch_count,
        "pdf_filename": pdf_filename,
        "pdf_size_bytes": len(pdf_bytes),
    }


def send_weekly_elektromery_branch_report(
    *,
    reference_date: date | None = None,
    recipients: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    report = build_weekly_elektromery_branch_report(reference_date=reference_date)
    return _send_report(
        report,
        recipients=recipients,
        default_recipients_loader=_load_weekly_recipients,
        sender_alias_resolver=_resolve_weekly_sender_alias,
    )


def send_monthly_elektromery_branch_report(
    *,
    reference_date: date | None = None,
    recipients: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    report = build_monthly_elektromery_branch_report(reference_date=reference_date)
    return _send_report(
        report,
        recipients=recipients,
        default_recipients_loader=_load_monthly_recipients,
        sender_alias_resolver=_resolve_monthly_sender_alias,
    )
