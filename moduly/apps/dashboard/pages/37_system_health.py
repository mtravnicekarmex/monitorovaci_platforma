from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    get_system_database_health as api_get_system_database_health,
    get_system_proxy_health as api_get_system_proxy_health,
    get_system_runtime_health as api_get_system_runtime_health,
    get_system_scheduler_health as api_get_system_scheduler_health,
    get_system_smartfuelpass_health as api_get_system_smartfuelpass_health,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access


st.set_page_config(
    page_title="Health systému",
    page_icon="🖥️",
    layout="wide",
)


require_page_access("system_health")


SYSTEM_HEALTH_SECTIONS = (
    ("Proxy", "Caddy routing, veřejné odpovědi a bezpečnostní hlavičky."),
    ("Scheduler", "Heartbeat scheduleru, joby a aktuální runtime log."),
    ("Databáze", "PostgreSQL metadata a bezpečné agregované kontroly."),
    ("SmartFuelPass", "Databázový sync, reportovací období a bezpečné souhrny."),
)


SYSTEM_HEALTH_SECTIONS = tuple(
    item for item in SYSTEM_HEALTH_SECTIONS if item[0] not in {"Proxy", "Scheduler", "Databáze"}
)

SYSTEM_HEALTH_SECTIONS = tuple(
    item for item in SYSTEM_HEALTH_SECTIONS if item[0] != "SmartFuelPass"
)


STATUS_LABELS = {
    "ok": "OK",
    "degraded": "VAROVÁNÍ",
    "error": "CHYBA",
}


def _require_access_token() -> str:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybí bearer token pro dashboard API.")
    return access_token


@st.cache_data(ttl=30)
def load_system_runtime_health(access_token: str) -> dict[str, object]:
    return api_get_system_runtime_health(access_token)


@st.cache_data(ttl=30)
def load_system_proxy_health(access_token: str) -> dict[str, object]:
    return api_get_system_proxy_health(access_token)


@st.cache_data(ttl=30)
def load_system_scheduler_health(access_token: str) -> dict[str, object]:
    return api_get_system_scheduler_health(access_token)


@st.cache_data(ttl=30)
def load_system_database_health(access_token: str) -> dict[str, object]:
    return api_get_system_database_health(access_token)


@st.cache_data(ttl=30)
def load_system_smartfuelpass_health(access_token: str) -> dict[str, object]:
    return api_get_system_smartfuelpass_health(access_token)


def _parse_datetime(value: object) -> object:
    if value in (None, ""):
        return None
    if hasattr(value, "strftime"):
        return value
    if isinstance(value, str):
        try:
            from datetime import datetime

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


def _status_label(value: object) -> str:
    status = str(value or "error").lower()
    return STATUS_LABELS.get(status, status.upper())


def _format_seconds(value: object) -> str:
    if value in (None, ""):
        return "-"
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return str(value)
    if seconds < 60:
        return f"{seconds:.0f} s"
    return f"{seconds / 60:.1f} min"


def _format_milliseconds(value: object) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):.1f} ms"
    except (TypeError, ValueError):
        return str(value)


def _format_amount(value: object) -> str:
    if value in (None, ""):
        return "-"
    try:
        whole, fraction = f"{float(value):.2f}".split(".")
        return f"{int(whole):,}".replace(",", " ") + f",{fraction} Kc"
    except (TypeError, ValueError):
        return str(value)


def _format_bool(value: object) -> str:
    if value is True:
        return "ANO"
    if value is False:
        return "NE"
    return "-"


def _status_message(status: str) -> None:
    if status == "ok":
        st.success("Runtime startup check je v očekávaném stavu.")
    elif status == "degraded":
        st.warning("Runtime startup check má neúplná nebo nedostupná metadata.")
    else:
        st.error("Runtime startup check našel chybějící nebo nečekané listenery.")


