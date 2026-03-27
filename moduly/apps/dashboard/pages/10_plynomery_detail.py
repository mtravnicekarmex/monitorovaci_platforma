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
from moduly.apps.dashboard.plynomery_shared import (
    format_consumption_dataframe,
    format_consumption_with_unit,
    format_value,
    get_plynomery_access_context,
    load_device_detail,
    load_ident_options,
    load_measurement_series,
    round_consumption_columns,
)


GAS_CONSUMPTION_COLOR = "#eab308"
GAS_CONSUMPTION_TEXT_COLOR = "#a16207"


st.set_page_config(
    page_title="Plynomery - Detail",
    page_icon="🧭",
    layout="wide",
)


require_page_access("plynomery_detail")


DETAIL_DEVICE_KEY = "plynomery_detail_identifikace"


def render_detail_sidebar(user_is_admin: bool, allowed_devices: tuple[str, ...]) -> str:
    ident_options = load_ident_options(allowed_devices, user_is_admin)
    if not ident_options:
        st.warning("Pro aktualni kombinaci opravneni nejsou k dispozici zadne plynomery.")
        st.stop()

    current_ident = st.session_state.get(DETAIL_DEVICE_KEY)
    if current_ident not in ident_options:
        st.session_state[DETAIL_DEVICE_KEY] = ident_options[0]

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        return st.selectbox("Plynoměr", ident_options, key=DETAIL_DEVICE_KEY)


def prepare_consumption_history(df: pd.DataFrame) -> pd.DataFrame:
    history_df = df.copy()
    history_df["date"] = pd.to_datetime(history_df["date"], errors="coerce")
    history_df["objem"] = pd.to_numeric(history_df["objem"], errors="coerce")
    history_df["seriove_cislo"] = history_df["seriove_cislo"].astype(str)
    history_df["platne"] = history_df["platne"].fillna(True).astype(bool)
    history_df = history_df.dropna(subset=["date", "objem"]).sort_values("date").reset_index(drop=True)
    if history_df.empty:
        return history_df

    diff_from_volume = history_df["objem"].diff().fillna(0.0)
    serial_changed = history_df["seriove_cislo"].ne(history_df["seriove_cislo"].shift()).fillna(False)
    history_df["reset_detected"] = diff_from_volume.lt(0) | serial_changed
    history_df["spotreba"] = diff_from_volume
    history_df.loc[history_df["spotreba"] < 0, "spotreba"] = 0.0
    history_df.loc[history_df["reset_detected"], "spotreba"] = 0.0
    history_df.loc[~history_df["platne"], "spotreba"] = 0.0
    history_df["spotreba"] = history_df["spotreba"].round(3)
    return history_df


def build_daily_history(history_df: pd.DataFrame, days: int) -> pd.DataFrame:
    daily_history = (
        history_df.set_index("date")
        .resample("D")
        .agg(spotreba=("spotreba", "sum"))
        .reset_index()
    )
    daily_history = daily_history[daily_history["spotreba"].notna()].copy()
    if daily_history.empty:
        return daily_history
    last_date = daily_history["date"].max()
    start_window = last_date - pd.Timedelta(days=days - 1)
    daily_history = daily_history[daily_history["date"] >= start_window].copy()
    daily_history["day_label"] = daily_history["date"].dt.strftime("%d.%m.")
    return daily_history


def build_daily_chart(daily_history: pd.DataFrame) -> alt.Chart:
    day_order = daily_history["day_label"].tolist()
    chart_df = daily_history.copy()
    chart_df["day_index"] = range(len(chart_df))
    chart_df["spotreba_label"] = chart_df["spotreba"].map(lambda value: f"{value:.3f}")
    bar_size = 42 if len(chart_df) <= 8 else 22
    bars = (
        alt.Chart(chart_df)
        .mark_bar(color=GAS_CONSUMPTION_COLOR, cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=bar_size)
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
            y=alt.Y("spotreba:Q", title="Spotřeba [m³]"),
            tooltip=[
                alt.Tooltip("yearmonthdate(date):T", title="Den"),
                alt.Tooltip("spotreba:Q", title="Spotřeba", format=".3f"),
            ],
        )
    )
    labels = (
        alt.Chart(chart_df)
        .mark_text(color=GAS_CONSUMPTION_TEXT_COLOR, fontWeight="bold", fontSize=12, dy=-8)
        .encode(
            x=alt.X("day_index:Q"),
            y=alt.Y("spotreba:Q"),
            text=alt.Text("spotreba_label:N"),
        )
    )
    return (bars + labels).properties(height=320)


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


