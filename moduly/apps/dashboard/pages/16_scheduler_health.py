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
    get_scheduler_health as api_get_scheduler_health,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access


st.set_page_config(
    page_title="Health scheduleru",
    page_icon="🩺",
    layout="wide",
)


require_page_access("scheduler_health")


STATUS_LABELS = {
    "ok": "OK",
    "degraded": "DEGRADED",
    "error": "ERROR",
}


def _require_access_token() -> str:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return access_token


@st.cache_data(ttl=30)
def load_scheduler_health(access_token: str) -> dict[str, object]:
    return api_get_scheduler_health(access_token)


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


def _format_duration(value: object) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.2f} s"
    except (TypeError, ValueError):
        return str(value)


def _format_failure_rate(value: object) -> str:
    try:
        return f"{float(value) * 100:.1f} %"
    except (TypeError, ValueError):
        return "-"


def _build_jobs_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    dataframe = pd.DataFrame(
        [
            {
                "job": str(row.get("id") or "-"),
                "stav": str(row.get("last_status") or "unknown"),
                "posledni_beh": _format_timestamp(row.get("last_run")),
                "doba_posledniho_behu": _format_duration(row.get("last_duration_seconds")),
                "dalsi_beh": _format_timestamp(row.get("next_run")),
                "chybovost_24h": _format_failure_rate(row.get("failure_rate_24h")),
                "prumerna_doba_24h": _format_duration(row.get("avg_duration_24h")),
            }
            for row in rows
        ]
    )
    return dataframe.sort_values(by=["job"], kind="stable")


def _build_schedule_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    prepared_rows: list[dict[str, object]] = []
    for row in rows:
        scheduled_at = _parse_datetime(row.get("scheduled_at"))
        prepared_rows.append(
            {
                "_sort_ts": scheduled_at.timestamp() if scheduled_at is not None else float("inf"),
                "cas": _format_timestamp(row.get("scheduled_at")),
                "job": str(row.get("job_label") or row.get("job_id") or "-"),
                "job_id": str(row.get("job_id") or "-"),
                "popis": str(row.get("description") or "-"),
            }
        )

    dataframe = pd.DataFrame(prepared_rows)
    dataframe = dataframe.sort_values(by=["_sort_ts", "job_id"], kind="stable")
    return dataframe.drop(columns=["_sort_ts"])


def render_page() -> None:
    access_token = _require_access_token()

    header_col, action_col = st.columns([5, 1])
    with header_col:
        st.title("Health scheduleru")
        st.caption("Admin report nad behy scheduleru a jeho vnitrnimi kroky.")
    with action_col:
        st.write("")
        st.write("")
        if st.button("Obnovit", width="stretch"):
            load_scheduler_health.clear()
            st.rerun()

    payload = load_scheduler_health(access_token)
    jobs = [dict(row) for row in list(payload.get("jobs") or ())]
    schedule = [dict(row) for row in list(payload.get("schedule") or ())]
    status = str(payload.get("status") or "error")
    scheduler_running = bool(payload.get("scheduler_running"))
    checked_at = payload.get("checked_at")

    error_jobs = [
        row for row in jobs if str(row.get("last_status") or "").lower().startswith("error")
    ]
    skipped_jobs = [
        row for row in jobs if str(row.get("last_status") or "").lower().startswith("skipped")
    ]
    scheduled_jobs = [row for row in jobs if row.get("next_run")]
    internal_steps = [row for row in jobs if not row.get("next_run")]

    status_col, running_col, jobs_col, errors_col = st.columns(4)
    status_col.metric("Celkovy stav", STATUS_LABELS.get(status, status.upper()))
    running_col.metric("Scheduler bezi", "ANO" if scheduler_running else "NE")
    jobs_col.metric("Evidovane zaznamy", str(len(jobs)))
    errors_col.metric("Chybove zaznamy", str(len(error_jobs)))

    st.caption(f"Posledni kontrola API: {_format_timestamp(checked_at)}")

    if not scheduler_running:
        st.error("Scheduler neposila aktualni heartbeat. Report muze byt zastaraly.")
    elif error_jobs:
        st.warning("Nektere joby skoncily chybou. Zkontroluj detailni tabulky niz.")
    elif skipped_jobs:
        st.info("Report obsahuje preskocene joby. Typicky jde o lock nebo max_instances.")
    else:
        st.success("Scheduler hlasi zdravy stav bez aktualnich chyb.")

    st.subheader("Naplanovane joby")
    if scheduled_jobs:
        st.dataframe(
            _build_jobs_dataframe(scheduled_jobs),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Scheduler zatim neposkytl zadne planovane joby s dalsim terminem behu.")

    st.subheader("Vnitrni kroky scheduleru")
    if internal_steps:
        st.dataframe(
            _build_jobs_dataframe(internal_steps),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Zatim nejsou evidovane zadne vnitrni kroky z safe_call metrik.")

    st.subheader("Schedule")
    st.caption("Jizdni rad jobu na nasledujicich 24 hodin.")
    if schedule:
        st.dataframe(
            _build_schedule_dataframe(schedule),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("Pro nasledujicich 24 hodin nebyly vypocteny zadne behy.")


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist health scheduleru.")
    st.exception(exc)
