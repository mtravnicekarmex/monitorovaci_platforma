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
    build_prediction_metric_summary,
    format_consumption_dataframe,
    format_consumption_with_unit,
    format_value,
    get_plynomery_access_context,
    load_ident_options,
    load_measurement_series,
    load_prediction_series,
    normalize_date_range,
    render_page_styles,
    round_consumption_columns,
)
from moduly.apps.dashboard.time_semantics import add_chart_time, time_axis_column
from moduly.mereni.reset_detection import (
    RESET_NEGATIVE_DIFF_ROUND_DECIMALS,
    RESET_NEGATIVE_DIFF_THRESHOLD,
    has_significant_negative_diff,
)


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
PREDICTION_COLOR = "#dedcd9"


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
    stored_reset = prepared["reset_detected"].map(lambda value: bool(value) if pd.notna(value) else False)
    reset_detected = diff_from_volume.round(RESET_NEGATIVE_DIFF_ROUND_DECIMALS).lt(
        -RESET_NEGATIVE_DIFF_THRESHOLD
    ).fillna(False) | stored_reset
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
        volume_reset = has_significant_negative_diff(row["objem"], previous_row["objem"])
        reset_flag = bool(row.get("reset_detected", False))

        if volume_reset or reset_flag:
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


def render_prediction_summary(prediction: dict[str, object]) -> None:
    rows = prediction["rows"]
    if not prediction.get("prediction_available") or rows.empty:
        st.metric("Predikce za období", "Nedostupné")
        if prediction.get("availability_reason") == "insufficient_history":
            st.caption(
                "Pro toto odběrné místo zatím není dostatečná historie."
            )
        return

    expected_total = round(float(rows["ocekavana_spotreba"].sum()), 3)
    st.metric(
        "Predikce za období",
        format_consumption_with_unit(expected_total),
    )
    if prediction.get("availability_status") == "partial":
        st.warning("Predikce je dostupná pouze pro část vybraného období.")


def render_overview_metrics(
    measurements_df: pd.DataFrame,
    prediction: dict[str, object],
) -> None:
    prediction_df = prediction["rows"]
    prediction_available = (
        bool(prediction.get("prediction_available"))
        and not prediction_df.empty
    )
    summary = build_prediction_metric_summary(
        measurements_df,
        prediction_df if prediction_available else prediction_df.iloc[0:0],
    )
    with st.container(key="mobile_metric_grid_plynomery_summary"):
        metric_cols = st.columns(4)
        metric_cols[0].metric(
            "Spotřeba za období",
            format_consumption_with_unit(summary["actual_total"]),
        )
        if prediction_available:
            expected_total = summary["expected_total"]
            deviation = summary["deviation"]
            deviation_pct = summary["deviation_pct"]
            metric_cols[1].metric(
                "Očekávaná spotřeba",
                format_consumption_with_unit(expected_total),
            )
            metric_cols[2].metric(
                "Odchylka",
                format_consumption_with_unit(deviation, signed=True),
            )
            metric_cols[3].metric(
                "Odchylka [%]",
                "N/A" if deviation_pct is None else f"{deviation_pct:+.1f} %",
            )
        else:
            metric_cols[1].metric("Očekávaná spotřeba", "Nedostupné")
            metric_cols[2].metric("Odchylka", "Nedostupné")
            metric_cols[3].metric("Odchylka [%]", "Nedostupné")

    if prediction.get("availability_reason") == "insufficient_history":
        st.caption(
            "Pro toto odběrné místo zatím není dostatečná historie."
        )
    if prediction.get("availability_status") == "partial":
        st.warning("Predikce je dostupná pouze pro část vybraného období.")


def build_prediction_chart(
    prediction_df: pd.DataFrame,
    *,
    value_column: str = "ocekavana_spotreba",
    y_title: str = "Spotřeba [m³]",
    tooltip_title: str = "Predikce",
) -> alt.Chart:
    return (
        alt.Chart(
            prediction_df.dropna(
                subset=["date", value_column]
            )
        )
        .mark_line(
            color=PREDICTION_COLOR,
            strokeWidth=2.5,
        )
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y(
                f"{value_column}:Q",
                title=y_title,
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Datum"),
                alt.Tooltip(
                    f"{value_column}:Q",
                    title=tooltip_title,
                    format=".3f",
                ),
            ],
        )
        .properties(height=320)
    )


