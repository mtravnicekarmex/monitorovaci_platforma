from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import DashboardApiError
from moduly.apps.dashboard.auth import get_auth_token, require_page_access
from moduly.apps.dashboard.outlier_review_shared import (
    DETECTION_KIND_LABELS,
    OUTLIER_REVIEW_MODULE_OPTIONS,
    OUTLIER_REVIEW_MODULES,
    OUTLIER_REVIEW_MODULE_LABELS,
    SOURCE_ALL_OPTION,
    STATUS_LABELS,
    STATUS_OPTIONS,
    STATUS_SAVE_OPTIONS,
    build_outlier_review_device_options,
    format_outlier_review_device_option,
    format_outlier_review_number,
    format_outlier_review_timestamp,
    get_outlier_review_module_config,
    get_outlier_review_source_label,
    get_outlier_review_source_options,
    get_outlier_review_warnings,
    get_selected_outlier_review_module_keys,
    merge_outlier_review_rows,
    normalize_outlier_review_row,
    resolve_outlier_review_source_filter,
)


st.set_page_config(
    page_title="Review outlieru",
    page_icon="🔎",
    layout="wide",
)


require_page_access("outlier_review")


@st.cache_data(ttl=60)
def load_module_device_options(module_key: str) -> list[str]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    config = get_outlier_review_module_config(module_key)
    return config.load_device_options(access_token)


@st.cache_data(ttl=30)
def load_module_reviews(
    module_key: str,
    review_status: str | None,
    identifikace: str | None,
    source_filter: str,
    limit: int,
) -> list[dict[str, object]]:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    config = get_outlier_review_module_config(module_key)
    return config.list_reviews(
        access_token,
        review_status=review_status,
        identifikace=identifikace,
        source_filter=source_filter,
        limit=limit,
    )


def load_all_device_options() -> list[tuple[str, str]]:
    return build_outlier_review_device_options(
        {config.key: load_module_device_options(config.key) for config in OUTLIER_REVIEW_MODULES}
    )


def load_combined_reviews(
    *,
    selected_module: str,
    selected_status: str,
    selected_source: str,
    selected_device: tuple[str, str],
    limit: int,
) -> tuple[list[dict[str, object]], tuple[str, ...]]:
    selected_device_module = selected_device[0] or None
    selected_identifikace = selected_device[1] or None
    selected_module_keys = get_selected_outlier_review_module_keys(selected_module, selected_device_module)
    resolved_status = None if selected_status == "ALL" else selected_status

    combined_rows: list[dict[str, object]] = []
    loaded_module_keys: list[str] = []
    for module_key in selected_module_keys:
        source_filter = resolve_outlier_review_source_filter(selected_source, module_key)
        if source_filter is None:
            continue
        loaded_module_keys.append(module_key)
        module_rows = load_module_reviews(
            module_key,
            resolved_status,
            selected_identifikace if selected_device_module == module_key else None,
            source_filter,
            limit,
        )
        combined_rows.extend(normalize_outlier_review_row(module_key, row) for row in module_rows)

    return merge_outlier_review_rows(combined_rows, limit=limit), tuple(loaded_module_keys)


