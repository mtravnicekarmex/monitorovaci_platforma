from __future__ import annotations

import base64
import concurrent.futures
import datetime
import asyncio
import mimetypes
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from html import escape
from math import ceil, floor, isfinite, log10, sqrt
from pathlib import Path
import re
import sys
import warnings

import pandas as pd


REPORT_PERIOD_OPTIONS: dict[str, str] = {
    "day": "Denní",
    "week": "Týdenní",
    "month": "Měsíční",
}
OTE_INTERVAL_HOURS = 0.25

_CURVE_COLOR = "#dc2626"
_CURVE_FILL = "#fee2e2"
_LIMIT_COLOR = "#111827"
CHARGING_STRIPE_FREQUENCY = "2min"
_X_TICK_GRID_COLOR = "#d1d5db"
_X_TICK_GRID_DASHARRAY = "4 4"
_CURVE_LAYER_PALETTE = (
    (_CURVE_COLOR, _CURVE_FILL),
    ("#059669", "#d1fae5"),
    ("#d97706", "#fef3c7"),
    ("#7c3aed", "#ede9fe"),
    ("#0f766e", "#ccfbf1"),
    ("#db2777", "#fce7f3"),
    ("#2563eb", "#dbeafe"),
)
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


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
    peak_at: datetime.datetime | None = None


@dataclass(frozen=True)
class OteCurveLayer:
    key: str
    label: str
    color: str
    fill_color: str
    curve_rows: tuple[OteCurveRow, ...]
    selected_identifications: tuple[str, ...] = ()


@dataclass(frozen=True)
class OteDeviceSummaryRow:
    identifikace: str
    spotreba_kwh: float
    pocet_mereni: int
    summary_row: bool = False


@dataclass(frozen=True)
class OteExceedanceRow:
    date: datetime.datetime
    odber_kw: float
    prekroceni_kw: float


@dataclass(frozen=True)
class OteChargeOverlayRow:
    id_relace: str
    overlay_start: datetime.datetime
    overlay_end: datetime.datetime
    midpoint_at: datetime.datetime
    lane: int
    duration_line: str
    kwh_line: str
    speed_line: str


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
    curve_layers: tuple[OteCurveLayer, ...] = ()
    charge_overlay_rows: tuple[OteChargeOverlayRow, ...] = ()
    selected_identifications: tuple[str, ...] = ()
    available_identification_count: int | None = None


def _format_charge_overlay_value(value: object, *, unit: str = "", digits: int = 3) -> str:
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
    suffix = f" {unit}" if unit else ""
    return f"{numeric_value:.{digits}f}{suffix}"


def _format_charge_overlay_duration(value: object) -> str:
    try:
        total_minutes = max(int(round(float(value or 0))), 0)
    except (TypeError, ValueError):
        return "-"
    return f"{total_minutes} min"


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
            bucket_frequency="h",
            bucket_label="hodina",
        )

    raise ValueError(f"Neznamy typ reportu: {period_kind}")


def filter_measurements_for_period(df: pd.DataFrame, period: OteReportPeriod) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    date_series = pd.to_datetime(df["date"], errors="coerce")
    return df.loc[(date_series >= period.period_start) & (date_series < period.period_end)].copy()


def _bucket_hours(period: OteReportPeriod) -> float:
    if period.bucket_frequency == "15min":
        return OTE_INTERVAL_HOURS
    if period.bucket_frequency == "h":
        return 1.0
    if period.bucket_frequency == "D":
        return 24.0
    return 1.0


