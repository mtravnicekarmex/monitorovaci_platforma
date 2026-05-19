from __future__ import annotations

import datetime
import io
from pathlib import Path
import sys

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app.time_utils import prague_today


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.nabijecky_shared import (
    ALL_FILTER_LABEL,
    build_daily_summary,
    format_charge_currency,
    format_charge_energy,
    format_charge_sessions_dataframe,
    format_charge_speed,
    format_value,
    load_charge_sessions,
    load_location_options,
    load_tariff_options,
    normalize_date_range,
    prepare_charge_sessions,
    render_page_styles,
    summarize_charge_sessions,
)


DATE_RANGE_KEY = "nabijecky_overview_date_range"
LOCATION_KEY = "nabijecky_overview_location"
TARIFF_KEY = "nabijecky_overview_tariff"
GRAPH_KEY = "nabijecky_overview_graph"
APPLIED_KEY = "nabijecky_overview_applied"

GRAPH_OPTIONS = ("Ne", "Ano")
ENERGY_COLOR = "#16a34a"
COST_COLOR = "#0f766e"


st.set_page_config(
    page_title="Nabíječky - Přehled",
    page_icon="🔌",
    layout="wide",
)


require_page_access("nabijecky_overview")


def init_overview_state() -> None:
    default_end = prague_today()
    default_start = default_end - datetime.timedelta(days=30)
    st.session_state.setdefault(DATE_RANGE_KEY, (default_start, default_end))
    st.session_state.setdefault(LOCATION_KEY, ALL_FILTER_LABEL)
    st.session_state.setdefault(TARIFF_KEY, ALL_FILTER_LABEL)
    st.session_state.setdefault(GRAPH_KEY, "Ano")
    st.session_state.setdefault(APPLIED_KEY, False)


def render_overview_sidebar() -> tuple[datetime.date, datetime.date, str | None, str | None, bool]:
    init_overview_state()

    location_options = [ALL_FILTER_LABEL] + load_location_options()
    tariff_options = [ALL_FILTER_LABEL] + load_tariff_options()

    if st.session_state.get(LOCATION_KEY) not in location_options:
        st.session_state[LOCATION_KEY] = ALL_FILTER_LABEL
    if st.session_state.get(TARIFF_KEY) not in tariff_options:
        st.session_state[TARIFF_KEY] = ALL_FILTER_LABEL

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        with st.form("nabijecky_overview_filters"):
            date_range = st.date_input("Vybrat období:", key=DATE_RANGE_KEY)
            lokace = st.selectbox("Lokace", location_options, key=LOCATION_KEY)
            tarif = st.selectbox("Tarif", tariff_options, key=TARIFF_KEY)
            graph_option = st.selectbox("Graf", GRAPH_OPTIONS, key=GRAPH_KEY)
            apply_filters = st.form_submit_button("Načíst data", width="stretch")

    if apply_filters:
        st.session_state[APPLIED_KEY] = True

    start_date, end_date = normalize_date_range(date_range)
    selected_location = None if lokace == ALL_FILTER_LABEL else lokace
    selected_tariff = None if tarif == ALL_FILTER_LABEL else tarif
    return start_date, end_date, selected_location, selected_tariff, graph_option == "Ano"


def build_bar_chart(
    chart_df: pd.DataFrame,
    value_column: str,
    title: str,
    color: str,
    tooltip_format: str,
) -> alt.Chart:
    return (
        alt.Chart(chart_df)
        .mark_bar(color=color)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y(f"{value_column}:Q", title=title),
            tooltip=[
                alt.Tooltip("date:T", title="Datum"),
                alt.Tooltip("session_count:Q", title="Relace"),
                alt.Tooltip(f"{value_column}:Q", title=title, format=tooltip_format),
            ],
        )
        .properties(height=320)
        .interactive()
    )