def _listener_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "stav": _status_label(row.get("status")),
                "sluzba": str(row.get("label") or row.get("key") or "-"),
                "adresa": str(row.get("local_address") or "*"),
                "port": row.get("local_port"),
                "pritomno": "ANO" if bool(row.get("present")) else "NE",
                "procesy": ", ".join(str(pid) for pid in row.get("process_ids") or ()) or "-",
                "detail": str(row.get("detail") or "-"),
            }
            for row in rows
        ]
    )


def _proxy_routes_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "stav": _status_label(row.get("status")),
                "kontrola": str(row.get("label") or row.get("key") or "-"),
                "metoda": str(row.get("method") or "-"),
                "schema": str(row.get("scheme") or "-"),
                "cesta": str(row.get("path") or "-"),
                "ocekavano": row.get("expected_status_code"),
                "skutecne": row.get("actual_status_code") or "-",
                "content-type": str(row.get("actual_content_type") or "-"),
                "location": str(row.get("actual_location") or "-"),
                "detail": str(row.get("detail") or "-"),
            }
            for row in rows
        ]
    )


def _proxy_headers_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "stav": _status_label(row.get("status")),
                "hlavicka": str(row.get("header_name") or row.get("key") or "-"),
                "ocekavano": str(row.get("expected") or "-"),
                "pritomno": "ANO" if bool(row.get("present")) else "NE",
                "detail": str(row.get("detail") or "-"),
            }
            for row in rows
        ]
    )


def _scheduler_jobs_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "stav": _status_label(row.get("status")),
                "job": str(row.get("label") or row.get("job_id") or "-"),
                "job_id": str(row.get("job_id") or "-"),
                "posledni_stav": str(row.get("last_status") or "unknown"),
                "posledni_beh": _format_timestamp(row.get("last_run")),
                "dalsi_beh": _format_timestamp(row.get("next_run")),
                "uspechy_24h": int(row.get("success_count_24h") or 0),
                "chyby_24h": int(row.get("failure_count_24h") or 0),
                "detail": str(row.get("detail") or "-"),
            }
            for row in rows
        ]
    )


def _postgres_schema_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "stav": _status_label(row.get("status")),
                "schema": str(row.get("schema_name") or "-"),
                "pritomno": "ANO" if bool(row.get("present")) else "NE",
                "pocet_tabulek": row.get("table_count") if row.get("table_count") is not None else "-",
                "detail": str(row.get("detail") or "-"),
            }
            for row in rows
        ]
    )


def _smartfuelpass_period_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "obdobi": str(row.get("label") or row.get("key") or "-"),
                "start": _format_timestamp(row.get("start")),
                "konec": _format_timestamp(row.get("end")),
                "relace": int(row.get("session_count") or 0),
                "castka": _format_amount(row.get("total_amount")),
                "lokace": int(row.get("location_count") or 0),
                "konektory": int(row.get("connector_count") or 0),
                "prvni_relace": _format_timestamp(row.get("first_session_at")),
                "posledni_relace": _format_timestamp(row.get("last_session_at")),
            }
            for row in rows
        ]
    )


def _smartfuelpass_job_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "stav": _status_label(row.get("status")),
                "job": str(row.get("label") or row.get("job_id") or "-"),
                "job_id": str(row.get("job_id") or "-"),
                "posledni_stav": str(row.get("last_status") or "unknown"),
                "posledni_beh": _format_timestamp(row.get("last_run")),
                "uspechy_24h": int(row.get("success_count_24h") or 0),
                "chyby_24h": int(row.get("failure_count_24h") or 0),
                "trvani": _format_seconds(row.get("last_duration_seconds")),
                "detail": str(row.get("detail") or "-"),
            }
            for row in rows
        ]
    )


def _proxy_status_message(status: str) -> None:
    if status == "ok":
        st.success("Proxy a verejne routovani jsou v ocekavanem stavu.")
    elif status == "degraded":
        st.warning("Proxy check ma neuplna nebo nedostupna metadata.")
    else:
        st.error("Proxy check nasel neocekavanou verejnou odpoved nebo hlavicku.")


