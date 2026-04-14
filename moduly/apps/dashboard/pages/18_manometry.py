from __future__ import annotations

import datetime
import io
from pathlib import Path
import sys

import altair as alt
import pandas as pd
import streamlit as st

from app.time_utils import prague_today


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.manometry_shared import (
    format_pressure_dataframe,
    format_pressure_with_unit,
    format_value,
    get_manometry_access_context,
    load_device_detail,
    load_ident_options,
    load_measurement_series,
    normalize_date_range,
    render_page_styles,
    round_pressure_columns,
)


DEVICE_KEY = "manometry_overview_identifikace"
DATE_RANGE_KEY = "manometry_overview_date_range"
DETAIL_KEY = "manometry_overview_detail"
GRAPH_KEY = "manometry_overview_graph"
APPLIED_KEY = "manometry_overview_applied"

DETAIL_OPTIONS = ("Ne", "Měsíčně", "Denně", "Hodinově")
GRAPH_OPTIONS = ("Ne", "Ano")
PRESSURE_LINE_COLOR = "#2563eb"
PRESSURE_BAND_COLOR = "#93c5fd"
INVALID_POINT_COLOR = "#dc2626"


st.set_page_config(
    page_title="Manometry - Přehled",
    page_icon="🎚️",
    layout="wide",
)


require_page_access("manometry_overview")


def format_metric_date(value: object) -> str:
    if value is None or value == "":
        return "-"
    if isinstance(value, datetime.datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, datetime.date):
        return value.strftime("%d.%m.%Y")
    parsed_value = pd.to_datetime(value, errors="coerce")
    if pd.notna(parsed_value):
        return parsed_value.strftime("%d.%m.%Y")
    return str(value)


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
        st.warning("Pro aktuální kombinaci oprávnění nejsou k dispozici žádné manometry.")
        st.stop()

    current_ident = st.session_state.get(DEVICE_KEY)
    if current_ident not in ident_options:
        st.session_state[DEVICE_KEY] = ident_options[0]

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        with st.form("manometry_overview_filters"):
            identifikace = st.selectbox("Manometr", ident_options, key=DEVICE_KEY)
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
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared["hodnota"] = pd.to_numeric(prepared["hodnota"], errors="coerce")
    prepared["platne"] = prepared["platne"].fillna(True).astype(bool)
    prepared = prepared.dropna(subset=["date", "hodnota"]).sort_values("date").reset_index(drop=True)
    return prepared


def build_detail_table(df: pd.DataFrame, detail_level: str) -> pd.DataFrame:
    if detail_level == "Ne" or df.empty:
        return pd.DataFrame()

    freq_map = {
        "Měsíčně": "ME",
        "Denně": "D",
        "Hodinově": "h",
    }
    working_df = df.copy()
    working_df["hodnota_valid"] = working_df["hodnota"].where(working_df["platne"], pd.NA)
    resampled = (
        working_df.set_index("date")
        .resample(freq_map[detail_level])
        .agg(
            identifikace=("identifikace", "first"),
            seriove_cislo=("seriove_cislo", "last"),
            tlak_min=("hodnota_valid", "min"),
            tlak_max=("hodnota_valid", "max"),
            tlak_prumer=("hodnota_valid", "mean"),
            tlak_posledni=("hodnota_valid", "last"),
            pocet_mereni=("hodnota", "count"),
            platna_mereni=("platne", "sum"),
        )
        .reset_index()
    )
    resampled = resampled[resampled["pocet_mereni"] > 0].copy()
    if resampled.empty:
        return resampled

    for column in ("tlak_min", "tlak_max", "tlak_prumer", "tlak_posledni"):
        resampled[column] = pd.to_numeric(resampled[column], errors="coerce").round(3)
    resampled["pocet_mereni"] = pd.to_numeric(resampled["pocet_mereni"], errors="coerce").fillna(0).astype(int)
    resampled["platna_mereni"] = pd.to_numeric(resampled["platna_mereni"], errors="coerce").fillna(0).astype(int)
    resampled["neplatna_mereni"] = (resampled["pocet_mereni"] - resampled["platna_mereni"]).clip(lower=0).astype(int)
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
                series_width = export_df[column].astype(str).str.len().max()
                max_width = max(len(str(column)), int(series_width)) + 2
            worksheet.set_column(idx, idx, min(max_width, 32))
    buffer.seek(0)
    return buffer.getvalue()