def render_filter_summary(
    start_date: datetime.date,
    end_date: datetime.date,
    selected_location: str | None,
    selected_tariff: str | None,
) -> None:
    location_label = selected_location or ALL_FILTER_LABEL
    tariff_label = selected_tariff or ALL_FILTER_LABEL
    st.markdown(
        (
            '<div class="vodomery-filters">'
            f'<span class="vodomery-pill">Lokace: {location_label}</span>'
            f'<span class="vodomery-pill">Tarif: {tariff_label}</span>'
            f'<span class="vodomery-pill">Období: {format_value(start_date)} - {format_value(end_date)}</span>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_summary_metrics(summary: dict[str, object]) -> None:
    metric_cols = st.columns(4)
    metric_cols[0].metric("Relace", f"{int(summary['session_count']):,}".replace(",", " "))
    metric_cols[1].metric("Energie", format_charge_energy(summary["total_kwh"]))
    metric_cols[2].metric("Suma", format_charge_currency(summary["total_suma"]))
    metric_cols[3].metric("Průměrná rychlost", format_charge_speed(summary["average_speed"]))


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    buffer = io.BytesIO()
    export_df = df.copy()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
        worksheet = writer.sheets[sheet_name]
        for idx, column in enumerate(export_df.columns):
            if export_df.empty:
                max_width = len(str(column)) + 2
            else:
                series_width = export_df[column].astype("string").fillna("").str.len().max()
                max_width = max(len(str(column)), int(series_width)) + 2
            worksheet.set_column(idx, idx, min(max_width, 36))
    buffer.seek(0)
    return buffer.getvalue()


def build_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    export_df = df.copy()
    for column in (
        "started_at",
        "ended_at",
        "started_chart_time",
        "ended_chart_time",
        "duration_minutes",
        "id_relace",
        "lokace",
        "kwh",
        "suma",
        "tarif",
        "battery_status",
        "rychlost_nabijeni",
        "imported_at",
    ):
        if column not in export_df.columns:
            export_df[column] = pd.NA
    export_df["started_at"] = export_df["started_chart_time"].where(
        export_df["started_chart_time"].notna(),
        export_df["started_at"],
    )
    export_df["ended_at"] = export_df["ended_chart_time"].where(
        export_df["ended_chart_time"].notna(),
        export_df["ended_at"],
    )
    return export_df.rename(
        columns={
            "started_at": "zacatek",
            "ended_at": "konec",
            "duration_minutes": "trvani_min",
            "id_relace": "id_relace",
            "lokace": "lokace",
            "kwh": "odebrano_kwh",
            "suma": "suma_czk",
            "tarif": "tarif",
            "battery_status": "battery_status_pct",
            "rychlost_nabijeni": "rychlost_nabijeni_kw",
            "imported_at": "importovano",
        }
    )[
        [
            "zacatek",
            "konec",
            "trvani_min",
            "id_relace",
            "lokace",
            "odebrano_kwh",
            "suma_czk",
            "tarif",
            "battery_status_pct",
            "rychlost_nabijeni_kw",
            "importovano",
        ]
    ].copy()


def render_export_button(
    df: pd.DataFrame,
    start_date: datetime.date,
    end_date: datetime.date,
) -> None:
    file_name = f"nabijecky_prehled_{start_date}_{end_date}.xlsx"
    excel_bytes = dataframe_to_excel_bytes(build_export_dataframe(df), "Nabijeci relace")
    st.download_button(
        label="Stáhnout data Excel",
        data=excel_bytes,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def render_graphs(daily_summary_df: pd.DataFrame) -> None:
    if daily_summary_df.empty:
        st.info("Pro zvolený filtr zatím nejsou dostupná agregovaná data.")
        return

    chart_cols = st.columns(2)
    with chart_cols[0]:
        st.subheader("Denní energie")
        st.altair_chart(
            build_bar_chart(daily_summary_df, "kwh", "Energie [kWh]", ENERGY_COLOR, ".3f"),
            width="stretch",
        )
    with chart_cols[1]:
        st.subheader("Denní suma")
        st.altair_chart(
            build_bar_chart(daily_summary_df, "suma", "Suma [Kč]", COST_COLOR, ".2f"),
            width="stretch",
        )


def render_data_table(df: pd.DataFrame) -> None:
    sort_column = "started_chart_time" if "started_chart_time" in df.columns else "started_at"
    table_df = df.sort_values(sort_column, ascending=False).reset_index(drop=True)
    st.dataframe(
        format_charge_sessions_dataframe(table_df),
        width="stretch",
        hide_index=True,
    )


def render_dashboard() -> None:
    render_page_styles()
    st.markdown(
        """
        <div class="vodomery-hero">
            <div class="vodomery-eyebrow">Monitoring</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    start_date, end_date, selected_location, selected_tariff, graph_enabled = render_overview_sidebar()
    st.caption("Filtr se aplikuje až po kliknutí na `Načíst data` v sidebaru.")

    if not st.session_state.get(APPLIED_KEY):
        st.info("Klikněte na `Načíst data` pro zobrazení nabíjecích relací.")
        return

    sessions_df = load_charge_sessions(start_date, end_date, selected_location, selected_tariff)
    sessions_df = prepare_charge_sessions(sessions_df)
    if sessions_df.empty:
        st.info("Pro zvolený filtr nejsou k dispozici žádné nabíjecí relace.")
        return

    summary = summarize_charge_sessions(sessions_df)
    daily_summary_df = build_daily_summary(sessions_df)

    st.title("Nabíjecí relace")
    actual_range = (
        f"{format_value(sessions_df['started_chart_time'].min())} - "
        f"{format_value(sessions_df['ended_chart_time'].max())}"
    )
    st.caption(f"Reálně načtený rozsah dat: {actual_range}")

    render_summary_metrics(summary)

    with st.container(border=True):
        render_filter_summary(start_date, end_date, selected_location, selected_tariff)
        render_export_button(sessions_df, start_date, end_date)

    if graph_enabled:
        with st.container(border=True):
            render_graphs(daily_summary_df)

    with st.container(border=True):
        st.subheader("Data")
        render_data_table(sessions_df)


try:
    render_dashboard()
except SQLAlchemyError as exc:
    st.error("Nepodařilo se načíst data z databáze.")
    st.exception(exc)
