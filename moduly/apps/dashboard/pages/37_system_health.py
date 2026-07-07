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
    get_system_proxy_health as api_get_system_proxy_health,
    get_system_runtime_health as api_get_system_runtime_health,
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
    item for item in SYSTEM_HEALTH_SECTIONS if item[0] != "Proxy"
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


def _proxy_status_message(status: str) -> None:
    if status == "ok":
        st.success("Proxy a verejne routovani jsou v ocekavanem stavu.")
    elif status == "degraded":
        st.warning("Proxy check ma neuplna nebo nedostupna metadata.")
    else:
        st.error("Proxy check nasel neocekavanou verejnou odpoved nebo hlavicku.")


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


def render_page() -> None:
    access_token = _require_access_token()

    st.title("Health systému")
    st.caption("Admin přehled porestartových kontrol provozních částí platformy.")

    _render_runtime_section(access_token)
    st.divider()
    _render_proxy_section(access_token)

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
