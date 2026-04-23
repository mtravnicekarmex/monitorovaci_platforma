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
    get_plynomery_devices,
    list_plynomery_outlier_reviews,
    update_plynomery_outlier_review,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access


st.set_page_config(
    page_title="Review outlieru plynomeru",
    page_icon="🔎",
    layout="wide",
)


require_page_access("plynomery_outlier_review")


STATUS_OPTIONS = ("ALL", "PENDING", "CONFIRMED_OUTLIER", "CONFIRMED_CONSUMPTION")
STATUS_LABELS = {
    "ALL": "Vse",
    "PENDING": "Ceka na review",
    "CONFIRMED_OUTLIER": "Potvrzeny outlier",
    "CONFIRMED_CONSUMPTION": "Potvrzeny odber",
}
SOURCE_OPTIONS = ("VSE", "AREAL")
SOURCE_LABELS = {
    "VSE": "Vsechny zdroje",
    "AREAL": "AREAL",
}
DETECTION_KIND_LABELS = {
    "NORMAL_DELTA": "Standardni interval",
    "GAP_MEAN": "Prumer z gap-fill intervalu",
}


@st.cache_data(ttl=60)
def load_device_options() -> list[str]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return get_plynomery_devices(access_token, limit=5000)


@st.cache_data(ttl=30)
def load_reviews(
    review_status: str | None,
    identifikace: str | None,
    source_filter: str,
    limit: int,
) -> list[dict[str, object]]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return list_plynomery_outlier_reviews(
        access_token,
        review_status=review_status,
        identifikace=identifikace,
        source_filter=source_filter,
        limit=limit,
    )


def format_timestamp(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return str(value)


def format_number(value: object, decimals: int = 3) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.{decimals}f}".replace(",", " ").replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def render_page() -> None:
    st.title("Review outlieru plynomeru")
    st.caption("Admin auditni fronta pro rucni rozhodnuti, zda invalidni skok byl skutecny outlier nebo legitimni odber.")

    device_options = load_device_options()

    filter_col, stats_col = st.columns([2, 3])
    with filter_col:
        with st.form("plynomery_outlier_review_filters"):
            selected_status = st.selectbox(
                "Stav review",
                options=list(STATUS_OPTIONS),
                index=1,
                format_func=lambda value: STATUS_LABELS.get(value, value),
            )
            selected_source = st.selectbox(
                "Zdroj",
                options=list(SOURCE_OPTIONS),
                format_func=lambda value: SOURCE_LABELS.get(value, value),
            )
            selected_ident = st.selectbox(
                "Zarizeni",
                options=[""] + device_options,
                format_func=lambda value: "Vsechna zarizeni" if value == "" else value,
            )
            limit = int(st.number_input("Max. pocet zaznamu", min_value=10, max_value=1000, value=200, step=10))
            submitted = st.form_submit_button("Nacist zaznamy")

        if submitted:
            load_reviews.clear()

    resolved_status = None if selected_status == "ALL" else selected_status
    resolved_ident = selected_ident or None
    reviews = load_reviews(resolved_status, resolved_ident, selected_source, limit)

    with stats_col:
        st.subheader("Souhrn")
        total_count = len(reviews)
        pending_count = sum(1 for row in reviews if row["review_status"] == "PENDING")
        confirmed_outlier_count = sum(1 for row in reviews if row["review_status"] == "CONFIRMED_OUTLIER")
        confirmed_consumption_count = sum(1 for row in reviews if row["review_status"] == "CONFIRMED_CONSUMPTION")
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        metric_col1.metric("Zobrazeno", total_count)
        metric_col2.metric("Ceka", pending_count)
        metric_col3.metric("Outlier", confirmed_outlier_count)
        metric_col4.metric("Odber", confirmed_consumption_count)

        if reviews:
            overview_df = pd.DataFrame(
                [
                    {
                        "datum": format_timestamp(row["date"]),
                        "identifikace": row["identifikace"],
                        "zdroj": row["zdroj"],
                        "delta": format_number(row["candidate_delta"]),
                        "threshold": format_number(row["threshold_delta"]),
                        "detekce": DETECTION_KIND_LABELS.get(str(row["detection_kind"]), str(row["detection_kind"])),
                        "stav": STATUS_LABELS.get(str(row["review_status"]), str(row["review_status"])),
                        "reviewer": row["reviewed_by"] or "-",
                    }
                    for row in reviews
                ]
            )
            st.dataframe(overview_df, width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader("Detailni review")

    if not reviews:
        st.info("Pro zadany filtr nebyly nalezeny zadne outlier review zaznamy.")
        return

    for row in reviews:
        review_id = int(row["id"])
        expander_title = (
            f"{format_timestamp(row['date'])} | {row['identifikace']} | "
            f"{STATUS_LABELS.get(str(row['review_status']), str(row['review_status']))}"
        )
        with st.expander(expander_title, expanded=row["review_status"] == "PENDING"):
            detail_col, stats_detail_col = st.columns(2)

            with detail_col:
                st.markdown(
                    "  \n".join(
                        [
                            f"**Zdroj:** {row['zdroj']}",
                            f"**Detekce:** {DETECTION_KIND_LABELS.get(str(row['detection_kind']), str(row['detection_kind']))}",
                            f"**Objem na radku:** {format_number(row['current_objem'])}",
                            f"**Predchozi baseline objem:** {format_number(row['baseline_objem'])}",
                            f"**Predchozi baseline datum:** {format_timestamp(row['baseline_date'])}",
                            f"**Kandidat delta:** {format_number(row['candidate_delta'])}",
                            f"**Threshold:** {format_number(row['threshold_delta'])}",
                        ]
                    )
                )

            with stats_detail_col:
                st.markdown(
                    "  \n".join(
                        [
                            f"**Sample size:** {row['sample_size'] or '-'}",
                            f"**Median delta:** {format_number(row['median_delta'])}",
                            f"**P90 delta:** {format_number(row['p90_delta'])}",
                            f"**P99 delta:** {format_number(row['p99_delta'])}",
                            f"**Std delta:** {format_number(row['std_delta'])}",
                            f"**Vytvoreno:** {format_timestamp(row['created_at'])}",
                            f"**Naposledy review:** {format_timestamp(row['reviewed_at'])}",
                        ]
                    )
                )

            with st.form(f"plynomery_outlier_review_form_{review_id}"):
                selected_review_status = st.selectbox(
                    "Verdikt",
                    options=["PENDING", "CONFIRMED_OUTLIER", "CONFIRMED_CONSUMPTION"],
                    index=["PENDING", "CONFIRMED_OUTLIER", "CONFIRMED_CONSUMPTION"].index(str(row["review_status"])),
                    format_func=lambda value: STATUS_LABELS.get(value, value),
                    key=f"plynomery_status_{review_id}",
                )
                review_note = st.text_area(
                    "Poznamka",
                    value=str(row["review_note"] or ""),
                    placeholder="Napriklad servisni zasah, test odberu nebo potvrzeny datovy glitch.",
                    key=f"plynomery_note_{review_id}",
                )
                save_pressed = st.form_submit_button("Ulozit review")

            if save_pressed:
                update_plynomery_outlier_review(
                    get_auth_token(),
                    review_id,
                    {
                        "review_status": selected_review_status,
                        "review_note": review_note.strip() or None,
                    },
                )
                st.success("Review bylo ulozeno.")
                st.cache_data.clear()
                st.rerun()


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist review outlieru plynomeru.")
    st.exception(exc)