def _scheduler_status_message(status: str, scheduler_running: bool) -> None:
    if not scheduler_running:
        st.error("Scheduler neposila aktualni heartbeat.")
    elif status == "ok":
        st.success("Scheduler heartbeat a metriky jobu jsou v ocekavanem stavu.")
    elif status == "degraded":
        st.warning("Scheduler bezi, ale nektere metriky vyzaduji kontrolu.")
    else:
        st.error("Scheduler health check nasel chybovy stav.")


def _database_status_message(status: str) -> None:
    if status == "ok":
        st.success("PostgreSQL je dostupny a ocekavana schemata jsou pritomna.")
    elif status == "degraded":
        st.warning("PostgreSQL check ma neuplna metadata nebo varovani.")
    else:
        st.error("PostgreSQL check nasel nedostupnost, read-only stav nebo chybejici schema.")


def _smartfuelpass_status_message(status: str) -> None:
    if status == "ok":
        st.success("SmartFuelPass databazovy sync a souhrny jsou v ocekavanem stavu.")
    elif status == "degraded":
        st.warning("SmartFuelPass check ma varovani ve freshnosti syncu nebo metrikach.")
    else:
        st.error("SmartFuelPass check nasel chybu databazoveho syncu nebo scheduler metrik.")


def _render_runtime_load_error(exc: DashboardApiError) -> None:
    if exc.status_code == 404:
        st.warning("Runtime health endpoint zatím není dostupný v běžícím API.")
        st.caption(
            "Streamlit už načetl novou stránku z pracovního stromu, ale FastAPI proces běží se starší verzí "
            "bez endpointu `/health/system/runtime`. Po restartu nebo reloadu FastAPI se tento blok začne plnit daty."
        )
        return

    st.error("Nepodařilo se načíst runtime health.")
    st.exception(exc)


def _render_proxy_load_error(exc: DashboardApiError) -> None:
    if exc.status_code == 404:
        st.warning("Proxy health endpoint zatim neni dostupny v bezicim API.")
        st.caption("Po restartu nebo reloadu FastAPI se blok proxy kontrol zacne plnit daty.")
        return

    st.error("Nepodarilo se nacist proxy health.")
    st.exception(exc)


def _render_scheduler_load_error(exc: DashboardApiError) -> None:
    if exc.status_code == 404:
        st.warning("Scheduler system health endpoint zatim neni dostupny v bezicim API.")
        st.caption("Po restartu nebo reloadu FastAPI se blok scheduler kontrol zacne plnit daty.")
        return

    st.error("Nepodarilo se nacist scheduler system health.")
    st.exception(exc)


def _render_database_load_error(exc: DashboardApiError) -> None:
    if exc.status_code == 404:
        st.warning("Database system health endpoint zatim neni dostupny v bezicim API.")
        st.caption("Po restartu nebo reloadu FastAPI se blok PostgreSQL kontrol zacne plnit daty.")
        return

    st.error("Nepodarilo se nacist database system health.")
    st.exception(exc)


def _render_smartfuelpass_load_error(exc: DashboardApiError) -> None:
    if exc.status_code == 404:
        st.warning("SmartFuelPass system health endpoint zatim neni dostupny v bezicim API.")
        st.caption("Po restartu nebo reloadu FastAPI se blok SmartFuelPass kontrol zacne plnit daty.")
        return

    st.error("Nepodarilo se nacist SmartFuelPass system health.")
    st.exception(exc)


