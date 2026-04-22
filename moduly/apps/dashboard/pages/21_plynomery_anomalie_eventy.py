from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auto_refresh import enable_scheduled_page_refresh
from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    get_plynomery_open_events as api_get_plynomery_open_events,
    get_plynomery_resolved_events as api_get_plynomery_resolved_events,
)
from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.plynomery_shared import get_plynomery_access_context
from moduly.apps.dashboard.vodomery_shared import (
    filter_min_duration_events,
    prepare_event_display_dataframe,
    render_vodomery_header,
    require_dashboard_api_token,
)


st.set_page_config(
    page_title="Plynomery - Anomalie a eventy",
    page_icon="🚨",
    layout="wide",
)


require_page_access("plynomery_anomalie_eventy")


@st.cache_data(ttl=60)
def load_all_open_events(
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    limit: int = 500,
) -> pd.DataFrame:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_plynomery_open_events(
        access_token,
        limit=limit,
    )
    return pd.DataFrame(
        rows,
        columns=[
            "identifikace",
            "event_type",
            "start_time",
            "end_time",
            "duration_minutes",
            "max_z_score",
            "avg_z_score",
            "severity",
        ],
    )


@st.cache_data(ttl=60)
def load_recent_resolved_events(
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
    days: int = 7,
    limit: int = 500,
) -> pd.DataFrame:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_plynomery_resolved_events(
        access_token,
        days=days,
        limit=limit,
    )
    return pd.DataFrame(
        rows,
        columns=[
            "identifikace",
            "event_type",
            "start_time",
            "end_time",
            "duration_minutes",
            "max_z_score",
            "avg_z_score",
            "severity",
        ],
    )


enable_scheduled_page_refresh(
    "plynomery_anomalie_eventy",
    cache_clearers=(load_all_open_events.clear, load_recent_resolved_events.clear),
)


def format_events_table(events_df):
    display_df = events_df.rename(
        columns={
            "identifikace": "Plynomer",
            "event_type": "Typ eventu",
            "start_time": "Zacatek",
            "end_time": "Konec",
            "duration_minutes": "Trvani [min]",
            "severity": "Zavaznost",
        }
    )
    return prepare_event_display_dataframe(display_df)


def render_dashboard() -> None:
    render_vodomery_header("Plynoměry - Anomalie a eventy", "")
    user_is_admin, allowed_devices = get_plynomery_access_context()
    open_events_df = filter_min_duration_events(load_all_open_events(allowed_devices, user_is_admin, limit=500))

    resolved_events_df = filter_min_duration_events(
        load_recent_resolved_events(allowed_devices, user_is_admin, days=7, limit=500)
    )

    with st.container(border=True):
        st.subheader("Aktuálně otevřené eventy")
        st.caption("Zobrazeny jsou pouze eventy s trváním delším než 120 minut.")
        if open_events_df.empty:
            st.info("Nejsou evidovany zadne aktualne otevrene eventy.")
        else:
            summary_cols = st.columns(4)
            critical_events = int((open_events_df["severity"] == "CRITICAL").sum())
            high_events = int((open_events_df["severity"] == "HIGH").sum())
            medium_events = int((open_events_df["severity"] == "MEDIUM").sum())
            max_duration = int(open_events_df["duration_minutes"].fillna(0).max())

            summary_cols[0].metric("Aktivní eventy", len(open_events_df))
            summary_cols[1].metric("Critical eventy", critical_events)
            summary_cols[2].metric("High a medium", high_events + medium_events)
            summary_cols[3].metric("Nejdelší trvání", f"{max_duration} min")

            display_df = format_events_table(open_events_df).sort_values(["Trvani [min]"], ascending=[False])
            st.dataframe(display_df, width="stretch", hide_index=True)

    with st.container(border=True):
        st.subheader("Historie eventů")
        st.caption("Zobrazeny jsou pouze eventy s trváním delším než 120 minut.")
        if resolved_events_df.empty:
            st.info("Za posledních 7 dní nejsou evidovany zadne vyresene eventy.")
        else:
            history_df = format_events_table(resolved_events_df).sort_values(["Konec", "Trvani [min]"], ascending=[False, False])
            st.dataframe(history_df, width="stretch", hide_index=True)


try:
    render_dashboard()
except (SQLAlchemyError, DashboardApiError) as exc:
    st.error("Nepodarilo se nacist data pro plynomery.")
    st.exception(exc)
