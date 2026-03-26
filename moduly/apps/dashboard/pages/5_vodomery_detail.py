from __future__ import annotations

import datetime
from pathlib import Path
import sys

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError


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
    load_device_detail,
    load_event_history,
    load_ident_options,
    load_measurement_series,
    load_prediction_profiles,
    load_recent_anomalies,
    prepare_event_display_dataframe,
    round_consumption_columns,
)


st.set_page_config(
    page_title="Vodomery - Detail",
    page_icon="🧭",
    layout="wide",
)


require_page_access("vodomery_detail")


DETAIL_DEVICE_KEY = "vodomery_detail_identifikace"
DAY_OF_WEEK_LABELS = ("Po", "Út", "St", "Čt", "Pá", "So", "Ne")


def render_detail_sidebar(user_is_admin: bool, allowed_devices: tuple[str, ...]) -> str:
    ident_options = load_ident_options("VSE", allowed_devices, user_is_admin)
    if not ident_options:
        st.warning("Pro aktualni kombinaci opravneni nejsou k dispozici zadne vodomery.")
        st.stop()

    current_ident = st.session_state.get(DETAIL_DEVICE_KEY)
    if current_ident not in ident_options:
        st.session_state[DETAIL_DEVICE_KEY] = ident_options[0]

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        return st.selectbox("Vodoměr", ident_options, key=DETAIL_DEVICE_KEY)


def prepare_consumption_history(df: pd.DataFrame) -> pd.DataFrame:
    history_df = df.copy()
    history_df["date"] = pd.to_datetime(history_df["date"], errors="coerce")
    history_df = history_df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    history_df["spotreba"] = pd.to_numeric(history_df["delta"], errors="coerce")
    if history_df["spotreba"].isna().all():
        history_df["spotreba"] = pd.to_numeric(history_df["objem"], errors="coerce").diff()
    history_df["spotreba"] = history_df["spotreba"].fillna(0.0)
    history_df.loc[history_df["spotreba"] < 0, "spotreba"] = 0.0
    history_df["nocni_odber"] = history_df["nocni_odber"].fillna(False)
    return history_df


def build_expected_daily_map(profiles_df: pd.DataFrame) -> dict[int, float]:
    if profiles_df.empty:
        return {}
    expected_daily_profiles = profiles_df.copy()
    expected_daily_profiles["expected_mean"] = pd.to_numeric(
        expected_daily_profiles["expected_mean"],
        errors="coerce",
    )
    expected_daily_profiles["day_of_week"] = pd.to_numeric(
        expected_daily_profiles["day_of_week"],
        errors="coerce",
    )
    expected_daily_profiles = expected_daily_profiles.dropna(subset=["expected_mean", "day_of_week"])
    if expected_daily_profiles.empty:
        return {}
    return expected_daily_profiles.groupby("day_of_week")["expected_mean"].sum().to_dict()


def build_daily_history(history_df: pd.DataFrame, days: int) -> pd.DataFrame:
    working_df = history_df.copy()
    working_df["nocni_spotreba"] = working_df["spotreba"].where(working_df["nocni_odber"], 0.0)
    daily_history = (
        working_df.set_index("date")
        .resample("D")
        .agg(
            spotreba=("spotreba", "sum"),
            nocni_spotreba=("nocni_spotreba", "sum"),
        )
        .reset_index()
    )
    daily_history = daily_history[daily_history["spotreba"].notna()].copy()
    if daily_history.empty:
        return daily_history
    last_date = daily_history["date"].max()
    start_window = last_date - pd.Timedelta(days=days - 1)
    daily_history = daily_history[daily_history["date"] >= start_window].copy()
    daily_history["nocni_spotreba"] = daily_history["nocni_spotreba"].fillna(0.0)
    daily_history["nocni_odber_m3"] = daily_history["nocni_spotreba"].round(3)
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
        st.subheader("Průměrná spotřeba")
        if history_df.empty:
            st.info("Pro tento vodomer zatim neni dostatek dat pro vypocet prumerne spotreby.")
            return

        averages = build_average_consumption_summary(history_df)
        top_cols = st.columns(2)
        top_cols[0].metric(
            "Průměrná měsíční spotřeba",
            format_consumption_with_unit(averages["monthly"]),
        )
        top_cols[1].metric(
            "Průměrná týdenní spotřeba",
            format_consumption_with_unit(averages["weekly"]),
        )

        st.caption("Průměrná denní spotřeba podle dne v týdnu")
        weekday_cols = st.columns(7)
        weekday_values = averages["weekday"]
        for index, label in enumerate(DAY_OF_WEEK_LABELS):
            weekday_cols[index].metric(
                label,
                format_consumption_with_unit(weekday_values.get(index)),
            )