def build_interval_consumption_curve(period_df: pd.DataFrame) -> pd.DataFrame:
    if period_df.empty:
        return pd.DataFrame(columns=["date", "peak_at", "spotreba_kwh", "odber_kw", "pocet_mereni"])

    prepared = period_df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared["spotreba_kwh"] = pd.to_numeric(prepared["spotreba_kwh"], errors="coerce").fillna(0.0)
    prepared = prepared.dropna(subset=["date"]).copy()
    if prepared.empty:
        return pd.DataFrame(columns=["date", "peak_at", "spotreba_kwh", "odber_kw", "pocet_mereni"])

    curve = (
        prepared.groupby("date", as_index=False)
        .agg(
            spotreba_kwh=("spotreba_kwh", "sum"),
            pocet_mereni=("spotreba_kwh", "count"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )
    curve["spotreba_kwh"] = curve["spotreba_kwh"].round(6)
    curve["odber_kw"] = (curve["spotreba_kwh"] / OTE_INTERVAL_HOURS).round(6)
    curve["peak_at"] = curve["date"]
    return curve[["date", "peak_at", "spotreba_kwh", "odber_kw", "pocet_mereni"]].copy()


def build_consumption_curve(period_df: pd.DataFrame, period: OteReportPeriod) -> pd.DataFrame:
    interval_curve = build_interval_consumption_curve(period_df)
    if interval_curve.empty:
        return pd.DataFrame(columns=["date", "peak_at", "spotreba_kwh", "odber_kw", "pocet_mereni"])
    if period.bucket_frequency == "15min":
        return interval_curve

    indexed_curve = interval_curve.set_index("date")
    curve = (
        indexed_curve.resample(period.bucket_frequency)
        .agg(
            spotreba_kwh=("spotreba_kwh", "sum"),
            odber_kw=("odber_kw", "max"),
            pocet_mereni=("pocet_mereni", "sum"),
        )
        .reset_index()
    )
    peak_at_series = indexed_curve["odber_kw"].resample(period.bucket_frequency).apply(
        lambda values: values.idxmax() if len(values) else pd.NaT
    )
    curve["peak_at"] = peak_at_series.to_numpy()
    curve = curve[curve["pocet_mereni"] > 0].copy()
    curve["spotreba_kwh"] = pd.to_numeric(curve["spotreba_kwh"], errors="coerce").round(6)
    curve["odber_kw"] = pd.to_numeric(curve["odber_kw"], errors="coerce").round(6)
    curve["peak_at"] = pd.to_datetime(curve["peak_at"], errors="coerce")
    return curve[["date", "peak_at", "spotreba_kwh", "odber_kw", "pocet_mereni"]].reset_index(drop=True)


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


def build_layer_consumption_summary(curve_layers: Iterable[OteCurveLayer]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for layer in coerce_curve_layers(curve_layers):
        if not layer.curve_rows:
            continue
        rows.append(
            {
                "identifikace": curve_layer_legend_label(layer),
                "spotreba_kwh": round(sum(float(row.spotreba_kwh) for row in layer.curve_rows), 3),
                "pocet_mereni": int(sum(int(row.pocet_mereni) for row in layer.curve_rows)),
                "summary_row": True,
            }
        )
    return pd.DataFrame(rows, columns=["identifikace", "spotreba_kwh", "pocet_mereni", "summary_row"])


def build_device_summary_with_layer_totals(
    device_summary_df: pd.DataFrame,
    curve_layers: Iterable[OteCurveLayer],
) -> pd.DataFrame:
    del device_summary_df
    return build_layer_consumption_summary(curve_layers)


def prepare_charge_session_overlays(
    charge_sessions_df: pd.DataFrame,
    *,
    period_start: datetime.datetime,
    period_end: datetime.datetime,
) -> pd.DataFrame:
    if charge_sessions_df.empty:
        return pd.DataFrame(
            columns=[
                "id_relace",
                "lokace",
                "started_at",
                "ended_at",
                "overlay_start",
                "overlay_end",
                "midpoint_at",
                "duration_minutes",
                "duration_label",
                "kwh",
                "kwh_label",
                "rychlost_nabijeni",
                "speed_label",
                "annotation_label",
                "duration_line",
                "kwh_line",
                "speed_line",
                "lane",
                "lane_label",
            ]
        )

    prepared = charge_sessions_df.copy()
    for column in ("started_at", "ended_at"):
        prepared[column] = pd.to_datetime(prepared[column], errors="coerce")
    for column in ("kwh", "rychlost_nabijeni"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared["id_relace"] = prepared.get("id_relace", pd.Series(dtype="string")).astype("string")
    prepared["lokace"] = prepared.get("lokace", pd.Series(dtype="string")).astype("string")
    prepared = prepared.dropna(subset=["started_at", "ended_at"]).copy()
    prepared = prepared.loc[
        (prepared["started_at"] < period_end) & (prepared["ended_at"] > period_start)
    ].copy()
    if prepared.empty:
        return pd.DataFrame(
            columns=[
                "id_relace",
                "lokace",
                "started_at",
                "ended_at",
                "overlay_start",
                "overlay_end",
                "midpoint_at",
                "duration_minutes",
                "duration_label",
                "kwh",
                "kwh_label",
                "rychlost_nabijeni",
                "speed_label",
                "annotation_label",
                "duration_line",
                "kwh_line",
                "speed_line",
                "lane",
                "lane_label",
            ]
        )

    prepared["overlay_start"] = prepared["started_at"].clip(lower=period_start)
    prepared["overlay_end"] = prepared["ended_at"].clip(upper=period_end)
    prepared = prepared.loc[prepared["overlay_end"] > prepared["overlay_start"]].copy()
    prepared = prepared.sort_values(["overlay_start", "overlay_end", "id_relace"]).reset_index(drop=True)
    if prepared.empty:
        return pd.DataFrame(
            columns=[
                "id_relace",
                "lokace",
                "started_at",
                "ended_at",
                "overlay_start",
                "overlay_end",
                "midpoint_at",
                "duration_minutes",
                "duration_label",
                "kwh",
                "kwh_label",
                "rychlost_nabijeni",
                "speed_label",
                "annotation_label",
                "duration_line",
                "kwh_line",
                "speed_line",
                "lane",
                "lane_label",
            ]
        )

    prepared["duration_minutes"] = (
        (prepared["ended_at"] - prepared["started_at"]).dt.total_seconds().div(60).clip(lower=0).round(1)
    )
    prepared["duration_label"] = prepared["duration_minutes"].map(_format_charge_overlay_duration)
    prepared["kwh_label"] = prepared["kwh"].map(lambda value: _format_charge_overlay_value(value, unit="kWh"))
    prepared["speed_label"] = prepared["rychlost_nabijeni"].map(
        lambda value: _format_charge_overlay_value(value, unit="kW")
    )
    prepared["annotation_label"] = prepared.apply(
        lambda row: (
            f"Trvání {row['duration_label']} | "
            f"Odebráno {row['kwh_label']} | "
            f"Rychlost {row['speed_label']}"
        ),
        axis=1,
    )
    prepared["duration_line"] = prepared["duration_label"]
    prepared["kwh_line"] = prepared["kwh_label"]
    prepared["speed_line"] = prepared["speed_label"]
    prepared["midpoint_at"] = prepared["overlay_start"] + (
        prepared["overlay_end"] - prepared["overlay_start"]
    ) / 2

    lane_end_times: list[pd.Timestamp] = []
    lane_values: list[int] = []
    for row in prepared.itertuples(index=False):
        assigned_lane = None
        overlay_start = pd.Timestamp(row.overlay_start)
        overlay_end = pd.Timestamp(row.overlay_end)
        for lane_index, lane_end in enumerate(lane_end_times):
            if overlay_start >= lane_end:
                assigned_lane = lane_index
                lane_end_times[lane_index] = overlay_end
                break
        if assigned_lane is None:
            assigned_lane = len(lane_end_times)
            lane_end_times.append(overlay_end)
        lane_values.append(assigned_lane)

    prepared["lane"] = lane_values
    prepared["lane_label"] = prepared["lane"].map(lambda lane: f"Relace {int(lane) + 1}")
    return prepared[
        [
            "id_relace",
            "lokace",
            "started_at",
            "ended_at",
            "overlay_start",
            "overlay_end",
            "midpoint_at",
            "duration_minutes",
            "duration_label",
            "kwh",
            "kwh_label",
            "rychlost_nabijeni",
            "speed_label",
            "annotation_label",
            "duration_line",
            "kwh_line",
            "speed_line",
            "lane",
            "lane_label",
        ]
    ].copy()


def build_charge_session_stripe_dataframe(
    overlay_df: pd.DataFrame,
    *,
    curve_df: pd.DataFrame | None = None,
    stripe_frequency: str = CHARGING_STRIPE_FREQUENCY,
) -> pd.DataFrame:
    if overlay_df.empty:
        return pd.DataFrame(columns=["id_relace", "stripe_at", "stripe_odber_kw", "zero_kw"])

    curve_points: list[tuple[pd.Timestamp, float]] = []
    if curve_df is not None and not curve_df.empty:
        prepared_curve = curve_df.copy()
        prepared_curve["date"] = pd.to_datetime(prepared_curve["date"], errors="coerce")
        prepared_curve["odber_kw"] = pd.to_numeric(prepared_curve["odber_kw"], errors="coerce")
        prepared_curve = prepared_curve.dropna(subset=["date", "odber_kw"]).sort_values("date").reset_index(drop=True)
        curve_points = [
            (pd.Timestamp(row.date), float(row.odber_kw))
            for row in prepared_curve.itertuples(index=False)
        ]

    def interpolate_odber_kw(target_time: pd.Timestamp) -> float | None:
        if not curve_points:
            return None
        if len(curve_points) == 1:
            return curve_points[0][1]
        if target_time <= curve_points[0][0]:
            return curve_points[0][1]
        if target_time >= curve_points[-1][0]:
            return curve_points[-1][1]
        for index in range(1, len(curve_points)):
            left_time, left_value = curve_points[index - 1]
            right_time, right_value = curve_points[index]
            if target_time <= right_time:
                total_seconds = (right_time - left_time).total_seconds()
                if total_seconds <= 0:
                    return right_value
                offset_seconds = (target_time - left_time).total_seconds()
                ratio = offset_seconds / total_seconds
                return left_value + (right_value - left_value) * ratio
        return curve_points[-1][1]

    stripe_rows: list[dict[str, object]] = []
    for row in overlay_df.itertuples(index=False):
        overlay_start = pd.Timestamp(row.overlay_start)
        overlay_end = pd.Timestamp(row.overlay_end)
        stripe_times = pd.date_range(start=overlay_start, end=overlay_end, freq=stripe_frequency, inclusive="left")
        if len(stripe_times) == 0:
            stripe_times = pd.DatetimeIndex([overlay_start])
        for stripe_at in stripe_times:
            stripe_rows.append(
                {
                    "id_relace": row.id_relace,
                    "stripe_at": stripe_at.to_pydatetime(),
                    "stripe_odber_kw": interpolate_odber_kw(pd.Timestamp(stripe_at)),
                    "zero_kw": 0.0,
                }
            )
    return pd.DataFrame(stripe_rows)


def summarize_report(
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    *,
    peak_curve_df: pd.DataFrame | None = None,
) -> dict[str, object]:
    total_consumption = 0.0
    measurement_count = 0
    device_count = 0
    if not period_df.empty:
        total_consumption = round(float(pd.to_numeric(period_df["spotreba_kwh"], errors="coerce").fillna(0.0).sum()), 3)
        measurement_count = int(len(period_df))
        device_count = int(period_df["identifikace"].nunique())

    max_power_kw = None
    max_power_at = None
    peak_source_df = curve_df if peak_curve_df is None else peak_curve_df
    if not peak_source_df.empty:
        power_series = pd.to_numeric(peak_source_df["odber_kw"], errors="coerce")
        max_index = power_series.idxmax()
        max_power_kw = round(float(peak_source_df.loc[max_index, "odber_kw"]), 3)
        peak_timestamp = peak_source_df.loc[max_index, "peak_at"] if "peak_at" in peak_source_df.columns else peak_source_df.loc[max_index, "date"]
        max_power_at = pd.to_datetime(peak_timestamp).to_pydatetime()

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
    timestamp_column = "peak_at" if "peak_at" in prepared.columns else "date"
    prepared["prekroceni_kw"] = (prepared["odber_kw"] - float(reserved_power_kw)).round(3)
    result = prepared.loc[prepared["prekroceni_kw"] > 0, [timestamp_column, "odber_kw", "prekroceni_kw"]].copy()
    return result.rename(columns={timestamp_column: "date"}).reset_index(drop=True)


def describe_selected_identifications(
    selected_identifications: Iterable[str] | tuple[str, ...],
    *,
    total_available_count: int | None = None,
    preview_limit: int | None = 5,
    collapse_full_selection: bool = True,
) -> str:
    normalized = tuple(
        str(item).strip()
        for item in selected_identifications
        if item is not None and str(item).strip()
    )
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


def curve_layer_legend_label(layer: OteCurveLayer) -> str:
    selected_identifications = _normalize_selected_identifications(layer.selected_identifications)
    if selected_identifications:
        return ", ".join(selected_identifications)
    return layer.label


def curve_layer_label(index: int) -> str:
    if index <= 0:
        return "Hlavní výběr"
    return f"Vrstva {index}"


def curve_layer_color(index: int) -> str:
    return _CURVE_LAYER_PALETTE[index % len(_CURVE_LAYER_PALETTE)][0]


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


def curve_layer_fill_color(index: int, color: str | None = None) -> str:
    if color is not None:
        return _derive_curve_fill_color(color)
    return _CURVE_LAYER_PALETTE[index % len(_CURVE_LAYER_PALETTE)][1]


def _normalize_selected_identifications(selected_identifications: Iterable[str] | None) -> tuple[str, ...]:
    return tuple(
        str(item).strip()
        for item in (selected_identifications or ())
        if item is not None and str(item).strip()
    )


def _build_curve_rows(curve_df: pd.DataFrame) -> tuple[OteCurveRow, ...]:
    return tuple(
        OteCurveRow(
            date=pd.to_datetime(row.date).to_pydatetime(),
            spotreba_kwh=round(float(row.spotreba_kwh), 3),
            odber_kw=round(float(row.odber_kw), 3),
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
) -> OteCurveLayer:
    layer_index = max(int(index), 0)
    resolved_color = _normalize_curve_color(color, fallback=curve_layer_color(layer_index))
    return OteCurveLayer(
        key=key or f"curve-layer-{layer_index}",
        label=label or curve_layer_label(layer_index),
        color=resolved_color,
        fill_color=curve_layer_fill_color(layer_index, resolved_color if color is not None else None),
        curve_rows=_build_curve_rows(curve_df),
        selected_identifications=_normalize_selected_identifications(selected_identifications),
    )


def coerce_curve_layers(curve_layers: Iterable[object] | None) -> tuple[OteCurveLayer, ...]:
    normalized_layers: list[OteCurveLayer] = []
    for index, layer in enumerate(curve_layers or ()):
        if layer is None:
            continue
        normalized_layers.append(
            OteCurveLayer(
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


def _resolve_report_curve_layers(report: OtePdfReport) -> tuple[OteCurveLayer, ...]:
    if report.curve_layers:
        return coerce_curve_layers(report.curve_layers)
    return (
        OteCurveLayer(
            key="curve-layer-0",
            label=curve_layer_label(0),
            color=curve_layer_color(0),
            fill_color=curve_layer_fill_color(0),
            curve_rows=report.curve_rows,
            selected_identifications=report.selected_identifications,
        ),
    )


def build_ote_pdf_report(
    *,
    period: OteReportPeriod,
    period_label: str,
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    device_summary_df: pd.DataFrame,
    reserved_power_kw: float | None,
    curve_layers: Iterable[OteCurveLayer] | None = None,
    peak_curve_df: pd.DataFrame | None = None,
    exceedance_curve_df: pd.DataFrame | None = None,
    charge_overlay_df: pd.DataFrame | None = None,
    generated_at: datetime.datetime | None = None,
    selected_identifications: Iterable[str] | None = None,
    available_identification_count: int | None = None,
) -> OtePdfReport:
    summary = summarize_report(period_df, curve_df, peak_curve_df=peak_curve_df)
    exceedance_df = build_threshold_exceedance(
        curve_df if exceedance_curve_df is None else exceedance_curve_df,
        reserved_power_kw,
    )
    normalized_selected_identifications = _normalize_selected_identifications(selected_identifications)

    resolved_curve_layers = tuple(curve_layers or ())
    if not resolved_curve_layers:
        resolved_curve_layers = (
            build_curve_layer(
                index=0,
                curve_df=curve_df,
                selected_identifications=normalized_selected_identifications,
            ),
        )

    curve_rows = resolved_curve_layers[0].curve_rows if resolved_curve_layers else _build_curve_rows(curve_df)
    report_device_summary_df = build_device_summary_with_layer_totals(
        device_summary_df,
        resolved_curve_layers,
    )
    device_rows = tuple(
        OteDeviceSummaryRow(
            identifikace=str(row.identifikace),
            spotreba_kwh=round(float(row.spotreba_kwh), 3),
            pocet_mereni=int(row.pocet_mereni),
            summary_row=bool(getattr(row, "summary_row", False)),
        )
        for row in report_device_summary_df.itertuples(index=False)
    )
    exceedance_rows = tuple(
        OteExceedanceRow(
            date=pd.to_datetime(row.date).to_pydatetime(),
            odber_kw=round(float(row.odber_kw), 3),
            prekroceni_kw=round(float(row.prekroceni_kw), 3),
        )
        for row in exceedance_df.itertuples(index=False)
    )
    overlay_rows = tuple(
        OteChargeOverlayRow(
            id_relace=str(row.id_relace),
            overlay_start=pd.to_datetime(row.overlay_start).to_pydatetime(),
            overlay_end=pd.to_datetime(row.overlay_end).to_pydatetime(),
            midpoint_at=pd.to_datetime(row.midpoint_at).to_pydatetime(),
            lane=int(row.lane),
            duration_line=str(row.duration_line),
            kwh_line=str(row.kwh_line),
            speed_line=str(row.speed_line),
        )
        for row in (charge_overlay_df if charge_overlay_df is not None else pd.DataFrame()).itertuples(index=False)
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
        curve_layers=resolved_curve_layers,
        charge_overlay_rows=overlay_rows,
        selected_identifications=normalized_selected_identifications,
        available_identification_count=available_identification_count,
    )


def build_ote_report_pdf_filename(report: OtePdfReport) -> str:
    prefix_by_kind = {
        "day": "Denni",
        "week": "Tydenni",
        "month": "Mesicni",
    }
    prefix = prefix_by_kind.get(report.period.kind, "Report")
    return f"{prefix} report elektromeru - {report.period.date_range_label}.pdf"


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


def _resolve_curve_y_axis(max_value: float, *, tick_count: int = 5) -> tuple[float, tuple[float, ...]]:
    interval_count = max(int(tick_count) - 1, 1)
    if max_value <= 0:
        axis_max = 1.0
        step = axis_max / interval_count
        return axis_max, tuple(step * index for index in range(interval_count + 1))

    raw_step = max_value / interval_count
    magnitude = 10 ** floor(log10(raw_step))
    error = raw_step / magnitude
    if error >= sqrt(50):
        factor = 10
    elif error >= sqrt(10):
        factor = 5
    elif error >= sqrt(2):
        factor = 2
    else:
        factor = 1

    step = factor * magnitude
    axis_max = step * ceil(max_value / step)
    tick_total = max(int(round(axis_max / step)), 1)
    return axis_max, tuple(step * index for index in range(tick_total + 1))


def _curve_label(value: datetime.datetime, period: OteReportPeriod) -> str:
    if period.kind == "day":
        return value.strftime("%H:%M")
    if period.kind in {"week", "month"}:
        return value.strftime("%d.%m. %H:%M")
    return value.strftime("%d.%m.")


def _axis_label(value: datetime.datetime, *, period: OteReportPeriod, tick_step: datetime.timedelta) -> str:
    if period.kind == "day":
        return value.strftime("%H:%M")
    if tick_step >= datetime.timedelta(days=1):
        return value.strftime("%d.%m.")
    return _curve_label(value, period)


def build_axis_label_format(period: OteReportPeriod) -> str:
    if period.kind == "day":
        return "%H:%M"
    return "%d.%m."


def build_axis_tick_times(period: OteReportPeriod) -> list[datetime.datetime]:
    if period.kind == "day":
        tick_step = datetime.timedelta(hours=1)
    elif period.kind == "week":
        tick_step = datetime.timedelta(days=1)
    else:
        tick_step = datetime.timedelta(days=1)

    tick_times: list[datetime.datetime] = []
    current_tick = period.period_start
    while current_tick < period.period_end:
        tick_times.append(current_tick)
        current_tick += tick_step
    return tick_times


def _build_curve_svg(report: OtePdfReport) -> str:
    resolved_curve_layers = _resolve_report_curve_layers(report)
    plotted_curve_layers = tuple(layer for layer in resolved_curve_layers if layer.curve_rows)
    if not plotted_curve_layers:
        return "<div class='chart-empty'>Pro zvolené období nejsou k dispozici data pro křivku odběru.</div>"

    width = 920
    margin_left = 58
    margin_right = 18
    margin_top = 18
    overlay_lane_count = max((row.lane for row in report.charge_overlay_rows), default=-1) + 1
    overlay_text_height = overlay_lane_count * 34 if overlay_lane_count > 0 else 0
    margin_bottom = 54 + overlay_text_height
    height = 300 + overlay_text_height
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    bottom = margin_top + plot_height

    peak_value = max(row.odber_kw for layer in plotted_curve_layers for row in layer.curve_rows)
    if report.reserved_power_kw is not None and report.reserved_power_kw > 0:
        peak_value = max(peak_value, float(report.reserved_power_kw))
    axis_max, tick_values = _resolve_curve_y_axis(peak_value)

    period_start = report.period.period_start
    period_duration_seconds = max((report.period.period_end - report.period.period_start).total_seconds(), 1.0)
    anchor_point_count = len(plotted_curve_layers[0].curve_rows)

    def x_position_for_timestamp(value: datetime.datetime) -> float:
        if anchor_point_count == 1:
            return margin_left + plot_width / 2
        offset_seconds = (value - period_start).total_seconds()
        ratio = min(max(offset_seconds / period_duration_seconds, 0.0), 1.0)
        return margin_left + plot_width * ratio

    def y_position(value: float) -> float:
        if axis_max <= 0:
            return float(bottom)
        return bottom - (value / axis_max) * plot_height

    points_by_layer = [
        (layer, [(x_position_for_timestamp(row.date), y_position(row.odber_kw), row) for row in layer.curve_rows])
        for layer in plotted_curve_layers
    ]
    anchor_layer, anchor_points = points_by_layer[0]
    area_paths = "".join(
        (
            f"<path d='{' '.join(['M', f'{points[0][0]:.2f}', f'{bottom:.2f}', 'L'] + [f'{x:.2f} {y:.2f}' for x, y, _ in points] + [f'L {points[-1][0]:.2f} {bottom:.2f}', 'Z'])}' "
            f"fill='{layer.fill_color}' opacity='0.88' />"
        )
        for layer, points in points_by_layer
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
    axis_label_y = bottom + 18
    axis_tick_times = build_axis_tick_times(report.period)
    axis_tick_step = (
        axis_tick_times[1] - axis_tick_times[0]
        if len(axis_tick_times) > 1
        else datetime.timedelta(hours=4 if report.period.kind == "day" else 24)
    )
    x_grid = "".join(
        (
            f"<line x1='{x_position_for_timestamp(tick_time):.2f}' y1='{margin_top}' "
            f"x2='{x_position_for_timestamp(tick_time):.2f}' y2='{bottom:.2f}' "
            f"stroke='{_X_TICK_GRID_COLOR}' stroke-width='1' stroke-dasharray='{_X_TICK_GRID_DASHARRAY}' />"
        )
        for tick_time in axis_tick_times
    )
    x_labels = "".join(
        (
            f"<line x1='{x_position_for_timestamp(tick_time):.2f}' y1='{bottom}' x2='{x_position_for_timestamp(tick_time):.2f}' y2='{bottom + 4}' "
            "stroke='#94a3b8' stroke-width='1' />"
            f"<text x='{x_position_for_timestamp(tick_time):.2f}' y='{axis_label_y}' text-anchor='middle' class='chart-axis-label'>"
            f"{escape(_axis_label(tick_time, period=report.period, tick_step=axis_tick_step))}</text>"
        )
        for tick_time in axis_tick_times
    )

    curve_paths = "".join(
        f"<path d='{' '.join((('M' if index == 0 else 'L') + f' {x:.2f} {y:.2f}') for index, (x, y, _) in enumerate(points))}' "
        f"fill='none' stroke='{layer.color}' stroke-width='2.5' stroke-linejoin='round' stroke-linecap='round' />"
        for layer, points in points_by_layer
    )

    total_point_count = sum(len(points) for _, points in points_by_layer)
    circle_points = ""
    if total_point_count <= 240:
        circle_points = "".join(
            f"<circle cx='{x:.2f}' cy='{y:.2f}' r='2.2' fill='{layer.color}' />"
            for layer, points in points_by_layer
            for x, y, _ in points
        )

    point_time_offsets = [
        (row.date - period_start).total_seconds()
        for row in anchor_layer.curve_rows
    ]

    def y_curve_at(value: datetime.datetime) -> float:
        if not anchor_points:
            return float(bottom)
        if len(anchor_points) == 1:
            return anchor_points[0][1]
        target_offset = (value - period_start).total_seconds()
        if target_offset <= point_time_offsets[0]:
            return anchor_points[0][1]
        if target_offset >= point_time_offsets[-1]:
            return anchor_points[-1][1]
        for index in range(1, len(anchor_points)):
            left_offset = point_time_offsets[index - 1]
            right_offset = point_time_offsets[index]
            if target_offset <= right_offset:
                _, left_y, _ = anchor_points[index - 1]
                _, right_y, _ = anchor_points[index]
                if right_offset == left_offset:
                    return right_y
                ratio = (target_offset - left_offset) / (right_offset - left_offset)
                return left_y + (right_y - left_y) * ratio
        return anchor_points[-1][1]

    charge_stripe_lines = ""
    if report.charge_overlay_rows:
        stripe_segments: list[str] = []
        for overlay_row in report.charge_overlay_rows:
            stripe_times = pd.date_range(
                start=overlay_row.overlay_start,
                end=overlay_row.overlay_end,
                freq=CHARGING_STRIPE_FREQUENCY,
                inclusive="left",
            )
            if len(stripe_times) == 0:
                stripe_times = pd.DatetimeIndex([overlay_row.overlay_start])
            for stripe_at in stripe_times:
                stripe_dt = stripe_at.to_pydatetime()
                stripe_x = x_position_for_timestamp(stripe_dt)
                stripe_y = y_curve_at(stripe_dt)
                stripe_segments.append(
                    f"<line x1='{stripe_x:.2f}' y1='{bottom:.2f}' x2='{stripe_x:.2f}' y2='{stripe_y:.2f}' "
                    "stroke='#2563eb' stroke-width='2' opacity='0.22' />"
                )
        charge_stripe_lines = "".join(stripe_segments)

    limit_line = ""
    legend_items = [
        (
            "<span class='chart-line-legend-item'>"
            f"<span class='chart-line-legend-dot' style='background:{layer.color};'></span>"
            f"<span>{escape(curve_layer_legend_label(layer))}</span></span>"
        )
        for layer in plotted_curve_layers
    ]
    if report.charge_overlay_rows:
        legend_items.append(
            "<span class='chart-line-legend-item'>"
            "<span class='chart-line-legend-rule' style='border-top-style:solid;border-top-color:#2563eb;opacity:0.45;'></span>"
            "<span>Nabíjecí relace</span></span>"
        )
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

    overlay_text_svg = ""
    if report.charge_overlay_rows and report.period.kind != "month":
        text_rows = []
        text_start_y = axis_label_y + 16
        for overlay_row in report.charge_overlay_rows:
            text_x = x_position_for_timestamp(overlay_row.midpoint_at)
            lane_y = text_start_y + overlay_row.lane * 34
            text_rows.append(
                (
                    f"<text x='{text_x:.2f}' y='{lane_y:.2f}' text-anchor='middle' fill='#1d4ed8' "
                    "font-size='9.5px' font-family='Segoe UI, Arial, sans-serif'>"
                    f"<tspan x='{text_x:.2f}' dy='0'>{escape(overlay_row.duration_line)}</tspan>"
                    f"<tspan x='{text_x:.2f}' dy='11'>{escape(overlay_row.kwh_line)}</tspan>"
                    f"<tspan x='{text_x:.2f}' dy='11'>{escape(overlay_row.speed_line)}</tspan>"
                    "</text>"
                )
            )
        overlay_text_svg = "".join(text_rows)

    return (
        "<div class='branch-chart'>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='Křivka odběru'>"
        f"{y_grid}"
        f"{x_grid}"
        f"<line x1='{margin_left}' y1='{bottom}' x2='{width - margin_right}' y2='{bottom}' stroke='#94a3b8' stroke-width='1.2' />"
        f"{area_paths}"
        f"{charge_stripe_lines}"
        f"{limit_line}"
        f"{curve_paths}"
        f"{circle_points}"
        f"{overlay_text_svg}"
        f"{x_labels}"
        f"<text x='{margin_left}' y='{margin_top - 6}' class='chart-axis-label'>Odběr [kW]</text>"
        "</svg>"
        f"<div class='chart-line-legend'>{''.join(legend_items)}</div>"
        "</div>"
    )


def _build_device_table_html(report: OtePdfReport) -> str:
    if not report.device_rows:
        return "<p class='empty-state'>Ve zvoleném období nebyla nalezena žádná data vrstev.</p>"

    row_parts: list[str] = []
    for row in report.device_rows:
        is_summary = bool(row.summary_row)
        row_class = " class='balance-total-row'" if is_summary else ""
        identifikace = escape(row.identifikace)
        spotreba = escape(_format_value(row.spotreba_kwh, unit="kWh"))
        if is_summary:
            identifikace = f"<strong>{identifikace}</strong>"
            spotreba = f"<strong>{spotreba}</strong>"
        row_parts.append(
            (
                f"<tr{row_class}>"
                f"<td>{identifikace}</td>"
                f"<td class='numeric'>{spotreba}</td>"
                "</tr>"
            )
        )
    rows_html = "".join(row_parts)
    return (
        "<table class='branch-table'>"
        "<thead><tr>"
        "<th>Vrstva</th>"
        "<th class='numeric'>kWh</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
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
      <strong>Zdroj:</strong> dbo.Mereni_elektromery_BINARY
    </div>
  </header>

  <section class="report-section">
    <div class="report-hero">
      <div class="report-title-block">
        <div class="title-eyebrow">Souhrn reportu</div>
        <h2>Křivka odběru a rezervovaná hladina</h2>
        <div class="report-meta"><strong>Typ reportu:</strong> {escape(report.period_label)}</div>
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
