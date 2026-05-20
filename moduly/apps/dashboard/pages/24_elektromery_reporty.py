from __future__ import annotations

from pathlib import Path
import sys

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import bindparam, text
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.time_semantics import local_datetime_range_to_utc, to_prague_naive
from moduly.apps.dashboard.elektromery_reports import (
    ELECTROMERY_REPORT_DATA_SOURCE_LABEL,
    ElektromeryDashboardReportError,
    OteCurveLayer,
    REPORT_PERIOD_OPTIONS,
    REPORT_SOURCE_BINARY,
    REPORT_SOURCE_SOFTLINK,
    build_axis_label_format,
    build_axis_tick_times,
    build_charge_session_stripe_dataframe,
    build_consumption_curve,
    build_curve_layer,
    build_device_summary,
    build_device_summary_with_layer_totals,
    build_interval_consumption_curve,
    build_ote_pdf_report,
    build_ote_report_pdf_filename,
    build_threshold_exceedance,
    choose_report_measurement_source_for_coverage,
    curve_layer_color,
    curve_layer_legend_label,
    coerce_curve_layers,
    curve_layer_label,
    describe_measurement_intervals,
    describe_selected_identifications,
    ote_records_to_dataframe,
    prepare_charge_session_overlays,
    render_ote_report_pdf,
    resolve_report_period,
    summarize_report,
)
from moduly.apps.dashboard.vodomery_shared import render_page_styles
from core.db.connect import get_session_pg
from moduly.apps.smartfuelpass.database.models import SmartFuelPassRelace


REPORT_RESULT_KEY = "elektromery_reports_result"
SHOW_CHARGING_OVERLAY_KEY = "elektromery_reports_show_charging_overlay"
REPORT_LAYER_COUNT_KEY = "elektromery_reports_layer_count"
REPORT_LAYER_SELECTION_KEY_PREFIX = "elektromery_reports_layer_selection_"
REPORT_LAYER_COLOR_KEY_PREFIX = "elektromery_reports_layer_color_"
REPORT_BINARY_SOURCE_PATTERN = "BINARY_%"
REPORT_FALLBACK_SOURCE = "SOFTLINK"


st.set_page_config(
    page_title="Elektroměry - Reporty",
    page_icon="📈",
    layout="wide",
)


require_page_access("elektromery_reports")


def format_datetime(value: object) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return "-"
    return timestamp.strftime("%d.%m.%Y %H:%M")


def format_energy(value: object, unit: str = "kWh") -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value):
        return "-"
    if abs(numeric_value) < 0.0005:
        numeric_value = 0.0
    return f"{numeric_value:.3f} {unit}"


def report_source_label(source: str | None) -> str:
    if source == REPORT_SOURCE_BINARY:
        return "BINARY_"
    if source == REPORT_SOURCE_SOFTLINK:
        return REPORT_FALLBACK_SOURCE
    return "-"


def _report_source_params() -> dict[str, object]:
    return {
        "binary_source_pattern": REPORT_BINARY_SOURCE_PATTERN,
        "fallback_source": REPORT_FALLBACK_SOURCE,
    }


def _report_allowed_sources_condition() -> str:
    return "(zdroj LIKE :binary_source_pattern OR zdroj = :fallback_source)"


def _report_selected_source_condition(report_source: str) -> str:
    if report_source == REPORT_SOURCE_BINARY:
        return (
            "zdroj LIKE :binary_source_pattern "
            "AND time_utc >= :period_start_utc "
            "AND time_utc < :period_end_utc"
        )
    if report_source == REPORT_SOURCE_SOFTLINK:
        return (
            "zdroj = :fallback_source "
            "AND time_utc > :period_start_utc "
            "AND time_utc - make_interval(mins => COALESCE(interval_minutes, 1440)) < :period_end_utc"
        )
    raise ValueError(f"Neznamy zdroj reportu: {report_source}")