def render_dashboard() -> None:
    user_is_admin, allowed_devices = get_plynomery_access_context()
    selected_ident = render_detail_sidebar(user_is_admin, allowed_devices)

    if not selected_ident:
        st.info("Vyber v sidebaru konkretni plynomer. Detailni stranka se zobrazi az po jeho vyberu.")
        st.stop()

    measurements_df = load_measurement_series(
        selected_ident,
        datetime.date(2000, 1, 1),
        prague_today(),
        allowed_devices,
        user_is_admin,
    )
    device_detail = load_device_detail(selected_ident, allowed_devices, user_is_admin)
    history_df = prepare_consumption_history(measurements_df) if not measurements_df.empty else pd.DataFrame()
    change_table = build_change_table(history_df) if not history_df.empty else pd.DataFrame()

    top_cols = st.columns([2, 1, 1, 1])
    first_measurement_date = "-"
    latest_volume = "-"
    invalid_measurements = 0
    if not history_df.empty:
        first_measurement = pd.to_datetime(history_df["date"], errors="coerce").dropna().min()
        latest_row = history_df.iloc[-1]
        if pd.notna(first_measurement):
            first_measurement_date = first_measurement.strftime("%d.%m.%Y")
        latest_volume = format_consumption_with_unit(latest_row["objem"])
        invalid_measurements = int((~history_df["platne"]).sum())
    top_cols[0].metric("Plynoměr", selected_ident)
    top_cols[1].metric("Měřeno od:", first_measurement_date)
    top_cols[2].metric("Poslední odečet", latest_volume)
    top_cols[3].metric("Neplatná měření", invalid_measurements)

    with st.container(border=True):
        st.subheader("Detail odběrného místa")
        if device_detail is None:
            st.info("Metadata zařízení nebyla nalezena.")
        else:
            metadata_pairs = [
                ("Identifikace", format_value(device_detail["identifikace"])),
                ("Sériové číslo", format_value(device_detail["seriove_cislo"])),
                ("MBUS", format_value(device_detail["mbus"])),
                ("Objekt", format_value(device_detail["objekt"])),
                ("Patro", format_value(device_detail["patro"])),
                ("Místnost", format_value(device_detail["mistnost"])),
                ("Umístění", format_value(device_detail["umisteni"])),
                ("Napájí", format_value(device_detail["napaji"])),
                ("Koncový odběratel", format_value(device_detail["koncovy_odberatel"])),
                ("Platnost cejchu", format_value(device_detail["platnost_cejchu"])),
                ("Poznámka", format_value(device_detail["poznamka"])),
            ]
            metadata_df = pd.DataFrame(metadata_pairs, columns=["Pole", "Hodnota"])
            meta_col_1, meta_col_2 = st.columns(2)
            midpoint = (len(metadata_df) + 1) // 2
            meta_col_1.dataframe(metadata_df.iloc[:midpoint], width="stretch", hide_index=True)
            meta_col_2.dataframe(metadata_df.iloc[midpoint:], width="stretch", hide_index=True)

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
                            Průměrný měsíční odběr
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            if history_df.empty:
                st.info("Pro vybrany plynomer nejsou v danem obdobi zadna mereni.")
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
                    .mark_bar(color=GAS_CONSUMPTION_COLOR, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                    .encode(
                        x=alt.X("month_label:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=-90)),
                        y=alt.Y("spotreba:Q", title="Spotřeba [m³]"),
                        tooltip=[
                            alt.Tooltip("yearmonth(date):T", title="Měsíc"),
                            alt.Tooltip("spotreba:Q", title="Spotřeba", format=".3f"),
                        ],
                    )
                )
                labels = (
                    alt.Chart(monthly_labels_df)
                    .mark_text(color=GAS_CONSUMPTION_TEXT_COLOR, fontWeight="bold", fontSize=12, dy=-8)
                    .encode(
                        x=alt.X("month_label:N", sort=month_order),
                        y=alt.Y("spotreba:Q"),
                        text=alt.Text("spotreba_label:N"),
                    )
                )
                average_line = (
                    alt.Chart(average_line_df)
                    .mark_rule(color="#f97316", strokeWidth=2, strokeDash=[6, 4])
                    .encode(
                        y=alt.Y("prumerna_mesicni_spotreba:Q"),
                        tooltip=[alt.Tooltip("prumerna_mesicni_spotreba:Q", title="Průměrný měsíční odběr", format=".3f")],
                    )
                )
                st.altair_chart((bars + labels + average_line).properties(height=320), width="stretch")

    with status_col:
        with st.container(border=True):
            st.subheader("Posledních 7 dní")
            if history_df.empty:
                st.info("Pro plynomer zatim neni zadne mereni.")
            else:
                daily_history = build_daily_history(history_df, 7)
                if daily_history.empty:
                    st.info("Pro plynomer zatim neni dostatek dat pro denni graf.")
                else:
                    st.altair_chart(build_daily_chart(daily_history), width="stretch")

    with st.container(border=True):
        st.subheader("Poslední měsíc")
        if history_df.empty:
            st.info("Pro plynomer zatim neni zadne mereni.")
        else:
            month_history = build_daily_history(history_df, 31)
            if month_history.empty:
                st.info("Pro plynomer zatim neni dostatek dat pro mesicni denni graf.")
            else:
                st.altair_chart(build_daily_chart(month_history), width="stretch")

    detail_left, detail_right = st.columns(2)

    with detail_left:
        with st.container(border=True):
            st.subheader("Poslední měření")
            if history_df.empty:
                st.info("Pro tento plynomer nejsou zadna mereni.")
            else:
                recent_measurements = history_df.sort_values("date", ascending=False).head(50).copy()
                recent_measurements = recent_measurements.rename(
                    columns={
                        "date": "Datum",
                        "seriove_cislo": "Sériové číslo",
                        "objem": "Objem",
                        "platne": "Platné",
                        "spotreba": "Spotřeba",
                    }
                )
                recent_measurements = format_consumption_dataframe(
                    recent_measurements,
                    columns=("Objem", "Spotřeba"),
                )
                st.dataframe(
                    recent_measurements[["Datum", "Sériové číslo", "Objem", "Platné", "Spotřeba"]],
                    width="stretch",
                    hide_index=True,
                )

    with detail_right:
        with st.container(border=True):
            st.subheader("Resety nebo výměny")
            if change_table.empty:
                st.info("Pro tento plynomer nebyly detekovany resety ani vymeny.")
            else:
                st.dataframe(
                    format_consumption_dataframe(change_table, columns=("Objem",)),
                    width="stretch",
                    hide_index=True,
                )


try:
    render_dashboard()
except SQLAlchemyError as exc:
    st.error("Nepodarilo se nacist data z databaze.")
    st.exception(exc)
