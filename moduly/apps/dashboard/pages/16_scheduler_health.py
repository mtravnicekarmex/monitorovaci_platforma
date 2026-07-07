from __future__ import annotations

from datetime import datetime
import html
from pathlib import Path
import sys
import time

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    get_scheduler_health as api_get_scheduler_health,
    get_scheduler_log as api_get_scheduler_log,
    run_scheduler_job_once as api_run_scheduler_job_once,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access
from moduly.apps.dashboard.scheduler_health_view import (
    manual_run_confirmation_text,
    manual_run_impact_label,
    manual_run_requires_confirmation,
)
from moduly.apps.dashboard.scheduler_log_view import (
    extract_error_log_blocks,
    extract_manual_run_log_content,
    get_manual_run_completion_status,
)


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

MANUAL_RUN_STATE_KEY = "scheduler_manual_run_monitor"
MANUAL_RUN_LOG_LINES = 2000
MANUAL_RUN_POLL_SECONDS = 2.0

SCHEDULER_ERROR_LOG_STYLE = """
<style>
.scheduler-error-log {
    background: #7f1d1d;
    border: 1px solid #ef4444;
    border-radius: 8px;
    color: #fee2e2;
    font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
    font-size: 0.86rem;
    line-height: 1.45;
    max-height: 360px;
    overflow: auto;
    padding: 0.85rem 1rem;
    white-space: pre-wrap;
}
</style>
"""


def _require_access_token() -> str:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return access_token


@st.cache_data(ttl=30)
def load_scheduler_health(access_token: str) -> dict[str, object]:
    return api_get_scheduler_health(access_token)


@st.cache_data(ttl=5)
def load_scheduler_log(access_token: str, lines: int) -> dict[str, object]:
    return api_get_scheduler_log(access_token, lines=lines)


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


def _render_log_error_summary(
    content: str,
    *,
    heading: str,
    clean_message: str | None = None,
) -> bool:
    error_blocks = extract_error_log_blocks(content)
    if error_blocks:
        st.markdown(f"**{heading}**")
        st.markdown(SCHEDULER_ERROR_LOG_STYLE, unsafe_allow_html=True)
        error_log_html = html.escape("\n\n".join(error_blocks))
        st.markdown(
            f'<div class="scheduler-error-log">{error_log_html}</div>',
            unsafe_allow_html=True,
        )
        return True

    if clean_message:
        st.success(clean_message)
    return False


def _get_manual_run_state() -> dict[str, object] | None:
    state = st.session_state.get(MANUAL_RUN_STATE_KEY)
    return state if isinstance(state, dict) else None


def _manual_run_is_polling() -> bool:
    state = _get_manual_run_state()
    if not state:
        return False
    return (
        str(state.get("api_status") or "").lower() == "started"
        and not str(state.get("completion_status") or "").strip()
    )


def _store_manual_run_state(state: dict[str, object]) -> None:
    st.session_state[MANUAL_RUN_STATE_KEY] = state


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
                "dopad": manual_run_impact_label(row),
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


def _refresh_manual_run_log_state(
    access_token: str,
    state: dict[str, object],
) -> dict[str, object]:
    job_id = str(state.get("job_id") or "").strip()
    requested_at = _parse_datetime(state.get("requested_at"))

    payload = api_get_scheduler_log(
        access_token,
        lines=MANUAL_RUN_LOG_LINES,
        since=requested_at,
    )
    raw_content = str(payload.get("content") or "")
    if requested_at is None:
        content = raw_content
    else:
        content = extract_manual_run_log_content(
            raw_content,
            job_id=job_id,
            requested_at=requested_at,
        )

    refreshed_state = {
        **state,
        "log_content": content,
        "log_updated_at": payload.get("updated_at"),
        "log_lines_returned": payload.get("lines_returned"),
        "log_error": "",
        "last_poll_at": datetime.now().astimezone().isoformat(),
    }
    completion_status = get_manual_run_completion_status(content, job_id)
    if completion_status:
        refreshed_state["completion_status"] = completion_status
        refreshed_state["completed_at"] = datetime.now().astimezone().isoformat()
        load_scheduler_health.clear()

    _store_manual_run_state(refreshed_state)
    return refreshed_state