@st.cache_data(ttl=60)
def load_charge_session_overlay_rows(period_start, period_end) -> pd.DataFrame:
    session = get_session_pg()
    try:
        period_start_utc, period_end_utc = local_datetime_range_to_utc(period_start, period_end)
        rows = (
            session.query(
                SmartFuelPassRelace.id_relace,
                SmartFuelPassRelace.started_at,
                SmartFuelPassRelace.ended_at,
                SmartFuelPassRelace.started_at_utc,
                SmartFuelPassRelace.ended_at_utc,
                SmartFuelPassRelace.lokace,
                SmartFuelPassRelace.kwh,
                SmartFuelPassRelace.rychlost_nabijeni,
            )
            .filter(
                SmartFuelPassRelace.started_at_utc < period_end_utc,
                SmartFuelPassRelace.ended_at_utc > period_start_utc,
            )
            .order_by(SmartFuelPassRelace.started_at_utc.asc(), SmartFuelPassRelace.id_relace.asc())
            .all()
        )
        return pd.DataFrame(
            [
                {
                    "id_relace": row.id_relace,
                    "started_at": to_prague_naive(row.started_at_utc) or row.started_at,
                    "ended_at": to_prague_naive(row.ended_at_utc) or row.ended_at,
                    "lokace": row.lokace,
                    "kwh": row.kwh,
                    "rychlost_nabijeni": row.rychlost_nabijeni,
                }
                for row in rows
            ]
        )
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_report_data_bounds() -> dict[str, object]:
    session = get_session_pg()
    try:
        row = session.execute(
            text(
                f"""
                SELECT
                    MIN(time_utc) AS date_min,
                    MAX(time_utc) AS date_max,
                    COUNT(id) AS measurement_count,
                    COUNT(DISTINCT identifikace) AS device_count
                FROM monitoring."Mereni_elektromery_vse"
                WHERE
                    time_utc IS NOT NULL
                    AND identifikace IS NOT NULL
                    AND delta IS NOT NULL
                    AND platne IS TRUE
                    AND {_report_allowed_sources_condition()}
                """
            ),
            _report_source_params(),
        ).mappings().one()
        return {
            "date_min": to_prague_naive(row["date_min"]),
            "date_max": to_prague_naive(row["date_max"]),
            "measurement_count": int(row["measurement_count"] or 0),
            "device_count": int(row["device_count"] or 0),
        }
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_report_identifikace_options() -> tuple[str, ...]:
    session = get_session_pg()
    try:
        rows = session.execute(
            text(
                f"""
                SELECT DISTINCT identifikace
                FROM monitoring."Mereni_elektromery_vse"
                WHERE
                    identifikace IS NOT NULL
                    AND delta IS NOT NULL
                    AND platne IS TRUE
                    AND {_report_allowed_sources_condition()}
                ORDER BY identifikace ASC
                """
            ),
            _report_source_params(),
        ).mappings().all()
        return tuple(
            str(row["identifikace"]).strip()
            for row in rows
            if row["identifikace"] and str(row["identifikace"]).strip()
        )
    finally:
        session.close()


@st.cache_data(ttl=60)
def resolve_report_measurement_source(
    period_start,
    period_end,
    selected_identifications: tuple[str, ...],
) -> str | None:
    normalized_identifications = tuple(
        dict.fromkeys(str(item).strip() for item in selected_identifications if str(item).strip())
    )
    if not normalized_identifications:
        return None

    session = get_session_pg()
    try:
        period_start_utc, period_end_utc = local_datetime_range_to_utc(period_start, period_end)
        statement = text(
            """
            SELECT
                COUNT(DISTINCT identifikace) FILTER (
                    WHERE
                        zdroj LIKE :binary_source_pattern
                        AND time_utc >= :period_start_utc
                        AND time_utc < :period_end_utc
                ) AS binary_identification_count,
                COUNT(DISTINCT identifikace) FILTER (
                    WHERE
                        zdroj = :fallback_source
                        AND time_utc > :period_start_utc
                        AND time_utc - make_interval(mins => COALESCE(interval_minutes, 1440)) < :period_end_utc
                ) AS softlink_identification_count
            FROM monitoring."Mereni_elektromery_vse"
            WHERE
                identifikace IS NOT NULL
                AND delta IS NOT NULL
                AND platne IS TRUE
                AND identifikace IN :selected_identifications
                AND (zdroj LIKE :binary_source_pattern OR zdroj = :fallback_source)
            """
        ).bindparams(bindparam("selected_identifications", expanding=True))
        params = {
            "period_start_utc": period_start_utc,
            "period_end_utc": period_end_utc,
            "selected_identifications": normalized_identifications,
            **_report_source_params(),
        }
        row = session.execute(statement, params).mappings().one()
        return choose_report_measurement_source_for_coverage(
            row["binary_identification_count"],
            row["softlink_identification_count"],
            len(normalized_identifications),
        )
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_report_measurements(
    period_start,
    period_end,
    selected_identifications: tuple[str, ...] | None = None,
    report_source: str | None = None,
) -> pd.DataFrame:
    if selected_identifications is not None and len(selected_identifications) == 0:
        return pd.DataFrame(
            columns=["date", "identifikace", "seriove_cislo", "spotreba_kwh", "interval_minutes", "source_file"]
        )
    if report_source is None:
        return pd.DataFrame(
            columns=["date", "identifikace", "seriove_cislo", "spotreba_kwh", "interval_minutes", "source_file"]
        )

    session = get_session_pg()
    try:
        period_start_utc, period_end_utc = local_datetime_range_to_utc(period_start, period_end)
        source_condition = _report_selected_source_condition(report_source)
        query_text = f"""
            SELECT
                time_utc AT TIME ZONE 'Europe/Prague' AS date,
                identifikace,
                seriove_cislo,
                delta AS spotreba_kwh,
                interval_minutes,
                zdroj AS source_file
            FROM monitoring."Mereni_elektromery_vse"
            WHERE
                identifikace IS NOT NULL
                AND delta IS NOT NULL
                AND platne IS TRUE
                AND {source_condition}
        """
        params = {
            "period_start_utc": period_start_utc,
            "period_end_utc": period_end_utc,
            **_report_source_params(),
        }
        if selected_identifications:
            query_text += " AND identifikace IN :selected_identifications"
            params["selected_identifications"] = tuple(selected_identifications)
        query_text += " ORDER BY time_utc ASC, identifikace ASC"

        statement = text(query_text)
        if selected_identifications:
            statement = statement.bindparams(bindparam("selected_identifications", expanding=True))
        rows = session.execute(statement, params).mappings().all()
        return ote_records_to_dataframe(
            dict(row)
            for row in rows
        )
    finally:
        session.close()


