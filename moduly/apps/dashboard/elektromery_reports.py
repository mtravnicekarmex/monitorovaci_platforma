from __future__ import annotations

import base64
import concurrent.futures
import datetime
import asyncio
import mimetypes
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from html import escape
from math import floor, isfinite, log10
from pathlib import Path
import sys
import warnings

import pandas as pd


REPORT_PERIOD_OPTIONS: dict[str, str] = {
    "day": "Denní",
    "week": "Týdenní",
    "month": "Měsíční",
}

_CURVE_COLOR = "#dc2626"
_CURVE_FILL = "#fee2e2"
_LIMIT_COLOR = "#111827"


class ElektromeryDashboardReportError(RuntimeError):
    """Raised when the dashboard OTE report cannot be rendered."""


@dataclass(frozen=True)
class OteReportPeriod:
    kind: str
    label: str
    period_start: datetime.datetime
    period_end: datetime.datetime
    bucket_frequency: str
    bucket_label: str

    @property
    def date_range_label(self) -> str:
        inclusive_end = self.period_end - datetime.timedelta(seconds=1)
        if self.period_start.date() == inclusive_end.date():
            return self.period_start.strftime("%d.%m.%Y")
        return f"{self.period_start.strftime('%d.%m.%Y')} - {inclusive_end.strftime('%d.%m.%Y')}"


@dataclass(frozen=True)
class OteCurveRow:
    date: datetime.datetime
    spotreba_kwh: float
    odber_kw: float
    pocet_mereni: int


@dataclass(frozen=True)
class OteDeviceSummaryRow:
    identifikace: str
    spotreba_kwh: float
    pocet_mereni: int


@dataclass(frozen=True)
class OteExceedanceRow:
    date: datetime.datetime
    odber_kw: float
    prekroceni_kw: float


@dataclass(frozen=True)
class OtePdfReport:
    generated_at: datetime.datetime
    period: OteReportPeriod
    period_label: str
    reserved_power_kw: float | None
    total_consumption_kwh: float
    measurement_count: int
    device_count: int
    max_power_kw: float | None
    max_power_at: datetime.datetime | None
    exceedance_count: int
    curve_rows: tuple[OteCurveRow, ...]
    device_rows: tuple[OteDeviceSummaryRow, ...]
    exceedance_rows: tuple[OteExceedanceRow, ...]
    selected_identifications: tuple[str, ...] = ()
    available_identification_count: int | None = None


def _record_value(record: object, key: str) -> object:
    if isinstance(record, Mapping):
        return record.get(key)
    return getattr(record, key, None)


def ote_records_to_dataframe(records: Iterable[object]) -> pd.DataFrame:
    def consumption_value(record: object) -> object:
        value = _record_value(record, "spotreba_kwh")
        return _record_value(record, "objem") if value is None else value

    rows = [
        {
            "date": _record_value(record, "date"),
            "identifikace": _record_value(record, "identifikace"),
            "seriove_cislo": _record_value(record, "seriove_cislo"),
            "spotreba_kwh": consumption_value(record),
            "source_file": _record_value(record, "source_file"),
        }
        for record in records
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["date", "identifikace", "seriove_cislo", "spotreba_kwh", "source_file"])

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["spotreba_kwh"] = pd.to_numeric(df["spotreba_kwh"], errors="coerce")
    df = df.dropna(subset=["date", "identifikace", "spotreba_kwh"]).copy()
    df["identifikace"] = df["identifikace"].astype(str)
    df["source_file"] = df["source_file"].astype("string")
    df = df.sort_values(["date", "identifikace"]).reset_index(drop=True)
    return df


