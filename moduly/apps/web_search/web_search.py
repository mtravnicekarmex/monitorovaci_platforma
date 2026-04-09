from __future__ import annotations

import streamlit as st

from moduly.apps.web_search.ui import render_web_search_page


st.set_page_config(
    page_title="Monitor webových stránek",
    page_icon="🔍",
    layout="wide",
)


render_web_search_page()