def _layer_selection_key(layer_number: int) -> str:
    return f"{REPORT_LAYER_SELECTION_KEY_PREFIX}{layer_number}"


def _layer_color_key(layer_number: int) -> str:
    return f"{REPORT_LAYER_COLOR_KEY_PREFIX}{layer_number}"


def _normalize_identification_selection(values: object) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set)):
        return ()
    return tuple(str(item).strip() for item in values if item is not None and str(item).strip())


def _curve_layers_to_dataframe(curve_layers: tuple[OteCurveLayer, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for layer in curve_layers:
        for row in layer.curve_rows:
            rows.append(
                {
                    "layer_key": layer.key,
                    "layer_label": layer.label,
                    "layer_legend_label": curve_layer_legend_label(layer),
                    "layer_source": report_source_label(getattr(layer, "measurement_source", None)),
                    "layer_color": layer.color,
                    "date": row.date,
                    "peak_at": row.peak_at if row.peak_at is not None else row.date,
                    "spotreba_kwh": row.spotreba_kwh,
                    "odber_kw": row.odber_kw,
                    "pocet_mereni": row.pocet_mereni,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "layer_key",
            "layer_label",
            "layer_legend_label",
            "layer_source",
            "layer_color",
            "date",
            "peak_at",
            "spotreba_kwh",
            "odber_kw",
            "pocet_mereni",
        ],
    )


def build_curve_chart(
    curve_layers: tuple[OteCurveLayer, ...],
    reserved_power_kw: float | None,
    report_period,
    *,
    hide_x_axis: bool = False,
) -> alt.Chart:
    visible_layers = tuple(layer for layer in coerce_curve_layers(curve_layers) if layer.curve_rows)
    chart_source = _curve_layers_to_dataframe(visible_layers)
    chart_source["spotreba_kwh"] = pd.to_numeric(chart_source["spotreba_kwh"], errors="coerce").round(3)
    chart_source["odber_kw"] = pd.to_numeric(chart_source["odber_kw"], errors="coerce").round(3)
    axis_tick_times = build_axis_tick_times(report_period)
    x_scale = alt.Scale(domain=[report_period.period_start, report_period.period_end])
    peak_tooltip_needed = False
    tooltip_items = [
        alt.Tooltip("layer_legend_label:N", title="Vrstva"),
        alt.Tooltip("layer_source:N", title="Zdroj"),
        alt.Tooltip("date:T", title="Interval"),
        alt.Tooltip("spotreba_kwh:Q", title="Spotřeba [kWh]", format=".3f"),
        alt.Tooltip("odber_kw:Q", title="Odběr [kW]", format=".3f"),
    ]
    if "peak_at" in chart_source.columns:
        chart_source["peak_at"] = pd.to_datetime(chart_source["peak_at"], errors="coerce")
        peak_tooltip_needed = not chart_source["peak_at"].equals(pd.to_datetime(chart_source["date"], errors="coerce"))
        if peak_tooltip_needed:
            tooltip_items.append(alt.Tooltip("peak_at:T", title="Špička v"))

    base = alt.Chart(chart_source).encode(
        x=alt.X(
            "date:T",
            title=None,
            scale=x_scale,
            axis=alt.Axis(
                labels=not hide_x_axis,
                ticks=not hide_x_axis,
                domain=not hide_x_axis,
                values=axis_tick_times,
                format=build_axis_label_format(report_period),
                grid=True,
                gridColor="#d1d5db",
                gridDash=[4, 4],
                labelFlush=False,
            ),
        ),
        tooltip=tooltip_items,
    )
    color_scale = alt.Scale(
        domain=[curve_layer_legend_label(layer) for layer in visible_layers],
        range=[layer.color for layer in visible_layers],
    )
    fill_scale = alt.Scale(
        domain=[curve_layer_legend_label(layer) for layer in visible_layers],
        range=[layer.fill_color for layer in visible_layers],
    )
    line = base.mark_line(strokeWidth=2.6).encode(
        y=alt.Y("odber_kw:Q", title="Odběr [kW]"),
        color=alt.Color("layer_legend_label:N", title=None, scale=color_scale),
    )
    area = base.mark_area(opacity=0.88).encode(
        y=alt.Y("odber_kw:Q", title="Odběr [kW]", stack=None),
        fill=alt.Fill("layer_legend_label:N", title=None, scale=fill_scale, legend=None),
    )
    chart = area + line
    if len(chart_source) <= 240:
        points = base.mark_point(size=24, opacity=0.72).encode(
            y=alt.Y("odber_kw:Q", title="Odběr [kW]"),
            color=alt.Color("layer_legend_label:N", title=None, scale=color_scale, legend=None),
        )
        chart = chart + points
    if reserved_power_kw is not None and reserved_power_kw > 0:
        limit_df = pd.DataFrame({"rezervovana_hladina_kw": [float(reserved_power_kw)]})
        limit = alt.Chart(limit_df).mark_rule(color="#111827", strokeDash=[6, 4], strokeWidth=2).encode(
            y=alt.Y("rezervovana_hladina_kw:Q", title="Odběr [kW]"),
            tooltip=[alt.Tooltip("rezervovana_hladina_kw:Q", title="Rezervovaná hladina [kW]", format=".3f")],
        )
        chart = chart + limit

    return chart.properties(height=360).interactive()


def build_curve_chart_with_charge_overlay(
    curve_layers: tuple[OteCurveLayer, ...],
    primary_curve_df: pd.DataFrame,
    reserved_power_kw: float | None,
    report_period,
    overlay_df: pd.DataFrame,
) -> alt.ConcatChart | alt.Chart:
    if overlay_df.empty or primary_curve_df.empty:
        return build_curve_chart(curve_layers, reserved_power_kw, report_period)

    stripe_df = build_charge_session_stripe_dataframe(overlay_df, curve_df=primary_curve_df)
    top_chart = build_curve_chart(curve_layers, reserved_power_kw, report_period, hide_x_axis=False)

    stripe_layer = alt.Chart(stripe_df).mark_rule(
        color="#2563eb",
        opacity=0.22,
        strokeWidth=2,
    ).encode(
        x=alt.X(
            "stripe_at:T",
            title=None,
            scale=alt.Scale(domain=[report_period.period_start, report_period.period_end]),
        ),
        y=alt.Y("stripe_odber_kw:Q", title="Odběr [kW]"),
        y2="zero_kw:Q",
    )
    layered_top_chart = (top_chart + stripe_layer).properties(height=360)
    if report_period.kind in {"month", "year"}:
        return layered_top_chart

    timeline_source = overlay_df.copy()
    lane_order = [
        lane_label
        for _, lane_label in (
            timeline_source[["lane", "lane_label"]]
            .drop_duplicates()
            .sort_values("lane", ascending=True)
            .itertuples(index=False, name=None)
        )
    ]
    lane_count = max(int(timeline_source["lane"].max()) + 1, 1)
    timeline_height = min(max(44 + lane_count * 42, 72), 280)
    timeline_base = alt.Chart(timeline_source).encode(
        x=alt.X(
            "midpoint_at:T",
            title=None,
            scale=alt.Scale(domain=[report_period.period_start, report_period.period_end]),
            axis=alt.Axis(labels=False, ticks=False, domain=False),
        ),
        y=alt.Y("lane_label:N", sort=lane_order, title=None, axis=None),
        tooltip=[
            alt.Tooltip("started_at:T", title="Začátek"),
            alt.Tooltip("ended_at:T", title="Konec"),
            alt.Tooltip("lokace:N", title="Lokace"),
            alt.Tooltip("duration_label:N", title="Trvání"),
            alt.Tooltip("kwh:Q", title="Odebráno [kWh]", format=".3f"),
            alt.Tooltip("rychlost_nabijeni:Q", title="Rychlost [kW]", format=".3f"),
        ],
    )
    duration_text = timeline_base.mark_text(
        align="center",
        baseline="middle",
        color="#1d4ed8",
        fontSize=10,
        dy=-12,
    ).encode(text="duration_line:N")
    energy_text = timeline_base.mark_text(
        align="center",
        baseline="middle",
        color="#1d4ed8",
        fontSize=10,
        dy=0,
    ).encode(text="kwh_line:N")
    speed_text = timeline_base.mark_text(
        align="center",
        baseline="middle",
        color="#1d4ed8",
        fontSize=10,
        dy=12,
    ).encode(text="speed_line:N")
    timeline_text = (duration_text + energy_text + speed_text).properties(height=timeline_height)
    return alt.vconcat(layered_top_chart, timeline_text).resolve_scale(x="shared")


def render_report_result(
    *,
    report_period,
    period_label: str,
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    curve_layers: tuple[OteCurveLayer, ...],
    interval_curve_df: pd.DataFrame | None = None,
    device_summary_df: pd.DataFrame,
    reserved_power_kw: float | None,
    summary: dict[str, object],
    exceedance_df: pd.DataFrame,
    pdf_bytes: bytes | None,
    pdf_filename: str | None,
    pdf_error: str | None,
    pdf_variants: dict[bool, dict[str, object]] | None = None,
    selected_identifications: tuple[str, ...] = (),
    available_identification_count: int = 0,
    measurement_interval_label: str | None = None,
    report_source: str | None = None,
) -> None:
    del interval_curve_df, pdf_bytes, pdf_filename, pdf_error, pdf_variants
    curve_layers = coerce_curve_layers(curve_layers)
    metric_cols = st.columns(5)
    metric_cols[0].metric("Spotřeba", format_energy(summary["total_consumption_kwh"]))
    metric_cols[1].metric("Max. odběr", format_energy(summary["max_power_kw"], unit="kW"))
    metric_cols[2].metric("Datum maxima", format_datetime(summary["max_power_at"]))
    metric_cols[3].metric("Měřidla", summary["device_count"])
    metric_cols[4].metric("Překročení", len(exceedance_df))
    st.caption(
        f"Hlavní výběr: {describe_selected_identifications(selected_identifications, total_available_count=available_identification_count, collapse_full_selection=False)}"
    )
    if measurement_interval_label:
        st.caption(f"Intervaly měření: {measurement_interval_label}")
    layer_source_descriptions = [
        f"{layer.label}: {report_source_label(getattr(layer, 'measurement_source', None))}"
        for layer in curve_layers
        if report_source_label(getattr(layer, "measurement_source", None)) != "-"
    ]
    if layer_source_descriptions:
        st.caption(f"Zdroje vrstev: {', '.join(layer_source_descriptions)}")
    for layer in curve_layers[1:]:
        st.caption(
            f"{layer.label}: {describe_selected_identifications(layer.selected_identifications, total_available_count=available_identification_count, collapse_full_selection=False)}"
        )

    visible_curve_layers = tuple(layer for layer in curve_layers if layer.curve_rows)
    if not visible_curve_layers:
        st.info("Pro zvolené období a výběry vrstev nejsou v databázi žádná data elektroměrů.")
        return
    if curve_df.empty and visible_curve_layers:
        st.info("Hlavní výběr nemá ve zvoleném období žádná data elektroměrů. V grafu jsou zobrazeny pouze další vrstvy.")

    show_charging_overlay = st.checkbox(
        "Zobrazit nabíjecí relace SmartFuelPass v grafu",
        key=SHOW_CHARGING_OVERLAY_KEY,
        help=(
            "Do časové křivky odběru přidá modré šrafování odpovídající době nabíjení "
            "a dole zobrazí trvání, odebranou energii a rychlost nabíjení."
        ),
    )

    chart = build_curve_chart(visible_curve_layers, reserved_power_kw, report_period)
    overlay_df = pd.DataFrame()
    if show_charging_overlay:
        charge_sessions_df = load_charge_session_overlay_rows(
            report_period.period_start,
            report_period.period_end,
        )
        overlay_df = prepare_charge_session_overlays(
            charge_sessions_df,
            period_start=report_period.period_start,
            period_end=report_period.period_end,
        )
        if overlay_df.empty:
            st.info("Pro zvolené období nejsou ve SmartFuelPass databázi žádné dokončené nabíjecí relace.")
        else:
            chart = build_curve_chart_with_charge_overlay(
                visible_curve_layers,
                curve_df,
                reserved_power_kw,
                report_period,
                overlay_df,
            )

    st.altair_chart(chart, width="stretch")

    table_cols = st.columns(2)
    with table_cols[0]:
        st.subheader("Souhrn měřidel")
        st.dataframe(
            device_summary_df[["identifikace", "spotreba_kwh"]].rename(
                columns={
                    "identifikace": "Vrstva",
                    "spotreba_kwh": "kWh",
                }
            ),
            width="stretch",
            hide_index=True,
        )
    with table_cols[1]:
        st.subheader("Překročení hladiny")
        if exceedance_df.empty:
            if reserved_power_kw is None or reserved_power_kw <= 0:
                st.info("Rezervovaná hladina nebyla zadána.")
            else:
                st.info("Bez překročení ve zvoleném období.")
        else:
            st.dataframe(exceedance_df, width="stretch", hide_index=True)


def _build_report_result(
    *,
    report_period,
    period_label: str,
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    curve_layers: tuple[OteCurveLayer, ...],
    interval_curve_df: pd.DataFrame,
    device_summary_df: pd.DataFrame,
    reserved_power_kw: float | None,
    selected_identifications: tuple[str, ...],
    available_identification_count: int,
    report_source: str | None,
) -> dict[str, object]:
    summary = summarize_report(period_df, curve_df, peak_curve_df=interval_curve_df)
    exceedance_df = build_threshold_exceedance(interval_curve_df, reserved_power_kw)
    device_summary_with_layers_df = build_device_summary_with_layer_totals(
        device_summary_df,
        curve_layers,
    )
    measurement_interval_label = describe_measurement_intervals(period_df)
    pdf_bytes = None
    pdf_filename = None
    pdf_error = None
    pdf_variants: dict[bool, dict[str, object]] = {}
    has_chart_data = any(layer.curve_rows for layer in curve_layers)

    if has_chart_data:
        pdf_report = build_ote_pdf_report(
            period=report_period,
            period_label=period_label,
            period_df=period_df,
            curve_df=curve_df,
            device_summary_df=device_summary_with_layers_df,
            reserved_power_kw=reserved_power_kw,
            curve_layers=curve_layers,
            peak_curve_df=interval_curve_df,
            exceedance_curve_df=interval_curve_df,
            selected_identifications=selected_identifications,
            available_identification_count=available_identification_count,
        )
        try:
            pdf_bytes = render_ote_report_pdf(pdf_report)
            pdf_filename = build_ote_report_pdf_filename(pdf_report)
        except ElektromeryDashboardReportError as exc:
            pdf_error = str(exc)
        except Exception as exc:
            pdf_error = f"PDF report se nepodařilo připravit: {exc.__class__.__name__}."
        pdf_variants[False] = {
            "pdf_bytes": pdf_bytes,
            "pdf_filename": pdf_filename,
            "pdf_error": pdf_error,
        }

    return {
        "report_period": report_period,
        "period_label": period_label,
        "period_df": period_df,
        "curve_df": curve_df,
        "curve_layers": curve_layers,
        "interval_curve_df": interval_curve_df,
        "device_summary_df": device_summary_with_layers_df,
        "reserved_power_kw": reserved_power_kw,
        "selected_identifications": selected_identifications,
        "available_identification_count": available_identification_count,
        "report_source": report_source,
        "measurement_interval_label": measurement_interval_label,
        "summary": summary,
        "exceedance_df": exceedance_df,
        "pdf_bytes": pdf_bytes,
        "pdf_filename": pdf_filename,
        "pdf_error": pdf_error,
        "pdf_variants": pdf_variants,
    }


def _resolve_pdf_variant(report_result: dict[str, object], include_charge_overlay: bool) -> dict[str, object]:
    pdf_variants = report_result.setdefault("pdf_variants", {})
    if not isinstance(pdf_variants, dict):
        pdf_variants = {}
        report_result["pdf_variants"] = pdf_variants

    if include_charge_overlay in pdf_variants:
        variant = pdf_variants[include_charge_overlay]
        if isinstance(variant, dict):
            return variant

    curve_layers = tuple(report_result.get("curve_layers") or ())
    curve_df = report_result.get("curve_df")
    if (not isinstance(curve_df, pd.DataFrame) or curve_df.empty) and not any(layer.curve_rows for layer in curve_layers):
        variant = {"pdf_bytes": None, "pdf_filename": None, "pdf_error": None}
        pdf_variants[include_charge_overlay] = variant
        return variant

    report_period = report_result["report_period"]
    period_label = str(report_result["period_label"])
    period_df = report_result["period_df"]
    interval_curve_df = report_result.get("interval_curve_df")
    device_summary_df = report_result["device_summary_df"]
    reserved_power_kw = report_result["reserved_power_kw"]
    selected_identifications = tuple(report_result.get("selected_identifications") or ())
    available_identification_count = int(report_result.get("available_identification_count") or 0)

    charge_overlay_df = None
    if include_charge_overlay:
        charge_sessions_df = load_charge_session_overlay_rows(
            report_period.period_start,
            report_period.period_end,
        )
        overlay_df = prepare_charge_session_overlays(
            charge_sessions_df,
            period_start=report_period.period_start,
            period_end=report_period.period_end,
        )
        if not overlay_df.empty:
            charge_overlay_df = overlay_df

    pdf_report = build_ote_pdf_report(
        period=report_period,
        period_label=period_label,
        period_df=period_df,
        curve_df=curve_df,
        device_summary_df=device_summary_df,
        reserved_power_kw=reserved_power_kw,
        curve_layers=curve_layers,
        peak_curve_df=interval_curve_df if isinstance(interval_curve_df, pd.DataFrame) else None,
        exceedance_curve_df=interval_curve_df if isinstance(interval_curve_df, pd.DataFrame) else None,
        charge_overlay_df=charge_overlay_df,
        selected_identifications=selected_identifications,
        available_identification_count=available_identification_count,
    )
    try:
        variant = {
            "pdf_bytes": render_ote_report_pdf(pdf_report),
            "pdf_filename": build_ote_report_pdf_filename(pdf_report),
            "pdf_error": None,
        }
    except ElektromeryDashboardReportError as exc:
        variant = {
            "pdf_bytes": None,
            "pdf_filename": None,
            "pdf_error": str(exc),
        }
    except Exception as exc:
        variant = {
            "pdf_bytes": None,
            "pdf_filename": None,
            "pdf_error": f"PDF report se nepodařilo připravit: {exc.__class__.__name__}.",
        }
    pdf_variants[include_charge_overlay] = variant
    return variant


def render_dashboard() -> None:
    render_page_styles()
    st.title("Reporty elektroměrů")
    st.caption(f"Manuální vytvoření reportu z PostgreSQL tabulky `{ELECTROMERY_REPORT_DATA_SOURCE_LABEL}`.")

    bounds = load_report_data_bounds()
    if not bounds["measurement_count"] or bounds["date_min"] is None or bounds["date_max"] is None:
        st.info(f"V tabulce `{ELECTROMERY_REPORT_DATA_SOURCE_LABEL}` zatím nejsou žádná data pro report.")
        return

    identifikace_options = load_report_identifikace_options()
    if not identifikace_options:
        st.info(f"V tabulce `{ELECTROMERY_REPORT_DATA_SOURCE_LABEL}` nejsou dostupné žádné identifikace odběrných míst.")
        return

    min_date = pd.to_datetime(bounds["date_min"]).date()
    max_date = pd.to_datetime(bounds["date_max"]).date()
    label_to_kind = {label: key for key, label in REPORT_PERIOD_OPTIONS.items()}

    form_cols = st.columns((1.1, 1.1, 1.1, 2.7))
    with form_cols[0]:
        selected_period_label = st.selectbox("Typ reportu", list(label_to_kind.keys()))
    with form_cols[1]:
        selected_date = st.date_input(
            "Datum období",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
        )
    with form_cols[2]:
        reserved_power_kw = st.number_input(
            "Rezervovaná hladina [kW]",
            min_value=0.0,
            value=0.0,
            step=10.0,
        )
    with form_cols[3]:
        selected_identifications = st.multiselect(
            "Zahrnout do reportu",
            options=list(identifikace_options),
            default=list(identifikace_options),
            help=f"Hodnoty jsou načtené jako unikátní `identifikace` z PostgreSQL tabulky `{ELECTROMERY_REPORT_DATA_SOURCE_LABEL}`.",
        )
    main_layer_meta_cols = st.columns((3.6, 1))
    with main_layer_meta_cols[1]:
        main_layer_color = st.color_picker(
            "Barva hlavní vrstvy",
            value=curve_layer_color(0),
            key=_layer_color_key(0),
        )
    st.caption(f"Načteno {len(identifikace_options)} unikátních odběrných míst z databáze.")

    additional_layer_count = int(st.session_state.get(REPORT_LAYER_COUNT_KEY, 0))
    layer_control_cols = st.columns((1.2, 1.2, 4))
    with layer_control_cols[0]:
        if st.button("Přidat vrstvu", use_container_width=True):
            st.session_state[REPORT_LAYER_COUNT_KEY] = additional_layer_count + 1
            st.rerun()
    with layer_control_cols[1]:
        if st.button("Odebrat vrstvu", disabled=additional_layer_count <= 0, use_container_width=True):
            st.session_state.pop(_layer_selection_key(additional_layer_count), None)
            st.session_state.pop(_layer_color_key(additional_layer_count), None)
            st.session_state[REPORT_LAYER_COUNT_KEY] = max(additional_layer_count - 1, 0)
            st.rerun()

    for layer_number in range(1, additional_layer_count + 1):
        layer_cols = st.columns((3.6, 1))
        with layer_cols[0]:
            st.multiselect(
                curve_layer_label(layer_number),
                options=list(identifikace_options),
                default=[],
                key=_layer_selection_key(layer_number),
                help="Další vrstva vykreslí samostatnou křivku ze součtu vybraných odběrných míst.",
            )
        with layer_cols[1]:
            st.color_picker(
                f"Barva {curve_layer_label(layer_number).lower()}",
                value=curve_layer_color(layer_number),
                key=_layer_color_key(layer_number),
            )

    action_cols = st.columns((1.2, 1.2, 4))
    with action_cols[0]:
        submitted = st.button("Vytvořit report", type="primary", use_container_width=True)

    if submitted:
        selected_identifications_tuple = tuple(str(item).strip() for item in selected_identifications if str(item).strip())
        if not selected_identifications_tuple:
            st.session_state.pop(REPORT_RESULT_KEY, None)
            st.warning("Vyberte alespoň jedno odběrné místo.")
            return

        period_kind = label_to_kind[selected_period_label]
        report_period = resolve_report_period(period_kind, selected_date)
        additional_layers: list[tuple[int, tuple[str, ...], str]] = []
        for layer_number in range(1, additional_layer_count + 1):
            layer_identifications = _normalize_identification_selection(
                st.session_state.get(_layer_selection_key(layer_number), ())
            )
            layer_color = str(st.session_state.get(_layer_color_key(layer_number), curve_layer_color(layer_number)))
            if not layer_identifications:
                continue
            additional_layers.append((layer_number, layer_identifications, layer_color))
        with st.spinner("Vytvářím report a připravuji PDF..."):
            report_source = resolve_report_measurement_source(
                report_period.period_start,
                report_period.period_end,
                selected_identifications_tuple,
            )
            resolved_additional_layers: list[tuple[int, tuple[str, ...], str, str]] = []
            skipped_layers: list[str] = []
            for layer_number, layer_identifications, layer_color in additional_layers:
                layer_source = resolve_report_measurement_source(
                    report_period.period_start,
                    report_period.period_end,
                    layer_identifications,
                )
                if layer_source is None:
                    skipped_layers.append(curve_layer_label(layer_number))
                    continue
                resolved_additional_layers.append((layer_number, layer_identifications, layer_color, layer_source))

            if report_source is None and not resolved_additional_layers:
                st.session_state.pop(REPORT_RESULT_KEY, None)
                warning_parts = [
                    "Pro zvolene obdobi a vybery nejsou dostupna data v jednom zdroji na urovni zadne vrstvy.",
                    "Kazda vrstva se nacita bud cela z BINARY_, nebo cela ze SOFTLINK.",
                ]
                st.warning(" ".join(warning_parts))
                return
            if skipped_layers:
                st.warning(f"Bez dat pro zvolene obdobi: {', '.join(skipped_layers)}.")

            period_df = load_report_measurements(
                report_period.period_start,
                report_period.period_end,
                selected_identifications_tuple,
                report_source,
            )
            measurement_interval_label = describe_measurement_intervals(period_df)
            interval_curve_df = build_interval_consumption_curve(period_df, report_period)
            curve_df = build_consumption_curve(period_df, report_period)
            device_summary_df = build_device_summary(period_df)
            curve_layers = [
                build_curve_layer(
                    index=0,
                    curve_df=curve_df,
                    selected_identifications=selected_identifications_tuple,
                    color=main_layer_color,
                    measurement_source=report_source,
                )
            ]
            for layer_number, layer_identifications, layer_color, layer_source in resolved_additional_layers:
                layer_period_df = load_report_measurements(
                    report_period.period_start,
                    report_period.period_end,
                    layer_identifications,
                    layer_source,
                )
                layer_curve_df = build_consumption_curve(layer_period_df, report_period)
                curve_layers.append(
                    build_curve_layer(
                        index=layer_number,
                        curve_df=layer_curve_df,
                        selected_identifications=layer_identifications,
                        color=layer_color,
                        measurement_source=layer_source,
                    )
                )
            period_label = (
                f"{report_period.label} report | {report_period.date_range_label} | interval měření {measurement_interval_label}"
            )
            layer_source_labels = tuple(
                dict.fromkeys(
                    report_source_label(getattr(layer, "measurement_source", None))
                    for layer in curve_layers
                    if report_source_label(getattr(layer, "measurement_source", None)) != "-"
                )
            )
            if len(layer_source_labels) == 1:
                period_label = f"{period_label} | zdroj {layer_source_labels[0]}"
            elif layer_source_labels:
                period_label = f"{period_label} | zdroje vrstev {', '.join(layer_source_labels)}"
            st.session_state[REPORT_RESULT_KEY] = _build_report_result(
                report_period=report_period,
                period_label=period_label,
                period_df=period_df,
                curve_df=curve_df,
                curve_layers=tuple(curve_layers),
                interval_curve_df=interval_curve_df,
                device_summary_df=device_summary_df,
                reserved_power_kw=reserved_power_kw,
                selected_identifications=selected_identifications_tuple,
                available_identification_count=len(identifikace_options),
                report_source=report_source,
            )

    report_result = st.session_state.get(REPORT_RESULT_KEY)
    if report_result is None:
        return

    with action_cols[1]:
        include_charge_overlay = bool(st.session_state.get(SHOW_CHARGING_OVERLAY_KEY, False))
        pdf_variant = _resolve_pdf_variant(report_result, include_charge_overlay)
        pdf_bytes = pdf_variant.get("pdf_bytes")
        pdf_filename = pdf_variant.get("pdf_filename")
        pdf_error = pdf_variant.get("pdf_error")
        if pdf_bytes is not None and pdf_filename is not None:
            st.download_button(
                "Stáhnout PDF report",
                data=pdf_bytes,
                file_name=pdf_filename,
                mime="application/pdf",
                width="stretch",
            )
        elif pdf_error:
            st.button("Stáhnout PDF report", disabled=True, use_container_width=True)
            st.warning(pdf_error)

    render_report_result(**report_result)


try:
    render_dashboard()
except SQLAlchemyError as exc:
    st.error("Nepodařilo se načíst data elektroměrů z PostgreSQL.")
    st.exception(exc)
