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
from moduly.apps.dashboard.elektromery_shared import (
    build_change_table,
    build_delta_consumption_summary,
    format_consumption_dataframe,
    format_energy_metric,
    format_value,
    get_elektromery_access_context,
    load_ident_options,
    load_measurement_series,
    normalize_date_range,
    prepare_measurements,
    render_page_styles,
    round_consumption_columns,
    uses_ote_delta_source,
)


DEVICE_KEY = "elektromery_overview_identifikace"
DATE_RANGE_KEY = "elektromery_overview_date_range"
DETAIL_KEY = "elektromery_overview_detail"
GRAPH_KEY = "elektromery_overview_graph"
APPLIED_KEY = "elektromery_overview_applied"

DETAIL_OPTIONS = ("Ne", "Měsíčně", "Denně", "Hodinově")
GRAPH_OPTIONS = ("Ne", "Ano")
ELECTRICITY_STATE_COLOR = "#dc2626"
ELECTRICITY_CONSUMPTION_COLOR = "#dc2626"


st.set_page_config(
    page_title="Elektroměry - Přehled",
    page_icon="⚡",
    layout="wide",
)


require_page_access("elektromery_overview")


def init_overview_state() -> None:
    default_end = prague_today()
    default_start = default_end - datetime.timedelta(days=1)
    st.session_state.setdefault(DATE_RANGE_KEY, (default_start, default_end))
    st.session_state.setdefault(DETAIL_KEY, "Ne")
    st.session_state.setdefault(GRAPH_KEY, "Ne")
    st.session_state.setdefault(APPLIED_KEY, False)


def render_overview_sidebar(
    user_is_admin: bool,
    allowed_devices: tuple[str, ...],
) -> tuple[str, datetime.date, datetime.date, str, bool]:
    init_overview_state()

    ident_options = load_ident_options(allowed_devices, user_is_admin)
    if not ident_options:
        st.warning("Pro aktuální kombinaci oprávnění nejsou k dispozici žádné elektroměry.")
        st.stop()

    current_ident = st.session_state.get(DEVICE_KEY)
    if current_ident not in ident_options:
        st.session_state[DEVICE_KEY] = ident_options[0]

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        with st.form("elektromery_overview_filters"):
            identifikace = st.selectbox("Elektroměr", ident_options, key=DEVICE_KEY)
            date_range = st.date_input("Vybrat období:", key=DATE_RANGE_KEY)
            detail_level = st.selectbox("Detailní výpis", DETAIL_OPTIONS, key=DETAIL_KEY)
            graph_option = st.selectbox("Graf", GRAPH_OPTIONS, key=GRAPH_KEY)
            apply_filters = st.form_submit_button("Načíst data", width="stretch")

    if apply_filters:
        st.session_state[APPLIED_KEY] = True

    start_date, end_date = normalize_date_range(date_range)
    return identifikace, start_date, end_date, detail_level, graph_option == "Ano"


def build_boundary_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    boundary = df.iloc[[0, -1]].copy()
    boundary = boundary.drop_duplicates(subset=["date", "stav_celkem", "seriove_cislo"])
    return boundary.rename(
        columns={
            "date": "Datum",
            "vt": "Stav VT",
            "nt": "Stav NT",
            "stav_celkem": "Stav celkem",
            "identifikace": "Elektroměr",
            "seriove_cislo": "Sériové číslo",
        }
    )[["Datum", "Stav VT", "Stav NT", "Stav celkem", "Elektroměr", "Sériové číslo"]]


