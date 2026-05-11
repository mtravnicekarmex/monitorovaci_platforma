from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import datetime
import mimetypes
import re
import sys
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from html import escape
from math import ceil, floor, isfinite, log10
from pathlib import Path

import pandas as pd


REPORT_PERIOD_OPTIONS: dict[str, str] = {
    "day": "Denní",
    "week": "Týdenní",
    "month": "Měsíční",
}

_CURVE_COLOR = "#0f766e"
_CURVE_FILL = "#ccfbf1"
_CURVE_LAYER_PALETTE = (
    (_CURVE_COLOR, _CURVE_FILL),
    ("#2563eb", "#dbeafe"),
    ("#d97706", "#fef3c7"),
    ("#7c3aed", "#ede9fe"),
    ("#dc2626", "#fee2e2"),
    ("#059669", "#d1fae5"),
    ("#db2777", "#fce7f3"),
)
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class VodomeryDashboardReportError(RuntimeError):
    """Raised when the dashboard vodomery report cannot be rendered."""


@dataclass(frozen=True)
class VodomeryReportPeriod:
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
class VodomeryCurveRow:
    date: datetime.datetime
    spotreba_m3: float
    prutok_m3h: float
    pocet_mereni: int
    peak_at: datetime.datetime | None = None


@dataclass(frozen=True)
class VodomeryCurveLayer:
    key: str
    label: str
    color: str
    fill_color: str
    curve_rows: tuple[VodomeryCurveRow, ...]
    selected_identifications: tuple[str, ...] = ()


@dataclass(frozen=True)
class VodomeryDeviceSummaryRow:
    identifikace: str
    spotreba_m3: float
    pocet_mereni: int


@dataclass(frozen=True)
class VodomeryPdfReport:
    generated_at: datetime.datetime
    period: VodomeryReportPeriod
    period_label: str
    total_consumption_m3: float
    measurement_count: int
    device_count: int
    max_flow_m3h: float | None
    max_flow_at: datetime.datetime | None
    curve_rows: tuple[VodomeryCurveRow, ...]
    device_rows: tuple[VodomeryDeviceSummaryRow, ...]
    curve_layers: tuple[VodomeryCurveLayer, ...] = ()
    selected_identifications: tuple[str, ...] = ()
    available_identification_count: int | None = None


def _record_value(record: object, key: str) -> object:
    if isinstance(record, Mapping):
        return record.get(key)
    return getattr(record, key, None)