def _render_manual_run_monitor(access_token: str) -> None:
    state = _get_manual_run_state()
    if not state:
        return

    job_id = str(state.get("job_id") or "").strip()
    job_name = str(state.get("job_name") or job_id or "job")
    requested_at = _format_timestamp(state.get("requested_at"))
    api_status = str(state.get("api_status") or "").lower()
    completion_status = str(state.get("completion_status") or "").lower()

    with st.expander(f"Prubeh rucniho spusteni: {job_name}", expanded=True):
        close_col, status_col = st.columns([1.3, 4])
        with close_col:
            if st.button("Zavrit okno prubehu", key="scheduler_manual_run_close"):
                st.session_state.pop(MANUAL_RUN_STATE_KEY, None)
                st.rerun()
        with status_col:
            status_text = completion_status.upper() if completion_status else api_status.upper()
            st.caption(
                f"Job: `{job_id}` | pozadavek: {requested_at} | stav: {status_text or '-'}"
            )

        if api_status == "busy":
            st.warning(str(state.get("detail") or "Job uz prave bezi."))
            return

        if not completion_status:
            try:
                state = _refresh_manual_run_log_state(access_token, state)
                completion_status = str(state.get("completion_status") or "").lower()
            except DashboardApiError as exc:
                state = {
                    **state,
                    "log_error": str(exc),
                    "last_poll_at": datetime.now().astimezone().isoformat(),
                }
                _store_manual_run_state(state)
                st.error("Nepodarilo se nacist aktualni log rucniho spusteni.")
                st.exception(exc)

        content = str(state.get("log_content") or "")
        updated_at = _format_timestamp(state.get("log_updated_at"))
        last_poll_at = _format_timestamp(state.get("last_poll_at"))
        lines_returned = int(state.get("log_lines_returned") or 0)

        if completion_status == "success":
            st.success(f"{job_name}: rucni beh byl dokoncen.")
        elif completion_status == "error":
            st.error(f"{job_name}: rucni beh skoncil chybou.")
        elif completion_status == "skipped":
            st.warning(f"{job_name}: rucni beh byl preskocen.")
        else:
            st.info(f"{job_name}: rucni beh probiha.")

        if not content:
            st.caption(
                f"Posledni zmena logu: {updated_at} | posledni kontrola: {last_poll_at} | "
                f"nacteno radku: {lines_returned}"
            )
            st.info("Cekam na prvni zaznam rucniho behu v scheduler logu.")
        else:
            st.caption(
                f"Posledni zmena logu: {updated_at} | posledni kontrola: {last_poll_at} | "
                f"nacteno radku: {lines_returned}"
            )
            if completion_status == "success":
                _render_log_error_summary(
                    content,
                    heading="Chybove zaznamy v prubehu rucniho spusteni",
                    clean_message="Nejsou zadne ERROR zaznamy",
                )
            elif completion_status == "error":
                _render_log_error_summary(
                    content,
                    heading="Chybove zaznamy v prubehu rucniho spusteni",
                )
            else:
                has_errors = _render_log_error_summary(
                    content,
                    heading="Chybove zaznamy v prubehu rucniho spusteni",
                )
                if not has_errors:
                    st.info("V nactenem prubehu zatim nejsou zadne ERROR zaznamy.")

        st.text_area(
            "Obsah logu rucniho spusteni",
            value=content or "Cekam na prvni zaznam rucniho behu v scheduler logu.",
            height=420,
            disabled=True,
            label_visibility="collapsed",
            key=f"scheduler_manual_run_log_{job_id}_{state.get('requested_at')}",
        )
        if content:
            st.download_button(
                "Stahnout log rucniho spusteni",
                data=content,
                file_name=f"scheduler-manual-{job_id or 'job'}.log.txt",
                mime="text/plain",
            )

        if _manual_run_is_polling():
            time.sleep(MANUAL_RUN_POLL_SECONDS)
            st.rerun()


