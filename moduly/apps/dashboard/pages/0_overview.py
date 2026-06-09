from __future__ import annotations

import altair as alt
from html import escape
import pandas as pd
from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import (
    get_allowed_devices,
    has_page_access,
    has_section_access,
    is_admin,
    require_page_access,
)
from moduly.apps.dashboard.auto_refresh import QUARTER_HOUR_PAGE_REFRESH_MINUTES, enable_scheduled_page_refresh
from moduly.apps.dashboard.navigation_config import SECTIONS, get_page_definition
from moduly.apps.dashboard.overview_shared import (
    MANOMETRY_CHART_DEVICE_LIMIT,
    RECENT_WINDOW_DAYS,
    format_overview_timestamp,
    load_dashboard_overview_cards,
)
from moduly.apps.dashboard.overview_weather import (
    OverviewWeatherSnapshot,
    fetch_overview_weather_snapshot,
    format_overview_date,
)
from moduly.apps.dashboard.manometry_shared import format_pressure_with_unit
from moduly.apps.dashboard.responsive import render_responsive_page_styles
from moduly.apps.dashboard.vodomery_shared import align_latest_hour_timestamp, format_consumption_with_unit
from app.time_utils import prague_now_naive


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

        .dashboard-overview-hero-grid {
            display: grid;
            grid-template-columns: minmax(240px, 0.58fr) minmax(0, 1.42fr);
            gap: 1rem;
            align-items: stretch;
        }

        .dashboard-overview-kicker {
            text-transform: uppercase;
            letter-spacing: 0.18em;
            font-size: 0.76rem;
            color: #0f4c81;
            font-weight: 700;
            margin-bottom: 0.55rem;
        }

        .dashboard-overview-date {
            margin: 0;
            color: #102a43;
            font-size: 1.45rem;
            line-height: 1.15;
            font-weight: 700;
        }

        .dashboard-overview-date-note {
            margin-top: 0.5rem;
            color: #486581;
            font-size: 0.92rem;
            line-height: 1.55;
        }

        .dashboard-overview-weather-shell {
            position: relative;
            overflow: hidden;
            border-radius: 22px;
            padding: 1rem 1.05rem;
            background: linear-gradient(160deg, #334155 0%, #475569 55%, #94a3b8 100%);
            border: 1px solid rgba(255, 255, 255, 0.18);
            backdrop-filter: blur(10px);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.16);
        }

        .dashboard-overview-weather-shell::before {
            content: "";
            position: absolute;
            inset: 0;
            background:
                radial-gradient(circle at top right, rgba(255,255,255,0.22), transparent 34%),
                radial-gradient(circle at bottom left, rgba(255,255,255,0.16), transparent 32%);
            pointer-events: none;
        }

        .dashboard-overview-weather-shell > * {
            position: relative;
            z-index: 1;
        }

        .dashboard-overview-weather-summary {
            display: grid;
            grid-template-columns: minmax(0, 0.9fr) minmax(360px, 1.1fr);
            gap: 0.75rem;
            align-items: start;
        }

        .dashboard-overview-weather-info {
            min-width: 0;
        }

        .dashboard-overview-weather-days-wrap {
            display: flex;
            justify-content: flex-end;
            align-self: start;
        }

        .dashboard-overview-weather-days {
            display: grid;
            grid-template-columns: repeat(5, minmax(92px, 1fr));
            justify-content: end;
            gap: 0.45rem;
            width: min(100%, 500px);
        }

        .dashboard-overview-weather-day {
            position: relative;
            overflow: hidden;
            border-radius: 16px;
            padding: 0.58rem 0.52rem;
            border: 1px solid rgba(255, 255, 255, 0.18);
            text-align: center;
            min-height: 74px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.28);
        }

        .dashboard-overview-weather-day::before {
            content: "";
            position: absolute;
            top: 8px;
            right: 8px;
            width: 28px;
            height: 28px;
            border-radius: 999px;
            background: rgba(255,255,255,0.16);
        }

        .dashboard-overview-weather-day::after {
            content: "";
            position: absolute;
            left: 8px;
            bottom: 10px;
            width: 34px;
            height: 34px;
            border-radius: 999px;
            background: rgba(255,255,255,0.10);
        }

        .dashboard-overview-weather-day-label {
            font-size: 0.74rem;
            color: rgba(255,255,255,0.95);
            font-weight: 800;
            letter-spacing: 0.04em;
            position: relative;
            z-index: 1;
        }

        .dashboard-overview-weather-day-date {
            margin-top: 0.1rem;
            font-size: 0.68rem;
            color: rgba(255,255,255,0.74);
            position: relative;
            z-index: 1;
        }

        .dashboard-overview-weather-day-emoji {
            display: block;
            margin-top: 0.2rem;
            font-size: 1.15rem;
            line-height: 1;
            position: relative;
            z-index: 1;
        }

        .dashboard-overview-weather-day-temp {
            margin-top: 0.22rem;
            font-size: 0.72rem;
            color: rgba(255,255,255,0.96);
            font-weight: 700;
            position: relative;
            z-index: 1;
            white-space: nowrap;
        }

        .dashboard-overview-weather-day-rain {
            margin-top: 0.24rem;
            font-size: 0.68rem;
            color: rgba(255,255,255,0.82);
            position: relative;
            z-index: 1;
        }

        .dashboard-overview-weather-body {
            display: grid;
            grid-template-rows: auto auto;
            gap: 0.7rem;
            min-width: 0;
        }

        .dashboard-overview-weather-eyebrow {
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.72rem;
            color: rgba(255,255,255,0.82);
            font-weight: 700;
            margin-bottom: 0.35rem;
        }

        .dashboard-overview-weather-temp-row {
            display: flex;
            align-items: baseline;
            gap: 0.7rem;
            flex-wrap: wrap;
        }

        .dashboard-overview-weather-temp {
            font-size: 2.25rem;
            font-weight: 800;
            color: #ffffff;
            line-height: 1;
            text-shadow: 0 1px 2px rgba(15, 23, 42, 0.22);
        }

        .dashboard-overview-weather-label {
            font-size: 1rem;
            color: #f8fafc;
            font-weight: 700;
            text-shadow: 0 1px 2px rgba(15, 23, 42, 0.18);
        }

        .dashboard-overview-weather-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 0.8rem;
        }

        .dashboard-overview-weather-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            padding: 0.36rem 0.66rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.14);
            border: 1px solid rgba(255, 255, 255, 0.2);
            color: #f8fafc;
            font-size: 0.82rem;
            backdrop-filter: blur(8px);
        }

        .dashboard-overview-weather-hourly-title {
            margin: 0 0 0.55rem 0;
            color: #f8fafc;
            font-size: 0.92rem;
            font-weight: 700;
            text-shadow: 0 1px 2px rgba(15, 23, 42, 0.16);
        }

        .dashboard-overview-weather-hourly {
            display: grid;
            grid-auto-flow: column;
            grid-auto-columns: minmax(76px, 1fr);
            gap: 0.45rem;
            overflow-x: auto;
            padding-bottom: 0.2rem;
            scrollbar-width: thin;
        }

        .dashboard-overview-weather-hour {
            border-radius: 16px;
            padding: 0.58rem 0.52rem;
            background: rgba(248, 250, 252, 0.92);
            border: 1px solid #d9e2ec;
            min-height: 74px;
        }

        .dashboard-overview-weather-hour-time {
            font-size: 0.74rem;
            color: #486581;
            font-weight: 700;
        }

        .dashboard-overview-weather-hour-temp {
            margin-top: 0.28rem;
            font-size: 0.92rem;
            font-weight: 800;
            color: #102a43;
        }

        .dashboard-overview-weather-hour-meta {
            display: flex;
            align-items: center;
            gap: 0.35rem;
            margin-top: 0.28rem;
            color: #486581;
            font-size: 0.72rem;
        }

        .dashboard-overview-weather-emoji {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 1.1em;
            line-height: 1;
        }

        .dashboard-overview-weather-unavailable {
            min-height: 10rem;
            border: 1px dashed #cbd5e1;
            border-radius: 18px;
            background: rgba(248, 250, 252, 0.88);
            color: #52606d;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 1rem;
        }

        .weather-visual-clear {
            background: linear-gradient(160deg, #0f4c81 0%, #1d7dbb 54%, #56c0e8 100%);
        }

        .weather-visual-clouds {
            background: linear-gradient(160deg, #475569 0%, #64748b 55%, #cbd5e1 100%);
        }

        .weather-visual-fog {
            background: linear-gradient(160deg, #64748b 0%, #94a3b8 55%, #e2e8f0 100%);
        }

        .weather-visual-rain {
            background: linear-gradient(160deg, #0f766e 0%, #0ea5a4 55%, #7dd3fc 100%);
        }

        .weather-visual-snow {
            background: linear-gradient(160deg, #94a3b8 0%, #cbd5e1 52%, #f8fafc 100%);
        }

        .weather-visual-storm {
            background: linear-gradient(160deg, #312e81 0%, #4c1d95 55%, #7c3aed 100%);
        }

        .weather-visual-unknown {
            background: linear-gradient(160deg, #334155 0%, #475569 55%, #94a3b8 100%);
        }

        .weather-tone-clear {
            background: #0ea5e9;
        }

        .weather-tone-clouds {
            background: #64748b;
        }

        .weather-tone-fog {
            background: #94a3b8;
        }

        .weather-tone-rain {
            background: #0f766e;
        }

        .weather-tone-snow {
            background: #cbd5e1;
        }

        .weather-tone-storm {
            background: #7c3aed;
        }

        .weather-tone-unknown {
            background: #94a3b8;
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

        .dashboard-overview-alarm-summary {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.45rem;
            margin: 0.9rem 0 0.95rem 0;
        }

        .dashboard-overview-alarm-stat {
            border-radius: 14px;
            border: 1px solid #fecaca;
            background: linear-gradient(180deg, #fff5f5 0%, #fff1f2 100%);
            padding: 0.58rem 0.62rem;
        }

        .dashboard-overview-alarm-stat-label {
            font-size: 0.68rem;
            color: #9f1239;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            font-weight: 700;
        }

        .dashboard-overview-alarm-stat-value {
            margin-top: 0.2rem;
            font-size: 1.02rem;
            color: #7f1d1d;
            font-weight: 800;
            line-height: 1.1;
        }

        .dashboard-overview-alarm-list {
            display: flex;
            flex-direction: column;
            gap: 0.55rem;
            padding-bottom: 0.35rem;
        }

        .dashboard-overview-alarm-row {
            border-radius: 15px;
            border: 1px solid #fed7d7;
            background: linear-gradient(135deg, #fff7f7 0%, #fff1f2 100%);
            padding: 0.72rem 0.78rem;
        }

        .dashboard-overview-alarm-main {
            display: flex;
            align-items: baseline;
            gap: 0.38rem;
            flex-wrap: wrap;
            min-width: 0;
        }

        .dashboard-overview-alarm-ident {
            font-size: 0.96rem;
            font-weight: 700;
            color: #111827;
        }

        .dashboard-overview-alarm-type {
            margin-top: 0;
            color: #9a3412;
            font-size: 0.76rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }

        .dashboard-overview-alarm-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 0.38rem;
            margin-top: 0.48rem;
        }

        .dashboard-overview-alarm-meta span {
            display: inline-flex;
            align-items: center;
            padding: 0.14rem 0.44rem;
            border-radius: 999px;
            border: 1px solid #fbd5c4;
            background: rgba(255, 255, 255, 0.8);
            color: #6b7280;
            font-size: 0.75rem;
        }

        .dashboard-overview-alarm-empty {
            min-height: 8.5rem;
            border: 1px dashed #fca5a5;
            border-radius: 16px;
            background: linear-gradient(135deg, #fff7f7 0%, #fffaf0 100%);
            color: #7f1d1d;
            display: flex;
            align-items: center;
            justify-content: center;
            text-align: center;
            padding: 1rem;
            font-size: 0.92rem;
        }

        .dashboard-overview-locked {
            border-style: dashed;
        }

        @media (max-width: 980px) {
            .dashboard-overview-hero-grid {
                grid-template-columns: 1fr;
            }

            .dashboard-overview-weather-summary {
                grid-template-columns: 1fr;
            }

            .dashboard-overview-weather-days-wrap {
                justify-content: flex-end;
            }

            .dashboard-overview-weather-days {
                grid-template-columns: repeat(5, minmax(88px, 1fr));
                width: min(100%, 500px);
            }

        }

        @media (max-width: 720px) {
            .dashboard-overview-hero {
                padding: 1rem;
                border-radius: 18px;
            }

            .dashboard-overview-weather-shell {
                padding: 0.8rem;
                border-radius: 16px;
            }

            .dashboard-overview-weather-days {
                grid-template-columns: repeat(2, minmax(0, 1fr));
                width: 100%;
            }

            .dashboard-overview-weather-day:last-child:nth-child(odd) {
                grid-column: 1 / -1;
            }

            .dashboard-overview-chart-header,
            .dashboard-overview-alarm-row,
            .dashboard-overview-alarm-meta {
                align-items: flex-start;
                flex-direction: column;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_accessible_section_keys() -> tuple[str, ...]:
    return tuple(section.key for section in SECTIONS if has_section_access(section.key))


@st.cache_data(ttl=900, show_spinner=False)
def load_overview_weather() -> OverviewWeatherSnapshot | None:
    try:
        return fetch_overview_weather_snapshot(now=prague_now_naive())
    except Exception:
        return None


def _format_weather_temperature(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1f} °C"


def _format_weather_percent(value: float | None) -> str:
    return "N/A" if value is None else f"{int(round(value))} %"


def _format_weather_wind(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.1f} km/h"


def _format_sunshine_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    sunshine_value = max(0.0, min(100.0, 100.0 - float(value)))
    return _format_weather_percent(sunshine_value)


def _weather_emoji(condition_key: str) -> str:
    return {
        "clear": "☀️",
        "clouds": "⛅",
        "fog": "🌫️",
        "rain": "🌧️",
        "snow": "❄️",
        "storm": "⛈️",
    }.get(condition_key, "🌤️")


def _hourly_sky_emoji(point, snapshot: OverviewWeatherSnapshot) -> str:
    sunset_at = getattr(snapshot, "sunset_at", None)
    if sunset_at is not None and point.timestamp >= sunset_at:
        return "🌙"
    return "☀️"


def _build_weather_daily_markup(snapshot: OverviewWeatherSnapshot) -> str:
    if not snapshot.daily_forecast:
        return ""

    day_cards = []
    for point in snapshot.daily_forecast:
        day_cards.append(
            f"<div class='dashboard-overview-weather-day weather-visual-{escape(point.condition_key)}'>"
            f"<div class='dashboard-overview-weather-day-label'>{escape(point.day_label)}</div>"
            f"<div class='dashboard-overview-weather-day-date'>{escape(point.date_label)}</div>"
            f"<span class='dashboard-overview-weather-day-emoji'>{_weather_emoji(point.condition_key)}</span>"
            f"<div class='dashboard-overview-weather-day-temp'>{escape(_format_weather_temperature(point.temperature_max))} / {escape(_format_weather_temperature(point.temperature_min))}</div>"
            f"<div class='dashboard-overview-weather-day-rain'>🌧️ {escape(_format_weather_percent(point.precipitation_probability_max))}</div>"
            f"<div class='dashboard-overview-weather-day-rain'>☀️ {escape(_format_sunshine_percent(point.cloud_cover_mean))}</div>"
            "</div>"
        )
    return f"<div class='dashboard-overview-weather-days'>{''.join(day_cards)}</div>"


def _build_weather_hourly_markup(snapshot: OverviewWeatherSnapshot) -> str:
    if not snapshot.hourly_forecast:
        return "<div class='dashboard-overview-weather-unavailable'>Pro zbytek dnešního dne zatím není hodinová předpověď dostupná.</div>"

    hour_cards = []
    for point in snapshot.hourly_forecast:
        hour_cards.append(
            "<div class='dashboard-overview-weather-hour'>"
            f"<div class='dashboard-overview-weather-hour-time'>{escape(point.time_label)}</div>"
            f"<div class='dashboard-overview-weather-hour-temp'>{escape(_format_weather_temperature(point.temperature))}</div>"
            "<div class='dashboard-overview-weather-hour-meta'>"
            f"<span class='dashboard-overview-weather-emoji'>🌧️</span><span>{escape(_format_weather_percent(point.precipitation_probability))}</span>"
            "</div>"
            "<div class='dashboard-overview-weather-hour-meta'>"
            f"<span class='dashboard-overview-weather-emoji'>{_hourly_sky_emoji(point, snapshot)}</span><span>{escape(_format_sunshine_percent(point.cloud_cover))}</span>"
            "</div>"
            "</div>"
        )
    return f"<div class='dashboard-overview-weather-hourly'>{''.join(hour_cards)}</div>"


def _build_weather_panel_markup(snapshot: OverviewWeatherSnapshot | None) -> str:
    if snapshot is None:
        return "<div class='dashboard-overview-weather-unavailable'>Aktuální počasí se teď nepodařilo načíst.</div>"

    observed_at_label = snapshot.observed_at.strftime("%H:%M")

    return (
        f"<div class='dashboard-overview-weather-shell weather-visual-{escape(snapshot.condition_key)}'>"
        "<div class='dashboard-overview-weather-body'>"
        "<div class='dashboard-overview-weather-summary'>"
        "<div class='dashboard-overview-weather-info'>"
        "<div class='dashboard-overview-weather-eyebrow'>AKTUÁLNÍ POČASÍ V AREÁLU</div>"
        "<div class='dashboard-overview-weather-temp-row'>"
        f"<div class='dashboard-overview-weather-temp'>{escape(_format_weather_temperature(snapshot.current_temperature))}</div>"
        f"<div class='dashboard-overview-weather-label'>{escape(snapshot.condition_label)}</div>"
        "</div>"
        "<div class='dashboard-overview-weather-meta'>"
        f"<span class='dashboard-overview-weather-pill'>Pocitově {escape(_format_weather_temperature(snapshot.apparent_temperature))}</span>"
        f"<span class='dashboard-overview-weather-pill'>Vlhkost {escape(_format_weather_percent(snapshot.relative_humidity))}</span>"
        f"<span class='dashboard-overview-weather-pill'>Vítr {escape(_format_weather_wind(snapshot.wind_speed))}</span>"
        f"<span class='dashboard-overview-weather-pill'>Aktualizace {escape(observed_at_label)}</span>"
        "</div>"
        "</div>"
        f"<div class='dashboard-overview-weather-days-wrap'>{_build_weather_daily_markup(snapshot)}</div>"
        "</div>"
        "<div>"
        "<div class='dashboard-overview-weather-hourly-title'>Hodinová předpověď pro dnešek</div>"
        f"{_build_weather_hourly_markup(snapshot)}"
        "</div>"
        "</div>"
        "</div>"
    )


def render_hero() -> None:
    current_day = prague_now_naive().date()
    weather_snapshot = load_overview_weather()

    st.markdown(
        f"""
        <section class="dashboard-overview-hero">
            <div class="dashboard-overview-hero-grid">
                <div>
                    <div class="dashboard-overview-kicker">MONITORING PLATFORMA</div>
                    <div class="dashboard-overview-date">{escape(format_overview_date(current_day))}</div>
                </div>
                <div>
                    {_build_weather_panel_markup(weather_snapshot)}
                </div>
            </div>
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


def render_module_page_link(card: dict[str, object]) -> None:
    page_key = card.get("page_key")
    if not isinstance(page_key, str) or not has_page_access(page_key):
        return

    page = get_page_definition(page_key)
    if page is not None:
        st.page_link(page.path, label=f"Otevřít {page.title.lower()}", icon=page.icon or None)


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
    area_df = align_latest_hour_timestamp(area_df, last_actual_timestamp)

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


def _format_alarm_duration_minutes(value: object) -> str:
    try:
        total_minutes = max(int(value or 0), 0)
    except (TypeError, ValueError):
        return "N/A"

    hours, minutes = divmod(total_minutes, 60)
    if hours == 0:
        return f"{minutes} min"
    if minutes == 0:
        return f"{hours} h"
    return f"{hours} h {minutes} min"


def render_vodomery_alarm_card(card: dict[str, object]) -> None:
    summary_items = [
        ("Eventy", int(card.get("total_open_events") or 0)),
        ("Critical", int(card.get("critical_count") or 0)),
        ("Vodoměry", int(card.get("affected_devices") or 0)),
    ]
    summary_html = "".join(
        (
            "<div class='dashboard-overview-alarm-stat'>"
            f"<div class='dashboard-overview-alarm-stat-label'>{escape(label)}</div>"
            f"<div class='dashboard-overview-alarm-stat-value'>{value:,}".replace(",", " ")
            + "</div></div>"
        )
        for label, value in summary_items
    )
    st.markdown(f"<div class='dashboard-overview-alarm-summary'>{summary_html}</div>", unsafe_allow_html=True)

    event_rows = list(card.get("open_event_rows") or [])
    if not event_rows:
        st.markdown(
            "<div class='dashboard-overview-alarm-empty'>Na vodoměrech teď nejsou žádné otevřené Anomaly eventy.</div>",
            unsafe_allow_html=True,
        )
        return

    row_markup = []
    for row in event_rows:
        row_markup.append(
            "<div class='dashboard-overview-alarm-row'>"
            "<div class='dashboard-overview-alarm-main'>"
            f"<div class='dashboard-overview-alarm-ident'>{escape(str(row.get('identifikace') or '-'))}</div>"
            f"<div class='dashboard-overview-alarm-type'>{escape(str(row.get('event_type_label') or row.get('event_type') or '-'))}</div>"
            "</div>"
            "<div class='dashboard-overview-alarm-meta'>"
            f"<span>Od {escape(format_overview_timestamp(row.get('start_time')))}</span>"
            f"<span>Trvá {escape(_format_alarm_duration_minutes(row.get('duration_minutes')))}</span>"
            "</div>"
            "</div>"
        )

    st.markdown(
        f"<div class='dashboard-overview-alarm-list'>{''.join(row_markup)}</div>",
        unsafe_allow_html=True,
    )
    hidden_event_count = int(card.get("hidden_event_count") or 0)
    if hidden_event_count > 0:
        st.caption(f"Zobrazeno prvních {len(event_rows)} eventů, dalších {hidden_event_count} je v detailu.")


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
    is_vodomery_alarm = section_key == "vodomery_alarm"
    is_nabijecky = section_key == "nabijecky"

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
        elif is_vodomery_alarm:
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

        error_message = card.get("error")
        if error_message:
            st.warning(str(error_message))

        if is_manometry:
            render_manometry_recent_charts(list(card.get("chart_series") or []))
            return

        if is_vodomery:
            render_vodomery_branch_area_charts(list(card.get("branch_chart_rows") or []))
            return

        if is_vodomery_alarm:
            render_vodomery_alarm_card(card)
            return

        if is_nabijecky:
            with st.container(key=f"mobile_metric_grid_overview_{section_key}"):
                metric_cols = st.columns(3)
                metric_cols[0].metric("Lokace", f"{int(card.get('total_devices') or 0):,}".replace(",", " "))
                metric_cols[1].metric(
                    f"S relacemi / {recent_window_label}",
                    f"{int(card.get('recent_devices') or 0):,}".replace(",", " "),
                )
                metric_cols[2].metric(
                    f"Relace / {recent_window_label}",
                    f"{int(card.get('recent_measurements') or 0):,}".replace(",", " "),
                )

            render_module_badges(list(card.get("badges") or []))
            st.markdown(
                f"<div class='dashboard-overview-muted'>Poslední ukončená relace: <strong>{format_overview_timestamp(card.get('last_measurement_at'))}</strong></div>",
                unsafe_allow_html=True,
            )
            render_module_page_link(card)
            return

        with st.container(key=f"mobile_metric_grid_overview_{section_key}"):
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
        render_module_page_link(card)


def render_module_grid(cards: list[dict[str, object]]) -> None:
    card_by_section = {
        str(card.get("section_key")): card
        for card in cards
    }

    first_row_cards = [
        card_by_section[section_key]
        for section_key in ("vodomery", "vodomery_alarm")
        if section_key in card_by_section
    ]
    third_row_cards = [
        card_by_section[section_key]
        for section_key in ("plynomery", "elektromery", "nabijecky", "kalorimetry")
        if section_key in card_by_section
    ]

    if len(first_row_cards) == 2:
        row_cols = st.columns([4, 1])
        for col, card in zip(row_cols, first_row_cards):
            with col:
                render_module_card(card)
    elif first_row_cards:
        row_cols = st.columns(len(first_row_cards))
        for col, card in zip(row_cols, first_row_cards):
            with col:
                render_module_card(card)

    manometry_card = card_by_section.get("manometry")
    if manometry_card is not None:
        render_module_card(manometry_card)

    if third_row_cards:
        row_cols = st.columns(len(third_row_cards))
        for col, card in zip(row_cols, third_row_cards):
            with col:
                render_module_card(card)


render_overview_styles()
render_responsive_page_styles()
enable_scheduled_page_refresh(
    "dashboard_overview",
    cache_clearers=(load_dashboard_overview_cards.clear, load_overview_weather.clear),
    refresh_minutes=QUARTER_HOUR_PAGE_REFRESH_MINUTES,
)
accessible_section_keys = build_accessible_section_keys()
cards = load_dashboard_overview_cards(accessible_section_keys, get_allowed_devices(), is_admin())

render_hero()
render_module_grid(cards)
