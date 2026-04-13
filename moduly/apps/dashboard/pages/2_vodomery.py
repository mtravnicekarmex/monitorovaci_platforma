from __future__ import annotations

import datetime
import io
import altair as alt
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from app.time_utils import prague_today


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.vodomery_shared import (
    format_consumption_dataframe,
    format_consumption_with_unit,
    format_value,
    get_vodomery_access_context,
    load_ident_options,
    load_measurement_series,
    load_prediction_profiles,
    normalize_date_range,
    round_consumption_columns,
    render_page_styles,
)


SOURCE_FILTER_KEY = "vodomery_overview_source_filter"
DEVICE_KEY = "vodomery_overview_identifikace"
DATE_RANGE_KEY = "vodomery_overview_date_range"
DETAIL_KEY = "vodomery_overview_detail"
GRAPH_KEY = "vodomery_overview_graph"
APPLIED_KEY = "vodomery_overview_applied"

DETAIL_OPTIONS = ("Ne", "Měsíčně", "Denně", "Hodinově")
GRAPH_OPTIONS = ("Ne", "Ano")


st.set_page_config(
    page_title="Vodoměry - Přehled",
    page_icon="💧",
    layout="wide",
)


require_page_access("vodomery_overview")


def init_overview_state() -> None:
    default_end = prague_today()
    default_start = default_end - datetime.timedelta(days=1)
    st.session_state.setdefault(SOURCE_FILTER_KEY, "VSE")
    st.session_state.setdefault(DATE_RANGE_KEY, (default_start, default_end))
    st.session_state.setdefault(DETAIL_KEY, "Ne")
    st.session_state.setdefault(GRAPH_KEY, "Ne")
    st.session_state.setdefault(APPLIED_KEY, False)


def render_overview_sidebar(
    user_is_admin: bool,
    allowed_devices: tuple[str, ...],
) -> tuple[str, str, datetime.date, datetime.date, str, bool]:
    init_overview_state()

    source_filter = "VSE"
    st.session_state[SOURCE_FILTER_KEY] = source_filter
    ident_options = load_ident_options(source_filter, allowed_devices, user_is_admin)
    if not ident_options:
        st.warning("Pro aktuální kombinaci oprávnění nejsou k dispozici žádné vodoměry.")
        st.stop()

    current_ident = st.session_state.get(DEVICE_KEY)
    if current_ident not in ident_options:
        st.session_state[DEVICE_KEY] = ident_options[0]

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        with st.form("vodomery_overview_filters"):
            identifikace = st.selectbox("Vodoměr", ident_options, key=DEVICE_KEY)
            date_range = st.date_input("Vybrat období:", key=DATE_RANGE_KEY)
            detail_level = st.selectbox("Detailní výpis", DETAIL_OPTIONS, key=DETAIL_KEY)
            graph_option = st.selectbox("Graf", GRAPH_OPTIONS, key=GRAPH_KEY)
            apply_filters = st.form_submit_button("Načíst data", width="stretch")

    if apply_filters:
        st.session_state[APPLIED_KEY] = True

    start_date, end_date = normalize_date_range(date_range)
    graph_enabled = graph_option == "Ano"
    return source_filter, identifikace, start_date, end_date, detail_level, graph_enabled