def _render_runtime_section(access_token: str) -> None:
    st.subheader("Runtime po restartu")
    st.caption(
        "Kontroluje boot time, startup task, očekávané listenery a absenci dočasných portů. "
        "Výstup je sanitizovaný a neobsahuje command line procesů."
    )

    refresh_col, _spacer = st.columns([1, 4])
    with refresh_col:
        if st.button("Obnovit runtime", width="stretch"):
            load_system_runtime_health.clear()
            st.rerun()

    try:
        payload = load_system_runtime_health(access_token)
    except DashboardApiError as exc:
        _render_runtime_load_error(exc)
        return

    status = str(payload.get("status") or "error").lower()
    boot = dict(payload.get("boot") or {})
    startup_task = dict(payload.get("startup_task") or {})
    expected_listeners = [dict(row) for row in list(payload.get("expected_listeners") or ())]
    temporary_listeners = [dict(row) for row in list(payload.get("temporary_listeners") or ())]

    missing_expected = sum(1 for row in expected_listeners if not bool(row.get("present")))
    present_temporary = sum(1 for row in temporary_listeners if bool(row.get("present")))

    status_col, boot_col, task_col, listener_col = st.columns(4)
    status_col.metric("Celkový stav", _status_label(status))
    boot_col.metric("Boot systému", _format_timestamp(boot.get("boot_time")))
    task_col.metric("Startup task", str(startup_task.get("last_task_result") if startup_task.get("last_task_result") is not None else "-"))
    listener_col.metric("Chybějící listenery", str(missing_expected + present_temporary))

    st.caption(f"Poslední kontrola API: {_format_timestamp(payload.get('checked_at'))}")
    _status_message(status)

    task_detail = str(startup_task.get("detail") or "-")
    task_last_run = _format_timestamp(startup_task.get("last_run_time"))
    task_name = str(startup_task.get("task_name") or "-")
    st.write(
        f"Startup task `{task_name}`: {_status_label(startup_task.get('status'))}; "
        f"poslední běh: {task_last_run}; detail: {task_detail}"
    )

    st.markdown("**Očekávané listenery**")
    expected_dataframe = _listener_dataframe(expected_listeners)
    if expected_dataframe.empty:
        st.info("Backend nevrátil žádné očekávané listenery.")
    else:
        st.dataframe(expected_dataframe, width="stretch", hide_index=True)

    st.markdown("**Dočasné porty**")
    temporary_dataframe = _listener_dataframe(temporary_listeners)
    if temporary_dataframe.empty:
        st.info("Backend nevrátil žádné dočasné porty ke kontrole.")
    else:
        st.dataframe(temporary_dataframe, width="stretch", hide_index=True)


def _render_proxy_section(access_token: str) -> None:
    st.subheader("Proxy a routovani")
    st.caption(
        "Kontroluje lokalni Caddy hostname routing, blokovani dokumentacnich cest, "
        "chranene API bez prihlaseni a verejne bezpecnostni hlavicky."
    )

    refresh_col, _spacer = st.columns([1, 4])
    with refresh_col:
        if st.button("Obnovit proxy", width="stretch"):
            load_system_proxy_health.clear()
            st.rerun()

    try:
        payload = load_system_proxy_health(access_token)
    except DashboardApiError as exc:
        _render_proxy_load_error(exc)
        return

    status = str(payload.get("status") or "error").lower()
    routes = [dict(row) for row in list(payload.get("routes") or ())]
    headers = [dict(row) for row in list(payload.get("headers") or ())]

    route_errors = sum(1 for row in routes if str(row.get("status") or "error").lower() != "ok")
    header_errors = sum(1 for row in headers if str(row.get("status") or "error").lower() != "ok")

    status_col, host_col, route_col, header_col = st.columns(4)
    status_col.metric("Celkovy stav", _status_label(status))
    host_col.metric("Public host", str(payload.get("public_host") or "-"))
    route_col.metric("Routy mimo OK", str(route_errors))
    header_col.metric("Hlavicky mimo OK", str(header_errors))

    st.caption(f"Posledni kontrola API: {_format_timestamp(payload.get('checked_at'))}")
    _proxy_status_message(status)

    st.markdown("**Verejne routy**")
    routes_dataframe = _proxy_routes_dataframe(routes)
    if routes_dataframe.empty:
        st.info("Backend nevratil zadne proxy routy ke kontrole.")
    else:
        st.dataframe(routes_dataframe, width="stretch", hide_index=True)

    st.markdown("**Bezpecnostni hlavicky**")
    headers_dataframe = _proxy_headers_dataframe(headers)
    if headers_dataframe.empty:
        st.info("Backend nevratil zadne hlavicky ke kontrole.")
    else:
        st.dataframe(headers_dataframe, width="stretch", hide_index=True)