def render_graph_legend(show_prediction: bool) -> None:
    legend_items = [
        '<span style="display:inline-flex;align-items:center;gap:0.4rem;margin-right:1rem;">'
        f'<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:{GAS_CONSUMPTION_COLOR};"></span>'
        "Spotřeba"
        "</span>"
    ]
    if show_prediction:
        legend_items.append(
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;">'
            f'<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:{PREDICTION_COLOR};border:1px solid #cfcac4;"></span>'
            "Predikce"
            "</span>"
        )
    st.markdown(
        f'<div style="margin-top:0.75rem;font-size:0.92rem;">{"".join(legend_items)}</div>',
        unsafe_allow_html=True,
    )


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


def render_graphs(
    df: pd.DataFrame,
    detail_df: pd.DataFrame,
    detail_level: str,
    prediction_df: pd.DataFrame,
) -> None:
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
            actual_chart = build_bar_chart(
                chart_source_df,
                "spotreba",
                "Spotřeba [m³]",
                GAS_CONSUMPTION_COLOR,
            )
            combined_chart = (
                build_prediction_chart(prediction_df) + actual_chart
                if not prediction_df.empty
                else actual_chart
            )
            st.altair_chart(combined_chart, width="stretch")
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
            actual_chart = build_line_chart(
                chart_df,
                "spotreba",
                "Spotřeba [m³]",
                GAS_CONSUMPTION_COLOR,
            )
        else:
            actual_chart = build_bar_chart(
                chart_df,
                "spotreba",
                "Spotřeba [m³]",
                GAS_CONSUMPTION_COLOR,
            )
        combined_chart = (
            build_prediction_chart(prediction_df) + actual_chart
            if not prediction_df.empty
            else actual_chart
        )
        st.altair_chart(combined_chart, width="stretch")
    with chart_cols[1]:
        st.subheader(f"Kumulovaná spotřeba - {detail_level.lower()}")
        cumulative_df = rounded_detail_df[["date", "kumulovana_spotreba"]].copy()
        actual_chart = build_line_chart(
            cumulative_df,
            "kumulovana_spotreba",
            "Kumulovaná spotřeba [m³]",
            GAS_CONSUMPTION_COLOR,
        )
        combined_chart = (
            build_prediction_chart(
                prediction_df,
                value_column="ocekavana_kumulovana_spotreba",
                y_title="Kumulovaná spotřeba [m³]",
                tooltip_title="Očekávaná kumulovaná spotřeba",
            )
            + actual_chart
            if not prediction_df.empty
            else actual_chart
        )
        st.altair_chart(
            combined_chart,
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
    granularity = {
        DETAIL_OPTIONS[1]: "monthly",
        DETAIL_OPTIONS[2]: "daily",
        DETAIL_OPTIONS[3]: "hourly",
    }.get(detail_level, "hourly")
    prediction = load_prediction_series(
        selected_ident,
        start_date,
        end_date,
        granularity,
        allowed_devices,
        user_is_admin,
    )
    prediction_df = prediction["rows"]

    if measurements_df.empty:
        st.info("Pro zvolený filtr nejsou k dispozici žádná měření.")
        st.title(f"Spotřeba plynu - {selected_ident}")
        render_prediction_summary(prediction)
        if graph_enabled and not prediction_df.empty:
            st.altair_chart(
                build_prediction_chart(prediction_df),
                width="stretch",
            )
        return

    detail_df = build_detail_table(measurements_df, detail_level)
    boundary_table = build_boundary_table(measurements_df)
    change_table = build_change_table(measurements_df)
    axis_column = time_axis_column(measurements_df)

    st.title(f"Spotřeba plynu - {selected_ident}")
    actual_range = f"{format_value(measurements_df[axis_column].min())} - {format_value(measurements_df[axis_column].max())}"
    st.caption(f"Reálně načtený rozsah dat: {actual_range}")

    render_overview_metrics(measurements_df, prediction)

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
            render_graphs(
                measurements_df,
                detail_df,
                detail_level,
                prediction_df,
            )
            render_graph_legend(not prediction_df.empty)

    with st.container(border=True):
        st.subheader("Data")
        render_data_table(measurements_df, detail_df, detail_level)


try:
    render_dashboard()
except SQLAlchemyError as exc:
    st.error("Nepodařilo se načíst data z databáze.")
    st.exception(exc)
