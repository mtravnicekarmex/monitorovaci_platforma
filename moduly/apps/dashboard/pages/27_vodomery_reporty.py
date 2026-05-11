from __future__ import annotations

from pathlib import Path
import sys

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db.connect import get_session_pg
from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.vodomery_reports import (
    REPORT_PERIOD_OPTIONS,
    VodomeryDashboardReportError,
    VodomeryCurveLayer,
    build_axis_grid_times,
    build_axis_label_format,
    build_axis_tick_times,
    build_consumption_curve,
    build_curve_layer,
    build_device_summary,
    build_interval_consumption_curve,
    build_vodomery_pdf_report,
    build_vodomery_report_pdf_filename,
    coerce_curve_layers,
    curve_layer_color,
    curve_layer_legend_label,
    curve_layer_label,
    describe_selected_identifications,
    filter_measurements_for_period,
    render_vodomery_report_pdf,
    resolve_report_period,
    summarize_report,
    vodomery_records_to_dataframe,
)
from moduly.apps.dashboard.vodomery_shared import render_page_styles
from moduly.mereni.vodomery.database.models import Mereni_vodomery


REPORT_RESULT_KEY = "vodomery_reports_result"
REPORT_LAYER_COUNT_KEY = "vodomery_reports_layer_count"
REPORT_LAYER_SELECTION_KEY_PREFIX = "vodomery_reports_layer_selection_"
REPORT_LAYER_COLOR_KEY_PREFIX = "vodomery_reports_layer_color_"


st.set_page_config(
    page_title="Vodoměry - Reporty",
    page_icon="📈",
    layout="wide",
)


require_page_access("vodomery_reports")