def _render_scheduler_section(access_token: str) -> None:
    st.subheader("Scheduler")
    st.caption(
        "Kontroluje heartbeat scheduleru a souhrnne metriky planovanych jobu. "
        "Detailni logy a rucni spousteni zustavaji na strance Health scheduleru."
    )

    refresh_col, _spacer = st.columns([1, 4])
    with refresh_col:
        if st.button("Obnovit scheduler", width="stretch"):
            load_system_scheduler_health.clear()
            st.rerun()

    try:
        payload = load_system_scheduler_health(access_token)
    except DashboardApiError as exc:
        _render_scheduler_load_error(exc)
        return

    status = str(payload.get("status") or "error").lower()
    scheduler_running = bool(payload.get("scheduler_running"))
    jobs = [dict(row) for row in list(payload.get("jobs") or ())]
    job_errors = sum(1 for row in jobs if str(row.get("status") or "error").lower() != "ok")

    status_col, running_col, heartbeat_col, errors_col = st.columns(4)
    status_col.metric("Celkovy stav", _status_label(status))
    running_col.metric("Scheduler bezi", "ANO" if scheduler_running else "NE")
    heartbeat_col.metric("Stari heartbeatu", _format_seconds(payload.get("heartbeat_age_seconds")))
    errors_col.metric("Chyby 24h", str(payload.get("total_failure_count_24h") or 0))

    st.caption(
        f"Posledni kontrola API: {_format_timestamp(payload.get('checked_at'))} | "
        f"posledni heartbeat: {_format_timestamp(payload.get('last_heartbeat'))} | "
        f"TTL heartbeatu: {_format_seconds(payload.get('heartbeat_ttl_seconds'))} | "
        f"joby mimo OK: {job_errors}"
    )
    _scheduler_status_message(status, scheduler_running)

    jobs_dataframe = _scheduler_jobs_dataframe(jobs)
    if jobs_dataframe.empty:
        st.info("Backend nevratil zadne scheduler joby ke kontrole.")
    else:
        st.dataframe(jobs_dataframe, width="stretch", hide_index=True)


def _render_database_section(access_token: str) -> None:
    st.subheader("PostgreSQL")
    st.caption(
        "Kontroluje dostupnost PostgreSQL, jednoduchou metadata query, read-only stav "
        "a pritomnost ocekavanych schemat. Vystup neobsahuje DSN, host, uzivatele ani raw data."
    )

    refresh_col, _spacer = st.columns([1, 4])
    with refresh_col:
        if st.button("Obnovit PostgreSQL", width="stretch"):
            load_system_database_health.clear()
            st.rerun()

    try:
        payload = load_system_database_health(access_token)
    except DashboardApiError as exc:
        _render_database_load_error(exc)
        return

    status = str(payload.get("status") or "error").lower()
    postgres = dict(payload.get("postgres") or {})
    schemas = [dict(row) for row in list(payload.get("expected_schemas") or ())]
    missing_schemas = sum(1 for row in schemas if not bool(row.get("present")))

    status_col, connected_col, latency_col, read_only_col = st.columns(4)
    status_col.metric("Celkovy stav", _status_label(status))
    connected_col.metric("Pripojeni", "ANO" if bool(postgres.get("connected")) else "NE")
    latency_col.metric("Latence query", _format_milliseconds(postgres.get("latency_ms")))
    read_only_col.metric("Read-only", _format_bool(postgres.get("transaction_read_only")))

    st.caption(
        f"Posledni kontrola API: {_format_timestamp(payload.get('checked_at'))} | "
        f"server time: {_format_timestamp(postgres.get('server_time'))} | "
        f"timezone: {str(postgres.get('server_timezone') or '-')} | "
        f"server version: {str(postgres.get('server_version') or '-')} | "
        f"chybejici schemata: {missing_schemas}"
    )
    _database_status_message(status)
    st.write(str(postgres.get("detail") or "-"))

    schemas_dataframe = _postgres_schema_dataframe(schemas)
    if schemas_dataframe.empty:
        st.info("Backend nevratil zadna PostgreSQL schemata ke kontrole.")
    else:
        st.dataframe(schemas_dataframe, width="stretch", hide_index=True)


