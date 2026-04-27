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
    run_scheduler_job_once as api_run_scheduler_job_once,
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


def _has_runtime_activity(row: dict[str, object]) -> bool:
    if _parse_datetime(row.get("last_run")) is not None:
        return True
    if _parse_datetime(row.get("next_run")) is not None:
        return True
    if row.get("avg_duration_24h") not in (None, ""):
        return True
    if str(row.get("last_status") or "unknown").lower() != "unknown":
        return True

    try:
        return float(row.get("failure_rate_24h") or 0) > 0
    except (TypeError, ValueError):
        return False


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


def _job_display_name(row: dict[str, object]) -> str:
    label = str(row.get("label") or "").strip()
    job_id = str(row.get("id") or "").strip()
    if label and label != job_id:
        return f"{label} ({job_id})"
    return job_id or label or "-"


def _build_manual_jobs_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    dataframe = pd.DataFrame(
        [
            {
                "typ": "job" if row.get("is_scheduled") else "vnitrni krok",
                "job": _job_display_name(row),
                "popis": str(row.get("description") or "-"),
                "stav": str(row.get("last_status") or "unknown"),
                "posledni_beh": _format_timestamp(row.get("last_run")),
                "dalsi_beh": _format_timestamp(row.get("next_run")),
            }
            for row in rows
        ]
    )
    return dataframe.sort_values(by=["typ", "job"], kind="stable")


def _show_manual_run_feedback() -> None:
    feedback = st.session_state.pop("scheduler_manual_run_feedback", None)
    if not isinstance(feedback, dict):
        return

    status = str(feedback.get("status") or "").lower()
    job_name = str(feedback.get("job_name") or feedback.get("job_id") or "job")
    detail = str(feedback.get("detail") or "")
    requested_at = _format_timestamp(feedback.get("requested_at"))
    message = f"{job_name}: {detail}"
    if requested_at != "-":
        message = f"{message} Cas pozadavku: {requested_at}."

    if status == "started":
        st.success(message)
    elif status == "busy":
        st.warning(message)
    else:
        st.info(message)


def _trigger_manual_job_run(access_token: str, row: dict[str, object]) -> None:
    job_id = str(row.get("id") or "").strip()
    if not job_id:
        raise DashboardApiError("Scheduler job nema validni identifikator.")

    result = api_run_scheduler_job_once(access_token, job_id)
    st.session_state["scheduler_manual_run_feedback"] = {
        "job_id": job_id,
        "job_name": _job_display_name(row),
        "status": result.get("status"),
        "detail": result.get("detail"),
        "requested_at": result.get("requested_at"),
    }
    load_scheduler_health.clear()
    st.rerun()


def _render_manual_run_section(access_token: str, rows: list[dict[str, object]]) -> None:
    st.subheader("Rucni spusteni jobu a kroku")
    st.caption(
        "Jednorazovy trigger scheduler jobu nebo vnitrniho kroku. Beh se spousti na pozadi a respektuje stejne locky jako scheduler."
    )
    _show_manual_run_feedback()

    if not rows:
        st.info("Nejsou k dispozici zadne scheduler joby ani vnitrni kroky pro rucni spusteni.")
        return

    runnable_rows = sorted(rows, key=lambda item: str(item.get("id") or ""))
    st.dataframe(
        _build_manual_jobs_dataframe(runnable_rows),
        width="stretch",
        hide_index=True,
    )

    jobs_by_id = {
        str(row.get("id") or "").strip(): row
        for row in runnable_rows
        if str(row.get("id") or "").strip()
    }
    job_ids = list(jobs_by_id)

    with st.form("scheduler_manual_run_form"):
        select_col, action_col = st.columns([4, 1.2])
        with select_col:
            selected_job_id = st.selectbox(
                "Vyber job nebo vnitrni krok pro jednorazove spusteni",
                options=job_ids,
                format_func=lambda job_id: _job_display_name(jobs_by_id[job_id]),
            )
        with action_col:
            st.write("")
            st.write("")
            submit_run = st.form_submit_button("Spustit jednou", width="stretch")

        if submit_run:
            selected_row = jobs_by_id[selected_job_id]
            try:
                _trigger_manual_job_run(access_token, selected_row)
            except DashboardApiError as exc:
                st.error(f"Nepodarilo se spustit job `{selected_job_id}`.")
                st.exception(exc)


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
    visible_rows = [row for row in jobs if bool(row.get("is_scheduled")) or _has_runtime_activity(row)]
    manual_runnable_jobs = [row for row in jobs if bool(row.get("is_manual_runnable"))]
    scheduled_jobs = [row for row in jobs if row.get("next_run")]
    internal_steps = [row for row in visible_rows if not row.get("next_run")]

    status_col, running_col, jobs_col, errors_col = st.columns(4)
    status_col.metric("Celkovy stav", STATUS_LABELS.get(status, status.upper()))
    running_col.metric("Scheduler bezi", "ANO" if scheduler_running else "NE")
    jobs_col.metric("Evidovane zaznamy", str(len(visible_rows)))
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

    _render_manual_run_section(access_token, manual_runnable_jobs)


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist health scheduleru.")
    st.exception(exc)
