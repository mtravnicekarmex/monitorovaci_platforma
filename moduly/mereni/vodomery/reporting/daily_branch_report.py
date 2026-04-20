from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import date, datetime, timedelta
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
from services.api.services.dashboard_auth import DashboardUserContext
from services.api.services.vodomery import load_branch_day_overview


DEFAULT_DAILY_BRANCH_REPORT_RECIPIENTS = "ops@example.com"
DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS = "upozorneni@example.com"
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
BILLING_CURVE_COLOR = "#f97316"


class VodomeryDailyBranchReportError(RuntimeError):
    """Raised when the daily branch report cannot be built or delivered."""


@dataclass(frozen=True)
class BranchDeviceReportRow:
    identifikace: str
    start_value: float | None
    end_value: float | None
    spotreba: float
    podil_procent: float
    ocekavana_spotreba: float | None
    spotreba_ku_ocekavani_procent: float | None
    color_hex: str


@dataclass(frozen=True)
class BranchDailyReportSection:
    key: str
    title: str
    billing_ident: str
    actual_total: float
    expected_total: float
    daily_limit: float | None
    remaining_to_limit: float | None
    billing_total: float | None
    difference_vs_billing: float | None
    actual_vs_billing_percent: float | None
    last_actual_timestamp: datetime | None
    device_rows: tuple[BranchDeviceReportRow, ...]
    chart_svg: str


@dataclass(frozen=True)
class DailyBranchReport:
    generated_at: datetime
    target_date: date
    branches: tuple[BranchDailyReportSection, ...]

    @property
    def total_branch_count(self) -> int:
        return len(self.branches)


def _build_scheduler_admin_context() -> DashboardUserContext:
    return DashboardUserContext(
        username="scheduler",
        email=None,
        is_admin=True,
        is_active=True,
        allowed_sections=("vodomery",),
        allowed_pages=(),
        allowed_devices=(),
        last_login_at=None,
        token_version=0,
    )


def _resolve_target_date(target_date: date | None = None) -> date:
    if target_date is not None:
        return target_date
    return prague_today() - timedelta(days=1)


def _load_recipients() -> tuple[str, ...]:
    return load_report_recipients(
        "VODOMERY_DAILY_BRANCH_REPORT_RECIPIENTS",
        default=DEFAULT_DAILY_BRANCH_REPORT_RECIPIENTS,
        error_cls=VodomeryDailyBranchReportError,
    )


def _resolve_sender_alias() -> str | None:
    return sanitize_sender_alias(
        config(
            "VODOMERY_DAILY_BRANCH_REPORT_SENDER_ALIAS",
            default=config("O_EMAIL_UPOZORNENI", default=DEFAULT_DAILY_BRANCH_REPORT_SENDER_ALIAS),
        ),
        context_label="VODOMERY_DAILY_BRANCH_REPORT_SENDER_ALIAS",
    )


def _load_playwright_api():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VodomeryDailyBranchReportError(
            "Playwright je vyzadovan pro render PDF denniho reportu vodomeru."
        ) from exc
    return sync_playwright


def _format_volume(value: object, *, signed: bool = False) -> str:
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
    return f"{numeric_value:{format_spec}} m³"


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


def _format_percent_delta(value: object) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value) or not isfinite(numeric_value):
        return "-"
    rounded_value = int(round(numeric_value))
    if rounded_value == 0:
        return "0%"
    return f"{rounded_value:+d}%"


def _format_datetime(value: datetime | None) -> str:
    return "-" if value is None else value.strftime("%d.%m.%Y %H:%M")


def _sum_email_volume_column(values: tuple[object, ...]) -> float:
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


def _build_report_subject(report: DailyBranchReport) -> str:
    return f"Vodomery | denni report fakturacnich vodomeru | {report.target_date:%d.%m.%Y}"


def _build_report_pdf_filename(report: DailyBranchReport) -> str:
    return f"Denni report vodomeru - {report.target_date:%d.%m.%Y}.pdf"


def _load_image_data_uri(image_path: Path) -> str:
    if not image_path.exists():
        raise VodomeryDailyBranchReportError(f"Logo file was not found: {image_path}")
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _armex_logo_path() -> Path:
    return Path.cwd() / "data" / "ARMEX" / "logo_ARMEX.png"


def _format_limit_remaining(remaining_to_limit: float | None) -> tuple[str, bool]:
    if remaining_to_limit is None:
        return "-", False
    if remaining_to_limit >= 0:
        return _format_volume(remaining_to_limit), False
    return _format_volume(abs(remaining_to_limit), signed=True), True


