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
from moduly.apps.dashboard.kalorimetry_shared import (
    format_consumption_dataframe,
    format_energy_metric,
    format_value,
    get_kalorimetry_access_context,
    load_device_detail,
    load_ident_options,
    load_measurement_series,
    render_device_photo,
    round_consumption_columns,
)


ENERGY_CONSUMPTION_COLOR = "#dc2626"
ENERGY_CONSUMPTION_TEXT_COLOR = "#991b1b"


st.set_page_config(
    page_title="Kalorimetry - Detail",
    page_icon="🧭",
    layout="wide",
)


require_page_access("kalorimetry_detail")


DETAIL_DEVICE_KEY = "kalorimetry_detail_identifikace"
DAY_OF_WEEK_LABELS = ("Po", "Út", "St", "Čt", "Pá", "So", "Ne")


def render_detail_sidebar(user_is_admin: bool, allowed_devices: tuple[str, ...]) -> str:
    ident_options = load_ident_options(allowed_devices, user_is_admin)
    if not ident_options:
        st.warning("Pro aktualni kombinaci opravneni nejsou k dispozici zadne kalorimetry.")
        st.stop()

    current_ident = st.session_state.get(DETAIL_DEVICE_KEY)
    if current_ident not in ident_options:
        st.session_state[DETAIL_DEVICE_KEY] = ident_options[0]

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        return st.selectbox("Kalorimetr", ident_options, key=DETAIL_DEVICE_KEY)


def prepare_consumption_history(df: pd.DataFrame) -> pd.DataFrame:
    history_df = df.copy()
    history_df["date"] = pd.to_datetime(history_df["date"], errors="coerce")
    history_df["spotreba_energie"] = pd.to_numeric(history_df["spotreba_energie"], errors="coerce")
    history_df["seriove_cislo"] = history_df["seriove_cislo"].astype(str)
    history_df["platne"] = history_df["platne"].fillna(True).astype(bool)
    history_df = history_df.dropna(subset=["date", "spotreba_energie"]).sort_values("date").reset_index(drop=True)
    if history_df.empty:
        return history_df

    diff_from_state = history_df["spotreba_energie"].diff().fillna(0.0)
    serial_changed = history_df["seriove_cislo"].ne(history_df["seriove_cislo"].shift()).fillna(False)
    history_df["reset_detected"] = diff_from_state.lt(0) | serial_changed
    history_df["spotreba"] = diff_from_state
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


def build_average_consumption_summary(history_df: pd.DataFrame) -> dict[str, object]:
    if history_df.empty:
        return {"monthly": None, "weekly": None, "weekday": {}}

    daily_totals = (
        history_df.set_index("date")
        .resample("D")
        .agg(spotreba=("spotreba", "sum"))
        .reset_index()
    )
    daily_totals = daily_totals[daily_totals["spotreba"].notna()].copy()
    if daily_totals.empty:
        return {"monthly": None, "weekly": None, "weekday": {}}

    daily_totals["spotreba"] = pd.to_numeric(daily_totals["spotreba"], errors="coerce").fillna(0.0)
    monthly_totals = (
        daily_totals.assign(month_period=daily_totals["date"].dt.to_period("M"))
        .groupby("month_period")["spotreba"]
        .sum()
    )
    iso_calendar = daily_totals["date"].dt.isocalendar()
    weekly_totals = (
        daily_totals.assign(iso_year=iso_calendar.year, iso_week=iso_calendar.week)
        .groupby(["iso_year", "iso_week"])["spotreba"]
        .sum()
    )
    weekday_totals = (
        daily_totals.assign(day_of_week=daily_totals["date"].dt.dayofweek)
        .groupby("day_of_week")["spotreba"]
        .mean()
    )

    return {
        "monthly": round(float(monthly_totals.mean()), 3) if not monthly_totals.empty else None,
        "weekly": round(float(weekly_totals.mean()), 3) if not weekly_totals.empty else None,
        "weekday": {
            int(day_of_week): round(float(value), 3)
            for day_of_week, value in weekday_totals.items()
        },
    }


