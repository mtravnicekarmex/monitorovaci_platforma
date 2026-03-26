from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    get_vodomery_devices,
    get_vodomery_expected_zero,
    update_vodomery_expected_zero,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access


st.set_page_config(
    page_title="Expected zero",
    page_icon="⭕",
    layout="wide",
)


require_page_access("expected_zero")


@st.cache_data(ttl=60)
def load_device_options() -> list[str]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return get_vodomery_devices(access_token, source_filter="VSE", limit=5000)


@st.cache_data(ttl=60)
def load_expected_zero_rows() -> list[dict[str, object]]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return get_vodomery_expected_zero(access_token)


def format_timestamp(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return str(value)


def render_page() -> None:
    st.title("Expected zero")
    st.caption("Admin seznam odbernych mist, u kterych se ocekava nulovy odber.")

    device_options = load_device_options()
    expected_zero_rows = load_expected_zero_rows()
    selected_defaults = [row["identifikace"] for row in expected_zero_rows]

    with st.form("expected_zero_form"):
        selected_devices = st.multiselect(
            "Zarizeni s ocekavanym nulovym odberem",
            options=device_options,
            default=selected_defaults,
            help="Pro tato odberna mista se nebude zobrazovat ZERO_FLOW a jakykoliv odber se bude resit jako samostatny event.",
        )
        submitted = st.form_submit_button("Ulozit seznam")

    if submitted:
        update_vodomery_expected_zero(get_auth_token(), selected_devices)
        st.cache_data.clear()
        st.success("Seznam expected_zero byl ulozen.")
        st.rerun()

    st.subheader("Aktualni seznam")
    if not expected_zero_rows:
        st.info("Zatim neni nastavene zadne odberne misto s expected_zero.")
    else:
        overview_df = pd.DataFrame(
            [
                {
                    "identifikace": row["identifikace"],
                    "upravil": row["updated_by"] or "-",
                    "vytvoreno": format_timestamp(row["created_at"]),
                    "aktualizovano": format_timestamp(row["updated_at"]),
                }
                for row in expected_zero_rows
            ]
        )
        st.dataframe(overview_df, width="stretch", hide_index=True)


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist expected zero konfiguraci.")
    st.exception(exc)