def build_export_dataframe(df: pd.DataFrame, detail_level: str) -> pd.DataFrame:
    export_df = df.copy()
    if detail_level == "Ne":
        for column in ("date", "identifikace", "seriove_cislo", "hodnota", "platne"):
            if column not in export_df.columns:
                export_df[column] = pd.NA
        return export_df[["date", "identifikace", "seriove_cislo", "hodnota", "platne"]].copy()

    for column in (
        "date",
        "identifikace",
        "seriove_cislo",
        "tlak_min",
        "tlak_max",
        "tlak_prumer",
        "tlak_posledni",
        "pocet_mereni",
        "platna_mereni",
        "neplatna_mereni",
    ):
        if column not in export_df.columns:
            export_df[column] = pd.NA
    return export_df[
        [
            "date",
            "identifikace",
            "seriove_cislo",
            "tlak_min",
            "tlak_max",
            "tlak_prumer",
            "tlak_posledni",
            "pocet_mereni",
            "platna_mereni",
            "neplatna_mereni",
        ]
    ].copy()


def render_summary_metrics(device_detail: dict[str, object] | None) -> None:
    metric_cols = st.columns(4)
    if device_detail is None:
        metric_cols[0].metric("Minimální tlak", "-")
        metric_cols[1].metric("Datum minima", "-")
        metric_cols[2].metric("Maximální tlak", "-")
        metric_cols[3].metric("Datum maxima", "-")
        return

    metric_cols[0].metric("Minimální tlak", format_pressure_with_unit(device_detail.get("min_pressure")))
    metric_cols[1].metric("Datum minima", format_metric_date(device_detail.get("min_pressure_at")))
    metric_cols[2].metric("Maximální tlak", format_pressure_with_unit(device_detail.get("max_pressure")))
    metric_cols[3].metric("Datum maxima", format_metric_date(device_detail.get("max_pressure_at")))


def render_device_summary(
    device_detail: dict[str, object] | None,
    export_df: pd.DataFrame,
    selected_ident: str,
    start_date: datetime.date,
    end_date: datetime.date,
    detail_level: str,
) -> None:
    with st.container(border=True):
        summary_col, action_col = st.columns([4, 1])
        with summary_col:
            st.subheader("Souhrn manometru")
        with action_col:
            render_export_button(export_df, selected_ident, start_date, end_date, detail_level)

        if device_detail is None:
            st.info("Metadata manometru nebyla nalezena.")
            return

        metadata_pairs = [
            ("Identifikace", format_value(device_detail.get("identifikace"))),
            ("Sériové číslo", format_value(device_detail.get("seriove_cislo"))),
            ("Objekt", format_value(device_detail.get("objekt"))),
            ("Patro", format_value(device_detail.get("patro"))),
            ("Místnost", format_value(device_detail.get("mistnost"))),
            ("Větev", format_value(device_detail.get("vetev"))),
            ("Měřeno od", format_value(device_detail.get("first_measurement_at"))),
            ("Poslední měření", format_value(device_detail.get("last_measurement_at"))),
            ("Počet měření", format_value(device_detail.get("measurement_count"))),
            ("Platná měření", format_value(device_detail.get("valid_measurement_count"))),
        ]
        metadata_df = pd.DataFrame(metadata_pairs, columns=["Pole", "Hodnota"])
        meta_col_1, meta_col_2 = st.columns(2)
        midpoint = (len(metadata_df) + 1) // 2
        meta_col_1.dataframe(metadata_df.iloc[:midpoint], width="stretch", hide_index=True)
        meta_col_2.dataframe(metadata_df.iloc[midpoint:], width="stretch", hide_index=True)