def resolve_report_period(period_kind: str, selected_date: datetime.date) -> OteReportPeriod:
    if period_kind == "day":
        period_start = datetime.datetime.combine(selected_date, datetime.time.min)
        return OteReportPeriod(
            kind=period_kind,
            label=REPORT_PERIOD_OPTIONS[period_kind],
            period_start=period_start,
            period_end=period_start + datetime.timedelta(days=1),
            bucket_frequency="15min",
            bucket_label="15 min",
        )

    if period_kind == "week":
        week_start = selected_date - datetime.timedelta(days=selected_date.weekday())
        period_start = datetime.datetime.combine(week_start, datetime.time.min)
        return OteReportPeriod(
            kind=period_kind,
            label=REPORT_PERIOD_OPTIONS[period_kind],
            period_start=period_start,
            period_end=period_start + datetime.timedelta(days=7),
            bucket_frequency="h",
            bucket_label="hodina",
        )

    if period_kind == "month":
        month_start = selected_date.replace(day=1)
        if month_start.month == 12:
            next_month = month_start.replace(year=month_start.year + 1, month=1)
        else:
            next_month = month_start.replace(month=month_start.month + 1)
        return OteReportPeriod(
            kind=period_kind,
            label=REPORT_PERIOD_OPTIONS[period_kind],
            period_start=datetime.datetime.combine(month_start, datetime.time.min),
            period_end=datetime.datetime.combine(next_month, datetime.time.min),
            bucket_frequency="D",
            bucket_label="den",
        )

    raise ValueError(f"Neznamy typ reportu: {period_kind}")


def filter_measurements_for_period(df: pd.DataFrame, period: OteReportPeriod) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    date_series = pd.to_datetime(df["date"], errors="coerce")
    return df.loc[(date_series >= period.period_start) & (date_series < period.period_end)].copy()


def _bucket_hours(period: OteReportPeriod) -> float:
    if period.bucket_frequency == "15min":
        return 0.25
    if period.bucket_frequency == "h":
        return 1.0
    if period.bucket_frequency == "D":
        return 24.0
    return 1.0


def build_consumption_curve(period_df: pd.DataFrame, period: OteReportPeriod) -> pd.DataFrame:
    if period_df.empty:
        return pd.DataFrame(columns=["date", "spotreba_kwh", "odber_kw", "pocet_mereni"])

    prepared = period_df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared["spotreba_kwh"] = pd.to_numeric(prepared["spotreba_kwh"], errors="coerce").fillna(0.0)
    prepared = prepared.dropna(subset=["date"]).copy()
    if prepared.empty:
        return pd.DataFrame(columns=["date", "spotreba_kwh", "odber_kw", "pocet_mereni"])

    curve = (
        prepared.set_index("date")
        .resample(period.bucket_frequency)
        .agg(
            spotreba_kwh=("spotreba_kwh", "sum"),
            pocet_mereni=("spotreba_kwh", "count"),
        )
        .reset_index()
    )
    curve = curve[curve["pocet_mereni"] > 0].copy()
    curve["spotreba_kwh"] = curve["spotreba_kwh"].round(6)
    curve["odber_kw"] = (curve["spotreba_kwh"] / _bucket_hours(period)).round(6)
    return curve.reset_index(drop=True)


def build_device_summary(period_df: pd.DataFrame) -> pd.DataFrame:
    if period_df.empty:
        return pd.DataFrame(columns=["identifikace", "spotreba_kwh", "pocet_mereni"])

    summary = (
        period_df.groupby("identifikace", as_index=False)
        .agg(
            spotreba_kwh=("spotreba_kwh", "sum"),
            pocet_mereni=("spotreba_kwh", "count"),
        )
        .sort_values(["spotreba_kwh", "identifikace"], ascending=[False, True])
        .reset_index(drop=True)
    )
    summary["spotreba_kwh"] = pd.to_numeric(summary["spotreba_kwh"], errors="coerce").fillna(0.0).round(3)
    summary["pocet_mereni"] = summary["pocet_mereni"].astype(int)
    return summary


def summarize_report(period_df: pd.DataFrame, curve_df: pd.DataFrame) -> dict[str, object]:
    total_consumption = 0.0
    measurement_count = 0
    device_count = 0
    if not period_df.empty:
        total_consumption = round(float(pd.to_numeric(period_df["spotreba_kwh"], errors="coerce").fillna(0.0).sum()), 3)
        measurement_count = int(len(period_df))
        device_count = int(period_df["identifikace"].nunique())

    max_power_kw = None
    max_power_at = None
    if not curve_df.empty:
        max_index = pd.to_numeric(curve_df["odber_kw"], errors="coerce").idxmax()
        max_power_kw = round(float(curve_df.loc[max_index, "odber_kw"]), 3)
        max_power_at = pd.to_datetime(curve_df.loc[max_index, "date"]).to_pydatetime()

    return {
        "total_consumption_kwh": total_consumption,
        "measurement_count": measurement_count,
        "device_count": device_count,
        "max_power_kw": max_power_kw,
        "max_power_at": max_power_at,
    }