def build_detail_table(df: pd.DataFrame, detail_level: str) -> pd.DataFrame:
    if detail_level == "Ne" or df.empty:
        return pd.DataFrame()

    freq_map = {
        "Měsíčně": "ME",
        "Denně": "D",
        "Hodinově": "h",
    }
    time_axis_column = "chart_time" if "chart_time" in df.columns and df["chart_time"].notna().any() else "date"
    working_df = df.dropna(subset=[time_axis_column]).copy()
    if working_df.empty:
        return pd.DataFrame()

    resampled = (
        working_df.set_index(time_axis_column)
        .resample(freq_map[detail_level])
        .agg(
            vt=("vt", "last"),
            nt=("nt", "last"),
            total=("total", "last"),
            stav_celkem=("stav_celkem", "last"),
            identifikace=("identifikace", "first"),
            seriove_cislo=("seriove_cislo", "last"),
            zdroj=("zdroj", "first"),
            delta=("delta", "sum"),
            spotreba=("spotreba", "sum"),
            spotreba_vt=("spotreba_vt", "sum"),
            spotreba_nt=("spotreba_nt", "sum"),
            kumulovana_spotreba=("kumulovana_spotreba", "last"),
            reset_detected=("reset_detected", "sum"),
            pocet_zaznamu=("spotreba", "count"),
        )
        .reset_index()
        .rename(columns={time_axis_column: "date"})
    )
    resampled = resampled.rename(columns={"reset_detected": "pocet_resetu"})
    resampled = resampled[resampled["pocet_zaznamu"] > 0].drop(columns=["pocet_zaznamu"]).copy()
    if resampled.empty:
        return resampled
    for column in ("spotreba", "spotreba_vt", "spotreba_nt", "kumulovana_spotreba"):
        resampled[column] = pd.to_numeric(resampled[column], errors="coerce").round(3)
    resampled["pocet_resetu"] = resampled["pocet_resetu"].fillna(0).astype(int)
    return resampled


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
            worksheet.set_column(idx, idx, min(max_width, 32))
    buffer.seek(0)
    return buffer.getvalue()


def build_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    export_df = df.copy()

    for column in (
        "date",
        "vt",
        "nt",
        "total",
        "stav_celkem",
        "identifikace",
        "seriove_cislo",
        "zdroj",
        "delta",
        "spotreba",
        "spotreba_vt",
        "spotreba_nt",
        "kumulovana_spotreba",
    ):
        if column not in export_df.columns:
            export_df[column] = pd.NA

    return export_df[
        [
            "date",
            "vt",
            "nt",
            "total",
            "stav_celkem",
            "identifikace",
            "seriove_cislo",
            "zdroj",
            "delta",
            "spotreba",
            "spotreba_vt",
            "spotreba_nt",
            "kumulovana_spotreba",
        ]
    ].copy()


def render_summary_metrics(df: pd.DataFrame) -> None:
    total_consumption = round(float(df["kumulovana_spotreba"].iloc[-1]), 3)
    label = "Spotřeba za období (delta)" if uses_ote_delta_source(df) else "Spotřeba za období"
    st.metric(label, format_energy_metric(total_consumption))


def build_line_chart(
    chart_df: pd.DataFrame,
    value_column: str,
    title: str,
    color: str,
) -> alt.Chart:
    chart_source = chart_df.dropna(subset=[value_column]).copy()
    x_column = "chart_time" if "chart_time" in chart_source.columns and chart_source["chart_time"].notna().any() else "date"
    return (
        alt.Chart(chart_source)
        .mark_line(color=color, strokeWidth=2.5)
        .encode(
            x=alt.X(f"{x_column}:T", title=None),
            y=alt.Y(f"{value_column}:Q", title=title),
            tooltip=[
                alt.Tooltip(f"{x_column}:T", title="Čas"),
                alt.Tooltip(f"{value_column}:Q", title=title, format=".3f"),
            ],
        )
        .properties(height=320)
        .interactive()
    )


def build_bar_chart(
    chart_df: pd.DataFrame,
    value_column: str,
    title: str,
    color: str,
) -> alt.Chart:
    chart_source = chart_df.dropna(subset=[value_column]).copy()
    x_column = "chart_time" if "chart_time" in chart_source.columns and chart_source["chart_time"].notna().any() else "date"
    return (
        alt.Chart(chart_source)
        .mark_bar(color=color)
        .encode(
            x=alt.X(f"{x_column}:T", title=None),
            y=alt.Y(f"{value_column}:Q", title=title),
            tooltip=[
                alt.Tooltip(f"{x_column}:T", title="Čas"),
                alt.Tooltip(f"{value_column}:Q", title=title, format=".3f"),
            ],
        )
        .properties(height=320)
        .interactive()
    )