def render_average_consumption_section(history_df: pd.DataFrame) -> None:
    with st.container(border=True):
        st.subheader("Průměrná spotřeba energie")
        if history_df.empty:
            st.info("Pro tento kalorimetr zatím není dostatek dat pro výpočet průměrné spotřeby.")
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
        .mark_bar(color=ENERGY_CONSUMPTION_COLOR, cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=bar_size)
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
            y=alt.Y("spotreba:Q", title="Spotřeba energie"),
            tooltip=[
                alt.Tooltip("yearmonthdate(date):T", title="Den"),
                alt.Tooltip("spotreba:Q", title="Spotřeba energie", format=".3f"),
            ],
        )
    )
    labels = (
        alt.Chart(chart_df)
        .mark_text(color=ENERGY_CONSUMPTION_TEXT_COLOR, fontWeight="bold", fontSize=12, dy=-8)
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
        state_reset = row["spotreba_energie"] < previous_row["spotreba_energie"]
        if serial_changed or state_reset:
            rows.append(
                {
                    "Datum": previous_row["date"],
                    "Stav energie": previous_row["spotreba_energie"],
                    "Sériové číslo": previous_row["seriove_cislo"],
                    "Poznámka": "Konečný stav původního kalorimetru",
                }
            )
            rows.append(
                {
                    "Datum": row["date"],
                    "Stav energie": row["spotreba_energie"],
                    "Sériové číslo": row["seriove_cislo"],
                    "Poznámka": "Počáteční stav nového nebo resetovaného kalorimetru",
                }
            )
        previous_row = row
    return pd.DataFrame(rows)


def render_dashboard() -> None:
    user_is_admin, allowed_devices = get_kalorimetry_access_context()
    selected_ident = render_detail_sidebar(user_is_admin, allowed_devices)

    if not selected_ident:
        st.info("Vyber v sidebaru konkretni kalorimetr. Detailni stranka se zobrazi az po jeho vyberu.")
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

    top_cols = st.columns(5, vertical_alignment="bottom")
    first_measurement_date = "-"
    latest_state = "-"
    invalid_measurements = 0
    if not history_df.empty:
        first_measurement = pd.to_datetime(history_df["date"], errors="coerce").dropna().min()
        latest_row = history_df.iloc[-1]
        if pd.notna(first_measurement):
            first_measurement_date = first_measurement.strftime("%d.%m.%Y")
        latest_state = format_energy_metric(latest_row["spotreba_energie"])
        invalid_measurements = int((~history_df["platne"]).sum())
    top_cols[0].metric("Kalorimetr", selected_ident)
    with top_cols[1]:
        render_device_photo(device_detail)
    top_cols[2].metric("Měřeno od:", first_measurement_date)
    top_cols[3].metric("Poslední stav", latest_state)
    top_cols[4].metric("Neplatná měření", invalid_measurements)

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
                ("Zdroj", format_value(device_detail["zdroj"])),
                ("Zdroj měření", format_value(device_detail["zdroj_mereni"])),
                ("Koncový odběratel", format_value(device_detail["koncovy_odberatel"])),
                ("Platnost cejchu", format_value(device_detail["platnost_cejchu"])),
                ("Poznámka", format_value(device_detail["poznamka"])),
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
                st.subheader("Historie spotřeby energie")
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
                st.info("Pro vybrany kalorimetr nejsou v danem obdobi zadna mereni.")
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
                    .mark_bar(color=ENERGY_CONSUMPTION_COLOR, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                    .encode(
                        x=alt.X("month_label:N", title=None, sort=month_order, axis=alt.Axis(labelAngle=-90)),
                        y=alt.Y("spotreba:Q", title="Spotřeba energie"),
                        tooltip=[
                            alt.Tooltip("yearmonth(date):T", title="Měsíc"),
                            alt.Tooltip("spotreba:Q", title="Spotřeba energie", format=".3f"),
                        ],
                    )
                )
                labels = (
                    alt.Chart(monthly_labels_df)
                    .mark_text(color=ENERGY_CONSUMPTION_TEXT_COLOR, fontWeight="bold", fontSize=12, dy=-8)
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
                        tooltip=[alt.Tooltip("prumerna_mesicni_spotreba:Q", title="Průměrná měsíční spotřeba", format=".3f")],
                    )
                )
                st.altair_chart((bars + labels + average_line).properties(height=320), width="stretch")

    with status_col:
        with st.container(border=True):
            st.subheader("Posledních 7 dní")
            if history_df.empty:
                st.info("Pro kalorimetr zatim neni zadne mereni.")
            else:
                daily_history = build_daily_history(history_df, 7)
                if daily_history.empty:
                    st.info("Pro kalorimetr zatim neni dostatek dat pro denni graf.")
                else:
                    st.altair_chart(build_daily_chart(daily_history), width="stretch")

    with st.container(border=True):
        st.subheader("Poslední měsíc")
        if history_df.empty:
            st.info("Pro kalorimetr zatim neni zadne mereni.")
        else:
            month_history = build_daily_history(history_df, 31)
            if month_history.empty:
                st.info("Pro kalorimetr zatim neni dostatek dat pro mesicni denni graf.")
            else:
                st.altair_chart(build_daily_chart(month_history), width="stretch")

    detail_left, detail_right = st.columns(2)

    with detail_left:
        with st.container(border=True):
            st.subheader("Poslední měření")
            if history_df.empty:
                st.info("Pro tento kalorimetr nejsou zadna mereni.")
            else:
                recent_measurements = history_df.sort_values("date", ascending=False).head(50).copy()
                recent_measurements = recent_measurements.rename(
                    columns={
                        "date": "Datum",
                        "seriove_cislo": "Sériové číslo",
                        "spotreba_energie": "Stav energie",
                        "platne": "Platné",
                        "spotreba": "Spotřeba energie",
                    }
                )
                recent_measurements = format_consumption_dataframe(
                    recent_measurements,
                    columns=("Stav energie", "Spotřeba energie"),
                )
                st.dataframe(
                    recent_measurements[["Datum", "Sériové číslo", "Stav energie", "Platné", "Spotřeba energie"]],
                    width="stretch",
                    hide_index=True,
                )

    with detail_right:
        with st.container(border=True):
            st.subheader("Resety nebo výměny")
            if change_table.empty:
                st.info("Pro tento kalorimetr nebyly detekovany resety ani vymeny.")
            else:
                st.dataframe(
                    format_consumption_dataframe(change_table, columns=("Stav energie",)),
                    width="stretch",
                    hide_index=True,
                )


try:
    render_dashboard()
except SQLAlchemyError as exc:
    st.error("Nepodarilo se nacist data z databaze.")
    st.exception(exc)
