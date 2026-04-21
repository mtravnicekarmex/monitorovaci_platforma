from __future__ import annotations

import altair as alt
import pandas as pd
from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import (
    current_user_email,
    current_user_last_login_at,
    current_username,
    get_allowed_devices,
    has_page_access,
    has_section_access,
    is_admin,
    require_page_access,
)
from moduly.apps.dashboard.navigation_config import SECTIONS, get_page_definition
from moduly.apps.dashboard.overview_shared import (
    MANOMETRY_CHART_DEVICE_LIMIT,
    MODULE_OVERVIEW_PAGE_KEYS,
    RECENT_WINDOW_DAYS,
    format_overview_timestamp,
    load_dashboard_overview_cards,
)
from moduly.apps.dashboard.manometry_shared import format_pressure_with_unit
from moduly.apps.dashboard.vodomery_shared import format_consumption_with_unit


st.set_page_config(
    page_title="Overview",
    page_icon="🏠",
    layout="wide",
)


require_page_access("dashboard_overview")


def render_overview_styles() -> None:
    st.markdown(
        """
        <style>
        .dashboard-overview-hero {
            position: relative;
            overflow: hidden;
            padding: 1.5rem 1.6rem;
            margin-bottom: 1.1rem;
            border-radius: 24px;
            border: 1px solid #d9e7ec;
            background:
                radial-gradient(circle at top right, rgba(14, 165, 233, 0.16), transparent 36%),
                radial-gradient(circle at bottom left, rgba(20, 184, 166, 0.16), transparent 28%),
                linear-gradient(135deg, #f8fbfc 0%, #eef6f5 52%, #fef7ed 100%);
        }

        .dashboard-overview-kicker {
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.74rem;
            color: #0f766e;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }

        .dashboard-overview-title {
            margin: 0;
            color: #0f172a;
            font-size: 2rem;
            line-height: 1.1;
        }

        .dashboard-overview-subtitle {
            margin-top: 0.65rem;
            max-width: 52rem;
            color: #334155;
            font-size: 0.98rem;
            line-height: 1.55;
        }

        .dashboard-overview-chip-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            margin-top: 1rem;
        }

        .dashboard-overview-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.42rem 0.8rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.78);
            border: 1px solid rgba(148, 163, 184, 0.28);
            color: #0f172a;
            font-size: 0.86rem;
        }

        .dashboard-overview-card-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            margin-bottom: 0.35rem;
        }

        .dashboard-overview-card-title {
            font-weight: 700;
            color: #0f172a;
            font-size: 1.08rem;
        }

        .dashboard-overview-inline-header {
            display: flex;
            align-items: baseline;
            gap: 0.65rem;
            margin-bottom: 0.75rem;
            flex-wrap: wrap;
        }

        .dashboard-overview-inline-subtitle {
            color: #64748b;
            font-size: 0.82rem;
            line-height: 1.2;
        }

        .dashboard-overview-chart-header {
            display: flex;
            align-items: baseline;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin: 0.35rem 0 0.15rem 0;
        }

        .dashboard-overview-chart-ident {
            font-size: 0.95rem;
            font-weight: 700;
            color: #0f172a;
        }

        .dashboard-overview-chart-meta {
            font-size: 0.84rem;
            font-weight: 400;
            color: #64748b;
        }

        .dashboard-overview-card-subtitle {
            color: #475569;
            font-size: 0.92rem;
            min-height: 2.7rem;
        }

        .dashboard-overview-badges {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.85rem;
        }

        .dashboard-overview-badge {
            display: inline-flex;
            align-items: baseline;
            gap: 0.35rem;
            padding: 0.38rem 0.66rem;
            border-radius: 999px;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            color: #0f172a;
            font-size: 0.82rem;
        }

        .dashboard-overview-badge strong {
            font-size: 0.9rem;
        }

        .dashboard-overview-muted {
            color: #64748b;
            font-size: 0.88rem;
            margin-top: 0.8rem;
        }

        .dashboard-overview-placeholder {
            min-height: 8.5rem;
            border: 1px dashed #cbd5e1;
            border-radius: 14px;
            background: #f8fafc;
            color: #64748b;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            font-size: 0.9rem;
            padding: 0.8rem;
        }

        .dashboard-overview-locked {
            border-style: dashed;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_accessible_section_keys() -> tuple[str, ...]:
    return tuple(section.key for section in SECTIONS if has_section_access(section.key))


def render_hero(accessible_section_keys: tuple[str, ...]) -> None:
    username = current_username()
    role_label = "Admin" if is_admin() else "Uživatel"
    email = current_user_email() or "bez e-mailu"
    last_login = format_overview_timestamp(current_user_last_login_at())
    allowed_devices = len(get_allowed_devices())

    chips = [
        f"<span class='dashboard-overview-chip'><strong>{role_label}</strong></span>",
        f"<span class='dashboard-overview-chip'>Uživatel: <strong>{username}</strong></span>",
        f"<span class='dashboard-overview-chip'>Email: <strong>{email}</strong></span>",
        f"<span class='dashboard-overview-chip'>Dostupné moduly: <strong>{len(accessible_section_keys)}</strong></span>",
        f"<span class='dashboard-overview-chip'>Přiřazená zařízení: <strong>{allowed_devices}</strong></span>",
        f"<span class='dashboard-overview-chip'>Poslední login: <strong>{last_login}</strong></span>",
    ]

    st.markdown(
        f"""
        <section class="dashboard-overview-hero">
            <div class="dashboard-overview-kicker">Monitoring Platforma</div>
            <h1 class="dashboard-overview-title">Overview dashboardu</h1>
            <div class="dashboard-overview-subtitle">
                Úvodní obrazovka sjednocuje rychlý přehled nad dostupnými moduly a ukazuje,
                kde jsou nová data, kde se hromadí anomálie a do které části dashboardu má smysl jít jako první.
            </div>
            <div class="dashboard-overview-chip-row">{''.join(chips)}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_module_badges(badges: list[dict[str, object]]) -> None:
    if not badges:
        return

    badge_html = "".join(
        f"<span class='dashboard-overview-badge'>{badge['label']}: <strong>{badge['value']}</strong></span>"
        for badge in badges
    )
    st.markdown(f"<div class='dashboard-overview-badges'>{badge_html}</div>", unsafe_allow_html=True)


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


def build_branch_stacked_area_chart(
    device_hourly_df: pd.DataFrame,
    hourly_df: pd.DataFrame,
    chart_data: pd.DataFrame,
    last_actual_timestamp,
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
    prediction_df = prediction_df.dropna(subset=["date", "ocekavana_spotreba"])

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
    if prediction_df.empty:
        return area_chart.configure_view(stroke=None).interactive()

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
    return (area_chart + prediction_chart).configure_view(stroke=None).interactive()


def render_vodomery_branch_area_charts(branch_rows: list[dict[str, object]]) -> None:
    if not branch_rows:
        st.caption("Pro dnešní den není branch overview dostupný.")
        return

    for start_index in range(0, len(branch_rows), 2):
        row_columns = st.columns(2)
        row_branch_rows = branch_rows[start_index:start_index + 2]

        for column, branch_data in zip(row_columns, row_branch_rows):
            chart_data = prepare_branch_donut_data(branch_data["device_consumption_df"])
            area_chart = build_branch_stacked_area_chart(
                branch_data["device_hourly_df"],
                branch_data["hourly_df"],
                chart_data,
                branch_data["last_actual_timestamp"],
            )

            with column:
                with st.container(border=True):
                    expected_vs_limit = (
                        format_consumption_with_unit(branch_data["expected_vs_limit"], signed=True)
                        if branch_data.get("expected_vs_limit") is not None
                        else "N/A"
                    )
                    st.markdown(
                        (
                            "<div class='dashboard-overview-chart-header'>"
                            f"<span class='dashboard-overview-chart-ident'>{branch_data['title']} • {branch_data['billing_ident']}</span>"
                            f"<span class='dashboard-overview-chart-meta'>Očekávaná do limitu: {expected_vs_limit}</span>"
                            "</div>"
                        ),
                        unsafe_allow_html=True,
                    )
                    if area_chart is None:
                        st.info("Pro vybraný den zatím není k dispozici hodinová spotřeba odběrných míst.")
                    else:
                        st.altair_chart(area_chart, width="stretch")


def build_manometry_line_chart(chart_df: pd.DataFrame) -> alt.Chart:
    chart_source = chart_df.dropna(subset=["date", "hodnota_bar"]).copy()
    return (
        alt.Chart(chart_source)
        .mark_line(color="#2563eb", strokeWidth=2.2)
        .encode(
            x=alt.X("date:T", title=None, axis=alt.Axis(format="%H:%M", labelAngle=0)),
            y=alt.Y("hodnota_bar:Q", title="Tlak [bar]"),
            tooltip=[
                alt.Tooltip("date:T", title="Čas"),
                alt.Tooltip("hodnota_bar:Q", title="Tlak [bar]", format=".3f"),
            ],
        )
        .properties(height=145)
        .interactive()
    )


def render_manometry_placeholder(slot_index: int) -> None:
    st.markdown(
        f"<div class='dashboard-overview-placeholder'>Graf {slot_index}: pro tuto pozici zatím není dostupná 24h tlaková řada.</div>",
        unsafe_allow_html=True,
    )


def render_manometry_recent_charts(series_payloads: list[dict[str, object]]) -> None:
    for slot_index in range(MANOMETRY_CHART_DEVICE_LIMIT):
        if slot_index >= len(series_payloads):
            render_manometry_placeholder(slot_index + 1)
            continue

        payload = series_payloads[slot_index]
        chart_df = pd.DataFrame(list(payload.get("series_rows") or []))
        if "date" in chart_df.columns:
            chart_df["date"] = pd.to_datetime(chart_df["date"], errors="coerce")
        if "hodnota_bar" in chart_df.columns:
            chart_df["hodnota_bar"] = pd.to_numeric(chart_df["hodnota_bar"], errors="coerce")

        ident = str(payload.get("identifikace") or f"Graf {slot_index + 1}")
        if chart_df.empty:
            st.markdown(
                "<div class='dashboard-overview-placeholder'>Za posledních 24 hodin zatím nejsou dostupná data.</div>",
                unsafe_allow_html=True,
            )
            continue

        max_value = format_pressure_with_unit(payload.get("max_value_bar"))
        max_timestamp = format_overview_timestamp(payload.get("max_value_at"))
        min_value = format_pressure_with_unit(payload.get("min_value_bar"))
        min_timestamp = format_overview_timestamp(payload.get("min_value_at"))
        st.markdown(
            (
                "<div class='dashboard-overview-chart-header'>"
                f"<span class='dashboard-overview-chart-ident'>{ident}</span>"
                f"<span class='dashboard-overview-chart-meta'>Max: {max_value} • {max_timestamp}</span>"
                f"<span class='dashboard-overview-chart-meta'>Min: {min_value} • {min_timestamp}</span>"
                "</div>"
            ),
            unsafe_allow_html=True,
        )
        st.altair_chart(build_manometry_line_chart(chart_df), width="stretch")


def render_module_card(card: dict[str, object]) -> None:
    accent_color = str(card.get("accent_color") or "#64748b")
    accessible = bool(card.get("accessible"))
    title = str(card.get("title") or "")
    icon = str(card.get("icon") or "")
    description = str(card.get("description") or "")
    recent_window_label = f"{RECENT_WINDOW_DAYS} dní"
    section_key = str(card.get("section_key") or "")
    is_manometry = section_key == "manometry"
    is_vodomery = section_key == "vodomery"

    with st.container(border=True):
        if is_manometry:
            st.markdown(
                f"""
                <div class="dashboard-overview-inline-header">
                    <div class="dashboard-overview-card-title">{icon} {title}</div>
                    <div class="dashboard-overview-inline-subtitle">Posledních 24 hodin průběhu tlaku</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        elif is_vodomery:
            st.markdown(
                f"""
                <div class="dashboard-overview-card-head">
                    <div class="dashboard-overview-card-title">{icon} {title}</div>
                    <div style="width:0.9rem;height:0.9rem;border-radius:999px;background:{accent_color};"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="dashboard-overview-card-head">
                    <div class="dashboard-overview-card-title">{icon} {title}</div>
                    <div style="width:0.9rem;height:0.9rem;border-radius:999px;background:{accent_color};"></div>
                </div>
                <div class="dashboard-overview-card-subtitle">{description}</div>
                """,
                unsafe_allow_html=True,
            )

        if not accessible:
            st.info("Sekce není pro aktuální účet dostupná.")
            return

        if is_manometry:
            render_manometry_recent_charts(list(card.get("chart_series") or []))
            return

        if is_vodomery:
            render_vodomery_branch_area_charts(list(card.get("branch_chart_rows") or []))
            return

        error_message = card.get("error")
        if error_message:
            st.warning(str(error_message))

        metric_cols = st.columns(3)
        metric_cols[0].metric("Zařízení", f"{int(card.get('total_devices') or 0):,}".replace(",", " "))
        metric_cols[1].metric(
            f"S daty / {recent_window_label}",
            f"{int(card.get('recent_devices') or 0):,}".replace(",", " "),
        )
        metric_cols[2].metric(
            f"Řádky / {recent_window_label}",
            f"{int(card.get('recent_measurements') or 0):,}".replace(",", " "),
        )

        render_module_badges(list(card.get("badges") or []))
        st.markdown(
            f"<div class='dashboard-overview-muted'>Poslední měření: <strong>{format_overview_timestamp(card.get('last_measurement_at'))}</strong></div>",
            unsafe_allow_html=True,
        )

        page_key = card.get("page_key")
        if isinstance(page_key, str) and has_page_access(page_key):
            page = get_page_definition(page_key)
            if page is not None:
                st.page_link(page.path, label=f"Otevřít {page.title.lower()}", icon=page.icon or None)


def render_module_grid(cards: list[dict[str, object]]) -> None:
    st.subheader("Stav modulů")

    card_by_section = {
        str(card.get("section_key")): card
        for card in cards
    }

    first_row_cards = [
        card_by_section[section_key]
        for section_key in ("vodomery", "manometry")
        if section_key in card_by_section
    ]
    second_row_cards = [
        card_by_section[section_key]
        for section_key in ("plynomery", "elektromery", "kalorimetry")
        if section_key in card_by_section
    ]

    if len(first_row_cards) == 2:
        row_cols = st.columns([2, 1])
        for col, card in zip(row_cols, first_row_cards):
            with col:
                render_module_card(card)
    elif first_row_cards:
        row_cols = st.columns(len(first_row_cards))
        for col, card in zip(row_cols, first_row_cards):
            with col:
                render_module_card(card)

    if second_row_cards:
        row_cols = st.columns(len(second_row_cards))
        for col, card in zip(row_cols, second_row_cards):
            with col:
                render_module_card(card)


render_overview_styles()
accessible_section_keys = build_accessible_section_keys()
cards = load_dashboard_overview_cards(accessible_section_keys, get_allowed_devices(), is_admin())

render_hero(accessible_section_keys)
render_module_grid(cards)
