from __future__ import annotations

import streamlit as st


MOBILE_BREAKPOINT_PX = 720


RESPONSIVE_PAGE_STYLE = f"""
<style>
@media (max-width: {MOBILE_BREAKPOINT_PX}px) {{
    section.main > div.block-container,
    div[data-testid="stMainBlockContainer"] {{
        padding-top: 1rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        padding-bottom: 1.25rem !important;
    }}

    [data-testid="stHorizontalBlock"] {{
        flex-wrap: wrap !important;
        gap: 0.75rem !important;
    }}

    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        flex: 1 1 100% !important;
        width: 100% !important;
        min-width: 100% !important;
    }}

    [class*="st-key-mobile_metric_grid_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        flex: 1 1 calc(50% - 0.375rem) !important;
        width: calc(50% - 0.375rem) !important;
        min-width: calc(50% - 0.375rem) !important;
    }}

    [data-testid="stMetric"] {{
        min-height: 5.75rem;
        padding: 0.7rem 0.75rem;
        border: 1px solid rgba(49, 51, 63, 0.14);
        border-radius: 0.75rem;
    }}

    [data-testid="stMetricValue"] {{
        font-size: clamp(1.15rem, 6vw, 1.65rem);
    }}

    [data-testid="stDataFrame"],
    [data-testid="stTable"] {{
        max-width: 100%;
        overflow-x: auto;
    }}

    .stButton > button,
    .stFormSubmitButton > button,
    .stDownloadButton > button {{
        min-height: 2.75rem;
    }}

    h1 {{
        font-size: clamp(1.7rem, 8vw, 2.25rem) !important;
    }}
}}
</style>
"""


def render_responsive_page_styles() -> None:
    st.markdown(RESPONSIVE_PAGE_STYLE, unsafe_allow_html=True)