def _render_smartfuelpass_section(access_token: str) -> None:
    st.subheader("SmartFuelPass")
    st.caption(
        "Kontroluje databazovy sync relaci, scheduler metriky sync/report jobu "
        "a bezpecne agregovane souhrny reportovacich obdobi. Vystup neobsahuje raw relace ani portalova data."
    )

    refresh_col, _spacer = st.columns([1, 4])
    with refresh_col:
        if st.button("Obnovit SmartFuelPass", width="stretch"):
            load_system_smartfuelpass_health.clear()
            st.rerun()

    try:
        payload = load_system_smartfuelpass_health(access_token)
    except DashboardApiError as exc:
        _render_smartfuelpass_load_error(exc)
        return

    status = str(payload.get("status") or "error").lower()
    table = dict(payload.get("table") or {})
    sync_job = dict(payload.get("sync_job") or {})
    weekly_report_job = dict(payload.get("weekly_report_job") or {})
    periods = [dict(row) for row in list(payload.get("report_periods") or ())]

    status_col, rows_col, import_col, failures_col = st.columns(4)
    status_col.metric("Celkovy stav", _status_label(status))
    rows_col.metric("Relace v DB", str(table.get("total_session_count") or 0))
    import_col.metric("Posledni import", _format_timestamp(table.get("last_imported_at")))
    failures_col.metric(
        "Chyby jobu 24h",
        str((sync_job.get("failure_count_24h") or 0) + (weekly_report_job.get("failure_count_24h") or 0)),
    )

    st.caption(
        f"Posledni kontrola API: {_format_timestamp(payload.get('checked_at'))} | "
        f"zdroj: {str(payload.get('source') or '-')} | "
        f"basis obdobi: {str(payload.get('period_basis') or '-')} | "
        f"stari importu: {_format_seconds(table.get('last_import_age_seconds'))} | "
        f"missing UTC end: {int(table.get('missing_ended_at_utc_count') or 0)}"
    )
    _smartfuelpass_status_message(status)
    st.write(str(table.get("detail") or "-"))

    st.markdown("**Reportovaci obdobi a bezpecne souhrny**")
    periods_dataframe = _smartfuelpass_period_dataframe(periods)
    if periods_dataframe.empty:
        st.info("Backend nevratil zadne SmartFuelPass souhrny obdobi.")
    else:
        st.dataframe(periods_dataframe, width="stretch", hide_index=True)

    st.markdown("**Scheduler metriky SmartFuelPass**")
    jobs_dataframe = _smartfuelpass_job_dataframe([sync_job, weekly_report_job])
    if jobs_dataframe.empty:
        st.info("Backend nevratil zadne SmartFuelPass scheduler metriky.")
    else:
        st.dataframe(jobs_dataframe, width="stretch", hide_index=True)


def render_page() -> None:
    access_token = _require_access_token()

    st.title("Health systému")
    st.caption("Admin přehled porestartových kontrol provozních částí platformy.")

    _render_runtime_section(access_token)
    st.divider()
    _render_proxy_section(access_token)
    st.divider()
    _render_scheduler_section(access_token)
    st.divider()
    _render_database_section(access_token)
    st.divider()
    _render_smartfuelpass_section(access_token)

    if not SYSTEM_HEALTH_SECTIONS:
        return

    st.divider()
    st.subheader("Další plánované kontroly")
    st.info("Následující kontroly budou doplněny postupně po odsouhlasení datového zdroje a zobrazení.")
    columns = st.columns(2)
    for index, (title, description) in enumerate(SYSTEM_HEALTH_SECTIONS):
        with columns[index % 2]:
            with st.container(border=True):
                st.subheader(title)
                st.write(description)
                st.caption("Stav: připraveno k doplnění")


try:
    render_page()
except DashboardApiError as exc:
    st.error("Nepodařilo se načíst health systému.")
    st.exception(exc)
