from __future__ import annotations

import datetime
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
    build_average_consumption_summary,
    build_change_table,
    build_daily_history,
    format_consumption_dataframe,
    format_energy_metric,
    format_value,
    get_elektromery_access_context,
    load_device_detail,
    load_ident_options,
    load_measurement_series,
    prepare_measurements,
    round_consumption_columns,
)


ELECTRICITY_CONSUMPTION_COLOR = "#dc2626"
ELECTRICITY_CONSUMPTION_TEXT_COLOR = "#991b1b"
ELECTRICITY_AVERAGE_LINE_COLOR = "#b91c1c"


st.set_page_config(
    page_title="Elektroměry - Detail",
    page_icon="🧭",
    layout="wide",
)


require_page_access("elektromery_detail")


DETAIL_DEVICE_KEY = "elektromery_detail_identifikace"
DAY_OF_WEEK_LABELS = ("Po", "Út", "St", "Čt", "Pá", "So", "Ne")


def render_detail_sidebar(user_is_admin: bool, allowed_devices: tuple[str, ...]) -> str:
    ident_options = load_ident_options(allowed_devices, user_is_admin)
    if not ident_options:
        st.warning("Pro aktualni kombinaci opravneni nejsou k dispozici zadne elektromery.")
        st.stop()

    current_ident = st.session_state.get(DETAIL_DEVICE_KEY)
    if current_ident not in ident_options:
        st.session_state[DETAIL_DEVICE_KEY] = ident_options[0]

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        return st.selectbox("Elektroměr", ident_options, key=DETAIL_DEVICE_KEY)


def render_average_consumption_section(history_df: pd.DataFrame) -> None:
    with st.container(border=True):
        st.subheader("Průměrná spotřeba")
        if history_df.empty:
            st.info("Pro tento elektroměr zatím není dostatek dat pro výpočet průměrné spotřeby.")
            return

        averages = build_average_consumption_summary(history_df)
        top_cols = st.columns(2)
        top_cols[0].metric(
            "Průměrná měsíční spotřeba",
            format_energy_metric(averages["monthly"]),
        )
        top_cols[1].metric(
            "Průměrná týdenní spotřeba",
            format_energy_metric(averages["weekly"]),
        )

        st.caption("Průměrná denní spotřeba podle dne v týdnu")
        weekday_cols = st.columns(7)
        weekday_values = averages["weekday"]
        for index, label in enumerate(DAY_OF_WEEK_LABELS):
            weekday_cols[index].metric(
                label,
                format_energy_metric(weekday_values.get(index)),
            )


def build_daily_chart(daily_history: pd.DataFrame) -> alt.Chart:
    day_order = daily_history["day_label"].tolist()
    chart_df = daily_history.copy()
    chart_df["day_index"] = range(len(chart_df))
    chart_df["spotreba_label"] = chart_df["spotreba"].map(lambda value: f"{value:.3f}")
    bar_size = 42 if len(chart_df) <= 8 else 22
    bars = (
        alt.Chart(chart_df)
        .mark_bar(color=ELECTRICITY_CONSUMPTION_COLOR, cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=bar_size)
        .encode(
            x=alt.X(
                "day_index:Q",
                title=None,
                scale=alt.Scale(domain=[-0.5, len(day_order) - 0.5]),
                axis=alt.Axis(
                    labelAngle=0,
                    domain=False,
                    ticks=False,
                    tickSize=0,
                    grid=False,
                    values=list(range(len(day_order))),
                    labelExpr=f"[{', '.join(repr(label) for label in day_order)}][datum.value]",
                ),
            ),
            y=alt.Y("spotreba:Q", title="Spotřeba [kWh]"),
            tooltip=[
                alt.Tooltip("yearmonthdate(date):T", title="Den"),
                alt.Tooltip("spotreba:Q", title="Spotřeba", format=".3f"),
            ],
        )
    )
    labels = (
        alt.Chart(chart_df)
        .mark_text(color=ELECTRICITY_CONSUMPTION_TEXT_COLOR, fontWeight="bold", fontSize=12, dy=-8)
        .encode(
            x=alt.X("day_index:Q"),
            y=alt.Y("spotreba:Q"),
            text=alt.Text("spotreba_label:N"),
        )
    )
    return (bars + labels).properties(height=320)


def format_tariff_snapshot(vt: object, nt: object) -> str:
    vt_value = format_energy_metric(vt)
    nt_value = format_energy_metric(nt)
    if vt_value == "-" and nt_value == "-":
        return "-"
    if nt_value == "-":
        return f"VT {vt_value}"
    if vt_value == "-":
        return f"NT {nt_value}"
    return f"{vt_value} / {nt_value}"