def _normalize_selected_identifications(selected_identifications: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(
        str(item).strip()
        for item in (selected_identifications or ())
        if item is not None and str(item).strip()
    )


def _normalize_curve_color(color: str | None, *, fallback: str) -> str:
    if isinstance(color, str) and _HEX_COLOR_RE.fullmatch(color.strip()):
        return color.strip().lower()
    return fallback


def _derive_curve_fill_color(color: str) -> str:
    normalized = _normalize_curve_color(color, fallback=_CURVE_COLOR)
    red = int(normalized[1:3], 16)
    green = int(normalized[3:5], 16)
    blue = int(normalized[5:7], 16)

    def mix_with_white(channel: int) -> int:
        return round(channel + (255 - channel) * 0.82)

    return "#{:02x}{:02x}{:02x}".format(
        mix_with_white(red),
        mix_with_white(green),
        mix_with_white(blue),
    )


def curve_layer_color(index: int) -> str:
    return _CURVE_LAYER_PALETTE[index % len(_CURVE_LAYER_PALETTE)][0]


def curve_layer_fill_color(index: int, color: str | None = None) -> str:
    if color is not None:
        return _derive_curve_fill_color(color)
    return _CURVE_LAYER_PALETTE[index % len(_CURVE_LAYER_PALETTE)][1]


def curve_layer_label(index: int) -> str:
    if index <= 0:
        return "Hlavní výběr"
    return f"Vrstva {index}"


def curve_layer_legend_label(layer: VodomeryCurveLayer) -> str:
    selected_identifications = _normalize_selected_identifications(layer.selected_identifications)
    if selected_identifications:
        return ", ".join(selected_identifications)
    return layer.label


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


def describe_selected_identifications(
    selected_identifications: Iterable[str] | tuple[str, ...],
    *,
    total_available_count: int | None = None,
    preview_limit: int | None = 5,
    collapse_full_selection: bool = True,
) -> str:
    normalized = _normalize_selected_identifications(selected_identifications)
    if not normalized:
        return "Bez vybraných odběrných míst"
    if collapse_full_selection and total_available_count is not None and len(normalized) == total_available_count:
        return f"Všechna odběrná místa ({total_available_count})"

    if preview_limit is None or preview_limit <= 0:
        preview_limit = len(normalized)

    preview = ", ".join(normalized[:preview_limit])
    remaining = len(normalized) - preview_limit
    if remaining > 0:
        preview = f"{preview} + {remaining} další"

    if total_available_count is not None:
        return f"{len(normalized)} / {total_available_count} odběrných míst: {preview}"
    return f"{len(normalized)} odběrných míst: {preview}"


def vodomery_records_to_dataframe(records: Iterable[object]) -> pd.DataFrame:
    rows = [
        {
            "date": _record_value(record, "date"),
            "identifikace": _record_value(record, "identifikace"),
            "seriove_cislo": _record_value(record, "seriove_cislo"),
            "objem": _record_value(record, "objem"),
            "delta": _record_value(record, "delta"),
            "interval_minutes": _record_value(record, "interval_minutes"),
            "platne": _record_value(record, "platne"),
            "reset_detected": _record_value(record, "reset_detected"),
            "zdroj": _record_value(record, "zdroj"),
        }
        for record in records
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "identifikace",
                "seriove_cislo",
                "objem",
                "delta",
                "interval_minutes",
                "platne",
                "reset_detected",
                "zdroj",
                "spotreba_m3",
                "prutok_m3h",
            ]
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["objem"] = pd.to_numeric(df["objem"], errors="coerce")
    df["delta"] = pd.to_numeric(df["delta"], errors="coerce")
    df["interval_minutes"] = pd.to_numeric(df["interval_minutes"], errors="coerce")
    df["platne"] = df["platne"].fillna(True).astype(bool)
    df["reset_detected"] = df["reset_detected"].fillna(False).astype(bool)
    df = df.dropna(subset=["date", "identifikace", "objem"]).copy()
    df["identifikace"] = df["identifikace"].astype(str)
    df["seriove_cislo"] = df["seriove_cislo"].astype("string")
    df["zdroj"] = df["zdroj"].astype("string")
    df = df.sort_values(["identifikace", "date"]).reset_index(drop=True)

    diff_from_volume = df.groupby("identifikace")["objem"].diff()
    df["spotreba_m3"] = diff_from_volume
    df["spotreba_m3"] = pd.to_numeric(df["spotreba_m3"], errors="coerce").fillna(0.0)
    first_rows_mask = df.groupby("identifikace").cumcount() == 0
    df.loc[first_rows_mask, "spotreba_m3"] = 0.0
    df.loc[df["spotreba_m3"] < 0, "spotreba_m3"] = 0.0
    df.loc[~df["platne"], "spotreba_m3"] = 0.0
    df.loc[df["reset_detected"], "spotreba_m3"] = 0.0
    interval_hours = df["interval_minutes"].where(df["interval_minutes"] > 0).div(60.0)
    df["prutok_m3h"] = df["spotreba_m3"].where(interval_hours.isna(), df["spotreba_m3"] / interval_hours)
    df.loc[interval_hours.isna(), "prutok_m3h"] = 0.0
    df["prutok_m3h"] = df["prutok_m3h"].replace([float("inf"), float("-inf")], 0.0)
    df["prutok_m3h"] = pd.to_numeric(df["prutok_m3h"], errors="coerce").fillna(0.0)
    df["spotreba_m3"] = df["spotreba_m3"].round(6)
    df["prutok_m3h"] = df["prutok_m3h"].round(6)
    return df.sort_values(["date", "identifikace"]).reset_index(drop=True)


def resolve_report_period(period_kind: str, selected_date: datetime.date) -> VodomeryReportPeriod:
    if period_kind == "day":
        period_start = datetime.datetime.combine(selected_date, datetime.time.min)
        return VodomeryReportPeriod(
            kind=period_kind,
            label=REPORT_PERIOD_OPTIONS[period_kind],
            period_start=period_start,
            period_end=period_start + datetime.timedelta(days=1),
            bucket_frequency="h",
            bucket_label="hodina",
        )

    if period_kind == "week":
        week_start = selected_date - datetime.timedelta(days=selected_date.weekday())
        period_start = datetime.datetime.combine(week_start, datetime.time.min)
        return VodomeryReportPeriod(
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
        return VodomeryReportPeriod(
            kind=period_kind,
            label=REPORT_PERIOD_OPTIONS[period_kind],
            period_start=datetime.datetime.combine(month_start, datetime.time.min),
            period_end=datetime.datetime.combine(next_month, datetime.time.min),
            bucket_frequency="h",
            bucket_label="hodina",
        )

    raise ValueError(f"Neznamy typ reportu: {period_kind}")


def filter_measurements_for_period(df: pd.DataFrame, period: VodomeryReportPeriod) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    date_series = pd.to_datetime(df["date"], errors="coerce")
    return df.loc[(date_series >= period.period_start) & (date_series < period.period_end)].copy()


def build_interval_consumption_curve(period_df: pd.DataFrame) -> pd.DataFrame:
    if period_df.empty:
        return pd.DataFrame(columns=["date", "peak_at", "spotreba_m3", "prutok_m3h", "pocet_mereni"])

    prepared = period_df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared["spotreba_m3"] = pd.to_numeric(prepared["spotreba_m3"], errors="coerce").fillna(0.0)
    prepared["prutok_m3h"] = pd.to_numeric(prepared["prutok_m3h"], errors="coerce").fillna(0.0)
    prepared = prepared.dropna(subset=["date"]).copy()
    if prepared.empty:
        return pd.DataFrame(columns=["date", "peak_at", "spotreba_m3", "prutok_m3h", "pocet_mereni"])

    curve = (
        prepared.groupby("date", as_index=False)
        .agg(
            spotreba_m3=("spotreba_m3", "sum"),
            prutok_m3h=("prutok_m3h", "sum"),
            pocet_mereni=("spotreba_m3", "count"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )
    curve["spotreba_m3"] = curve["spotreba_m3"].round(6)
    curve["prutok_m3h"] = curve["prutok_m3h"].round(6)
    curve["peak_at"] = curve["date"]
    return curve[["date", "peak_at", "spotreba_m3", "prutok_m3h", "pocet_mereni"]].copy()


def build_consumption_curve(period_df: pd.DataFrame, period: VodomeryReportPeriod) -> pd.DataFrame:
    interval_curve = build_interval_consumption_curve(period_df)
    if interval_curve.empty:
        return pd.DataFrame(columns=["date", "peak_at", "spotreba_m3", "prutok_m3h", "pocet_mereni"])
    if period.bucket_frequency == "15min":
        return interval_curve

    indexed_curve = interval_curve.set_index("date")
    curve = (
        indexed_curve.resample(period.bucket_frequency)
        .agg(
            spotreba_m3=("spotreba_m3", "sum"),
            prutok_m3h=("prutok_m3h", "max"),
            pocet_mereni=("pocet_mereni", "sum"),
        )
        .reset_index()
    )
    peak_at_series = indexed_curve["prutok_m3h"].resample(period.bucket_frequency).apply(
        lambda values: values.idxmax() if len(values) else pd.NaT
    )
    curve["peak_at"] = peak_at_series.to_numpy()
    curve = curve[curve["pocet_mereni"] > 0].copy()
    curve["spotreba_m3"] = pd.to_numeric(curve["spotreba_m3"], errors="coerce").round(6)
    curve["prutok_m3h"] = pd.to_numeric(curve["prutok_m3h"], errors="coerce").round(6)
    curve["peak_at"] = pd.to_datetime(curve["peak_at"], errors="coerce")
    return curve[["date", "peak_at", "spotreba_m3", "prutok_m3h", "pocet_mereni"]].reset_index(drop=True)


def build_device_summary(period_df: pd.DataFrame) -> pd.DataFrame:
    if period_df.empty:
        return pd.DataFrame(columns=["identifikace", "spotreba_m3", "pocet_mereni"])

    summary = (
        period_df.groupby("identifikace", as_index=False)
        .agg(
            spotreba_m3=("spotreba_m3", "sum"),
            pocet_mereni=("spotreba_m3", "count"),
        )
        .sort_values(["spotreba_m3", "identifikace"], ascending=[False, True])
        .reset_index(drop=True)
    )
    summary["spotreba_m3"] = pd.to_numeric(summary["spotreba_m3"], errors="coerce").fillna(0.0).round(3)
    summary["pocet_mereni"] = summary["pocet_mereni"].astype(int)
    return summary


def summarize_report(
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    *,
    peak_curve_df: pd.DataFrame | None = None,
) -> dict[str, object]:
    total_consumption = round(float(pd.to_numeric(period_df.get("spotreba_m3"), errors="coerce").fillna(0.0).sum()), 3)
    measurement_count = int(len(period_df.index)) if not period_df.empty else 0
    device_count = int(period_df["identifikace"].nunique()) if "identifikace" in period_df.columns and not period_df.empty else 0

    max_source_df = peak_curve_df if isinstance(peak_curve_df, pd.DataFrame) and not peak_curve_df.empty else curve_df
    max_flow_m3h = None
    max_flow_at = None
    if isinstance(max_source_df, pd.DataFrame) and not max_source_df.empty:
        prepared = max_source_df.copy()
        prepared["prutok_m3h"] = pd.to_numeric(prepared["prutok_m3h"], errors="coerce")
        prepared = prepared.dropna(subset=["prutok_m3h"]).copy()
        if not prepared.empty:
            peak_row = prepared.loc[prepared["prutok_m3h"].idxmax()]
            max_flow_m3h = round(float(peak_row["prutok_m3h"]), 3)
            peak_at = peak_row.get("peak_at", peak_row.get("date"))
            if peak_at is not None and not pd.isna(peak_at):
                max_flow_at = pd.to_datetime(peak_at).to_pydatetime()

    return {
        "total_consumption_m3": total_consumption,
        "measurement_count": measurement_count,
        "device_count": device_count,
        "max_flow_m3h": max_flow_m3h,
        "max_flow_at": max_flow_at,
    }


def _build_curve_rows(curve_df: pd.DataFrame) -> tuple[VodomeryCurveRow, ...]:
    return tuple(
        VodomeryCurveRow(
            date=pd.to_datetime(row.date).to_pydatetime(),
            spotreba_m3=round(float(row.spotreba_m3), 3),
            prutok_m3h=round(float(row.prutok_m3h), 3),
            pocet_mereni=int(row.pocet_mereni),
            peak_at=(
                pd.to_datetime(row.peak_at).to_pydatetime()
                if getattr(row, "peak_at", None) is not None and not pd.isna(getattr(row, "peak_at", None))
                else None
            ),
        )
        for row in curve_df.itertuples(index=False)
    )


def build_curve_layer(
    *,
    index: int,
    curve_df: pd.DataFrame,
    selected_identifications: Iterable[str] | None = None,
    key: str | None = None,
    label: str | None = None,
    color: str | None = None,
) -> VodomeryCurveLayer:
    layer_index = max(int(index), 0)
    resolved_color = _normalize_curve_color(color, fallback=curve_layer_color(layer_index))
    return VodomeryCurveLayer(
        key=key or f"curve-layer-{layer_index}",
        label=label or curve_layer_label(layer_index),
        color=resolved_color,
        fill_color=curve_layer_fill_color(layer_index, resolved_color if color is not None else None),
        curve_rows=_build_curve_rows(curve_df),
        selected_identifications=_normalize_selected_identifications(selected_identifications),
    )


def coerce_curve_layers(curve_layers: Iterable[object] | None) -> tuple[VodomeryCurveLayer, ...]:
    normalized_layers: list[VodomeryCurveLayer] = []
    for index, layer in enumerate(curve_layers or ()):
        if layer is None:
            continue
        normalized_layers.append(
            VodomeryCurveLayer(
                key=str(getattr(layer, "key", f"curve-layer-{index}")),
                label=str(getattr(layer, "label", curve_layer_label(index))),
                color=_normalize_curve_color(getattr(layer, "color", None), fallback=curve_layer_color(index)),
                fill_color=_normalize_curve_color(
                    getattr(layer, "fill_color", None),
                    fallback=curve_layer_fill_color(index, getattr(layer, "color", None)),
                ),
                curve_rows=tuple(getattr(layer, "curve_rows", ()) or ()),
                selected_identifications=_normalize_selected_identifications(
                    getattr(layer, "selected_identifications", ())
                ),
            )
        )
    return tuple(normalized_layers)


def _resolve_report_curve_layers(report: VodomeryPdfReport) -> tuple[VodomeryCurveLayer, ...]:
    if report.curve_layers:
        return coerce_curve_layers(report.curve_layers)
    return (
        VodomeryCurveLayer(
            key="curve-layer-0",
            label=curve_layer_label(0),
            color=curve_layer_color(0),
            fill_color=curve_layer_fill_color(0),
            curve_rows=tuple(report.curve_rows),
            selected_identifications=_normalize_selected_identifications(report.selected_identifications),
        ),
    )


def build_vodomery_pdf_report(
    *,
    period: VodomeryReportPeriod,
    period_label: str,
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    device_summary_df: pd.DataFrame,
    curve_layers: Iterable[object] | None = None,
    peak_curve_df: pd.DataFrame | None = None,
    generated_at: datetime.datetime | None = None,
    selected_identifications: Iterable[str] | None = None,
    available_identification_count: int | None = None,
) -> VodomeryPdfReport:
    summary = summarize_report(period_df, curve_df, peak_curve_df=peak_curve_df)
    return VodomeryPdfReport(
        generated_at=generated_at or datetime.datetime.now(),
        period=period,
        period_label=period_label,
        total_consumption_m3=float(summary["total_consumption_m3"]),
        measurement_count=int(summary["measurement_count"]),
        device_count=int(summary["device_count"]),
        max_flow_m3h=summary["max_flow_m3h"],
        max_flow_at=summary["max_flow_at"],
        curve_rows=_build_curve_rows(curve_df),
        device_rows=tuple(
            VodomeryDeviceSummaryRow(
                identifikace=str(row.identifikace),
                spotreba_m3=round(float(row.spotreba_m3), 3),
                pocet_mereni=int(row.pocet_mereni),
            )
            for row in device_summary_df.itertuples(index=False)
        ),
        curve_layers=coerce_curve_layers(curve_layers),
        selected_identifications=_normalize_selected_identifications(selected_identifications),
        available_identification_count=available_identification_count,
    )


def build_vodomery_report_pdf_filename(report: VodomeryPdfReport) -> str:
    prefix_by_kind = {
        "day": "Denni",
        "week": "Tydenni",
        "month": "Mesicni",
    }
    prefix = prefix_by_kind.get(report.period.kind, "Vodomery")
    return f"{prefix} report vodomeru - {report.period.date_range_label}.pdf"


def _build_metric_card_html(label: str, value: str, detail: str | None = None, *, primary: bool = False) -> str:
    class_names = ["metric-card"]
    if primary:
        class_names.append("metric-card-primary")
    detail_html = f"<div class='metric-detail'>{escape(detail)}</div>" if detail else ""
    return (
        f"<div class='{' '.join(class_names)}'>"
        f"<div class='metric-label'>{escape(label)}</div>"
        f"<div class='metric-value'>{escape(value)}</div>"
        f"{detail_html}</div>"
    )


def _build_layer_metric_cards_html(report: VodomeryPdfReport) -> str:
    return "".join(
        _build_metric_card_html(
            f"Spotřeba {curve_layer_label(layer_index)}",
            _format_value(
                round(sum(float(row.spotreba_m3 or 0.0) for row in layer.curve_rows), 3),
                unit="m³",
            ),
        )
        for layer_index, layer in enumerate(_resolve_report_curve_layers(report), start=1)
    )


def _resolve_curve_y_axis(max_value: float, *, tick_count: int = 5) -> tuple[float, tuple[float, ...]]:
    safe_max = max(float(max_value or 0.0), 0.0)
    if safe_max <= 0:
        return 1.0, (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)

    rough_step = safe_max / max(tick_count, 1)
    magnitude = 10 ** floor(log10(rough_step)) if rough_step > 0 else 1
    normalized = rough_step / magnitude
    if normalized <= 1:
        nice_step = 1 * magnitude
    elif normalized <= 2:
        nice_step = 2 * magnitude
    elif normalized <= 5:
        nice_step = 5 * magnitude
    else:
        nice_step = 10 * magnitude
    ceiling = ceil(safe_max / nice_step) * nice_step
    ticks = tuple(round(nice_step * index, 3) for index in range(int(round(ceiling / nice_step)) + 1))
    return float(ceiling), ticks


def _curve_label(value: datetime.datetime, period: VodomeryReportPeriod) -> str:
    if period.kind == "day":
        return value.strftime("%H")
    return value.strftime("%d.%m.")


def build_axis_label_format(period: VodomeryReportPeriod) -> str:
    if period.kind == "day":
        return "%H"
    return "%d.%m."


def build_axis_tick_times(period: VodomeryReportPeriod) -> list[datetime.datetime]:
    if period.kind == "day":
        return [period.period_start + datetime.timedelta(hours=hour) for hour in range(24)]
    if period.kind == "week":
        return [period.period_start + datetime.timedelta(days=offset) for offset in range(7)]

    total_days = max((period.period_end - period.period_start).days, 1)
    if total_days <= 10:
        step = 1
    elif total_days <= 20:
        step = 2
    else:
        step = 5
    ticks: list[datetime.datetime] = []
    current = period.period_start
    while current < period.period_end:
        ticks.append(current)
        current += datetime.timedelta(days=step)
    if ticks[-1] != period.period_end - datetime.timedelta(days=1):
        ticks.append(period.period_end - datetime.timedelta(days=1))
    return ticks


def build_axis_grid_times(period: VodomeryReportPeriod) -> list[datetime.datetime]:
    if period.kind == "day":
        return [period.period_start + datetime.timedelta(hours=hour) for hour in range(24)]
    return build_axis_tick_times(period)


def _build_curve_svg(report: VodomeryPdfReport) -> str:
    plotted_curve_layers = tuple(layer for layer in _resolve_report_curve_layers(report) if layer.curve_rows)
    if not plotted_curve_layers:
        return "<div class='chart-empty'>Ve zvoleném období nejsou k dispozici žádná data.</div>"

    anchor_layer = plotted_curve_layers[0]
    width = 980
    height = 360
    margin_left = 58
    margin_right = 16
    margin_top = 18
    margin_bottom = 52
    bottom = height - margin_bottom
    period_start = report.period.period_start
    period_end = report.period.period_end
    total_seconds = max((period_end - period_start).total_seconds(), 1.0)

    all_consumption_values = [row.spotreba_m3 for layer in plotted_curve_layers for row in layer.curve_rows]
    max_consumption = max(all_consumption_values) if all_consumption_values else 0.0
    y_ceiling, y_ticks = _resolve_curve_y_axis(max_consumption)

    def x_position_for_timestamp(value: datetime.datetime) -> float:
        seconds = (value - period_start).total_seconds()
        usable_width = width - margin_left - margin_right
        return margin_left + max(min(seconds / total_seconds, 1.0), 0.0) * usable_width

    def y_position(value: float) -> float:
        usable_height = bottom - margin_top
        ratio = 0.0 if y_ceiling <= 0 else max(min(value / y_ceiling, 1.0), 0.0)
        return bottom - ratio * usable_height

    x_tick_times = build_axis_tick_times(report.period)
    x_grid_times = build_axis_grid_times(report.period)
    x_grid = "".join(
        f"<line x1='{x_position_for_timestamp(value):.2f}' y1='{margin_top}' x2='{x_position_for_timestamp(value):.2f}' y2='{bottom}' "
        "stroke='#d1d5db' stroke-width='1' stroke-dasharray='4 4' />"
        for value in x_grid_times
    )
    x_labels = "".join(
        f"<text x='{x_position_for_timestamp(value):.2f}' y='{bottom + 18}' text-anchor='middle' class='chart-axis-label'>{escape(_curve_label(value, report.period))}</text>"
        for value in x_tick_times
    )
    y_grid = "".join(
        f"<line x1='{margin_left}' y1='{y_position(value):.2f}' x2='{width - margin_right}' y2='{y_position(value):.2f}' "
        "stroke='#e5e7eb' stroke-width='1' />"
        f"<text x='{margin_left - 8}' y='{y_position(value) + 3:.2f}' text-anchor='end' class='chart-axis-label'>{escape(_format_value(value, unit='m³', digits=1))}</text>"
        for value in y_ticks
    )

    points_by_layer: list[tuple[VodomeryCurveLayer, list[tuple[float, float]]]] = []
    for layer in plotted_curve_layers:
        points = [
            (x_position_for_timestamp(row.date), y_position(row.spotreba_m3))
            for row in layer.curve_rows
        ]
        points_by_layer.append((layer, points))

    area_paths = "".join(
        (
            f"<path d='M {points[0][0]:.2f} {bottom:.2f} "
            + " ".join(f"L {x:.2f} {y:.2f}" for x, y in points)
            + f" L {points[-1][0]:.2f} {bottom:.2f} Z' fill='{layer.fill_color}' opacity='0.92' />"
        )
        for layer, points in points_by_layer
        if points
    )
    curve_paths = "".join(
        f"<path d='{' '.join(('M' if index == 0 else 'L') + f' {x:.2f} {y:.2f}' for index, (x, y) in enumerate(points))}' "
        f"fill='none' stroke='{layer.color}' stroke-width='2.5' stroke-linejoin='round' stroke-linecap='round' />"
        for layer, points in points_by_layer
        if points
    )
    total_point_count = sum(len(points) for _, points in points_by_layer)
    circle_points = ""
    if total_point_count <= 240:
        circle_points = "".join(
            f"<circle cx='{x:.2f}' cy='{y:.2f}' r='2.2' fill='{layer.color}' />"
            for layer, points in points_by_layer
            for x, y in points
        )

    legend_items = "".join(
        (
            "<span class='chart-line-legend-item'>"
            f"<span class='chart-line-legend-dot' style='background:{layer.color};'></span>"
            f"<span>{escape(curve_layer_legend_label(layer))}</span></span>"
        )
        for layer in plotted_curve_layers
    )

    return (
        "<div class='branch-chart'>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Křivka hodinové spotřeby'>"
        f"{y_grid}{x_grid}"
        f"<line x1='{margin_left}' y1='{bottom}' x2='{width - margin_right}' y2='{bottom}' stroke='#94a3b8' stroke-width='1.2' />"
        f"{area_paths}{curve_paths}{circle_points}{x_labels}"
        f"<text x='{margin_left}' y='{margin_top - 6}' class='chart-axis-label'>Hodinová spotřeba [m³]</text>"
        "</svg>"
        f"<div class='chart-line-legend'>{legend_items}</div>"
        "</div>"
    )


def _build_device_table_html(report: VodomeryPdfReport) -> str:
    if not report.device_rows:
        return "<p class='empty-state'>Ve zvoleném období nebyla nalezena žádná měřidla.</p>"

    rows_html = "".join(
        (
            "<tr>"
            f"<td>{escape(row.identifikace)}</td>"
            f"<td class='numeric'>{escape(_format_value(row.spotreba_m3, unit='m³'))}</td>"
            f"<td class='numeric'>{row.pocet_mereni}</td>"
            "</tr>"
        )
        for row in report.device_rows
    )
    total_row_html = (
        "<tr class='balance-total-row'>"
        "<td><strong>Celkem</strong></td>"
        f"<td class='numeric'><strong>{escape(_format_value(report.total_consumption_m3, unit='m³'))}</strong></td>"
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


def build_vodomery_report_html(report: VodomeryPdfReport) -> str:
    armex_logo_data_uri = _load_image_data_uri(_armex_logo_path())
    chart_svg = _build_curve_svg(report)
    selection_summary = describe_selected_identifications(
        report.selected_identifications,
        total_available_count=report.available_identification_count,
        preview_limit=None,
        collapse_full_selection=False,
    )
    additional_layer_meta_html = "".join(
        (
            f"<div class='report-meta'><strong>{escape(layer.label)}:</strong> "
            f"{escape(describe_selected_identifications(layer.selected_identifications, total_available_count=report.available_identification_count, preview_limit=None, collapse_full_selection=False))}</div>"
        )
        for layer in _resolve_report_curve_layers(report)[1:]
        if layer.selected_identifications
    )
    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Vodoměry | {escape(report.period.label.lower())} report spotřeby</title>
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
      grid-template-columns: minmax(0, 1fr);
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
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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
      flex-wrap: wrap;
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
      <h1>{escape(report.period.label)} report spotřeby vodoměrů</h1>
    </div>
    <div class="page-logo">
      <img src="{armex_logo_data_uri}" alt="ARMEX">
    </div>
    <div class="page-meta">
      <strong>Období:</strong> {escape(report.period.date_range_label)}<br>
      <strong>Vygenerováno:</strong> {escape(_format_datetime(report.generated_at))}<br>
      <strong>Zdroj:</strong> monitoring.Mereni_vodomery_vse
    </div>
  </header>

  <section class="report-section">
    <div class="report-hero">
      <div class="report-title-block">
        <div class="title-eyebrow">Souhrn reportu</div>
        <h2>Křivka hodinové spotřeby</h2>
        <div class="report-meta"><strong>Typ reportu:</strong> {escape(report.period_label)}</div>
        <div class="report-meta"><strong>Odběrná místa:</strong> {escape(selection_summary)}</div>
        {additional_layer_meta_html}
        <div class="report-description">
          Report vychází z provozních měření uložených v PostgreSQL tabulce
          <strong>monitoring.Mereni_vodomery_vse</strong> a sleduje hodinovou kumulaci
          spotřeby a souhrn vybraných odběrných míst.
        </div>
      </div>
    </div>

    <div class="metric-grid">
      {_build_layer_metric_cards_html(report)}
    </div>

    <div class="branch-chart-wrap">
      <div class="branch-subtitle">Hodinová spotřeba</div>
      {chart_svg}
    </div>

    <div class="branch-table-wrap">
      <div class="branch-subtitle">Souhrn měřidel</div>
      {_build_device_table_html(report)}
    </div>
  </section>
</body>
</html>"""


def _load_playwright_api():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise VodomeryDashboardReportError(
            "Playwright je vyzadovan pro render PDF reportu vodomeru."
        ) from exc
    return sync_playwright


def _load_image_data_uri(image_path: Path) -> str:
    if not image_path.exists():
        raise VodomeryDashboardReportError(f"Logo file was not found: {image_path}")
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _armex_logo_path() -> Path:
    return Path.cwd() / "data" / "ARMEX" / "logo_ARMEX.png"


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


def render_vodomery_report_pdf(report: VodomeryPdfReport) -> bytes:
    html = build_vodomery_report_html(report)
    try:
        if sys.platform == "win32":
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(_render_pdf_from_html_windows_worker, html).result()
        return _render_pdf_from_html(html)
    except VodomeryDashboardReportError:
        raise
    except NotImplementedError as exc:
        raise VodomeryDashboardReportError(
            "PDF report se nepodařilo vytvořit kvůli omezení Windows event loopu pro Playwright."
        ) from exc
    except Exception as exc:
        raise VodomeryDashboardReportError(
            f"PDF report se nepodařilo vytvořit: {exc.__class__.__name__}."
        ) from exc
