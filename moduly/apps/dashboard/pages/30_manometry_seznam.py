from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.device_list_shared import render_device_list_page


st.set_page_config(
    page_title="Manometry - Seznam",
    page_icon="🎚️",
    layout="wide",
)


require_page_access("manometry_list")


try:
    render_device_list_page("manometry")
except SQLAlchemyError as exc:
    st.error("Nepodařilo se načíst seznam manometrů z MS SQL.")
    st.exception(exc)
