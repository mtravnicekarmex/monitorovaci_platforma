from __future__ import annotations

import streamlit as st


MOBILE_BREAKPOINT_PX = 720


RESPONSIVE_PAGE_STYLE = f"""
<style>
@media (max-width: {MOBILE_BREAKPOINT_PX}px) {{
    section.main > div.block-container,
    div[data-testid="stMainBlockContainer"] {{
        box-sizing: border-box;
        max-width: 100% !important;
        overflow-x: clip;
        padding-top: 1rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
        padding-bottom: 1.25rem !important;
    }}

    [data-testid="stHorizontalBlock"] {{
        align-items: stretch !important;
        flex-wrap: wrap !important;
        gap: 0.75rem !important;
    }}

    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {{
        flex: 1 1 100% !important;
        width: 100% !important;
        min-width: 100% !important;
    }}

    [data-testid="stHorizontalBlock"]:has(
        > [data-testid="stColumn"]
        > [data-testid="stVerticalBlock"]
        > [data-testid="stElementContainer"]:first-child
        [data-testid="stMetric"]
    ) > [data-testid="stColumn"],
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
        overflow-wrap: anywhere;
    }}

    [data-testid="stMetricLabel"] p {{
        line-height: 1.25;
        white-space: normal !important;
    }}

    [data-testid="stDataFrame"],
    [data-testid="stTable"],
    [data-testid="stVegaLiteChart"],
    [data-testid="stPlotlyChart"],
    [data-testid="stImage"],
    [data-testid="stFileUploader"],
    [data-testid="stForm"],
    [data-testid="stExpander"],
    iframe {{
        box-sizing: border-box;
        max-width: 100%;
        width: 100% !important;
    }}

    [data-testid="stDataFrame"],
    [data-testid="stTable"],
    pre {{
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
    }}

    [data-testid="stImage"] img {{
        height: auto !important;
        max-width: 100% !important;
    }}

    [data-testid="stTabs"] [role="tablist"] {{
        flex-wrap: nowrap;
        overflow-x: auto;
        scrollbar-width: thin;
        -webkit-overflow-scrolling: touch;
    }}

    [data-testid="stTabs"] [role="tab"] {{
        flex: 0 0 auto;
        min-width: max-content;
        white-space: nowrap;
    }}

    .stButton,
    .stFormSubmitButton,
    .stDownloadButton,
    .stLinkButton,
    [data-testid="stButton"],
    [data-testid="stFormSubmitButton"],
    [data-testid="stDownloadButton"],
    [data-testid="stLinkButton"] {{
        width: 100% !important;
    }}

    [data-testid="stElementContainer"]:has([data-testid="stButton"]),
    [data-testid="stElementContainer"]:has([data-testid="stFormSubmitButton"]),
    [data-testid="stElementContainer"]:has([data-testid="stDownloadButton"]),
    [data-testid="stElementContainer"]:has([data-testid="stLinkButton"]) {{
        width: 100% !important;
    }}

    .stButton > button,
    .stFormSubmitButton > button,
    .stDownloadButton > button,
    .stLinkButton > a,
    [data-testid="stButton"] > button,
    [data-testid="stFormSubmitButton"] > button,
    [data-testid="stDownloadButton"] > button,
    [data-testid="stLinkButton"] > a {{
        min-height: 2.75rem;
        white-space: normal;
        width: 100% !important;
    }}

    input,
    textarea,
    [data-baseweb="select"] input {{
        font-size: 16px !important;
    }}

    [data-testid="stAlert"],
    [data-testid="stCaptionContainer"],
    [data-testid="stMarkdownContainer"] {{
        overflow-wrap: anywhere;
    }}

    [data-testid="stDialog"] [role="dialog"] {{
        box-sizing: border-box;
        max-height: calc(100vh - 1rem) !important;
        max-width: calc(100vw - 1rem) !important;
        width: calc(100vw - 1rem) !important;
    }}

    [data-testid="stSidebar"] {{
        max-width: min(88vw, 22rem) !important;
    }}

    .vodomery-hero {{
        padding-top: 0 !important;
    }}

    .vodomery-filters {{
        align-items: stretch;
        flex-direction: column;
    }}

    .vodomery-pill {{
        justify-content: center;
        text-align: center;
        width: 100%;
    }}

    h1 {{
        font-size: clamp(1.7rem, 8vw, 2.25rem) !important;
        line-height: 1.15 !important;
    }}

    h2 {{
        font-size: clamp(1.35rem, 6vw, 1.75rem) !important;
        line-height: 1.2 !important;
    }}

    h3 {{
        font-size: clamp(1.1rem, 5vw, 1.4rem) !important;
        line-height: 1.25 !important;
    }}
}}
</style>
"""


def render_responsive_page_styles() -> None:
    st.markdown(RESPONSIVE_PAGE_STYLE, unsafe_allow_html=True)
