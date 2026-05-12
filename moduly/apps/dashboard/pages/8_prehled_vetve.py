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

from moduly.apps.dashboard.auto_refresh import QUARTER_HOUR_PAGE_REFRESH_MINUTES, enable_scheduled_page_refresh
from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.vodomery_shared import (
    format_consumption_with_unit,
    get_vodomery_access_context,
    load_branch_day_overview,
    render_vodomery_header,
)


DATE_KEY = "vodomery_branch_overview_date"
DONUT_LABELS_MAX_HEIGHT_PX = 360


st.set_page_config(
    page_title="Vodoměry - Přehled větve",
    page_icon="🌿",
    layout="wide",
)


require_page_access("vodomery_branch_overview")


def init_page_state() -> None:
    st.session_state.setdefault(DATE_KEY, prague_today())


def render_branch_layout_styles() -> None:
    st.markdown(
        f"""
        <style>
        .branch-donut-label-list {{
            max-height: {DONUT_LABELS_MAX_HEIGHT_PX}px;
            overflow-y: auto;
            padding-right: 0.25rem;
        }}

        .branch-donut-label-list::-webkit-scrollbar {{
            width: 0.45rem;
        }}

        .branch-donut-label-list::-webkit-scrollbar-thumb {{
            background: #cbd5e1;
            border-radius: 999px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_filters() -> datetime.date:
    init_page_state()
    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        selected_date = st.date_input("Den", key=DATE_KEY)
    if not isinstance(selected_date, datetime.date):
        return prague_today()
    return selected_date


def build_branch_chart(hourly_df):
    limit_chart = alt.Chart(hourly_df.dropna(subset=["denni_limit"])).mark_line(color="#dc2626").encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("denni_limit:Q", title=None),
    )
    expected_chart = alt.Chart(hourly_df).mark_line(color="#dedcd9").encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("ocekavana_kumulovana_spotreba:Q", title=None),
    )
    actual_chart = alt.Chart(hourly_df).mark_line(color="#1f77b4").encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("kumulovana_spotreba_graf:Q", title=None),
    )
    billing_chart = alt.Chart(
        hourly_df.dropna(subset=["fakturacni_kumulovana_spotreba_graf"])
    ).mark_line(color="#f97316").encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("fakturacni_kumulovana_spotreba_graf:Q", title=None),
    )
    connected_prediction_chart = alt.Chart(
        hourly_df.dropna(subset=["navazna_predikce"])
    ).mark_line(color="#8ecae6").encode(
        x=alt.X("date:T", title=None),
        y=alt.Y("navazna_predikce:Q", title=None),
    )
    return (limit_chart + expected_chart + connected_prediction_chart + actual_chart + billing_chart).interactive()


def format_expected_deviation_percent(value: object) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if pd.isna(numeric_value):
        return "N/A"
    if abs(numeric_value) < 0.05:
        numeric_value = 0.0
    return f"{numeric_value:+.1f} %"


def prepare_branch_donut_data(device_consumption_df: pd.DataFrame) -> pd.DataFrame:
    if device_consumption_df.empty:
        return pd.DataFrame()

    chart_data = device_consumption_df.loc[device_consumption_df["spotreba"] > 0].copy()
    if chart_data.empty:
        return pd.DataFrame()
    if "ocekavana_spotreba" not in chart_data.columns:
        chart_data["ocekavana_spotreba"] = pd.NA
    if "odchylka_od_ocekavani_procent" not in chart_data.columns:
        chart_data["odchylka_od_ocekavani_procent"] = pd.NA

    palette = [
        "#4c78a8",
        "#f58518",
        "#e45756",
        "#72b7b2",
        "#54a24b",
        "#eeca3b",
        "#b279a2",
        "#ff9da6",
        "#9d755d",
        "#bab0ac",
    ]
    chart_data["color_hex"] = [palette[index % len(palette)] for index in range(len(chart_data))]
    chart_data["color_order"] = range(len(chart_data))
    chart_data["odchylka_od_ocekavani_label"] = chart_data["odchylka_od_ocekavani_procent"].apply(
        format_expected_deviation_percent
    )
    chart_data["label"] = chart_data.apply(
        lambda row: (
            f"{row['identifikace']} {format_consumption_with_unit(row['spotreba'])} "
            f"({row['podil_procent']:.1f} %, {row['odchylka_od_ocekavani_label']} vs očekávání)"
        ),
        axis=1,
    )
    return chart_data


def build_branch_donut_chart(chart_data: pd.DataFrame):
    if chart_data.empty:
        return None

    base_chart = alt.Chart(chart_data).encode(
        theta=alt.Theta("spotreba:Q", title="Spotřeba"),
        color=alt.Color(
            "color_hex:N",
            scale=None,
            legend=None,
        ),
        order=alt.Order("spotreba:Q", sort="descending"),
        tooltip=[
            alt.Tooltip("identifikace:N", title="Odběrné místo"),
            alt.Tooltip("spotreba:Q", title="Spotřeba [m³]", format=".3f"),
            alt.Tooltip("podil_procent:Q", title="Podíl [%]", format=".1f"),
            alt.Tooltip("ocekavana_spotreba:Q", title="Očekávaná spotřeba [m³]", format=".3f"),
            alt.Tooltip("odchylka_od_ocekavani_label:N", title="Odchylka vs očekávání"),
        ],
    )

    donut_chart = base_chart.mark_arc(innerRadius=58, outerRadius=96).properties(width=240, height=240)
    return donut_chart.configure_view(stroke=None)


def build_branch_stacked_area_chart(
    device_hourly_df: pd.DataFrame,
    hourly_df: pd.DataFrame,
    chart_data: pd.DataFrame,
    last_actual_timestamp: datetime.datetime | None,
):
    if device_hourly_df.empty or hourly_df.empty or chart_data.empty:
        return None

    area_df = device_hourly_df.merge(
        chart_data[["identifikace", "color_hex", "color_order"]],
        on="identifikace",
        how="inner",
    )
    if area_df.empty:
        return None
    if last_actual_timestamp is None:
        return None

    last_actual_hour = pd.Timestamp(last_actual_timestamp).floor("h").to_pydatetime()
    area_df = area_df.loc[area_df["date"] <= last_actual_hour].copy()
    if area_df.empty:
        return None

    prediction_df = hourly_df.loc[:, ["date", "ocekavana_spotreba"]].copy()
    prediction_df["ocekavana_spotreba"] = pd.to_numeric(prediction_df["ocekavana_spotreba"], errors="coerce")
    prediction_df = prediction_df.dropna(subset=["date", "ocekavana_spotreba"])

    billing_df = pd.DataFrame()
    billing_columns = {"date", "fakturacni_spotreba", "fakturacni_kumulovana_spotreba_graf"}
    if billing_columns.issubset(hourly_df.columns):
        visible_billing_mask = hourly_df["fakturacni_kumulovana_spotreba_graf"].notna()
        billing_df = hourly_df.loc[visible_billing_mask, ["date", "fakturacni_spotreba"]].copy()
        billing_df["fakturacni_spotreba"] = pd.to_numeric(billing_df["fakturacni_spotreba"], errors="coerce")
        billing_df = billing_df.dropna(subset=["date", "fakturacni_spotreba"])

    area_chart = (
        alt.Chart(area_df)
        .mark_area()
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("spotreba:Q", title="Spotřeba [m³]", stack="zero"),
            color=alt.Color("color_hex:N", scale=None, legend=None),
            detail=alt.Detail("identifikace:N"),
            order=alt.Order("color_order:Q", sort="ascending"),
            tooltip=[
                alt.Tooltip("date:T", title="Čas"),
                alt.Tooltip("identifikace:N", title="Odběrné místo"),
                alt.Tooltip("spotreba:Q", title="Spotřeba [m³]", format=".3f"),
            ],
        )
        .properties(height=220)
    )

    layered_chart = area_chart

    if not prediction_df.empty:
        prediction_chart = (
            alt.Chart(prediction_df)
            .mark_line(color="#dedcd9", strokeWidth=2.5)
            .encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("ocekavana_spotreba:Q", title="Spotřeba [m³]"),
                tooltip=[
                    alt.Tooltip("date:T", title="Čas"),
                    alt.Tooltip("ocekavana_spotreba:Q", title="Predikce [m³]", format=".3f"),
                ],
            )
        )
        layered_chart = layered_chart + prediction_chart

    if not billing_df.empty:
        billing_chart = (
            alt.Chart(billing_df)
            .mark_line(color="#f97316", strokeWidth=2.5)
            .encode(
                x=alt.X("date:T", title=None),
                y=alt.Y("fakturacni_spotreba:Q", title="Spotřeba [m³]"),
                tooltip=[
                    alt.Tooltip("date:T", title="Čas"),
                    alt.Tooltip("fakturacni_spotreba:Q", title="SČVK [m³]", format=".3f"),
                ],
            )
        )
        layered_chart = layered_chart + billing_chart

    return layered_chart.configure_view(stroke=None).interactive()


def render_branch_donut_labels(chart_data: pd.DataFrame) -> None:
    label_data = chart_data.loc[chart_data["podil_procent"] >= 1].copy()
    if label_data.empty:
        st.caption("Žádné odběrné místo nemá podíl alespoň 1 %.")
        return

    label_rows = []
    for row in label_data.itertuples(index=False):
        label_rows.append(
            (
                '<div style="display:flex;align-items:flex-start;gap:0.45rem;margin-bottom:0.35rem;">'
                f'<span style="width:0.8rem;height:0.8rem;border-radius:999px;background:{row.color_hex};'
                'display:inline-block;flex:0 0 auto;margin-top:0.18rem;"></span>'
                '<div style="line-height:1.2;">'
                f'<div style="font-size:0.85rem;font-weight:600;color:#0f172a;">{row.identifikace}</div>'
                f'<div style="font-size:0.8rem;color:#475569;">{format_consumption_with_unit(row.spotreba)} ({row.podil_procent:.1f} %)</div>'
                f'<div style="font-size:0.78rem;color:#64748b;">vs. očekávání: {row.odchylka_od_ocekavani_label}</div>'
                "</div>"
                "</div>"
            )
        )

    st.markdown(
        f'<div class="branch-donut-label-list">{"".join(label_rows)}</div>',
        unsafe_allow_html=True,
    )


def render_branch_legend() -> None:
    st.markdown(
        (
            '<div style="margin-top:0.75rem;font-size:0.92rem;">'
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;margin-right:1rem;">'
            '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#dc2626;"></span>'
            "Denní limit"
            "</span>"
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;margin-right:1rem;">'
            '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#1f77b4;"></span>'
            "Skutečná spotřeba"
            "</span>"
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;margin-right:1rem;">'
            '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#f97316;"></span>'
            "SČVK fakturační vodoměr"
            "</span>"
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;margin-right:1rem;">'
            '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#8ecae6;"></span>'
            "Očekávaná spotřeba"
            "</span>"
            '<span style="display:inline-flex;align-items:center;gap:0.4rem;">'
            '<span style="display:inline-block;width:0.85rem;height:0.85rem;border-radius:999px;background:#dedcd9;border:1px solid #cfcac4;"></span>'
            "Celodenní predikce"
            "</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_branch_card(branch_data: dict[str, object], selected_date: datetime.date) -> None:
    hourly_df = branch_data["hourly_df"]
    device_consumption_df = branch_data["device_consumption_df"]
    device_hourly_df = branch_data["device_hourly_df"]
    last_actual_timestamp = branch_data["last_actual_timestamp"]
    active_devices = tuple(branch_data["active_devices"])
    active_devices_label = ", ".join(active_devices) if active_devices else "-"
    daily_limit = branch_data["daily_limit"]
    remaining_to_limit = branch_data["remaining_to_limit"]

    with st.container(border=True):
        st.subheader(f"{branch_data['title']} • {branch_data['billing_ident']}")
        st.caption(
            f"Aktivní odběrná místa dne: {len(active_devices)} | {active_devices_label}"
        )
        if branch_data["last_actual_timestamp"] is not None:
            st.caption(
                "Skutečná data jsou v grafu vykreslena do: "
                f"{branch_data['last_actual_timestamp'].strftime('%d.%m.%Y %H:%M')}"
            )
        else:
            st.caption("Pro vybraný den zatím nejsou k dispozici žádná skutečná data.")

        metric_cols = st.columns(5)
        metric_cols[0].metric("Součet spotřeby", format_consumption_with_unit(branch_data["actual_total"]))
        metric_cols[1].metric("Celodenní predikce", format_consumption_with_unit(branch_data["expected_total"]))
        metric_cols[2].metric(
            "Očekávaná spotřeba na konci dne",
            format_consumption_with_unit(branch_data["expected_end_of_day"]),
        )
        metric_cols[3].metric(
            "Denní limit",
            format_consumption_with_unit(daily_limit) if daily_limit is not None else "N/A",
        )
        metric_cols[4].metric(
            "Očekávaná do limitu",
            format_consumption_with_unit(branch_data["expected_vs_limit"], signed=True)
            if branch_data["expected_vs_limit"] is not None
            else "N/A",
        )

        if daily_limit is not None and branch_data["expected_vs_limit"] is not None and branch_data["expected_vs_limit"] > 0:
            st.warning(
                f"Predikce pro {selected_date.strftime('%d.%m.%Y')} překračuje denní limit o "
                f"{format_consumption_with_unit(branch_data['expected_vs_limit'])}."
            )

        chart_data = prepare_branch_donut_data(device_consumption_df)

        charts_col, donut_col = st.columns((4.2, 1.8))
        with charts_col:
            with st.container(border=True):
                st.altair_chart(build_branch_chart(hourly_df), width="stretch")
                render_branch_legend()
            area_chart = build_branch_stacked_area_chart(
                device_hourly_df,
                hourly_df,
                chart_data,
                last_actual_timestamp,
            )
            with st.container(border=True):
                st.caption("Okamžitá spotřeba podle odběrných míst, SČVK vodoměr a hodinová predikce pro celý den")
                if area_chart is None:
                    st.info("Pro vybraný den zatím není k dispozici hodinová spotřeba odběrných míst.")
                else:
                    st.altair_chart(area_chart, width="stretch")

        with donut_col:
            with st.container(border=True, height="stretch"):
                st.caption("Podíl odběrných míst na skutečné spotřebě celé větve")
                donut_chart = build_branch_donut_chart(chart_data)
                if donut_chart is None:
                    st.info("Pro vybraný den zatím není k dispozici skutečná spotřeba odběrných míst.")
                else:
                    st.altair_chart(donut_chart, width="stretch")
                    render_branch_donut_labels(chart_data)


def render_dashboard() -> None:
    render_vodomery_header(
        "Přehled větve",
        "Denní součty skutečné spotřeby a predikce pro jednotlivé SČVK větve.",
    )
    render_branch_layout_styles()
    user_is_admin, allowed_devices = get_vodomery_access_context()
    selected_date = render_sidebar_filters()
    if selected_date == prague_today():
        enable_scheduled_page_refresh(
            "vodomery_branch_overview",
            cache_clearers=(load_branch_day_overview.clear,),
            refresh_minutes=QUARTER_HOUR_PAGE_REFRESH_MINUTES,
        )

    st.caption(
        "Modrá linka zobrazuje kumulovanou skutečnou spotřebu odběrných míst na větvi, "
        "oranžová fakturační SČVK vodoměr, šedá celodenní predikci a světle modrá očekávaný vývoj od aktuální spotřeby."
    )

    branch_rows = load_branch_day_overview(selected_date, allowed_devices, user_is_admin)
    if not branch_rows:
        st.info("Pro vybraný den a aktuální oprávnění nejsou k dispozici žádné větve.")
        return

    for branch_data in branch_rows:
        render_branch_card(branch_data, selected_date)


try:
    render_dashboard()
except (SQLAlchemyError, DashboardApiError) as exc:
    st.error("Nepodařilo se načíst data pro vodoměry.")
    st.exception(exc)