def _trigger_manual_job_run(access_token: str, row: dict[str, object]) -> None:
    job_id = str(row.get("id") or "").strip()
    if not job_id:
        raise DashboardApiError("Scheduler job nema validni identifikator.")

    result = api_run_scheduler_job_once(access_token, job_id)
    _store_manual_run_state(
        {
            "job_id": job_id,
            "job_name": _job_display_name(row),
            "api_status": result.get("status"),
            "completion_status": "",
            "detail": result.get("detail"),
            "requested_at": result.get("requested_at"),
            "log_content": "",
            "log_updated_at": None,
            "log_lines_returned": 0,
        }
    )
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
    _render_manual_run_monitor(access_token)

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
    manual_run_in_progress = _manual_run_is_polling()

    with st.form("scheduler_manual_run_form"):
        selected_job_id = st.selectbox(
            "Vyber job nebo vnitrni krok pro jednorazove spusteni",
            options=job_ids,
            format_func=lambda job_id: _job_display_name(jobs_by_id[job_id]),
        )
        selected_row = jobs_by_id[selected_job_id]
        requires_confirmation = manual_run_requires_confirmation(selected_row)
        confirmed_impact = True
        if requires_confirmation:
            st.warning(manual_run_confirmation_text(selected_row))
            confirmed_impact = st.checkbox(
                "Potvrzuji provozni dopad a chci tento cil spustit.",
                key=f"scheduler_manual_run_confirm_{selected_job_id}",
            )

        submit_run = st.form_submit_button(
            "Spustit jednou",
            width="stretch",
            disabled=manual_run_in_progress or (requires_confirmation and not confirmed_impact),
        )

        if submit_run:
            try:
                _trigger_manual_job_run(access_token, selected_row)
            except DashboardApiError as exc:
                st.error(f"Nepodarilo se spustit job `{selected_job_id}`.")
                st.exception(exc)


def _render_scheduler_log_section(access_token: str) -> None:
    st.subheader("Log scheduleru")
    st.caption("Aktualni vyrez ze souboru `core/scheduler/logs/scheduler.log`.")

    control_col, refresh_col = st.columns([4, 1])
    with control_col:
        selected_line_count = int(
            st.selectbox(
                "Pocet zobrazenych radku",
                options=[100, 300, 1000, 2000],
                index=1,
                key="scheduler_log_line_count",
            )
        )
    with refresh_col:
        st.write("")
        st.write("")
        if st.button("Obnovit log", width="stretch"):
            load_scheduler_log.clear()
            st.rerun()

    try:
        payload = load_scheduler_log(access_token, selected_line_count)
    except DashboardApiError as exc:
        st.error("Nepodarilo se nacist log scheduleru.")
        st.exception(exc)
        return

    log_path = str(payload.get("path") or "")
    exists = bool(payload.get("exists"))
    content = str(payload.get("content") or "")
    lines_returned = int(payload.get("lines_returned") or 0)
    updated_at = _format_timestamp(payload.get("updated_at"))

    if not exists:
        st.info(f"Soubor logu zatim neexistuje: `{log_path}`")
        return

    st.caption(
        f"Soubor: `{log_path}` | posledni zmena: {updated_at} | zobrazeno radku: {lines_returned}"
    )
    if not content:
        st.info("Log je zatim prazdny.")
        return

    _render_log_error_summary(
        content,
        heading="Chybove zaznamy v nactenem vyrezu",
        clean_message="V nactenem vyrezu logu nejsou zadne ERROR zaznamy.",
    )

    st.text_area(
        "Obsah logu",
        value=content,
        height=420,
        disabled=True,
        label_visibility="collapsed",
    )
    st.download_button(
        "Stahnout zobrazeny vyrez logu",
        data=content,
        file_name="scheduler.log.tail.txt",
        mime="text/plain",
    )


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

    _render_scheduler_log_section(access_token)

    _render_manual_run_section(access_token, manual_runnable_jobs)


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodarilo se nacist health scheduleru.")
    st.exception(exc)