def _safe_ratio_percent(numerator: object, denominator: object) -> float | None:
    try:
        numerator_value = float(numerator)
        denominator_value = float(denominator)
    except (TypeError, ValueError):
        return None
    if pd.isna(numerator_value) or pd.isna(denominator_value) or denominator_value <= 0:
        return None
    return round(numerator_value / denominator_value * 100, 1)


def _serialize_branch_dataframe_rows(raw_rows: list[dict[str, object]]) -> pd.DataFrame:
    frame = pd.DataFrame(raw_rows)
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


def _prepare_branch_device_rows(device_consumption_df: pd.DataFrame) -> tuple[BranchDeviceReportRow, ...]:
    if device_consumption_df.empty:
        return ()

    rows = device_consumption_df.copy()
    if "start_value" in rows.columns:
        rows["start_value"] = pd.to_numeric(rows["start_value"], errors="coerce")
    if "end_value" in rows.columns:
        rows["end_value"] = pd.to_numeric(rows["end_value"], errors="coerce")
    if "spotreba" in rows.columns:
        rows["spotreba"] = pd.to_numeric(rows["spotreba"], errors="coerce").fillna(0.0)
    if "podil_procent" in rows.columns:
        rows["podil_procent"] = pd.to_numeric(rows["podil_procent"], errors="coerce").fillna(0.0)
    if "ocekavana_spotreba" in rows.columns:
        rows["ocekavana_spotreba"] = pd.to_numeric(rows["ocekavana_spotreba"], errors="coerce")
    rows = rows.sort_values(["spotreba", "identifikace"], ascending=[False, True]).reset_index(drop=True)

    prepared_rows: list[BranchDeviceReportRow] = []
    for index, row in enumerate(rows.itertuples(index=False)):
        start_value = None if not hasattr(row, "start_value") or pd.isna(row.start_value) else round(float(row.start_value), 3)
        end_value = None if not hasattr(row, "end_value") or pd.isna(row.end_value) else round(float(row.end_value), 3)
        expected_value = None if pd.isna(row.ocekavana_spotreba) else round(float(row.ocekavana_spotreba), 3)
        prepared_rows.append(
            BranchDeviceReportRow(
                identifikace=str(row.identifikace),
                start_value=start_value,
                end_value=end_value,
                spotreba=round(float(row.spotreba), 3),
                podil_procent=round(float(row.podil_procent), 1),
                ocekavana_spotreba=expected_value,
                spotreba_ku_ocekavani_procent=_safe_ratio_percent(row.spotreba, expected_value),
                color_hex=PALETTE[index % len(PALETTE)],
            )
        )
    return tuple(prepared_rows)


def _prediction_delta_percent(actual_total: object, expected_total: object) -> float | None:
    ratio_percent = _safe_ratio_percent(actual_total, expected_total)
    if ratio_percent is None:
        return None
    return ratio_percent - 100.0