def prepare_measurements(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared = prepared.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    if prepared.empty:
        return prepared

    diff_from_volume = prepared["objem"].diff()
    prepared["spotreba"] = prepared["delta"].where(prepared["delta"].notna(), diff_from_volume)
    prepared["spotreba"] = pd.to_numeric(prepared["spotreba"], errors="coerce").fillna(0.0)
    prepared.loc[prepared.index[0], "spotreba"] = 0.0
    prepared.loc[prepared["spotreba"] < 0, "spotreba"] = 0.0
    if "platne" in prepared.columns:
        prepared.loc[~prepared["platne"].fillna(True), "spotreba"] = 0.0
    prepared.loc[prepared["reset_detected"].fillna(False), "spotreba"] = 0.0
    prepared["spotreba"] = prepared["spotreba"].round(3)
    prepared["kumulovana_spotreba"] = prepared["spotreba"].cumsum().round(3)
    return prepared


def apply_prediction_layer(df: pd.DataFrame, profiles_df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    prepared["ocekavana_spotreba"] = pd.NA
    prepared["ocekavana_kumulovana_spotreba"] = pd.NA
    prepared["model_version"] = pd.NA

    if prepared.empty or profiles_df.empty:
        return prepared

    prepared = prepared.drop(columns=["model_version"], errors="ignore")
    merged = prepared.merge(
        profiles_df[["interval_minutes", "day_of_week", "slot", "expected_mean", "model_version"]],
        on=["interval_minutes", "day_of_week", "slot"],
        how="left",
    )
    merged["ocekavana_spotreba"] = pd.to_numeric(merged["expected_mean"], errors="coerce").round(3)
    merged["ocekavana_kumulovana_spotreba"] = merged["ocekavana_spotreba"].fillna(0).cumsum().round(3)
    return merged


def has_prediction_data(df: pd.DataFrame) -> bool:
    return "ocekavana_spotreba" in df.columns and df["ocekavana_spotreba"].notna().any()


def build_full_day_hourly_prediction(profiles_df: pd.DataFrame, target_date: datetime.date) -> pd.DataFrame:
    if profiles_df.empty:
        return pd.DataFrame()

    weekday_profiles = profiles_df[profiles_df["day_of_week"] == target_date.weekday()].copy()
    if weekday_profiles.empty:
        return pd.DataFrame()

    weekday_profiles["interval_minutes"] = pd.to_numeric(weekday_profiles["interval_minutes"], errors="coerce")
    weekday_profiles["slot"] = pd.to_numeric(weekday_profiles["slot"], errors="coerce")
    weekday_profiles["expected_mean"] = pd.to_numeric(weekday_profiles["expected_mean"], errors="coerce")
    weekday_profiles = weekday_profiles.dropna(subset=["interval_minutes", "slot", "expected_mean"])
    if weekday_profiles.empty:
        return pd.DataFrame()

    day_start = pd.Timestamp(target_date)
    weekday_profiles["date"] = day_start + pd.to_timedelta(
        weekday_profiles["slot"] * weekday_profiles["interval_minutes"],
        unit="m",
    )

    hourly_prediction = (
        weekday_profiles[["date", "expected_mean"]]
        .set_index("date")
        .resample("h")
        .sum()
        .rename(columns={"expected_mean": "ocekavana_spotreba"})
    )
    full_index = pd.date_range(start=day_start, periods=24, freq="h")
    hourly_prediction = hourly_prediction.reindex(full_index, fill_value=0.0)
    hourly_prediction.index.name = "date"
    hourly_prediction = hourly_prediction.reset_index()
    hourly_prediction["ocekavana_kumulovana_spotreba"] = hourly_prediction["ocekavana_spotreba"].cumsum().round(3)
    hourly_prediction["ocekavana_spotreba"] = hourly_prediction["ocekavana_spotreba"].round(3)
    return hourly_prediction


def render_graph_legend(show_prediction: bool) -> None:
    legend_items = [
        '<span style="display:inline-flex;align-items:center;gap:0.4rem;margin-right:1rem;">'
        '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#1f77b4;"></span>'
        "Spotřeba"
        "</span>"
    ]
    if show_prediction:
        legend_items.append(
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;">'
            '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#dedcd9;border:1px solid #cfcac4;"></span>'
            "Predikce"
            "</span>"
        )
    st.markdown(
        f'<div style="margin-top:0.75rem;font-size:0.92rem;">{"".join(legend_items)}</div>',
        unsafe_allow_html=True,
    )


def build_boundary_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    boundary = df.iloc[[0, -1]].copy()
    boundary = boundary.drop_duplicates(subset=["date", "objem", "seriove_cislo"])
    return boundary.rename(
        columns={
            "date": "Datum",
            "objem": "Objem",
            "identifikace": "Vodomer",
            "seriove_cislo": "Seriove cislo",
            "zdroj": "Zdroj",
        }
    )[["Datum", "Objem", "Vodomer", "Seriove cislo", "Zdroj"]]


def build_change_table(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 2:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    previous_row = df.iloc[0]
    for _, row in df.iloc[1:].iterrows():
        serial_changed = row["seriove_cislo"] != previous_row["seriove_cislo"]
        volume_reset = row["objem"] < previous_row["objem"]
        reset_flag = bool(row["reset_detected"])

        if serial_changed or volume_reset or reset_flag:
            rows.append(
                {
                    "Datum": previous_row["date"],
                    "Objem": previous_row["objem"],
                    "Seriove cislo": previous_row["seriove_cislo"],
                    "Poznamka": "Konecny stav puvodniho vodomeru",
                }
            )
            rows.append(
                {
                    "Datum": row["date"],
                    "Objem": row["objem"],
                    "Seriove cislo": row["seriove_cislo"],
                    "Poznamka": "Pocatecni stav noveho nebo resetovaneho vodomeru",
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
    aggregation_map: dict[str, str] = {
        "objem": "last",
        "identifikace": "first",
        "seriove_cislo": "last",
        "zdroj": "last",
        "spotreba": "sum",
        "kumulovana_spotreba": "last",
        "synthetic": "max",
        "nocni_odber": "max",
        "gap_detected": "max",
        "reset_detected": "sum",
    }
    if "model_version" in df.columns:
        aggregation_map["model_version"] = "max"
    if "ocekavana_spotreba" in df.columns:
        aggregation_map["ocekavana_spotreba"] = "sum"
    if "ocekavana_kumulovana_spotreba" in df.columns:
        aggregation_map["ocekavana_kumulovana_spotreba"] = "last"

    resampled = df.set_index("date").resample(freq_map[detail_level]).agg(aggregation_map).reset_index()
    resampled = resampled.rename(
        columns={
            "synthetic": "synteticka_data",
            "gap_detected": "mezera_v_datech",
            "reset_detected": "pocet_resetu",
        }
    )
    resampled = resampled[resampled["objem"].notna()].copy()
    if resampled.empty:
        return resampled

    resampled["spotreba"] = resampled["spotreba"].round(3)
    resampled["kumulovana_spotreba"] = resampled["kumulovana_spotreba"].round(3)
    if "ocekavana_spotreba" in resampled.columns:
        resampled["ocekavana_spotreba"] = pd.to_numeric(resampled["ocekavana_spotreba"], errors="coerce").round(3)
    if "ocekavana_kumulovana_spotreba" in resampled.columns:
        resampled["ocekavana_kumulovana_spotreba"] = pd.to_numeric(
            resampled["ocekavana_kumulovana_spotreba"],
            errors="coerce",
        ).round(3)
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
                series_width = export_df[column].astype(str).str.len().max()
                max_width = max(len(str(column)), int(series_width)) + 2
            worksheet.set_column(idx, idx, min(max_width, 32))
    buffer.seek(0)
    return buffer.getvalue()


def build_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    export_df = df.copy()
    export_df = export_df.rename(
        columns={
            "date": "date",
            "objem": "objem",
            "identifikace": "identifikace",
            "seriove_cislo": "seriove_cislo",
            "spotreba": "spotreba",
            "kumulovana_spotreba": "kumulovana_spotreba",
        }
    )
    return export_df[
        [
            "date",
            "objem",
            "identifikace",
            "seriove_cislo",
            "spotreba",
            "kumulovana_spotreba",
        ]
    ].copy()


def render_summary_metrics(df: pd.DataFrame, change_table: pd.DataFrame) -> None:
    total_consumption = round(float(df["kumulovana_spotreba"].iloc[-1]), 3)
    metric_cols = st.columns(4)
    metric_cols[0].metric("Spotřeba za období", format_consumption_with_unit(total_consumption))
    if has_prediction_data(df):
        expected_total = round(float(df["ocekavana_spotreba"].fillna(0).sum()), 3)
        deviation = round(total_consumption - expected_total, 3)
        if expected_total != 0:
            deviation_pct = (deviation / expected_total) * 100
            deviation_pct_label = f"{deviation_pct:+.1f} %"
        else:
            deviation_pct_label = "N/A"
        metric_cols[1].metric("Očekávaná spotřeba", format_consumption_with_unit(expected_total))
        metric_cols[2].metric("Odchylka", format_consumption_with_unit(deviation, signed=True))
        metric_cols[3].metric("Odchylka [%]", deviation_pct_label)
    else:
        metric_cols[1].metric("Resety a výměny", max(int(df["reset_detected"].fillna(False).sum()), len(change_table) // 2))
        metric_cols[2].metric("Počet měření", int(len(df)))
        metric_cols[3].metric("Predikce", "N/A")




def render_graphs(
    df: pd.DataFrame,
    detail_df: pd.DataFrame,
    detail_level: str,
    start_date: datetime.date,
    end_date: datetime.date,
    profiles_df: pd.DataFrame,
) -> None:
    if detail_level == "Ne" or detail_df.empty:
        chart_source_df = round_consumption_columns(df, columns=("objem", "spotreba"))
        chart_cols = st.columns(2)
        with chart_cols[0]:
            st.subheader("Objem")
            st.line_chart(chart_source_df.set_index("date")[["objem"]], height=320)
        with chart_cols[1]:
            st.subheader("Spotřeba")
            st.bar_chart(chart_source_df.set_index("date")[["spotreba"]], height=320)
        return

    use_line_chart = detail_level == "Hodinově"
    prediction_available = has_prediction_data(detail_df)
    today = prague_today()
    use_full_day_today_prediction = (
        detail_level == "Hodinově"
        and start_date == end_date == today
        and not profiles_df.empty
    )
    full_day_prediction_df = build_full_day_hourly_prediction(profiles_df, start_date) if use_full_day_today_prediction else pd.DataFrame()
    if not full_day_prediction_df.empty:
        prediction_available = True
    rounded_detail_df = round_consumption_columns(
        detail_df,
        columns=("spotreba", "kumulovana_spotreba", "ocekavana_spotreba", "ocekavana_kumulovana_spotreba"),
    )
    chart_cols = st.columns(2)
    with chart_cols[0]:
        st.subheader(f"Spotřeba - {detail_level.lower()}")
        chart_df = rounded_detail_df[["date", "spotreba"]].rename(columns={"spotreba": "Spotřeba"}).copy()
        if prediction_available:
            if not full_day_prediction_df.empty:
                chart_df = chart_df.merge(
                    round_consumption_columns(full_day_prediction_df, columns=("ocekavana_spotreba",))[["date", "ocekavana_spotreba"]],
                    on="date",
                    how="outer",
                ).sort_values("date")
            else:
                chart_df["ocekavana_spotreba"] = rounded_detail_df["ocekavana_spotreba"].values
            chart_df = chart_df.rename(columns={"ocekavana_spotreba": "Očekávaná spotřeba"})
        if use_line_chart:
            if prediction_available:
                actual_chart = alt.Chart(chart_df).mark_line(color="#1f77b4").encode(
                    x=alt.X("date:T", title=None),
                    y=alt.Y("Spotřeba:Q", title=None),
                )
                expected_chart = alt.Chart(chart_df.dropna(subset=["Očekávaná spotřeba"])).mark_line(color="#dedcd9").encode(
                    x=alt.X("date:T", title=None),
                    y=alt.Y("Očekávaná spotřeba:Q", title=None),
                )
                st.altair_chart((expected_chart + actual_chart).interactive(), width="stretch")
            else:
                st.line_chart(chart_df.set_index("date")[["Spotřeba"]], height=320)
        else:
            st.bar_chart(chart_df.set_index("date")[["Spotřeba"]], height=320)
    with chart_cols[1]:
        st.subheader(f"Kumulovaná spotřeba - {detail_level.lower()}")
        cumulative_df = rounded_detail_df[["date", "kumulovana_spotreba"]].rename(
            columns={"kumulovana_spotreba": "Kumulovaná spotřeba"}
        ).copy()
        if prediction_available:
            if not full_day_prediction_df.empty:
                cumulative_df = cumulative_df.merge(
                    round_consumption_columns(
                        full_day_prediction_df,
                        columns=("ocekavana_kumulovana_spotreba",),
                    )[["date", "ocekavana_kumulovana_spotreba"]],
                    on="date",
                    how="outer",
                ).sort_values("date")
            else:
                cumulative_df["ocekavana_kumulovana_spotreba"] = rounded_detail_df["ocekavana_kumulovana_spotreba"].values
            cumulative_df = cumulative_df.rename(
                columns={"ocekavana_kumulovana_spotreba": "Očekávaná kumulovaná spotřeba"}
            )
            actual_chart = alt.Chart(cumulative_df).mark_line(color="#1f77b4").encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("Kumulovaná spotřeba:Q", title=None),
            )
            expected_chart = alt.Chart(
                cumulative_df.dropna(subset=["Očekávaná kumulovaná spotřeba"])
            ).mark_line(color="#dedcd9").encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("Očekávaná kumulovaná spotřeba:Q", title=None),
            )
            st.altair_chart((expected_chart + actual_chart).interactive(), width="stretch")
        else:
            st.line_chart(cumulative_df.set_index("date")[["Kumulovaná spotřeba"]], height=320)


def render_data_table(df: pd.DataFrame, detail_df: pd.DataFrame, detail_level: str) -> None:
    if detail_level == "Ne" or detail_df.empty:
        table_df = (
            df.rename(
                columns={
                    "date": "Datum",
                    "identifikace": "Vodomer",
                    "seriove_cislo": "Seriove cislo",
                    "zdroj": "Zdroj",
                    "objem": "Objem",
                    "delta": "Delta",
                    "spotreba": "Spotreba",
                    "kumulovana_spotreba": "Kumulovana spotreba",
                    "synthetic": "Synteticka data",
                    "nocni_odber": "Nocni odber",
                    "gap_detected": "Mezera v datech",
                    "reset_detected": "Reset detekovan",
                }
            )
            .sort_values("Datum", ascending=False)
        )
        table_df = format_consumption_dataframe(
            table_df,
            columns=("Objem", "Delta", "Spotreba", "Kumulovana spotreba"),
        )
        st.dataframe(table_df, width="stretch", hide_index=True)
        return

    table_df = detail_df.rename(
        columns={
            "date": "Datum",
            "identifikace": "Vodomer",
            "seriove_cislo": "Seriove cislo",
            "zdroj": "Zdroj",
            "objem": "Objem",
            "spotreba": "Spotreba",
            "kumulovana_spotreba": "Kumulovana spotreba",
            "ocekavana_spotreba": "Ocekavana spotreba",
            "ocekavana_kumulovana_spotreba": "Ocekavana kumulovana spotreba",
            "synteticka_data": "Synteticka data",
            "nocni_odber": "Nocni odber",
            "mezera_v_datech": "Mezera v datech",
            "pocet_resetu": "Pocet resetu",
        }
    ).sort_values("Datum", ascending=True)
    if not has_prediction_data(detail_df):
        table_df = table_df.drop(columns=["Ocekavana spotreba", "Ocekavana kumulovana spotreba"], errors="ignore")
    table_df = format_consumption_dataframe(
        table_df,
        columns=("Objem", "Spotreba", "Kumulovana spotreba", "Ocekavana spotreba", "Ocekavana kumulovana spotreba"),
    )
    st.dataframe(table_df, width="stretch", hide_index=True)


def render_export_button(df: pd.DataFrame, selected_ident: str, start_date: datetime.date, end_date: datetime.date, detail_level: str) -> None:
    file_suffix = "surova_data" if detail_level == "Ne" else detail_level.lower()
    file_name = f"spotřeba_vody_{selected_ident}_{start_date}_{end_date}_{file_suffix}.xlsx"
    excel_bytes = dataframe_to_excel_bytes(build_export_dataframe(df), "Spotřeba vody")
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
    user_is_admin, allowed_devices = get_vodomery_access_context()
    source_filter, selected_ident, start_date, end_date, detail_level, graph_enabled = render_overview_sidebar(
        user_is_admin,
        allowed_devices,
    )

    st.caption("Filtr se aplikuje až po kliknutí na `Načíst data` v sidebaru.")

    if not st.session_state.get(APPLIED_KEY):
        st.info("Klikněte na `Načíst data` pro zobrazení dat vybraného vodoměru.")
        return

    measurements_df = load_measurement_series(
        source_filter,
        selected_ident,
        start_date,
        end_date,
        allowed_devices,
        user_is_admin,
    )
    measurements_df = prepare_measurements(measurements_df)
    profiles_df = load_prediction_profiles(selected_ident, allowed_devices, user_is_admin)
    measurements_df = apply_prediction_layer(measurements_df, profiles_df)

    if measurements_df.empty:
        st.info("Pro zvolený filtr nejsou k dispozici žadná měření.")
        return

    detail_df = build_detail_table(measurements_df, detail_level)
    boundary_table = build_boundary_table(measurements_df)
    change_table = build_change_table(measurements_df)

    st.title(f"Spotřeba vody - {selected_ident}")
    actual_range = f"{format_value(measurements_df['date'].min())} - {format_value(measurements_df['date'].max())}"
    st.caption(f"Realně načtený rozsah dat: {actual_range}")

    render_summary_metrics(measurements_df, change_table)

    with st.container(border=True):
        st.subheader("Počáteční a konečný stav")
        boundary_display_df = format_consumption_dataframe(boundary_table, columns=("Objem",)).set_index("Datum")
        st.table(boundary_display_df)
        export_source = measurements_df if detail_level == "Ne" or detail_df.empty else detail_df
        render_export_button(export_source, selected_ident, start_date, end_date, detail_level)

    if not change_table.empty:
        with st.container(border=True):
            st.subheader("Resety nebo výměny vodoměrů")
            st.table(format_consumption_dataframe(change_table, columns=("Objem",)))

    if graph_enabled:
        with st.container(border=True):
            render_graphs(measurements_df, detail_df, detail_level, start_date, end_date, profiles_df)
            show_prediction_legend = has_prediction_data(detail_df) or (
                detail_level == "Hodinově"
                and start_date == end_date == prague_today()
                and not profiles_df.empty
            )
            render_graph_legend(show_prediction_legend)

    if detail_level != "Ne":
        with st.container(border=True):
            st.subheader(f"Agregovaná data - {detail_level.lower()}")
            render_data_table(measurements_df, detail_df, detail_level)


try:
    render_dashboard()
except (SQLAlchemyError, DashboardApiError) as exc:
    st.error("Nepodařilo se načíst data pro vodoměry.")
    st.exception(exc)