def render_graphs(df: pd.DataFrame, detail_df: pd.DataFrame, detail_level: str) -> None:
    if detail_level == "Ne" or detail_df.empty:
        chart_source_df = round_consumption_columns(df, columns=("stav_celkem", "spotreba"))
        if uses_ote_delta_source(df):
            chart_source_df = round_consumption_columns(df, columns=("spotreba", "kumulovana_spotreba"))
            chart_cols = st.columns(2)
            with chart_cols[0]:
                st.subheader("Spotřeba podle delta")
                st.altair_chart(
                    build_bar_chart(chart_source_df, "spotreba", "Spotřeba [kWh]", ELECTRICITY_CONSUMPTION_COLOR),
                    width="stretch",
                )
            with chart_cols[1]:
                st.subheader("Kumulovaná spotřeba")
                st.altair_chart(
                    build_line_chart(
                        chart_source_df,
                        "kumulovana_spotreba",
                        "Kumulovaná spotřeba [kWh]",
                        ELECTRICITY_CONSUMPTION_COLOR,
                    ),
                    width="stretch",
                )
            return

        chart_cols = st.columns(2)
        with chart_cols[0]:
            st.subheader("Stav celkem")
            st.altair_chart(
                build_line_chart(chart_source_df, "stav_celkem", "Stav celkem [kWh]", ELECTRICITY_STATE_COLOR),
                width="stretch",
            )
        with chart_cols[1]:
            st.subheader("Spotřeba")
            st.altair_chart(
                build_bar_chart(chart_source_df, "spotreba", "Spotřeba [kWh]", ELECTRICITY_CONSUMPTION_COLOR),
                width="stretch",
            )
        return

    rounded_detail_df = round_consumption_columns(
        detail_df,
        columns=("spotreba", "kumulovana_spotreba"),
    )
    chart_cols = st.columns(2)
    with chart_cols[0]:
        st.subheader(f"Spotřeba - {detail_level.lower()}")
        chart_df = rounded_detail_df[["date", "spotreba"]].copy()
        if detail_level == "Hodinově":
            st.altair_chart(
                build_line_chart(chart_df, "spotreba", "Spotřeba [kWh]", ELECTRICITY_CONSUMPTION_COLOR),
                width="stretch",
            )
        else:
            st.altair_chart(
                build_bar_chart(chart_df, "spotreba", "Spotřeba [kWh]", ELECTRICITY_CONSUMPTION_COLOR),
                width="stretch",
            )
    with chart_cols[1]:
        st.subheader(f"Kumulovaná spotřeba - {detail_level.lower()}")
        cumulative_df = rounded_detail_df[["date", "kumulovana_spotreba"]].copy()
        st.altair_chart(
            build_line_chart(
                cumulative_df,
                "kumulovana_spotreba",
                "Kumulovaná spotřeba [kWh]",
                ELECTRICITY_CONSUMPTION_COLOR,
            ),
            width="stretch",
        )


def render_data_table(df: pd.DataFrame, detail_df: pd.DataFrame, detail_level: str) -> None:
    if uses_ote_delta_source(df):
        source_df = df if detail_level == "Ne" or detail_df.empty else detail_df
        table_df = source_df.rename(
            columns={
                "date": "Datum",
                "identifikace": "Elektroměr",
                "seriove_cislo": "Sériové číslo",
                "zdroj": "Zdroj",
                "delta": "Delta",
                "spotreba": "Spotřeba",
                "kumulovana_spotreba": "Kumulovaná spotřeba",
                "reset_detected": "Reset detekován",
                "pocet_resetu": "Počet resetů",
            }
        ).sort_values("Datum", ascending=detail_level != "Ne")
        table_df = format_consumption_dataframe(
            table_df,
            columns=("Delta", "Spotřeba", "Kumulovaná spotřeba"),
        )
        visible_columns = [
            column
            for column in (
                "Datum",
                "Elektroměr",
                "Sériové číslo",
                "Zdroj",
                "Delta",
                "Spotřeba",
                "Kumulovaná spotřeba",
                "Reset detekován",
                "Počet resetů",
            )
            if column in table_df.columns
        ]
        st.dataframe(table_df[visible_columns], width="stretch", hide_index=True)
        return

    if detail_level == "Ne" or detail_df.empty:
        table_df = (
            df.rename(
                columns={
                    "date": "Datum",
                    "identifikace": "Elektroměr",
                    "seriove_cislo": "Sériové číslo",
                    "vt": "Stav VT",
                    "nt": "Stav NT",
                    "total": "TOTAL",
                    "stav_celkem": "Stav celkem",
                    "spotreba": "Spotřeba",
                    "spotreba_vt": "Spotřeba VT",
                    "spotreba_nt": "Spotřeba NT",
                    "kumulovana_spotreba": "Kumulovaná spotřeba",
                    "reset_detected": "Reset detekován",
                }
            )
            .sort_values("Datum", ascending=False)
        )
        table_df = format_consumption_dataframe(
            table_df,
            columns=("Stav VT", "Stav NT", "TOTAL", "Stav celkem", "Spotřeba", "Spotřeba VT", "Spotřeba NT", "Kumulovaná spotřeba"),
        )
        st.dataframe(table_df, width="stretch", hide_index=True)
        return

    table_df = detail_df.rename(
        columns={
            "date": "Datum",
            "identifikace": "Elektroměr",
            "seriove_cislo": "Sériové číslo",
            "vt": "Stav VT",
            "nt": "Stav NT",
            "total": "TOTAL",
            "stav_celkem": "Stav celkem",
            "spotreba": "Spotřeba",
            "spotreba_vt": "Spotřeba VT",
            "spotreba_nt": "Spotřeba NT",
            "kumulovana_spotreba": "Kumulovaná spotřeba",
            "pocet_resetu": "Počet resetů",
        }
    ).sort_values("Datum", ascending=True)
    table_df = format_consumption_dataframe(
        table_df,
        columns=("Stav VT", "Stav NT", "TOTAL", "Stav celkem", "Spotřeba", "Spotřeba VT", "Spotřeba NT", "Kumulovaná spotřeba"),
    )
    st.dataframe(table_df, width="stretch", hide_index=True)