def render_daily_legend(show_expected: bool, show_nightly: bool) -> None:
    legend_html = '<div style="text-align:right; font-size:12px; color:#6b7280; line-height:1.4; padding-top:0.35rem;">'
    if show_expected:
        legend_html += (
            '<span style="display:inline-flex; align-items:center; gap:0.35rem; margin-left:0.9rem;">'
            '<span style="display:inline-block; width:16px; border-top:2px dashed #f97316;"></span>'
            "Očekávaný denní odběr"
            "</span>"
        )
    if show_nightly:
        legend_html += (
            '<span style="display:inline-flex; align-items:center; gap:0.35rem; margin-left:0.9rem; color:#dc2626; font-weight:700;">'
            '<span style="display:inline-block; width:10px; height:10px; background:#dc2626; border-radius:2px;"></span>'
            "Noční odběr"
            "</span>"
        )
    legend_html += "</div>"
    st.markdown(legend_html, unsafe_allow_html=True)


def build_daily_chart(
    daily_history: pd.DataFrame,
    expected_daily_map: dict[int, float],
    include_expected: bool,
) -> alt.Chart:
    day_order = daily_history["day_label"].tolist()
    chart_df = daily_history.copy()
    chart_df["day_index"] = range(len(chart_df))
    chart_df["spotreba_label"] = chart_df["spotreba"].map(lambda value: f"{value:.3f}")
    bar_size = 42 if len(chart_df) <= 8 else 22
    bars = (
        alt.Chart(chart_df)
        .mark_bar(color="#1f77b4", cornerRadiusTopLeft=3, cornerRadiusTopRight=3, size=bar_size)
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
                alt.Tooltip("nocni_odber_m3:Q", title="Noční odběr [m³]", format=".3f"),
            ],
        )
    )
    bar_labels = (
        alt.Chart(chart_df)
        .mark_text(color="#1f77b4", fontWeight="bold", fontSize=12, dy=-8)
        .encode(
            x=alt.X("day_index:Q"),
            y=alt.Y("spotreba:Q"),
            text=alt.Text("spotreba_label:N"),
        )
    )

    chart: alt.Chart = bars + bar_labels
    if include_expected and expected_daily_map:
        average_line_df = chart_df[["date", "day_index"]].copy()
        average_line_df["expected_day_of_week"] = average_line_df["date"].dt.dayofweek
        average_line_df["prumerny_denni_odber"] = average_line_df["expected_day_of_week"].map(expected_daily_map)
        average_line_df = average_line_df.dropna(subset=["prumerny_denni_odber"])
        if not average_line_df.empty:
            average_line_df["x_start"] = average_line_df["day_index"] - 0.32
            average_line_df["x_end"] = average_line_df["day_index"] + 0.32
            average_line = (
                alt.Chart(average_line_df)
                .mark_rule(color="#f97316", strokeWidth=2, strokeDash=[6, 4])
                .encode(
                    x=alt.X("x_start:Q"),
                    x2=alt.X2("x_end:Q"),
                    y=alt.Y("prumerny_denni_odber:Q"),
                    tooltip=[
                        alt.Tooltip("yearmonthdate(date):T", title="Den"),
                        alt.Tooltip("prumerny_denni_odber:Q", title="Očekávaný denní odběr", format=".3f"),
                    ],
                )
            )
            chart = chart + average_line

    nightly_labels_df = chart_df[chart_df["nocni_odber_m3"] > 0].copy()
    nightly_labels_df["nocni_label"] = nightly_labels_df["nocni_odber_m3"].map(lambda value: f"{value:.3f}")
    if not nightly_labels_df.empty:
        nightly_labels = (
                alt.Chart(nightly_labels_df)
                .mark_text(color="#dc2626", fontWeight="bold", fontSize=12, dy=-24)
                .encode(
                    x=alt.X("day_index:Q"),
                    y=alt.Y("spotreba:Q"),
                    text=alt.Text("nocni_label:N"),
                    tooltip=[
                    alt.Tooltip("yearmonthdate(date):T", title="Den"),
                    alt.Tooltip("nocni_odber_m3:Q", title="Noční odběr [m³]", format=".3f"),
                ],
            )
        )
        chart = chart + nightly_labels

    return chart.properties(height=320)