@st.cache_data(ttl=60)
def load_vodomery_data_bounds() -> dict[str, object]:
    session = get_session_pg()
    try:
        row = (
            session.query(
                func.min(Mereni_vodomery.date).label("date_min"),
                func.max(Mereni_vodomery.date).label("date_max"),
                func.count(Mereni_vodomery.id).label("measurement_count"),
                func.count(func.distinct(Mereni_vodomery.identifikace)).label("device_count"),
            )
            .filter(Mereni_vodomery.identifikace.is_not(None))
            .one()
        )
        return {
            "date_min": row.date_min,
            "date_max": row.date_max,
            "measurement_count": int(row.measurement_count or 0),
            "device_count": int(row.device_count or 0),
        }
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_vodomery_identifikace_options() -> tuple[str, ...]:
    session = get_session_pg()
    try:
        rows = (
            session.query(Mereni_vodomery.identifikace)
            .filter(Mereni_vodomery.identifikace.is_not(None))
            .distinct()
            .order_by(Mereni_vodomery.identifikace.asc())
            .all()
        )
        return tuple(str(row.identifikace).strip() for row in rows if row.identifikace and str(row.identifikace).strip())
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_vodomery_measurements(
    period_start,
    period_end,
    selected_identifications: tuple[str, ...] | None = None,
) -> pd.DataFrame:
    if selected_identifications is not None and len(selected_identifications) == 0:
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

    session = get_session_pg()
    try:
        current_period_query = (
            session.query(
                Mereni_vodomery.date,
                Mereni_vodomery.identifikace,
                Mereni_vodomery.seriove_cislo,
                Mereni_vodomery.objem,
                Mereni_vodomery.delta,
                Mereni_vodomery.interval_minutes,
                Mereni_vodomery.platne,
                Mereni_vodomery.reset_detected,
                Mereni_vodomery.zdroj,
            )
            .filter(
                Mereni_vodomery.date >= period_start,
                Mereni_vodomery.date < period_end,
                Mereni_vodomery.identifikace.is_not(None),
                Mereni_vodomery.objem.is_not(None),
            )
        )
        if selected_identifications:
            current_period_query = current_period_query.filter(Mereni_vodomery.identifikace.in_(selected_identifications))

        ranked_previous_measurements = (
            session.query(
                Mereni_vodomery.date.label("date"),
                Mereni_vodomery.identifikace.label("identifikace"),
                Mereni_vodomery.seriove_cislo.label("seriove_cislo"),
                Mereni_vodomery.objem.label("objem"),
                Mereni_vodomery.delta.label("delta"),
                Mereni_vodomery.interval_minutes.label("interval_minutes"),
                Mereni_vodomery.platne.label("platne"),
                Mereni_vodomery.reset_detected.label("reset_detected"),
                Mereni_vodomery.zdroj.label("zdroj"),
                func.row_number().over(
                    partition_by=Mereni_vodomery.identifikace,
                    order_by=Mereni_vodomery.date.desc(),
                ).label("row_num"),
            )
            .filter(
                Mereni_vodomery.date < period_start,
                Mereni_vodomery.identifikace.is_not(None),
                Mereni_vodomery.objem.is_not(None),
                Mereni_vodomery.platne.is_(True),
            )
        )
        if selected_identifications:
            ranked_previous_measurements = ranked_previous_measurements.filter(
                Mereni_vodomery.identifikace.in_(selected_identifications)
            )
        previous_measurements_subquery = ranked_previous_measurements.subquery()
        previous_rows = (
            session.query(
                previous_measurements_subquery.c.date,
                previous_measurements_subquery.c.identifikace,
                previous_measurements_subquery.c.seriove_cislo,
                previous_measurements_subquery.c.objem,
                previous_measurements_subquery.c.delta,
                previous_measurements_subquery.c.interval_minutes,
                previous_measurements_subquery.c.platne,
                previous_measurements_subquery.c.reset_detected,
                previous_measurements_subquery.c.zdroj,
            )
            .filter(previous_measurements_subquery.c.row_num == 1)
            .order_by(
                previous_measurements_subquery.c.identifikace.asc(),
                previous_measurements_subquery.c.date.asc(),
            )
            .all()
        )
        current_rows = (
            current_period_query
            .order_by(Mereni_vodomery.identifikace.asc(), Mereni_vodomery.date.asc())
            .all()
        )
        return vodomery_records_to_dataframe(
            {
                "date": row.date,
                "identifikace": row.identifikace,
                "seriove_cislo": row.seriove_cislo,
                "objem": row.objem,
                "delta": row.delta,
                "interval_minutes": row.interval_minutes,
                "platne": row.platne,
                "reset_detected": row.reset_detected,
                "zdroj": row.zdroj,
            }
            for row in (*previous_rows, *current_rows)
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


def _curve_layers_to_dataframe(curve_layers: tuple[VodomeryCurveLayer, ...]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for layer in curve_layers:
        for row in layer.curve_rows:
            rows.append(
                {
                    "layer_key": layer.key,
                    "layer_label": layer.label,
                    "layer_legend_label": curve_layer_legend_label(layer),
                    "layer_color": layer.color,
                    "date": row.date,
                    "peak_at": row.peak_at if row.peak_at is not None else row.date,
                    "spotreba_m3": row.spotreba_m3,
                    "prutok_m3h": row.prutok_m3h,
                    "pocet_mereni": row.pocet_mereni,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "layer_key",
            "layer_label",
            "layer_legend_label",
            "layer_color",
            "date",
            "peak_at",
            "spotreba_m3",
            "prutok_m3h",
            "pocet_mereni",
        ],
    )


def build_curve_chart(
    curve_layers: tuple[VodomeryCurveLayer, ...],
    report_period,
) -> alt.Chart:
    visible_layers = tuple(layer for layer in coerce_curve_layers(curve_layers) if layer.curve_rows)
    chart_source = _curve_layers_to_dataframe(visible_layers)
    chart_source["spotreba_m3"] = pd.to_numeric(chart_source["spotreba_m3"], errors="coerce").round(3)
    axis_tick_times = build_axis_tick_times(report_period)
    axis_grid_times = build_axis_grid_times(report_period)
    x_scale = alt.Scale(domain=[report_period.period_start, report_period.period_end])
    tooltip_items = [
        alt.Tooltip("layer_legend_label:N", title="Vrstva"),
        alt.Tooltip("date:T", title="Hodina"),
        alt.Tooltip("spotreba_m3:Q", title="Spotřeba [m³]", format=".3f"),
    ]

    base = alt.Chart(chart_source).encode(
        x=alt.X(
            "date:T",
            title=None,
            scale=x_scale,
            axis=alt.Axis(
                values=axis_tick_times,
                format=build_axis_label_format(report_period),
                grid=False,
                labelFlush=False,
                labelOverlap=False,
            ),
        ),
        tooltip=tooltip_items,
    )
    grid_chart = (
        alt.Chart(pd.DataFrame({"date": axis_grid_times}))
        .mark_rule(color="#d1d5db", strokeDash=[4, 4])
        .encode(x=alt.X("date:T", scale=x_scale))
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
        y=alt.Y("spotreba_m3:Q", title="Hodinová spotřeba [m³]"),
        color=alt.Color("layer_legend_label:N", title=None, scale=color_scale),
        detail=alt.Detail("layer_key:N"),
    )
    area = base.mark_area(opacity=0.88).encode(
        y=alt.Y("spotreba_m3:Q", title="Hodinová spotřeba [m³]", stack=None),
        fill=alt.Fill("layer_legend_label:N", title=None, scale=fill_scale, legend=None),
        detail=alt.Detail("layer_key:N"),
    )
    chart = grid_chart + area + line
    if len(chart_source) <= 240:
        points = base.mark_point(size=24, opacity=0.72).encode(
            y=alt.Y("spotreba_m3:Q", title="Hodinová spotřeba [m³]"),
            color=alt.Color("layer_legend_label:N", title=None, scale=color_scale, legend=None),
            detail=alt.Detail("layer_key:N"),
        )
        chart = chart + points
    return chart.properties(height=360).interactive()


def render_report_result(
    *,
    report_period,
    period_label: str,
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    curve_layers: tuple[VodomeryCurveLayer, ...],
    interval_curve_df: pd.DataFrame | None = None,
    device_summary_df: pd.DataFrame,
    summary: dict[str, object],
    pdf_bytes: bytes | None,
    pdf_filename: str | None,
    pdf_error: str | None,
    selected_identifications: tuple[str, ...] = (),
    available_identification_count: int = 0,
) -> None:
    del period_label, period_df, interval_curve_df, pdf_bytes, pdf_filename, pdf_error, summary
    curve_layers = coerce_curve_layers(curve_layers)
    metric_cols = st.columns(len(curve_layers))
    for layer_index, (metric_col, layer) in enumerate(zip(metric_cols, curve_layers), start=1):
        layer_total_consumption = round(
            sum(float(row.spotreba_m3 or 0.0) for row in layer.curve_rows),
            3,
        )
        metric_col.metric(
            f"Spotřeba {curve_layer_label(layer_index)}",
            f"{layer_total_consumption:.3f} m³",
        )
    st.caption(
        f"Hlavní výběr: {describe_selected_identifications(selected_identifications, total_available_count=available_identification_count, collapse_full_selection=False)}"
    )
    for layer in curve_layers[1:]:
        st.caption(
            f"{layer.label}: {describe_selected_identifications(layer.selected_identifications, total_available_count=available_identification_count, collapse_full_selection=False)}"
        )

    visible_curve_layers = tuple(layer for layer in curve_layers if layer.curve_rows)
    if not visible_curve_layers:
        st.info("Pro zvolené období a výběry vrstev nejsou v databázi žádná vodoměrová data.")
        return
    if curve_df.empty and visible_curve_layers:
        st.info("Hlavní výběr nemá ve zvoleném období žádná vodoměrová data. V grafu jsou zobrazeny pouze další vrstvy.")

    st.caption("Graf zobrazuje hodinovou kumulaci spotřeby, aby byly vrstvy s různou hustotou odečtů porovnatelné.")
    st.altair_chart(build_curve_chart(visible_curve_layers, report_period), width="stretch")
    st.subheader("Souhrn měřidel")
    st.dataframe(device_summary_df, width="stretch", hide_index=True)


def _build_report_result(
    *,
    report_period,
    period_label: str,
    period_df: pd.DataFrame,
    curve_df: pd.DataFrame,
    curve_layers: tuple[VodomeryCurveLayer, ...],
    interval_curve_df: pd.DataFrame,
    device_summary_df: pd.DataFrame,
    selected_identifications: tuple[str, ...],
    available_identification_count: int,
) -> dict[str, object]:
    summary = summarize_report(period_df, curve_df, peak_curve_df=interval_curve_df)
    pdf_bytes = None
    pdf_filename = None
    pdf_error = None

    if any(layer.curve_rows for layer in curve_layers):
        pdf_report = build_vodomery_pdf_report(
            period=report_period,
            period_label=period_label,
            period_df=period_df,
            curve_df=curve_df,
            device_summary_df=device_summary_df,
            curve_layers=curve_layers,
            peak_curve_df=interval_curve_df,
            selected_identifications=selected_identifications,
            available_identification_count=available_identification_count,
        )
        try:
            pdf_bytes = render_vodomery_report_pdf(pdf_report)
            pdf_filename = build_vodomery_report_pdf_filename(pdf_report)
        except VodomeryDashboardReportError as exc:
            pdf_error = str(exc)
        except Exception as exc:
            pdf_error = f"PDF report se nepodařilo připravit: {exc.__class__.__name__}."

    return {
        "report_period": report_period,
        "period_label": period_label,
        "period_df": period_df,
        "curve_df": curve_df,
        "curve_layers": curve_layers,
        "interval_curve_df": interval_curve_df,
        "device_summary_df": device_summary_df,
        "summary": summary,
        "pdf_bytes": pdf_bytes,
        "pdf_filename": pdf_filename,
        "pdf_error": pdf_error,
        "selected_identifications": selected_identifications,
        "available_identification_count": available_identification_count,
    }


def render_dashboard() -> None:
    render_page_styles()
    st.title("Reporty vodoměrů")
    st.caption("Manuální vytvoření reportu z PostgreSQL tabulky `monitoring.Mereni_vodomery_vse`.")

    bounds = load_vodomery_data_bounds()
    if not bounds["measurement_count"] or bounds["date_min"] is None or bounds["date_max"] is None:
        st.info("V tabulce `monitoring.Mereni_vodomery_vse` zatím nejsou žádná data pro report.")
        return

    identifikace_options = load_vodomery_identifikace_options()
    if not identifikace_options:
        st.info("V tabulce `monitoring.Mereni_vodomery_vse` nejsou dostupné žádné identifikace odběrných míst.")
        return

    min_date = pd.to_datetime(bounds["date_min"]).date()
    max_date = pd.to_datetime(bounds["date_max"]).date()
    label_to_kind = {label: key for key, label in REPORT_PERIOD_OPTIONS.items()}

    form_cols = st.columns((1.1, 1.1, 2.8))
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
        selected_identifications = st.multiselect(
            "Zahrnout do reportu",
            options=list(identifikace_options),
            default=list(identifikace_options),
            help="Hodnoty jsou načtené jako unikátní `identifikace` z PostgreSQL tabulky `monitoring.Mereni_vodomery_vse`.",
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
        with st.spinner("Vytvářím report a připravuji PDF..."):
            raw_df = load_vodomery_measurements(
                report_period.period_start,
                report_period.period_end,
                selected_identifications_tuple,
            )
            period_df = filter_measurements_for_period(raw_df, report_period)
            interval_curve_df = build_interval_consumption_curve(period_df)
            curve_df = build_consumption_curve(period_df, report_period)
            device_summary_df = build_device_summary(period_df)
            curve_layers = [
                build_curve_layer(
                    index=0,
                    curve_df=curve_df,
                    selected_identifications=selected_identifications_tuple,
                    color=main_layer_color,
                )
            ]
            for layer_number in range(1, additional_layer_count + 1):
                layer_identifications = _normalize_identification_selection(
                    st.session_state.get(_layer_selection_key(layer_number), ())
                )
                layer_color = str(st.session_state.get(_layer_color_key(layer_number), curve_layer_color(layer_number)))
                if not layer_identifications:
                    continue
                layer_period_df = load_vodomery_measurements(
                    report_period.period_start,
                    report_period.period_end,
                    layer_identifications,
                )
                layer_curve_df = build_consumption_curve(
                    filter_measurements_for_period(layer_period_df, report_period),
                    report_period,
                )
                curve_layers.append(
                    build_curve_layer(
                        index=layer_number,
                        curve_df=layer_curve_df,
                        selected_identifications=layer_identifications,
                        color=layer_color,
                    )
                )
            period_label = (
                f"{report_period.label} report | {report_period.date_range_label} | krok {report_period.bucket_label}"
            )
            st.session_state[REPORT_RESULT_KEY] = _build_report_result(
                report_period=report_period,
                period_label=period_label,
                period_df=period_df,
                curve_df=curve_df,
                curve_layers=tuple(curve_layers),
                interval_curve_df=interval_curve_df,
                device_summary_df=device_summary_df,
                selected_identifications=selected_identifications_tuple,
                available_identification_count=len(identifikace_options),
            )

    report_result = st.session_state.get(REPORT_RESULT_KEY)
    if report_result is None:
        return

    with action_cols[1]:
        pdf_bytes = report_result.get("pdf_bytes")
        pdf_filename = report_result.get("pdf_filename")
        pdf_error = report_result.get("pdf_error")
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
            st.warning(str(pdf_error))

    render_report_result(**report_result)


try:
    render_dashboard()
except SQLAlchemyError as exc:
    st.error("Nepodařilo se načíst vodoměrová data z PostgreSQL.")
    st.exception(exc)
