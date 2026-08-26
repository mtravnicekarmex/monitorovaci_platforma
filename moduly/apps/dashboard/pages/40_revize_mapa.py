from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.map_page_shared import render_dashboard_map_page


st.set_page_config(
    page_title="Revize - Mapa",
    page_icon="map",
    layout="wide",
)


render_dashboard_map_page(
    page_key="revize_map",
    map_context="revize",
    empty_message="Pro revizni mapu nejsou dostupne zadne aktivni vrstvy.",
    load_error_message="Nepodarilo se nacist revizni mapu.",
)