def build_threshold_exceedance(curve_df: pd.DataFrame, reserved_power_kw: float | None) -> pd.DataFrame:
    if curve_df.empty or reserved_power_kw is None or reserved_power_kw <= 0:
        return pd.DataFrame(columns=["date", "odber_kw", "prekroceni_kw"])

    prepared = curve_df.copy()
    prepared["odber_kw"] = pd.to_numeric(prepared["odber_kw"], errors="coerce")
    prepared["prekroceni_kw"] = (prepared["odber_kw"] - float(reserved_power_kw)).round(3)
    return prepared.loc[prepared["prekroceni_kw"] > 0, ["date", "odber_kw", "prekroceni_kw"]].reset_index(drop=True)


def describe_selected_identifications(
    selected_identifications: Iterable[str] | tuple[str, ...],
    *,
    total_available_count: int | None = None,
    preview_limit: int = 5,
) -> str:
    normalized = tuple(
        str(item).strip()
        for item in selected_identifications
        if item is not None and str(item).strip()
    )
    if not normalized:
        return "Bez vybraných odběrných míst"
    if total_available_count is not None and len(normalized) == total_available_count:
        return f"Všechna odběrná místa ({total_available_count})"

    preview = ", ".join(normalized[:preview_limit])
    remaining = len(normalized) - preview_limit
    if remaining > 0:
        preview = f"{preview} + {remaining} další"

    if total_available_count is not None:
        return f"{len(normalized)} / {total_available_count} odběrných míst: {preview}"
    return f"{len(normalized)} odběrných míst: {preview}"


def build_ote_pdf_report(
    *,
    period: OteReportPeriod,
    period_label: str,
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    device_summary_df: pd.DataFrame,
    reserved_power_kw: float | None,
    generated_at: datetime.datetime | None = None,
    selected_identifications: Iterable[str] | None = None,
    available_identification_count: int | None = None,
) -> OtePdfReport:
    summary = summarize_report(period_df, curve_df)
    exceedance_df = build_threshold_exceedance(curve_df, reserved_power_kw)
    normalized_selected_identifications = tuple(
        str(item).strip()
        for item in (selected_identifications or ())
        if item is not None and str(item).strip()
    )

    curve_rows = tuple(
        OteCurveRow(
            date=pd.to_datetime(row.date).to_pydatetime(),
            spotreba_kwh=round(float(row.spotreba_kwh), 3),
            odber_kw=round(float(row.odber_kw), 3),
            pocet_mereni=int(row.pocet_mereni),
        )
        for row in curve_df.itertuples(index=False)
    )
    device_rows = tuple(
        OteDeviceSummaryRow(
            identifikace=str(row.identifikace),
            spotreba_kwh=round(float(row.spotreba_kwh), 3),
            pocet_mereni=int(row.pocet_mereni),
        )
        for row in device_summary_df.itertuples(index=False)
    )
    exceedance_rows = tuple(
        OteExceedanceRow(
            date=pd.to_datetime(row.date).to_pydatetime(),
            odber_kw=round(float(row.odber_kw), 3),
            prekroceni_kw=round(float(row.prekroceni_kw), 3),
        )
        for row in exceedance_df.itertuples(index=False)
    )

    return OtePdfReport(
        generated_at=generated_at or datetime.datetime.now(),
        period=period,
        period_label=period_label,
        reserved_power_kw=reserved_power_kw,
        total_consumption_kwh=round(float(summary["total_consumption_kwh"] or 0.0), 3),
        measurement_count=int(summary["measurement_count"] or 0),
        device_count=int(summary["device_count"] or 0),
        max_power_kw=None if summary["max_power_kw"] is None else round(float(summary["max_power_kw"]), 3),
        max_power_at=summary["max_power_at"],
        exceedance_count=len(exceedance_rows),
        curve_rows=curve_rows,
        device_rows=device_rows,
        exceedance_rows=exceedance_rows,
        selected_identifications=normalized_selected_identifications,
        available_identification_count=available_identification_count,
    )


