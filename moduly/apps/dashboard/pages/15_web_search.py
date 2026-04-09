from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.web_search_admin import render_web_search_admin_page


st.set_page_config(
    page_title="Monitor webových stránek",
    page_icon="🔍",
    layout="wide",
)


require_page_access("web_search_monitor")


try:
    render_web_search_admin_page()
except DashboardApiError as exc:
    st.error(str(exc))