def render_page() -> None:
    st.title("Review outlieru")
    st.caption(
        "Spolecna admin auditni fronta pro rucni rozhodnuti, zda invalidni skok byl skutecny outlier nebo legitimni odber."
    )
    st.info("Stranka je pripravena jako spolecny prehled pro vice modulu. Zatim nacita vodomery a plynomery.")

    device_options = load_all_device_options()
    source_options = get_outlier_review_source_options()

    filter_col, stats_col = st.columns([2, 3])
    with filter_col:
        with st.form("outlier_review_filters"):
            selected_module = st.selectbox(
                "Modul",
                options=list(OUTLIER_REVIEW_MODULE_OPTIONS),
                format_func=lambda value: OUTLIER_REVIEW_MODULE_LABELS.get(value, value),
            )
            selected_status = st.selectbox(
                "Stav review",
                options=list(STATUS_OPTIONS),
                index=1,
                format_func=lambda value: STATUS_LABELS.get(value, value),
            )
            selected_source = st.selectbox(
                "Zdroj",
                options=list(source_options),
                format_func=get_outlier_review_source_label,
            )
            selected_device = st.selectbox(
                "Zarizeni",
                options=device_options,
                format_func=format_outlier_review_device_option,
            )
            limit = int(st.number_input("Max. pocet zaznamu", min_value=10, max_value=1000, value=200, step=10))
            submitted = st.form_submit_button("Nacist zaznamy")

        if submitted:
            load_module_reviews.clear()

    reviews, active_module_keys = load_combined_reviews(
        selected_module=selected_module,
        selected_status=selected_status,
        selected_source=selected_source,
        selected_device=selected_device,
        limit=limit,
    )

    for warning_message in get_outlier_review_warnings(active_module_keys):
        st.warning(warning_message)

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
                        "datum": format_outlier_review_timestamp(row["date"]),
                        "modul": row["module_label"],
                        "identifikace": row["identifikace"],
                        "zdroj": row["zdroj"],
                        "delta": format_outlier_review_number(row["candidate_delta"]),
                        "threshold": format_outlier_review_number(row["threshold_delta"]),
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
        if selected_source != SOURCE_ALL_OPTION and not active_module_keys:
            st.info("Vybrany zdroj zatim neni podporovan pro zadany modul.")
        else:
            st.info("Pro zadany filtr nebyly nalezeny zadne outlier review zaznamy.")
        return

    for row in reviews:
        review_id = int(row["id"])
        module_key = str(row["module_key"])
        config = get_outlier_review_module_config(module_key)
        current_status = str(row["review_status"])
        resolved_status = current_status if current_status in STATUS_SAVE_OPTIONS else STATUS_SAVE_OPTIONS[0]
        expander_title = (
            f"{row['module_label']} | {format_outlier_review_timestamp(row['date'])} | "
            f"{row['identifikace']} | {STATUS_LABELS.get(current_status, current_status)}"
        )

        with st.expander(expander_title, expanded=current_status == "PENDING"):
            detail_col, stats_detail_col = st.columns(2)

            with detail_col:
                st.markdown(
                    "  \n".join(
                        [
                            f"**Modul:** {row['module_label']}",
                            f"**Zdroj:** {row['zdroj']}",
                            f"**Detekce:** {DETECTION_KIND_LABELS.get(str(row['detection_kind']), str(row['detection_kind']))}",
                            f"**Seriove cislo:** {row.get('seriove_cislo') or '-'}",
                            f"**Interval [min]:** {row.get('interval_minutes') or '-'}",
                            f"**Objem na radku:** {format_outlier_review_number(row['current_objem'])}",
                            f"**Predchozi baseline objem:** {format_outlier_review_number(row['baseline_objem'])}",
                            f"**Predchozi baseline datum:** {format_outlier_review_timestamp(row['baseline_date'])}",
                            f"**Kandidat delta:** {format_outlier_review_number(row['candidate_delta'])}",
                            f"**Threshold:** {format_outlier_review_number(row['threshold_delta'])}",
                        ]
                    )
                )

            with stats_detail_col:
                st.markdown(
                    "  \n".join(
                        [
                            f"**Sample size:** {row['sample_size'] or '-'}",
                            f"**Median delta:** {format_outlier_review_number(row['median_delta'])}",
                            f"**P90 delta:** {format_outlier_review_number(row['p90_delta'])}",
                            f"**P99 delta:** {format_outlier_review_number(row['p99_delta'])}",
                            f"**Std delta:** {format_outlier_review_number(row['std_delta'])}",
                            f"**Vytvoreno:** {format_outlier_review_timestamp(row['created_at'])}",
                            f"**Naposledy review:** {format_outlier_review_timestamp(row['reviewed_at'])}",
                        ]
                    )
                )

            with st.form(f"outlier_review_form_{module_key}_{review_id}"):
                selected_review_status = st.selectbox(
                    "Verdikt",
                    options=list(STATUS_SAVE_OPTIONS),
                    index=list(STATUS_SAVE_OPTIONS).index(resolved_status),
                    format_func=lambda value: STATUS_LABELS.get(value, value),
                    key=f"outlier_review_status_{module_key}_{review_id}",
                )
                review_note = st.text_area(
                    "Poznamka",
                    value=str(row["review_note"] or ""),
                    placeholder="Napriklad servisni zasah, test odberu nebo potvrzeny datovy glitch.",
                    key=f"outlier_review_note_{module_key}_{review_id}",
                )
                save_pressed = st.form_submit_button("Ulozit review")

            if save_pressed:
                config.update_review(
                    get_auth_token(),
                    review_id,
                    {
                        "review_status": selected_review_status,
                        "review_note": review_note.strip() or None,
                    },
                )
                st.success(f"Review pro modul {row['module_label']} bylo ulozeno.")
                st.cache_data.clear()
                st.rerun()


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist review outlieru.")
    st.exception(exc)