def build_ote_report_pdf_filename(report: OtePdfReport) -> str:
    prefix_by_kind = {
        "day": "Denni",
        "week": "Tydenni",
        "month": "Mesicni",
    }
    prefix = prefix_by_kind.get(report.period.kind, "OTE")
    return f"{prefix} report OTE elektromeru - {report.period.date_range_label}.pdf"


def _load_playwright_api():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ElektromeryDashboardReportError(
            "Playwright je vyzadovan pro render PDF reportu elektromeru."
        ) from exc
    return sync_playwright


def _load_image_data_uri(image_path: Path) -> str:
    if not image_path.exists():
        raise ElektromeryDashboardReportError(f"Logo file was not found: {image_path}")
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _armex_logo_path() -> Path:
    return Path.cwd() / "data" / "ARMEX" / "logo_ARMEX.png"


def _format_value(value: object, *, unit: str = "", digits: int = 3, signed: bool = False) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value) or not isfinite(numeric_value):
        return "-"
    if abs(numeric_value) < 0.0005:
        numeric_value = 0.0
    format_spec = f"{'+' if signed else ''}.{digits}f"
    suffix = f" {unit}" if unit else ""
    return f"{numeric_value:{format_spec}}{suffix}"


def _format_datetime(value: datetime.datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%d.%m.%Y %H:%M")


def _build_metric_card_html(
    label: str,
    value: str,
    detail: str | None = None,
    *,
    primary: bool = False,
    alert: bool = False,
) -> str:
    class_names = ["metric-card"]
    if primary:
        class_names.append("metric-card-primary")
    if alert:
        class_names.append("metric-card-alert")
    detail_html = f"<div class='metric-detail'>{escape(detail)}</div>" if detail else ""
    return (
        f"<div class='{' '.join(class_names)}'>"
        f"<div class='metric-label'>{escape(label)}</div>"
        f"<div class='metric-value'>{escape(value)}</div>"
        f"{detail_html}"
        "</div>"
    )


def _axis_ceiling(max_value: float) -> float:
    if max_value <= 0:
        return 1.0
    scaled = max_value * 1.12
    magnitude = 10 ** floor(log10(scaled))
    normalized = scaled / magnitude
    if normalized <= 1:
        nice = 1
    elif normalized <= 2:
        nice = 2
    elif normalized <= 5:
        nice = 5
    else:
        nice = 10
    return nice * magnitude


def _curve_label(value: datetime.datetime, period: OteReportPeriod) -> str:
    if period.kind == "day":
        return value.strftime("%H:%M")
    if period.kind == "week":
        return value.strftime("%d.%m. %H:%M")
    return value.strftime("%d.%m.")


def _label_indexes(item_count: int, *, max_labels: int) -> list[int]:
    if item_count <= 0:
        return []
    if item_count <= max_labels:
        return list(range(item_count))
    indexes = {0, item_count - 1}
    step_count = max_labels - 1
    for step in range(1, step_count):
        index = round((item_count - 1) * step / step_count)
        indexes.add(index)
    return sorted(indexes)


def _build_curve_svg(report: OtePdfReport) -> str:
    if not report.curve_rows:
        return "<div class='chart-empty'>Pro zvolené období nejsou k dispozici data pro křivku odběru.</div>"

    width = 920
    height = 300
    margin_left = 58
    margin_right = 18
    margin_top = 18
    margin_bottom = 54
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    bottom = margin_top + plot_height

    peak_value = max(row.odber_kw for row in report.curve_rows)
    if report.reserved_power_kw is not None and report.reserved_power_kw > 0:
        peak_value = max(peak_value, float(report.reserved_power_kw))
    axis_max = _axis_ceiling(peak_value)
    tick_values = [axis_max * index / 4 for index in range(5)]

    def x_position(index: int) -> float:
        if len(report.curve_rows) == 1:
            return margin_left + plot_width / 2
        return margin_left + plot_width * index / (len(report.curve_rows) - 1)

    def y_position(value: float) -> float:
        if axis_max <= 0:
            return float(bottom)
        return bottom - (value / axis_max) * plot_height

    points = [(x_position(index), y_position(row.odber_kw), row) for index, row in enumerate(report.curve_rows)]
    area_path = " ".join(
        ["M", f"{points[0][0]:.2f}", f"{bottom:.2f}", "L"]
        + [f"{x:.2f} {y:.2f}" for x, y, _ in points]
        + [f"L {points[-1][0]:.2f} {bottom:.2f}", "Z"]
    )
    line_path = " ".join(
        ("M" if index == 0 else "L") + f" {x:.2f} {y:.2f}"
        for index, (x, y, _) in enumerate(points)
    )

    y_grid = "".join(
        (
            f"<line x1='{margin_left}' y1='{y_position(tick):.2f}' x2='{width - margin_right}' y2='{y_position(tick):.2f}' "
            "stroke='#e5e7eb' stroke-width='1' />"
            f"<text x='{margin_left - 10}' y='{y_position(tick) + 3:.2f}' text-anchor='end' class='chart-axis-label'>"
            f"{escape(_format_value(tick, unit='kW', digits=1))}</text>"
        )
        for tick in tick_values
    )
    x_labels = "".join(
        (
            f"<line x1='{x_position(index):.2f}' y1='{bottom}' x2='{x_position(index):.2f}' y2='{bottom + 4}' "
            "stroke='#94a3b8' stroke-width='1' />"
            f"<text x='{x_position(index):.2f}' y='{bottom + 18}' text-anchor='middle' class='chart-axis-label'>"
            f"{escape(_curve_label(report.curve_rows[index].date, report.period))}</text>"
        )
        for index in _label_indexes(len(report.curve_rows), max_labels=7 if report.period.kind == "day" else 6)
    )

    circle_points = ""
    if len(points) <= 120:
        circle_points = "".join(
            f"<circle cx='{x:.2f}' cy='{y:.2f}' r='2.2' fill='{_CURVE_COLOR}' />"
            for x, y, _ in points
        )

    limit_line = ""
    legend_items = [
        (
            "<span class='chart-line-legend-item'>"
            f"<span class='chart-line-legend-dot' style='background:{_CURVE_COLOR};'></span>"
            "<span>Odběr [kW]</span></span>"
        )
    ]
    if report.reserved_power_kw is not None and report.reserved_power_kw > 0:
        limit_y = y_position(float(report.reserved_power_kw))
        limit_line = (
            f"<line x1='{margin_left}' y1='{limit_y:.2f}' x2='{width - margin_right}' y2='{limit_y:.2f}' "
            f"stroke='{_LIMIT_COLOR}' stroke-width='2' stroke-dasharray='7 5' />"
        )
        legend_items.append(
            "<span class='chart-line-legend-item'>"
            "<span class='chart-line-legend-rule'></span>"
            "<span>Rezervovaná hladina</span></span>"
        )

    return (
        "<div class='branch-chart'>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Křivka odběru'>"
        f"{y_grid}"
        f"<line x1='{margin_left}' y1='{bottom}' x2='{width - margin_right}' y2='{bottom}' stroke='#94a3b8' stroke-width='1.2' />"
        f"<path d='{area_path}' fill='{_CURVE_FILL}' opacity='0.95' />"
        f"{limit_line}"
        f"<path d='{line_path}' fill='none' stroke='{_CURVE_COLOR}' stroke-width='2.5' stroke-linejoin='round' stroke-linecap='round' />"
        f"{circle_points}"
        f"{x_labels}"
        f"<text x='{margin_left}' y='{margin_top - 6}' class='chart-axis-label'>Odběr [kW]</text>"
        "</svg>"
        f"<div class='chart-line-legend'>{''.join(legend_items)}</div>"
        "</div>"
    )


def _build_device_table_html(report: OtePdfReport) -> str:
    if not report.device_rows:
        return "<p class='empty-state'>Ve zvoleném období nebyla nalezena žádná měřidla.</p>"

    rows_html = "".join(
        (
            "<tr>"
            f"<td>{escape(row.identifikace)}</td>"
            f"<td class='numeric'>{escape(_format_value(row.spotreba_kwh, unit='kWh'))}</td>"
            f"<td class='numeric'>{row.pocet_mereni}</td>"
            "</tr>"
        )
        for row in report.device_rows
    )
    total_row_html = (
        "<tr class='balance-total-row'>"
        "<td><strong>Celkem</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_value(report.total_consumption_kwh, unit='kWh'))}</strong></td>"
        f"<td class='numeric'><strong>{report.measurement_count}</strong></td>"
        "</tr>"
    )
    return (
        "<table class='branch-table'>"
        "<thead><tr>"
        "<th>Odběrné místo</th>"
        "<th class='numeric'>Spotřeba</th>"
        "<th class='numeric'>Počet měření</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}{total_row_html}</tbody>"
        "</table>"
    )


def _build_exceedance_table_html(report: OtePdfReport) -> str:
    if report.reserved_power_kw is None or report.reserved_power_kw <= 0:
        return "<p class='empty-state'>Rezervovaná hladina nebyla pro report zadána.</p>"
    if not report.exceedance_rows:
        return "<p class='empty-state'>Ve zvoleném období nebylo zjištěno žádné překročení rezervované hladiny.</p>"

    rows_html = "".join(
        (
            "<tr>"
            f"<td>{escape(_format_datetime(row.date))}</td>"
            f"<td class='numeric'>{escape(_format_value(row.odber_kw, unit='kW'))}</td>"
            f"<td class='numeric'>{escape(_format_value(row.prekroceni_kw, unit='kW'))}</td>"
            "</tr>"
        )
        for row in report.exceedance_rows
    )
    return (
        "<table class='branch-table'>"
        "<thead><tr>"
        "<th>Interval</th>"
        "<th class='numeric'>Odběr</th>"
        "<th class='numeric'>Překročení</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )


def build_ote_report_html(report: OtePdfReport) -> str:
    armex_logo_data_uri = _load_image_data_uri(_armex_logo_path())
    chart_svg = _build_curve_svg(report)
    selection_summary = describe_selected_identifications(
        report.selected_identifications,
        total_available_count=report.available_identification_count,
    )
    reserved_value = (
        _format_value(report.reserved_power_kw, unit="kW")
        if report.reserved_power_kw is not None and report.reserved_power_kw > 0
        else "Nezadáno"
    )
    limit_alert = bool(
        report.reserved_power_kw is not None
        and report.reserved_power_kw > 0
        and report.exceedance_count > 0
    )

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Elektroměry | {escape(report.period.label.lower())} report spotřeby</title>
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
      grid-template-columns: minmax(0, 1.45fr) auto minmax(220px, 0.95fr);
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
    .page-meta strong {{
      color: #111827;
    }}
    .report-section {{
      padding-top: 2px;
    }}
    .report-hero {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
      gap: 8px;
      align-items: stretch;
      margin-bottom: 8px;
    }}
    .report-title-block {{
      padding: 4px 0;
    }}
    .report-title-block h2 {{
      margin: 0;
      font-size: 20px;
      color: #0f4c81;
    }}
    .report-description, .report-meta {{
      margin-top: 5px;
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
    .metric-card-alert {{
      background: linear-gradient(180deg, #fff1f2 0%, #ffe4e6 100%);
      border-color: #fca5a5;
      color: #7f1d1d;
      box-shadow: 0 6px 16px rgba(220, 38, 38, 0.12);
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
    .report-summary-card .metric-card {{
      height: 100%;
      box-sizing: border-box;
    }}
    .branch-chart-wrap, .branch-table-wrap {{
      border: 1px solid #d8e1eb;
      border-radius: 10px;
      background: #ffffff;
      padding: 6px 8px 7px;
      box-shadow: 0 3px 12px rgba(15, 76, 129, 0.05);
      margin-bottom: 8px;
      break-inside: avoid-page;
      page-break-inside: avoid;
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
    .chart-line-legend-rule {{
      width: 14px;
      height: 0;
      border-top: 2px dashed {_LIMIT_COLOR};
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
    .balance-total-row td {{
      background: #e8edf3 !important;
    }}
    .numeric {{
      text-align: right;
      white-space: nowrap;
    }}
  </style>
</head>
<body>
  <header class="page-header">
    <div>
      <div class="title-eyebrow">Monitoring platforma</div>
      <h1>{escape(report.period.label)} report spotřeby elektroměrů</h1>
    </div>
    <div class="page-logo">
      <img src="{armex_logo_data_uri}" alt="ARMEX">
    </div>
    <div class="page-meta">
      <strong>Období:</strong> {escape(report.period.date_range_label)}<br>
      <strong>Vygenerováno:</strong> {escape(_format_datetime(report.generated_at))}<br>
      <strong>Zdroj:</strong> dbo.Mereni_elektromery_OTE
    </div>
  </header>

  <section class="report-section">
    <div class="report-hero">
      <div class="report-title-block">
        <div class="title-eyebrow">Souhrn reportu</div>
        <h2>Křivka odběru a rezervovaná hladina</h2>
        <div class="report-meta"><strong>Typ reportu:</strong> {escape(report.period_label)}</div>
        <div class="report-meta"><strong>Odběrná místa:</strong> {escape(selection_summary)}</div>
        <div class="report-description">
          Report vychází z OTE dat uložených v PostgreSQL a sleduje celkovou spotřebu, okamžitý odběr
          a případná překročení rezervované hladiny.
        </div>
      </div>
      <div class="report-summary-card">
        {_build_metric_card_html(
            "Celková spotřeba",
            _format_value(report.total_consumption_kwh, unit="kWh"),
            f"Maximum {_format_value(report.max_power_kw, unit='kW')} | Překročení {report.exceedance_count}",
            primary=True,
        )}
      </div>
    </div>

    <div class="metric-grid">
      {_build_metric_card_html("Max. odběr", _format_value(report.max_power_kw, unit="kW"), _format_datetime(report.max_power_at))}
      {_build_metric_card_html("Rezervovaná hladina", reserved_value, "Kontrola limitu odběru", alert=limit_alert)}
      {_build_metric_card_html("Měřidla", str(report.device_count), "Unikátní odběrná místa")}
      {_build_metric_card_html("Měření", str(report.measurement_count), f"Krok {report.period.bucket_label}")}
    </div>

    <div class="branch-chart-wrap">
      <div class="branch-subtitle">Křivka odběru</div>
      {chart_svg}
    </div>

    <div class="branch-table-wrap">
      <div class="branch-subtitle">Souhrn měřidel</div>
      {_build_device_table_html(report)}
    </div>

    <div class="branch-table-wrap">
      <div class="branch-subtitle">Překročení rezervované hladiny</div>
      {_build_exceedance_table_html(report)}
    </div>
  </section>
</body>
</html>"""


def _render_pdf_from_html(html: str) -> bytes:
    sync_playwright = _load_playwright_api()

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


def _render_pdf_from_html_windows_worker(html: str) -> bytes:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        original_policy = asyncio.get_event_loop_policy()
        windows_policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
        try:
            if windows_policy_cls is not None:
                asyncio.set_event_loop_policy(windows_policy_cls())
            return _render_pdf_from_html(html)
        finally:
            asyncio.set_event_loop_policy(original_policy)


def render_ote_report_pdf(report: OtePdfReport) -> bytes:
    html = build_ote_report_html(report)
    try:
        if sys.platform == "win32":
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(_render_pdf_from_html_windows_worker, html).result()
        return _render_pdf_from_html(html)
    except ElektromeryDashboardReportError:
        raise
    except NotImplementedError as exc:
        raise ElektromeryDashboardReportError(
            "PDF report se nepodařilo vytvořit kvůli omezení Windows event loopu pro Playwright."
        ) from exc
    except Exception as exc:
        raise ElektromeryDashboardReportError(
            f"PDF report se nepodařilo vytvořit: {exc.__class__.__name__}."
        ) from exc