def build_raw_chart(df: pd.DataFrame) -> alt.Chart | None:
    if df.empty:
        return None

    valid_df = df[df["platne"]].copy()
    if valid_df.empty:
        valid_df = df.copy()

    line_chart = (
        alt.Chart(valid_df)
        .mark_line(color=PRESSURE_LINE_COLOR, strokeWidth=2.5)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("hodnota:Q", title="Tlak [bar]"),
            tooltip=[
                alt.Tooltip("date:T", title="Datum"),
                alt.Tooltip("hodnota:Q", title="Tlak [bar]", format=".3f"),
                alt.Tooltip("seriove_cislo:N", title="Sériové číslo"),
                alt.Tooltip("platne:N", title="Platné"),
            ],
        )
    )
    invalid_df = df[~df["platne"]].copy()
    if invalid_df.empty:
        return line_chart.properties(height=340).interactive()

    invalid_points = (
        alt.Chart(invalid_df)
        .mark_circle(color=INVALID_POINT_COLOR, size=55)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("hodnota:Q", title="Tlak [bar]"),
            tooltip=[
                alt.Tooltip("date:T", title="Datum"),
                alt.Tooltip("hodnota:Q", title="Tlak [bar]", format=".3f"),
                alt.Tooltip("seriove_cislo:N", title="Sériové číslo"),
                alt.Tooltip("platne:N", title="Platné"),
            ],
        )
    )
    return (line_chart + invalid_points).properties(height=340).interactive()


def render_graph_legend(detail_level: str, has_invalid_measurements: bool) -> None:
    legend_items = []
    if detail_level == "Ne":
        legend_items.append(
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;margin-right:1rem;">'
            '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#2563eb;"></span>'
            "Platná měření"
            "</span>"
        )
        if has_invalid_measurements:
            legend_items.append(
                '<span style="display:inline-flex;align-items:center;gap:0.4rem;">'
                '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#dc2626;"></span>'
                "Neplatná měření"
                "</span>"
            )
    else:
        legend_items.append(
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;margin-right:1rem;">'
            '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#2563eb;"></span>'
            "Průměrný tlak"
            "</span>"
        )
        legend_items.append(
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;">'
            '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#93c5fd;"></span>'
            "Rozsah min-max"
            "</span>"
        )

    st.markdown(
        f'<div style="margin-top:0.75rem;font-size:0.92rem;">{"".join(legend_items)}</div>',
        unsafe_allow_html=True,
    )


def render_graphs(df: pd.DataFrame, detail_df: pd.DataFrame, detail_level: str) -> None:
    chart = build_raw_chart(df) if detail_level == "Ne" or detail_df.empty else build_detail_chart_with_format(detail_df, detail_level)
    if chart is None:
        st.info("Pro vybraný filtr není k dispozici dostatek dat pro vykreslení grafu.")
        return
    st.altair_chart(chart, width="stretch")
    render_graph_legend(detail_level, has_invalid_measurements=bool((~df["platne"]).any()))


def build_detail_chart_with_format(detail_df: pd.DataFrame, detail_level: str) -> alt.Chart | None:
    if detail_df.empty:
        return None

    chart_df = round_pressure_columns(
        detail_df,
        columns=("tlak_min", "tlak_max", "tlak_prumer", "tlak_posledni"),
    )
    band_chart = (
        alt.Chart(chart_df)
        .mark_area(color=PRESSURE_BAND_COLOR, opacity=0.28)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("tlak_min:Q", title="Tlak [bar]"),
            y2=alt.Y2("tlak_max:Q"),
            tooltip=[
                alt.Tooltip("date:T", title="Datum"),
                alt.Tooltip("tlak_min:Q", title="Tlak min [bar]", format=".3f"),
                alt.Tooltip("tlak_max:Q", title="Tlak max [bar]", format=".3f"),
                alt.Tooltip("tlak_prumer:Q", title="Tlak průměr [bar]", format=".3f"),
                alt.Tooltip("pocet_mereni:Q", title="Počet měření"),
            ],
        )
    )
    average_chart = (
        alt.Chart(chart_df)
        .mark_line(color=PRESSURE_LINE_COLOR, strokeWidth=2.5)
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("tlak_prumer:Q", title="Tlak [bar]"),
        )
    )
    return (band_chart + average_chart).properties(height=340).interactive()


