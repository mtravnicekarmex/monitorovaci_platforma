from __future__ import annotations

import datetime
import io
from pathlib import Path
import sys

import altair as alt
import streamlit as st
import pandas as pd
from sqlalchemy.exc import SQLAlchemyError

from app.time_utils import prague_today


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.plynomery_shared import (
    format_consumption_dataframe,
    format_consumption_with_unit,
    format_value,
    get_plynomery_access_context,
    load_ident_options,
    load_measurement_series,
    normalize_date_range,
    render_page_styles,
    round_consumption_columns,
)
from moduly.apps.dashboard.time_semantics import add_chart_time, time_axis_column


DEVICE_KEY = "plynomery_overview_identifikace"
DATE_RANGE_KEY = "plynomery_overview_date_range"
DETAIL_KEY = "plynomery_overview_detail"
GRAPH_KEY = "plynomery_overview_graph"
APPLIED_KEY = "plynomery_overview_applied"

DETAIL_OPTIONS = ("Ne", "Měsíčně", "Denně", "Hodinově")
GRAPH_OPTIONS = ("Ne", "Ano")
GAS_CONSUMPTION_COLOR = "#eab308"
GAS_CONSUMPTION_TEXT_COLOR = "#a16207"
NEUTRAL_VOLUME_COLOR = "#64748b"


st.set_page_config(
    page_title="Plynoměry - Přehled",
    page_icon="🔥",
    layout="wide",
)


require_page_access("plynomery_overview")


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
        st.warning("Pro aktuální kombinaci oprávnění nejsou k dispozici žádné plynoměry.")
        st.stop()

    current_ident = st.session_state.get(DEVICE_KEY)
    if current_ident not in ident_options:
        st.session_state[DEVICE_KEY] = ident_options[0]

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        with st.form("plynomery_overview_filters"):
            identifikace = st.selectbox("Plynoměr", ident_options, key=DEVICE_KEY)
            date_range = st.date_input("Vybrat období:", key=DATE_RANGE_KEY)
            detail_level = st.selectbox("Detailní výpis", DETAIL_OPTIONS, key=DETAIL_KEY)
            graph_option = st.selectbox("Graf", GRAPH_OPTIONS, key=GRAPH_KEY)
            apply_filters = st.form_submit_button("Načíst data", width="stretch")

    if apply_filters:
        st.session_state[APPLIED_KEY] = True

    start_date, end_date = normalize_date_range(date_range)
    return identifikace, start_date, end_date, detail_level, graph_option == "Ano"


