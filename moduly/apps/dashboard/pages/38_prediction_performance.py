from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (  # noqa: E402
    DashboardApiError,
    get_prediction_performance as api_get_prediction_performance,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access  # noqa: E402


st.set_page_config(
    page_title="Predikce modelu",
    page_icon="M",
    layout="wide",
)


require_page_access("prediction_performance")


def _require_access_token() -> str:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return access_token


@st.cache_data(ttl=30)
def load_prediction_performance(access_token: str) -> dict[str, object]:
    return api_get_prediction_performance(access_token)


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _format_timestamp(value: object) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return "-"
    try:
        parsed = parsed.astimezone()
    except ValueError:
        pass
    return parsed.strftime("%d.%m.%Y %H:%M:%S")


def _format_date(value: object) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return "-"
    return parsed.strftime("%d.%m.%Y")


def _format_number(value: object, decimals: int = 3) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def _format_percent(value: object) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value) * 100:.1f} %"
    except (TypeError, ValueError):
        return str(value)


def _status_label(value: object) -> str:
    return str(value or "-").upper()


def _media_items(payload: dict[str, object]) -> list[dict[str, object]]:
    media = payload.get("media")
    if not isinstance(media, list):
        return []
    return [dict(item) for item in media if isinstance(item, dict)]


def _build_media_summary_dataframe(media: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in media:
        run = item.get("latest_selection_run")
        run = run if isinstance(run, dict) else {}
        snapshot = item.get("snapshot_summary")
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        rows.append(
            {
                "medium": str(item.get("medium_label") or item.get("medium_key") or "-"),
                "stav": _status_label(item.get("status")),
                "cadence": str(item.get("forecast_cadence") or "-"),
                "selection_run": run.get("selection_run_id") or "-",
                "run_created": _format_timestamp(run.get("created_at")),
                "global_model": run.get("selected_model_name") or "-",
                "kandidati": len(item.get("candidate_catalog") or []),
                "snapshot_mode": snapshot.get("selection_mode") or "-",
                "snapshot_period": _format_period(snapshot),
                "snapshoty": snapshot.get("snapshot_count") or 0,
                "fallbacky": snapshot.get("fallback_count") or 0,
                "jiny_nez_global": snapshot.get("selected_differs_from_global_count") or 0,
            }
        )
    return pd.DataFrame(rows)


def _format_period(snapshot: dict[str, object]) -> str:
    if not snapshot:
        return "-"
    label = snapshot.get("forecast_period_label")
    if label:
        return str(label)
    start = _format_date(snapshot.get("forecast_period_start"))
    end = _format_date(snapshot.get("forecast_period_end"))
    if start == "-" and end == "-":
        return "-"
    return f"{start} - {end}"


def _build_candidate_dataframe(media: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in media:
        medium_label = str(item.get("medium_label") or item.get("medium_key") or "-")
        for candidate in item.get("candidate_performance") or []:
            if not isinstance(candidate, dict):
                continue
            rows.append(
                {
                    "medium": medium_label,
                    "run": candidate.get("selection_run_id"),
                    "model": candidate.get("model_name"),
                    "key": candidate.get("model_key"),
                    "eligible": "ANO" if candidate.get("selection_enabled") else "NE",
                    "selected": "ANO" if candidate.get("selected") else "NE",
                    "coverage": _format_percent(candidate.get("coverage")),
                    "mae": _format_number(candidate.get("mae")),
                    "rmse": _format_number(candidate.get("rmse")),
                    "bias": _format_number(candidate.get("bias")),
                    "wape": _format_number(candidate.get("rolling_wape") or candidate.get("wape")),
                    "folds": candidate.get("rolling_backtest_fold_count") or 0,
                    "profiles": candidate.get("profile_count") or 0,
                }
            )
    return pd.DataFrame(rows)


def _build_identifier_dataframe(media: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in media:
        medium_label = str(item.get("medium_label") or item.get("medium_key") or "-")
        for selection in item.get("worst_identifier_selections") or []:
            if not isinstance(selection, dict):
                continue
            rows.append(
                {
                    "medium": medium_label,
                    "identifier": selection.get("identifier"),
                    "mode": selection.get("selection_mode"),
                    "period": _format_period(selection),
                    "selected_model": selection.get("selected_model_name"),
                    "global_model": selection.get("global_model_name"),
                    "fallback": "ANO" if selection.get("uses_fallback") else "NE",
                    "fallback_reason": selection.get("fallback_reason") or "-",
                    "coverage": _format_percent(selection.get("coverage")),
                    "mae": _format_number(selection.get("mae")),
                    "rmse": _format_number(selection.get("rmse")),
                    "bias": _format_number(selection.get("bias")),
                    "wape": _format_number(selection.get("wape")),
                }
            )
    return pd.DataFrame(rows)


def _build_catalog_dataframe(media: list[dict[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in media:
        medium_label = str(item.get("medium_label") or item.get("medium_key") or "-")
        for candidate in item.get("candidate_catalog") or []:
            if not isinstance(candidate, dict):
                continue
            rows.append(
                {
                    "medium": medium_label,
                    "cadence": candidate.get("forecast_cadence"),
                    "model": candidate.get("model_name"),
                    "key": candidate.get("model_key"),
                    "train_months": candidate.get("training_window_months"),
                    "validation_months": candidate.get("validation_window_months"),
                    "eligible": "ANO" if candidate.get("selection_enabled") else "NE",
                }
            )
    return pd.DataFrame(rows)


def _render_distribution_tables(media: list[dict[str, object]]) -> None:
    rows: list[dict[str, object]] = []
    fallback_rows: list[dict[str, object]] = []
    for item in media:
        medium_label = str(item.get("medium_label") or item.get("medium_key") or "-")
        snapshot = item.get("snapshot_summary")
        if not isinstance(snapshot, dict):
            continue
        for row in snapshot.get("model_distribution") or []:
            if isinstance(row, dict):
                rows.append(
                    {
                        "medium": medium_label,
                        "model": row.get("label"),
                        "count": row.get("count"),
                    }
                )
        for row in snapshot.get("fallback_distribution") or []:
            if isinstance(row, dict):
                fallback_rows.append(
                    {
                        "medium": medium_label,
                        "fallback_reason": row.get("label"),
                        "count": row.get("count"),
                    }
                )

    left, right = st.columns(2)
    with left:
        st.subheader("Distribuce modelu")
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            st.info("Zadne snapshoty.")
    with right:
        st.subheader("Fallbacky")
        if fallback_rows:
            st.dataframe(pd.DataFrame(fallback_rows), hide_index=True, use_container_width=True)
        else:
            st.info("Zadne fallbacky.")


def _render_page() -> None:
    st.title("Predikce modelu")

    try:
        payload = load_prediction_performance(_require_access_token())
    except DashboardApiError as exc:
        st.error(str(exc))
        return

    media = _media_items(payload)
    candidate_df = _build_candidate_dataframe(media)
    identifier_df = _build_identifier_dataframe(media)
    snapshot_count = sum(
        int((item.get("snapshot_summary") or {}).get("snapshot_count") or 0)
        for item in media
        if isinstance(item.get("snapshot_summary"), dict)
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Stav", _status_label(payload.get("status")))
    col2.metric("Media", len(media))
    col3.metric("Kandidati", sum(len(item.get("candidate_catalog") or []) for item in media))
    col4.metric("Snapshoty", snapshot_count)

    tab_summary, tab_candidates, tab_identifiers, tab_catalog = st.tabs(
        ["Souhrn", "Kandidati", "Vybery zarizeni", "Katalog"]
    )

    with tab_summary:
        summary_df = _build_media_summary_dataframe(media)
        if summary_df.empty:
            st.info("Zadna data.")
        else:
            st.dataframe(summary_df, hide_index=True, use_container_width=True)
        _render_distribution_tables(media)

    with tab_candidates:
        if candidate_df.empty:
            st.info("Zadne ulozene candidate runy.")
        else:
            st.dataframe(candidate_df, hide_index=True, use_container_width=True)

    with tab_identifiers:
        if identifier_df.empty:
            st.info("Zadne per-identifier snapshoty.")
        else:
            st.dataframe(identifier_df, hide_index=True, use_container_width=True)

    with tab_catalog:
        catalog_df = _build_catalog_dataframe(media)
        if catalog_df.empty:
            st.info("Zadny katalog kandidatu.")
        else:
            st.dataframe(catalog_df, hide_index=True, use_container_width=True)


_render_page()