def render_export_button(df: pd.DataFrame, selected_ident: str, start_date: datetime.date, end_date: datetime.date, detail_level: str) -> None:
    file_suffix = "surova_data" if detail_level == "Ne" else detail_level.lower()
    file_name = f"spotreba_elektriny_{selected_ident}_{start_date}_{end_date}_{file_suffix}.xlsx"
    excel_bytes = dataframe_to_excel_bytes(build_export_dataframe(df), "Spotreba elektriny")
    st.download_button(
        label="Stáhnout data Excel",
        data=excel_bytes,
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
    user_is_admin, allowed_devices = get_elektromery_access_context()
    selected_ident, start_date, end_date, detail_level, graph_enabled = render_overview_sidebar(
        user_is_admin,
        allowed_devices,
    )

    st.caption("Filtr se aplikuje až po kliknutí na `Načíst data` v sidebaru.")

    if not st.session_state.get(APPLIED_KEY):
        st.info("Klikněte na `Načíst data` pro zobrazení dat vybraného elektroměru.")
        return

    measurements_df = load_measurement_series(
        selected_ident,
        start_date,
        end_date,
        allowed_devices,
        user_is_admin,
    )
    measurements_df = prepare_measurements(measurements_df)

    if measurements_df.empty:
        st.info("Pro zvolený filtr nejsou k dispozici žádná měření.")
        return

    detail_df = build_detail_table(measurements_df, detail_level)
    boundary_table = build_boundary_table(measurements_df)
    change_table = build_change_table(measurements_df)

    st.title(f"Spotřeba elektřiny - {selected_ident}")
    actual_range = f"{format_value(measurements_df['date'].min())} - {format_value(measurements_df['date'].max())}"
    st.caption(f"Reálně načtený rozsah dat: {actual_range}")

    render_summary_metrics(measurements_df)

    with st.container(border=True):
        if uses_ote_delta_source(measurements_df):
            st.subheader("Spotřeba podle delta")
            delta_summary_df = build_delta_consumption_summary(measurements_df)
            delta_summary_df = format_consumption_dataframe(delta_summary_df, columns=("Spotřeba z delta",))
            st.table(delta_summary_df.set_index("Zdroj"))
        else:
            st.subheader("Počáteční a konečný stav")
            boundary_display_df = format_consumption_dataframe(
                boundary_table,
                columns=("Stav VT", "Stav NT", "Stav celkem"),
            ).set_index("Datum")
            st.table(boundary_display_df)
        export_source = measurements_df if detail_level == "Ne" or detail_df.empty else detail_df
        render_export_button(export_source, selected_ident, start_date, end_date, detail_level)

    if not change_table.empty:
        with st.container(border=True):
            st.subheader("Resety nebo výměny elektroměrů")
            st.table(format_consumption_dataframe(change_table, columns=("Stav celkem",)))

    if graph_enabled:
        with st.container(border=True):
            render_graphs(measurements_df, detail_df, detail_level)

    with st.container(border=True):
        st.subheader("Data")
        render_data_table(measurements_df, detail_df, detail_level)


try:
    render_dashboard()
except SQLAlchemyError as exc:
    st.error("Nepodařilo se načíst data z databáze.")
    st.exception(exc)