def render_dashboard() -> None:
    user_is_admin, allowed_devices = get_elektromery_access_context()
    selected_ident = render_detail_sidebar(user_is_admin, allowed_devices)

    if not selected_ident:
        st.info("Vyber v sidebaru konkretni elektromer. Detailni stranka se zobrazi az po jeho vyberu.")
        st.stop()

    measurements_df = load_measurement_series(
        selected_ident,
        datetime.date(2000, 1, 1),
        prague_today(),
        allowed_devices,
        user_is_admin,
    )
    device_detail = load_device_detail(selected_ident, allowed_devices, user_is_admin)
    history_df = prepare_measurements(measurements_df) if not measurements_df.empty else pd.DataFrame()
    change_table = build_change_table(history_df) if not history_df.empty else pd.DataFrame()

    top_cols = st.columns([2, 1, 1, 1])
    first_measurement_date = "-"
    latest_total_state = "-"
    latest_tariffs = "-"
    if not history_df.empty:
        first_measurement = pd.to_datetime(history_df["date"], errors="coerce").dropna().min()
        latest_row = history_df.iloc[-1]
        if pd.notna(first_measurement):
            first_measurement_date = first_measurement.strftime("%d.%m.%Y")
        latest_total_state = format_energy_metric(latest_row["stav_celkem"])
        latest_tariffs = format_tariff_snapshot(latest_row["vt"], latest_row["nt"])
    top_cols[0].metric("Elektroměr", selected_ident)
    top_cols[1].metric("Měřeno od:", first_measurement_date)
    top_cols[2].metric("Poslední stav", latest_total_state)
    top_cols[3].metric("Poslední VT / NT", latest_tariffs)

    with st.container(border=True):
        st.subheader("Detail odběrného místa")
        if device_detail is None:
            st.info("Metadata zařízení nebyla nalezena.")
        else:
            metadata_pairs = [
                ("Identifikace", format_value(device_detail["identifikace"])),
                ("Sériové číslo", format_value(device_detail["seriove_cislo"])),
                ("Softlink ID", format_value(device_detail["softlink_id"])),
                ("EAN", format_value(device_detail["ean"])),
                ("Pozice", format_value(device_detail["pozice"])),
                ("Podružný", format_value(device_detail["podruzny"])),
                ("Místnost", format_value(device_detail["mistnost"])),
                ("Umístění", format_value(device_detail["umisteni"])),
                ("Napájí", format_value(device_detail["napaji"])),
                ("Koncový odběratel", format_value(device_detail["koncovy_odberatel"])),
                ("Platnost cejchu", format_value(device_detail["platnost_cejchu"])),
                ("Jistič", format_value(device_detail["jistic"])),
                ("Typ měřiče", format_value(device_detail["typ_merice"])),
                ("Rozvaděč", format_value(device_detail["rozvadec"])),
                ("Typ tarifu", format_value(device_detail["typ_tarifu"])),
                ("Platnost od", format_value(device_detail["platnost_od"])),
                ("Platnost do", format_value(device_detail["platnost_do"])),
                ("Plomb", format_value(device_detail["plomb"])),
                ("MIS ID", format_value(device_detail["mis_id"])),
                ("MET ID", format_value(device_detail["met_id"])),
            ]
            metadata_df = pd.DataFrame(metadata_pairs, columns=["Pole", "Hodnota"])
            meta_col_1, meta_col_2 = st.columns(2)
            midpoint = (len(metadata_df) + 1) // 2
            meta_col_1.dataframe(metadata_df.iloc[:midpoint], width="stretch", hide_index=True)
            meta_col_2.dataframe(metadata_df.iloc[midpoint:], width="stretch", hide_index=True)

    render_average_consumption_section(history_df)

    chart_col, status_col = st.columns([3, 2])

    with chart_col:
        with st.container(border=True):
            title_col, legend_col = st.columns([3, 2])
            with title_col:
                st.subheader("Historie spotřeby")
            with legend_col:
                st.markdown(
                    """
                    <div style="text-align:right; font-size:12px; color:#6b7280; line-height:1.4; padding-top:0.35rem;">
                        <span style="display:inline-flex; align-items:center; gap:0.35rem; margin-left:0.9rem;">
                            <span style="display:inline-block; width:16px; border-top:2px dashed #f97316;"></span>
                            Průměrná měsíční spotřeba
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            if history_df.empty:
                st.info("Pro vybrany elektromer nejsou v danem obdobi zadna mereni.")
            else:
                monthly_history = (
                    history_df.set_index("date")
                    .resample("ME")
                    .agg(spotreba=("spotreba", "sum"))
                    .reset_index()
                )
                monthly_history = monthly_history[monthly_history["spotreba"].notna()].copy()
                average_monthly_consumption = float(monthly_history["spotreba"].mean()) if not monthly_history.empty else 0.0
                if not monthly_history.empty:
                    monthly_history = monthly_history.tail(24).copy()
                monthly_history["month_label"] = monthly_history["date"].dt.strftime("%b %Y")
                month_order = monthly_history["month_label"].tolist()
                average_line_df = pd.DataFrame({"prumerna_mesicni_spotreba": [average_monthly_consumption]})
                monthly_history = round_consumption_columns(monthly_history, columns=("spotreba",))
                average_line_df = round_consumption_columns(average_line_df, columns=("prumerna_mesicni_spotreba",))
                monthly_labels_df = monthly_history.copy()
                monthly_labels_df["spotreba_label"] = monthly_labels_df["spotreba"].map(lambda value: f"{value:.3f}")

                bars = (
                    alt.Chart(monthly_history)
                    .mark_bar(color=ELECTRICITY_CONSUMPTION_COLOR, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                    .encode(
                        x=alt.X("month_label:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=-90)),
                        y=alt.Y("spotreba:Q", title="Spotřeba [kWh]"),
                        tooltip=[
                            alt.Tooltip("yearmonth(date):T", title="Měsíc"),
                            alt.Tooltip("spotreba:Q", title="Spotřeba", format=".3f"),
                        ],
                    )
                )
                labels = (
                    alt.Chart(monthly_labels_df)
                    .mark_text(color=ELECTRICITY_CONSUMPTION_TEXT_COLOR, fontWeight="bold", fontSize=12, dy=-8)
                    .encode(
                        x=alt.X("month_label:N", sort=month_order),
                        y=alt.Y("spotreba:Q"),
                        text=alt.Text("spotreba_label:N"),
                    )
                )
                average_line = (
                    alt.Chart(average_line_df)
                    .mark_rule(color=ELECTRICITY_AVERAGE_LINE_COLOR, strokeWidth=2, strokeDash=[6, 4])
                    .encode(
                        y=alt.Y("prumerna_mesicni_spotreba:Q"),
                        tooltip=[alt.Tooltip("prumerna_mesicni_spotreba:Q", title="Průměrná měsíční spotřeba", format=".3f")],
                    )
                )
                st.altair_chart((bars + labels + average_line).properties(height=320), width="stretch")

    with status_col:
        with st.container(border=True):
            st.subheader("Posledních 7 dní")
            if history_df.empty:
                st.info("Pro elektromer zatim neni zadne mereni.")
            else:
                daily_history = build_daily_history(history_df, 7)
                if daily_history.empty:
                    st.info("Pro elektromer zatim neni dostatek dat pro denni graf.")
                else:
                    st.altair_chart(build_daily_chart(daily_history), width="stretch")

    with st.container(border=True):
        st.subheader("Poslední měsíc")
        if history_df.empty:
            st.info("Pro elektromer zatim neni zadne mereni.")
        else:
            month_history = build_daily_history(history_df, 31)
            if month_history.empty:
                st.info("Pro elektromer zatim neni dostatek dat pro mesicni denni graf.")
            else:
                st.altair_chart(build_daily_chart(month_history), width="stretch")

    detail_left, detail_right = st.columns(2)

    with detail_left:
        with st.container(border=True):
            st.subheader("Poslední měření")
            if history_df.empty:
                st.info("Pro tento elektromer nejsou zadna mereni.")
            else:
                recent_measurements = history_df.sort_values("date", ascending=False).head(50).copy()
                recent_measurements = recent_measurements.rename(
                    columns={
                        "date": "Datum",
                        "seriove_cislo": "Sériové číslo",
                        "vt": "Stav VT",
                        "nt": "Stav NT",
                        "stav_celkem": "Stav celkem",
                        "spotreba": "Spotřeba",
                    }
                )
                recent_measurements = format_consumption_dataframe(
                    recent_measurements,
                    columns=("Stav VT", "Stav NT", "Stav celkem", "Spotřeba"),
                )
                st.dataframe(
                    recent_measurements[["Datum", "Sériové číslo", "Stav VT", "Stav NT", "Stav celkem", "Spotřeba"]],
                    width="stretch",
                    hide_index=True,
                )

    with detail_right:
        with st.container(border=True):
            st.subheader("Resety nebo výměny")
            if change_table.empty:
                st.info("Pro tento elektromer nebyly detekovany resety ani vymeny.")
            else:
                st.dataframe(
                    format_consumption_dataframe(change_table, columns=("Stav celkem",)),
                    width="stretch",
                    hide_index=True,
                )


try:
    render_dashboard()
except SQLAlchemyError as exc:
    st.error("Nepodarilo se nacist data z databaze.")
    st.exception(exc)