def prepare_measurements(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    for column in (
        "date",
        "objem",
        "delta",
        "identifikace",
        "seriove_cislo",
        "zdroj",
        "platne",
        "gap_detected",
        "synthetic",
        "reset_detected",
        "source_date",
        "time_utc",
        "time_basis",
        "source_timezone",
        "source_utc_offset_minutes",
        "time_fold",
        "timestamp_position",
    ):
        if column not in prepared.columns:
            prepared[column] = pd.NA

    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared["source_date"] = pd.to_datetime(prepared["source_date"], errors="coerce")
    prepared = add_chart_time(prepared)
    prepared["objem"] = pd.to_numeric(prepared["objem"], errors="coerce")
    prepared["delta"] = pd.to_numeric(prepared["delta"], errors="coerce")
    prepared["seriove_cislo"] = prepared["seriove_cislo"].astype("string")
    prepared["platne"] = prepared["platne"].fillna(True).astype(bool)
    prepared = prepared.dropna(subset=["chart_time", "objem"]).sort_values("chart_time").reset_index(drop=True)

    if prepared.empty:
        return prepared

    diff_from_volume = prepared["objem"].diff()
    serial_changed = prepared["seriove_cislo"].ne(prepared["seriove_cislo"].shift())
    stored_reset = prepared["reset_detected"].map(lambda value: bool(value) if pd.notna(value) else False)
    reset_detected = diff_from_volume.lt(0).fillna(False) | serial_changed.fillna(False) | stored_reset
    prepared["reset_detected"] = reset_detected
    source_delta_available = prepared["delta"].notna()
    prepared["spotreba"] = diff_from_volume.fillna(0.0)
    prepared.loc[source_delta_available, "spotreba"] = prepared.loc[source_delta_available, "delta"]
    prepared.loc[prepared["spotreba"] < 0, "spotreba"] = 0.0
    prepared.loc[prepared["reset_detected"] & ~source_delta_available, "spotreba"] = 0.0
    prepared.loc[~prepared["platne"], "spotreba"] = 0.0
    prepared["spotreba"] = prepared["spotreba"].round(3)
    prepared["kumulovana_spotreba"] = prepared["spotreba"].cumsum().round(3)
    return prepared


def build_boundary_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    boundary = df.iloc[[0, -1]].copy()
    boundary = boundary.drop_duplicates(subset=["date", "objem", "seriove_cislo"])
    return boundary.rename(
        columns={
            "date": "Datum",
            "objem": "Objem",
            "identifikace": "Plynoměr",
            "seriove_cislo": "Sériové číslo",
            "platne": "Platné",
        }
    )[["Datum", "Objem", "Plynoměr", "Sériové číslo", "Platné"]]


def build_change_table(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 2:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    previous_row = df.iloc[0]
    for _, row in df.iloc[1:].iterrows():
        serial_changed = row["seriove_cislo"] != previous_row["seriove_cislo"]
        volume_reset = row["objem"] < previous_row["objem"]

        if serial_changed or volume_reset:
            rows.append(
                {
                    "Datum": previous_row["date"],
                    "Objem": previous_row["objem"],
                    "Sériové číslo": previous_row["seriove_cislo"],
                    "Poznámka": "Konečný stav původního plynoměru",
                }
            )
            rows.append(
                {
                    "Datum": row["date"],
                    "Objem": row["objem"],
                    "Sériové číslo": row["seriove_cislo"],
                    "Poznámka": "Počáteční stav nového nebo resetovaného plynoměru",
                }
            )
        previous_row = row

    return pd.DataFrame(rows)


def build_detail_table(df: pd.DataFrame, detail_level: str) -> pd.DataFrame:
    if detail_level == "Ne" or df.empty:
        return pd.DataFrame()

    freq_map = {
        "Měsíčně": "ME",
        "Denně": "D",
        "Hodinově": "h",
    }
    axis_column = time_axis_column(df)
    resampled = (
        df.set_index(axis_column)
        .resample(freq_map[detail_level])
        .agg(
            objem=("objem", "last"),
            identifikace=("identifikace", "first"),
            seriove_cislo=("seriove_cislo", "last"),
            spotreba=("spotreba", "sum"),
            kumulovana_spotreba=("kumulovana_spotreba", "last"),
            platne=("platne", "min"),
            reset_detected=("reset_detected", "sum"),
        )
        .reset_index()
        .rename(columns={axis_column: "date"})
    )
    resampled = resampled.rename(
        columns={
            "platne": "platna_data",
            "reset_detected": "pocet_resetu",
        }
    )
    resampled = resampled[resampled["objem"].notna()].copy()
    if resampled.empty:
        return resampled
    resampled["spotreba"] = pd.to_numeric(resampled["spotreba"], errors="coerce").round(3)
    resampled["kumulovana_spotreba"] = pd.to_numeric(resampled["kumulovana_spotreba"], errors="coerce").round(3)
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
    if "platne" not in export_df.columns and "platna_data" in export_df.columns:
        export_df["platne"] = export_df["platna_data"]

    for column in (
        "date",
        "objem",
        "identifikace",
        "seriove_cislo",
        "platne",
        "spotreba",
        "kumulovana_spotreba",
    ):
        if column not in export_df.columns:
            export_df[column] = pd.NA

    return export_df[
        [
            "date",
            "objem",
            "identifikace",
            "seriove_cislo",
            "platne",
            "spotreba",
            "kumulovana_spotreba",
        ]
    ].copy()


def render_summary_metrics(df: pd.DataFrame) -> None:
    total_consumption = round(float(df["kumulovana_spotreba"].iloc[-1]), 3)
    st.metric("Spotřeba za období", format_consumption_with_unit(total_consumption))


def build_line_chart(
    chart_df: pd.DataFrame,
    value_column: str,
    title: str,
    color: str,
) -> alt.Chart:
    chart_source = chart_df.dropna(subset=[value_column]).copy()
    x_column = time_axis_column(chart_source)
    return (
        alt.Chart(chart_source)
        .mark_line(color=color, strokeWidth=2.5)
        .encode(
            x=alt.X(f"{x_column}:T", title=None),
            y=alt.Y(f"{value_column}:Q", title=title),
            tooltip=[
                alt.Tooltip(f"{x_column}:T", title="Datum"),
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
    x_column = time_axis_column(chart_source)
    return (
        alt.Chart(chart_source)
        .mark_bar(color=color)
        .encode(
            x=alt.X(f"{x_column}:T", title=None),
            y=alt.Y(f"{value_column}:Q", title=title),
            tooltip=[
                alt.Tooltip(f"{x_column}:T", title="Datum"),
                alt.Tooltip(f"{value_column}:Q", title=title, format=".3f"),
            ],
        )
        .properties(height=320)
        .interactive()
    )


def render_graphs(df: pd.DataFrame, detail_df: pd.DataFrame, detail_level: str) -> None:
    if detail_level == "Ne" or detail_df.empty:
        chart_source_df = round_consumption_columns(df, columns=("objem", "spotreba"))
        chart_cols = st.columns(2)
        with chart_cols[0]:
            st.subheader("Objem")
            st.altair_chart(
                build_line_chart(chart_source_df, "objem", "Objem [m³]", NEUTRAL_VOLUME_COLOR),
                width="stretch",
            )
        with chart_cols[1]:
            st.subheader("Spotřeba")
            st.altair_chart(
                build_bar_chart(chart_source_df, "spotreba", "Spotřeba [m³]", GAS_CONSUMPTION_COLOR),
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
                build_line_chart(chart_df, "spotreba", "Spotřeba [m³]", GAS_CONSUMPTION_COLOR),
                width="stretch",
            )
        else:
            st.altair_chart(
                build_bar_chart(chart_df, "spotreba", "Spotřeba [m³]", GAS_CONSUMPTION_COLOR),
                width="stretch",
            )
    with chart_cols[1]:
        st.subheader(f"Kumulovaná spotřeba - {detail_level.lower()}")
        cumulative_df = rounded_detail_df[["date", "kumulovana_spotreba"]].copy()
        st.altair_chart(
            build_line_chart(cumulative_df, "kumulovana_spotreba", "Kumulovaná spotřeba [m³]", GAS_CONSUMPTION_COLOR),
            width="stretch",
        )


def render_data_table(df: pd.DataFrame, detail_df: pd.DataFrame, detail_level: str) -> None:
    if detail_level == "Ne" or detail_df.empty:
        table_df = (
            df.rename(
                columns={
                    "date": "Datum",
                    "identifikace": "Plynoměr",
                    "seriove_cislo": "Sériové číslo",
                    "objem": "Objem",
                    "platne": "Platné",
                    "spotreba": "Spotřeba",
                    "kumulovana_spotreba": "Kumulovaná spotřeba",
                    "reset_detected": "Reset detekován",
                }
            )
            .sort_values("Datum", ascending=False)
        )
        table_df = format_consumption_dataframe(
            table_df,
            columns=("Objem", "Spotřeba", "Kumulovaná spotřeba"),
        )
        st.dataframe(table_df, width="stretch", hide_index=True)
        return

    table_df = detail_df.rename(
        columns={
            "date": "Datum",
            "identifikace": "Plynoměr",
            "seriove_cislo": "Sériové číslo",
            "objem": "Objem",
            "spotreba": "Spotřeba",
            "kumulovana_spotreba": "Kumulovaná spotřeba",
            "platna_data": "Platná data",
            "pocet_resetu": "Počet resetů",
        }
    ).sort_values("Datum", ascending=True)
    table_df = format_consumption_dataframe(
        table_df,
        columns=("Objem", "Spotřeba", "Kumulovaná spotřeba"),
    )
    st.dataframe(table_df, width="stretch", hide_index=True)


def render_export_button(df: pd.DataFrame, selected_ident: str, start_date: datetime.date, end_date: datetime.date, detail_level: str) -> None:
    file_suffix = "surova_data" if detail_level == "Ne" else detail_level.lower()
    file_name = f"spotreba_plynu_{selected_ident}_{start_date}_{end_date}_{file_suffix}.xlsx"
    excel_bytes = dataframe_to_excel_bytes(build_export_dataframe(df), "Spotreba plynu")
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
    user_is_admin, allowed_devices = get_plynomery_access_context()
    selected_ident, start_date, end_date, detail_level, graph_enabled = render_overview_sidebar(
        user_is_admin,
        allowed_devices,
    )

    st.caption("Filtr se aplikuje až po kliknutí na `Načíst data` v sidebaru.")

    if not st.session_state.get(APPLIED_KEY):
        st.info("Klikněte na `Načíst data` pro zobrazení dat vybraného plynoměru.")
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
    axis_column = time_axis_column(measurements_df)

    st.title(f"Spotřeba plynu - {selected_ident}")
    actual_range = f"{format_value(measurements_df[axis_column].min())} - {format_value(measurements_df[axis_column].max())}"
    st.caption(f"Reálně načtený rozsah dat: {actual_range}")

    render_summary_metrics(measurements_df)

    with st.container(border=True):
        st.subheader("Počáteční a konečný stav")
        boundary_display_df = format_consumption_dataframe(boundary_table, columns=("Objem",)).set_index("Datum")
        st.table(boundary_display_df)
        export_source = measurements_df if detail_level == "Ne" or detail_df.empty else detail_df
        render_export_button(export_source, selected_ident, start_date, end_date, detail_level)

    if not change_table.empty:
        with st.container(border=True):
            st.subheader("Resety nebo výměny plynoměrů")
            st.table(format_consumption_dataframe(change_table, columns=("Objem",)))

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