def _build_branch_chart_svg(
    device_hourly_df: pd.DataFrame,
    hourly_df: pd.DataFrame,
    device_rows: tuple[BranchDeviceReportRow, ...],
    last_actual_timestamp: datetime | None,
) -> str:
    if device_hourly_df.empty or hourly_df.empty or not device_rows or last_actual_timestamp is None:
        return (
            "<div class='chart-empty'>"
            "Pro vybranou větev nejsou k dispozici hodinová data pro vykreslení grafu."
            "</div>"
        )

    color_map = {row.identifikace: row.color_hex for row in device_rows if row.spotreba > 0}
    chart_idents = tuple(color_map)
    if not chart_idents:
        return "<div class='chart-empty'>Ve zvolené větvi nejsou pro denní graf žádná skutečná data.</div>"

    area_df = device_hourly_df.copy()
    area_df["date"] = pd.to_datetime(area_df["date"], errors="coerce")
    area_df["spotreba"] = pd.to_numeric(area_df["spotreba"], errors="coerce").fillna(0.0)
    area_df = area_df.loc[area_df["identifikace"].isin(chart_idents)].copy()
    if area_df.empty:
        return "<div class='chart-empty'>Ve zvolené větvi nejsou pro denní graf žádná skutečná data.</div>"

    last_actual_hour = pd.Timestamp(last_actual_timestamp).floor("h")
    area_df = area_df.loc[area_df["date"] <= last_actual_hour].copy()
    if area_df.empty:
        return "<div class='chart-empty'>Ve zvolené větvi nejsou pro denní graf žádná skutečná data.</div>"

    hourly_copy = hourly_df.copy()
    hourly_copy["date"] = pd.to_datetime(hourly_copy["date"], errors="coerce")
    hourly_copy["ocekavana_spotreba"] = pd.to_numeric(hourly_copy["ocekavana_spotreba"], errors="coerce").fillna(0.0)
    if "fakturacni_spotreba" in hourly_copy.columns:
        hourly_copy["fakturacni_spotreba"] = pd.to_numeric(
            hourly_copy["fakturacni_spotreba"],
            errors="coerce",
        ).fillna(0.0)
    else:
        hourly_copy["fakturacni_spotreba"] = 0.0

    hour_points = list(pd.date_range(start=area_df["date"].min(), end=last_actual_hour, freq="h"))
    if not hour_points:
        return "<div class='chart-empty'>Ve zvolené větvi nejsou pro denní graf žádná skutečná data.</div>"

    area_pivot = (
        area_df.pivot_table(index="date", columns="identifikace", values="spotreba", aggfunc="sum")
        .reindex(hour_points, fill_value=0.0)
        .fillna(0.0)
    )

    expected_series = (
        hourly_copy.set_index("date")["ocekavana_spotreba"]
        .reindex(pd.date_range(start=hourly_copy["date"].min(), end=hourly_copy["date"].max(), freq="h"), fill_value=0.0)
        if not hourly_copy.empty
        else pd.Series(dtype=float)
    )

    chart_width = 930
    chart_height = 212
    margin_left = 48
    margin_right = 18
    margin_top = 12
    margin_bottom = 30
    plot_width = chart_width - margin_left - margin_right
    plot_height = chart_height - margin_top - margin_bottom
    x_dates = list(area_pivot.index)
    expected_values = [float(expected_series.get(timestamp, 0.0)) for timestamp in x_dates]
    billing_series = hourly_copy.set_index("date")["fakturacni_spotreba"]
    billing_values = [float(billing_series.get(timestamp, 0.0)) for timestamp in x_dates]

    stack_totals = area_pivot.sum(axis=1).tolist()
    y_max = max(stack_totals + expected_values + billing_values + [0.1]) * 1.12
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
        if row.identifikace not in area_pivot.columns or row.spotreba <= 0:
            continue
        series_values = [float(area_pivot.at[timestamp, row.identifikace]) for timestamp in x_dates]
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
    for index, timestamp in enumerate(x_dates):
        if len(x_dates) <= 8 or index in {0, len(x_dates) - 1} or index % 3 == 0:
            x = scale_x(index)
            x_labels.append(
                f"<text x='{x:.1f}' y='{chart_height - 12:.1f}' text-anchor='middle' class='chart-axis-label'>"
                f"{timestamp.strftime('%H:%M')}</text>"
            )

    svg = StringIO()
    svg.write("<div class='branch-chart'>")
    svg.write(
        f"<svg viewBox='0 0 {chart_width} {chart_height}' role='img' aria-label='Denní graf spotřeby větve {escape(chart_idents[0])}'>"
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


def build_daily_branch_report(
    *,
    target_date: date | None = None,
    generated_at: datetime | None = None,
) -> DailyBranchReport:
    resolved_target_date = _resolve_target_date(target_date)
    resolved_generated_at = generated_at or prague_now_naive()
    raw_branches = load_branch_day_overview(
        _build_scheduler_admin_context(),
        target_date=resolved_target_date,
    )

    sections: list[BranchDailyReportSection] = []
    for branch in raw_branches:
        hourly_df = _serialize_branch_dataframe_rows(branch.get("hourly_rows", []))
        device_consumption_df = pd.DataFrame(branch.get("device_consumption_rows", []))
        device_hourly_df = _serialize_branch_dataframe_rows(branch.get("device_hourly_rows", []))
        device_rows = _prepare_branch_device_rows(device_consumption_df)

        billing_total = None
        if not hourly_df.empty and "fakturacni_spotreba" in hourly_df.columns:
            billing_total = round(
                float(pd.to_numeric(hourly_df["fakturacni_spotreba"], errors="coerce").fillna(0.0).sum()),
                3,
            )
        actual_total = round(float(branch.get("actual_total", 0.0) or 0.0), 3)
        expected_total = round(float(branch.get("expected_total", 0.0) or 0.0), 3)
        daily_limit = branch.get("daily_limit")
        remaining_to_limit = None if daily_limit is None else round(float(daily_limit) - actual_total, 3)
        difference_vs_billing = None if billing_total is None else round(actual_total - billing_total, 3)
        actual_vs_billing_percent = _safe_ratio_percent(actual_total, billing_total)
        last_actual_timestamp = branch.get("last_actual_timestamp")
        if isinstance(last_actual_timestamp, str):
            parsed_last_actual = pd.to_datetime(last_actual_timestamp, errors="coerce")
            last_actual_timestamp = None if pd.isna(parsed_last_actual) else parsed_last_actual.to_pydatetime()

        sections.append(
            BranchDailyReportSection(
                key=str(branch["key"]),
                title=str(branch["title"]),
                billing_ident=str(branch["billing_ident"]),
                actual_total=actual_total,
                expected_total=expected_total,
                daily_limit=float(daily_limit) if daily_limit is not None else None,
                remaining_to_limit=remaining_to_limit,
                billing_total=billing_total,
                difference_vs_billing=difference_vs_billing,
                actual_vs_billing_percent=actual_vs_billing_percent,
                last_actual_timestamp=last_actual_timestamp,
                device_rows=device_rows,
                chart_svg=_build_branch_chart_svg(device_hourly_df, hourly_df, device_rows, last_actual_timestamp),
            )
        )

    return DailyBranchReport(
        generated_at=resolved_generated_at,
        target_date=resolved_target_date,
        branches=tuple(sections),
    )


def _build_metric_card_html(
    label: str,
    value: str,
    detail: str | None = None,
    *,
    primary: bool = False,
    alert: bool = False,
) -> str:
    card_classes = ["metric-card"]
    if primary:
        card_classes.append("metric-card-primary")
    if alert:
        card_classes.append("metric-card-alert")
    card_class = " ".join(card_classes)
    detail_html = f"<div class='metric-detail'>{escape(detail)}</div>" if detail else ""
    return (
        f"<div class='{card_class}'>"
        f"<div class='metric-label'>{escape(label)}</div>"
        f"<div class='metric-value'>{escape(value)}</div>"
        f"{detail_html}"
        "</div>"
    )


def _build_device_table_html(device_rows: tuple[BranchDeviceReportRow, ...]) -> str:
    if not device_rows:
        return "<p class='empty-state'>Pro tuto větev nejsou k dispozici žádná odběrná místa.</p>"

    rows_html = []
    for row in device_rows:
        rows_html.append(
            "<tr>"
            f"<td><span class='row-ident'><span class='row-swatch' style='background:{escape(row.color_hex)};'></span>{escape(row.identifikace)}</span></td>"
            f"<td class='numeric'>{escape(_format_volume(row.start_value))}</td>"
            f"<td class='numeric'>{escape(_format_volume(row.end_value))}</td>"
            f"<td class='numeric'>{escape(_format_volume(row.spotreba))}</td>"
            f"<td class='numeric'>{escape(_format_percent(row.podil_procent))}</td>"
            f"<td class='numeric'>{escape(_format_volume(row.ocekavana_spotreba))}</td>"
            f"<td class='numeric'>{escape(_format_percent(row.spotreba_ku_ocekavani_procent))}</td>"
            "</tr>"
        )

    return (
        "<table class='branch-table'>"
        "<thead><tr>"
        "<th>Odběrné místo</th>"
        "<th class='numeric'>Počáteční stav</th>"
        "<th class='numeric'>Konečný stav</th>"
        "<th class='numeric'>Spotřeba</th>"
        "<th class='numeric'>Podíl na větvi</th>"
        "<th class='numeric'>Očekávaná spotřeba</th>"
        "<th class='numeric'>Spotřeba / očekávání</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )


def _format_branch_deviation(section: BranchDailyReportSection, *, per_hour: bool = False) -> str:
    if section.difference_vs_billing is None or not section.device_rows:
        return "-"
    device_count = len(section.device_rows)
    divisor = device_count * (24 if per_hour else 1)
    if divisor <= 0:
        return "-"
    return _format_volume(section.difference_vs_billing / divisor, signed=True)


def _build_branch_section_html(section: BranchDailyReportSection, *, is_first: bool) -> str:
    main_value = _format_volume(section.difference_vs_billing, signed=True)
    main_detail = (
        f"{_format_volume(section.actual_total)} vs. {_format_volume(section.billing_total)} | "
        f"Pokrytí {_format_percent(section.actual_vs_billing_percent)}"
        if section.billing_total is not None
        else f"{_format_volume(section.actual_total)} vs. -"
    )
    limit_value, limit_exceeded = _format_limit_remaining(section.remaining_to_limit)
    section_class = "branch-section branch-section-first" if is_first else "branch-section"
    return (
        f"<section class='{section_class}'>"
        "<div class='branch-header'>"
        f"<div class='branch-title-block'><div class='branch-eyebrow'>Větev</div><h2>{escape(section.title)}</h2>"
        f"<div class='branch-meta'>Fakturační vodoměr: <strong>{escape(section.billing_ident)}</strong></div></div>"
        f"<div class='branch-summary-card'>{_build_metric_card_html('Součet spotřeby vs. fakturační vodoměr', main_value, main_detail, primary=True)}</div>"
        "</div>"
        "<div class='metric-grid'>"
        f"{_build_metric_card_html('Do limitu SČVK', limit_value, alert=limit_exceeded)}"
        f"{_build_metric_card_html('Celodenní predikce', _format_volume(section.expected_total), _format_percent_delta(_prediction_delta_percent(section.actual_total, section.expected_total)))}"
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
        f"{_build_metric_card_html('Na 1 vodoměr / den', _format_branch_deviation(section))}"
        f"{_build_metric_card_html('Na 1 vodoměr / hodinu', _format_branch_deviation(section, per_hour=True))}"
        "</div>"
        "</div>"
        "</section>"
    )


def build_daily_branch_report_html(report: DailyBranchReport) -> str:
    armex_logo_data_uri = _load_image_data_uri(_armex_logo_path())
    branch_sections_html = "".join(
        _build_branch_section_html(section, is_first=index == 0)
        for index, section in enumerate(report.branches)
    )

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Vodoměry | denní report fakturačních vodoměrů</title>
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
      padding-top: 2px;
    }}
    .branch-section-first {{
      break-before: auto;
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
      grid-template-columns: repeat(4, 1fr);
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
      <h1>Denní report fakturačních vodoměrů</h1>
    </div>
    <div class="page-logo">
      <img src="{armex_logo_data_uri}" alt="ARMEX">
    </div>
    <div class="page-meta">
      <strong>Datum reportu:</strong> {escape(report.target_date.strftime("%d.%m.%Y"))}
    </div>
  </header>

  {branch_sections_html}
</body>
</html>"""


def render_daily_branch_report_pdf(report: DailyBranchReport) -> bytes:
    sync_playwright = _load_playwright_api()
    html = build_daily_branch_report_html(report)

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


def _build_report_email_body(report: DailyBranchReport, pdf_filename: str) -> str:
    total_actual = _sum_email_volume_column(tuple(branch.actual_total for branch in report.branches))
    total_billing = _sum_email_volume_column(tuple(branch.billing_total for branch in report.branches))
    total_difference = _sum_email_volume_column(tuple(branch.difference_vs_billing for branch in report.branches))
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
    total_row = (
        "<tr>"
        "<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;'><strong>Celkem</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;text-align:right;'><strong>{escape(_format_volume(total_actual))}</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;text-align:right;'><strong>{escape(_format_volume(total_billing))}</strong></td>"
        f"<td style='padding:8px 10px;border:1px solid #d0d7de;background:#e8edf3;text-align:right;'><strong>{escape(_format_volume(total_difference, signed=True))}</strong></td>"
        "</tr>"
    )
    return (
        "<html><body style='font-family:Segoe UI,Arial,sans-serif;color:#1f2328;'>"
        "<h2 style='margin:0 0 12px;'>Denní report fakturačních vodoměrů</h2>"
        "<p style='margin:0 0 12px;'>"
        "V příloze je denní PDF report s přehledem spotřeby jednotlivých větví, porovnáním "
        "součtu podružných vodoměrů s fakturačním vodoměrem a grafem hodinové spotřeby."
        "</p>"
        f"<p style='margin:0 0 16px;'><strong>Datum reportu:</strong> {escape(report.target_date.strftime('%d.%m.%Y'))}<br>"
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
        f"{total_row}"
        "</table>"
        "</body></html>"
    )


def send_daily_vodomery_branch_report(
    *,
    target_date: date | None = None,
    recipients: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    resolved_target_date = _resolve_target_date(target_date)
    resolved_recipients = filter_placeholder_recipients(
        recipients if recipients is not None else _load_recipients(),
        context_label="send_daily_vodomery_branch_report",
    )
    if not resolved_recipients:
        return {
            "title": f"Vodomery | denni report fakturacnich vodomeru | {resolved_target_date:%d.%m.%Y}",
            "recipient_count": 0,
            "recipients": (),
            "target_date": resolved_target_date.isoformat(),
            "branch_count": 0,
            "pdf_filename": f"Denni report vodomeru - {resolved_target_date:%d.%m.%Y}.pdf",
            "pdf_size_bytes": 0,
            "skipped": True,
            "skip_reason": "no_sendable_recipients",
        }
    report = build_daily_branch_report(target_date=resolved_target_date)
    pdf_bytes = render_daily_branch_report_pdf(report)
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
        "target_date": report.target_date.isoformat(),
        "branch_count": report.total_branch_count,
        "pdf_filename": pdf_filename,
        "pdf_size_bytes": len(pdf_bytes),
    }