def render_data_table(df: pd.DataFrame, detail_df: pd.DataFrame, detail_level: str) -> None:
    if detail_level == "Ne" or detail_df.empty:
        table_df = (
            df.rename(
                columns={
                    "date": "Datum",
                    "identifikace": "Manometr",
                    "seriove_cislo": "Sériové číslo",
                    "hodnota": "Tlak",
                    "platne": "Platné",
                }
            )
            .sort_values("Datum", ascending=False)
        )
        table_df = format_pressure_dataframe(table_df, columns=("Tlak",))
        st.dataframe(table_df, width="stretch", hide_index=True)
        return

    table_df = detail_df.rename(
        columns={
            "date": "Datum",
            "identifikace": "Manometr",
            "seriove_cislo": "Sériové číslo",
            "tlak_min": "Tlak min",
            "tlak_max": "Tlak max",
            "tlak_prumer": "Tlak prumer",
            "tlak_posledni": "Posledni tlak",
            "pocet_mereni": "Počet měření",
            "platna_mereni": "Platná měření",
            "neplatna_mereni": "Neplatná měření",
        }
    ).sort_values("Datum", ascending=True)
    table_df = format_pressure_dataframe(
        table_df,
        columns=("Tlak min", "Tlak max", "Tlak prumer", "Posledni tlak"),
    )
    st.dataframe(table_df, width="stretch", hide_index=True)


def render_export_button(
    df: pd.DataFrame,
    selected_ident: str,
    start_date: datetime.date,
    end_date: datetime.date,
    detail_level: str,
) -> None:
    file_suffix = "surova_data" if detail_level == "Ne" else detail_level.lower()
    file_name = f"tlak_manometru_{selected_ident}_{start_date}_{end_date}_{file_suffix}.xlsx"
    excel_bytes = dataframe_to_excel_bytes(build_export_dataframe(df, detail_level), "Tlak")
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
    user_is_admin, allowed_devices = get_manometry_access_context()
    selected_ident, start_date, end_date, detail_level, graph_enabled = render_overview_sidebar(
        user_is_admin,
        allowed_devices,
    )

    st.caption("Filtr se aplikuje až po kliknutí na `Načíst data` v sidebaru.")

    if not st.session_state.get(APPLIED_KEY):
        st.info("Klikněte na `Načíst data` pro zobrazení dat vybraného manometru.")
        return

    device_detail = load_device_detail(selected_ident, allowed_devices, user_is_admin)
    measurements_df = load_measurement_series(
        selected_ident,
        start_date,
        end_date,
        allowed_devices,
        user_is_admin,
    )
    measurements_df = prepare_measurements(measurements_df)
    detail_df = build_detail_table(measurements_df, detail_level)

    st.title(f"Průběh tlaku - {selected_ident}")
    render_summary_metrics(device_detail)

    export_source = measurements_df if detail_level == "Ne" or detail_df.empty else detail_df
    render_device_summary(device_detail, export_source, selected_ident, start_date, end_date, detail_level)

    if measurements_df.empty:
        st.info("Pro zvolený filtr nejsou k dispozici žádná měření.")
        return

    actual_range = f"{format_value(measurements_df['date'].min())} - {format_value(measurements_df['date'].max())}"
    st.caption(f"Reálně načtený rozsah dat: {actual_range}")

    with st.container(border=True):
        st.subheader("Graf s průběhem")
        if graph_enabled:
            render_graphs(measurements_df, detail_df, detail_level)
        else:
            st.info("Pro zobrazení grafu nastavte ve filtru `Graf` na `Ano` a načtěte data.")


try:
    render_dashboard()
except DashboardApiError as exc:
    st.error("Nepodařilo se načíst data pro manometry.")
    st.exception(exc)