def render_dashboard() -> None:
    user_is_admin, allowed_devices = get_vodomery_access_context()
    selected_ident = render_detail_sidebar(user_is_admin, allowed_devices)

    if not selected_ident:
        st.info("Vyber v sidebaru konkretni vodomer. Detailni stranka se zobrazi az po jeho vyberu.")
        st.stop()

    measurements_df = load_measurement_series(
        "VSE",
        selected_ident,
        datetime.date(2000, 1, 1),
        datetime.datetime.now().date(),
        allowed_devices,
        user_is_admin,
    )
    anomalies_df = load_recent_anomalies(
        "VSE",
        selected_ident,
        datetime.date(2000, 1, 1),
        datetime.datetime.now().date(),
        allowed_devices,
        user_is_admin,
        limit=50,
    )
    profiles_df = load_prediction_profiles(selected_ident, allowed_devices, user_is_admin)
    device_detail = load_device_detail(selected_ident, allowed_devices, user_is_admin)
    event_history_df = load_event_history(selected_ident, allowed_devices, user_is_admin)
    history_df = prepare_consumption_history(measurements_df) if not measurements_df.empty else pd.DataFrame()
    expected_daily_map = build_expected_daily_map(profiles_df)

    top_cols = st.columns([2, 1, 1, 1])
    first_measurement_date = "-"
    latest_state = "-"
    if not measurements_df.empty:
        first_measurement = pd.to_datetime(measurements_df["date"], errors="coerce").dropna().min()
        latest_measurement = history_df.iloc[-1] if not history_df.empty else None
        if pd.notna(first_measurement):
            first_measurement_date = first_measurement.strftime("%d.%m.%Y")
        if latest_measurement is not None:
            latest_state = format_consumption_with_unit(latest_measurement["objem"])
    top_cols[0].metric("Vodoměr", selected_ident)
    top_cols[1].metric("Aktuální stav:", latest_state)
    top_cols[2].metric("Měřeno od:", first_measurement_date)
    top_cols[3].metric("Anomalie v obdobi", len(anomalies_df))

    with st.container(border=True):
        st.subheader("Detail odberného místa")
        if device_detail is None:
            st.info("Metadata zařízení nebyla nalezena v mapové tabulce.")
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
                            Průměrný měsíční odběr
                        </span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            if measurements_df.empty:
                st.info("Pro vybrany vodomer nejsou v danem obdobi zadna mereni.")
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
                average_line_df = pd.DataFrame(
                    {"prumerna_mesicni_spotreba": [average_monthly_consumption]}
                )
                monthly_history = round_consumption_columns(
                    monthly_history,
                    columns=("spotreba",),
                )
                average_line_df = round_consumption_columns(
                    average_line_df,
                    columns=("prumerna_mesicni_spotreba",),
                )
                monthly_labels_df = monthly_history.copy()
                monthly_labels_df["spotreba_label"] = monthly_labels_df["spotreba"].map(lambda value: f"{value:.3f}")

                bars = (
                    alt.Chart(monthly_history)
                    .mark_bar(color="#1f77b4", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                    .encode(
                        x=alt.X(
                            "month_label:N",
                            title=None,
                            sort=month_order,
                            axis=alt.Axis(labelAngle=-90),
                        ),
                        y=alt.Y("spotreba:Q", title="Spotřeba [m³]"),
                        tooltip=[
                            alt.Tooltip("yearmonth(date):T", title="Měsíc"),
                            alt.Tooltip("spotreba:Q", title="Spotřeba", format=".3f"),
                        ],
                    )
                )
                bar_labels = (
                    alt.Chart(monthly_labels_df)
                    .mark_text(color="#1f77b4", fontWeight="bold", fontSize=12, dy=-8)
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
                chart = (bars + bar_labels + average_line).properties(height=320)
                st.altair_chart(chart, width="stretch")

    with status_col:
        with st.container(border=True):
            title_col, legend_col = st.columns([3, 2])
            with title_col:
                st.subheader("Posledních 7 dní")
            if measurements_df.empty:
                st.info("Pro vodomer zatim neni zadne mereni.")
            else:
                daily_history = build_daily_history(history_df, 7)
                if daily_history.empty:
                    st.info("Pro vodomer zatim neni dostatek dat pro denni graf.")
                else:
                    has_nightly_consumption = bool((daily_history["nocni_odber_m3"] > 0).any())
                    with legend_col:
                        render_daily_legend(True, has_nightly_consumption)
                    st.altair_chart(
                        build_daily_chart(daily_history, expected_daily_map, include_expected=True),
                        width="stretch",
                    )

    with st.container(border=True):
        title_col, legend_col = st.columns([3, 2])
        with title_col:
            st.subheader("Poslední měsíc")
        if measurements_df.empty:
            st.info("Pro vodomer zatim neni zadne mereni.")
        else:
            month_history = build_daily_history(history_df, 31)
            if month_history.empty:
                st.info("Pro vodomer zatim neni dostatek dat pro mesicni denni graf.")
            else:
                has_nightly_consumption = bool((month_history["nocni_odber_m3"] > 0).any())
                with legend_col:
                    render_daily_legend(False, has_nightly_consumption)
                st.altair_chart(
                    build_daily_chart(month_history, expected_daily_map, include_expected=False),
                    width="stretch",
                )

    detail_left, detail_right = st.columns(2)

    with detail_left:
        with st.container(border=True):
            st.subheader("Historie eventu")
            if event_history_df.empty:
                st.info("Pro tento vodomer neni evidovana historie eventu.")
            else:
                st.dataframe(prepare_event_display_dataframe(event_history_df), width="stretch", hide_index=True)

    with detail_right:
        with st.container(border=True):
            st.subheader("Posledni anomalie vodomeru")
            if anomalies_df.empty:
                st.info("Pro tento vodomer nejsou evidovany anomalie.")
            else:
                st.dataframe(
                    format_consumption_dataframe(
                        anomalies_df,
                        columns=("actual_value", "expected_mean"),
                    ),
                    width="stretch",
                    hide_index=True,
                )


try:
    render_dashboard()
except (SQLAlchemyError, DashboardApiError) as exc:
    st.error("Nepodarilo se nacist data pro vodomery.")
    st.exception(exc)
