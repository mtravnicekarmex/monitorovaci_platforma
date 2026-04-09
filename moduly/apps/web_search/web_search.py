from __future__ import annotations

import streamlit as st

from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.auth import has_page_access, init_auth_state, refresh_current_user
from moduly.apps.dashboard.web_search_admin import render_web_search_admin_page


st.set_page_config(
    page_title="Monitor webových stránek",
    page_icon="🔍",
    layout="wide",
)


init_auth_state()


def render_legacy_entry_notice() -> None:
    st.title("Monitor webových stránek")
    st.warning(
        "Samostatná web search stránka byla převedena pod hlavní dashboard a vyžaduje přihlášení admin uživatele."
    )
    st.caption("Preferovaný vstup je dashboard login a následné otevření položky `Web search` v sidebaru.")
    st.code(
        ".venv\\Scripts\\python.exe -m streamlit run moduly\\apps\\dashboard\\login.py --server.port 8001",
        language="powershell",
    )


if st.session_state.get("authenticated") and refresh_current_user():
    if has_page_access("web_search_monitor"):
        st.caption("Legacy vstup používá stejný dashboard API tok jako hlavní administrace.")
        try:
            render_web_search_admin_page()
        except DashboardApiError as exc:
            st.error(str(exc))
    else:
        st.error("Tato stránka je dostupná pouze adminovi v dashboardu.")
else:
    render_legacy_entry_notice()
