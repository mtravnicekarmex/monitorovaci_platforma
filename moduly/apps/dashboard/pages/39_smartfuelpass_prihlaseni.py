from __future__ import annotations

from pathlib import Path
import sys
import time

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    get_smartfuelpass_interactive_import_status,
    get_system_smartfuelpass_health,
    start_smartfuelpass_interactive_import,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access
from moduly.apps.dashboard.smartfuelpass_interactive_view import (
    interactive_import_can_start,
    interactive_import_is_active,
    interactive_import_status_label,
)


st.set_page_config(
    page_title="Přihlášení SmartFuelPass",
    page_icon="🔑",
    layout="wide",
)
require_page_access("smartfuelpass_interactive_login")


def _token() -> str:
    token = get_auth_token()
    if not token:
        raise DashboardApiError("Chybí přihlášení k dashboard API.")
    return token


@st.cache_data(ttl=2)
def _load_status(access_token: str) -> dict[str, object]:
    return get_smartfuelpass_interactive_import_status(access_token)


@st.cache_data(ttl=30)
def _load_health(access_token: str) -> dict[str, object]:
    return get_system_smartfuelpass_health(access_token)


st.title("Přihlášení SmartFuelPass")
st.info(
    "Po spuštění se na produkční stanici otevře samostatné okno prohlížeče. "
    "Dokončete v něm Cloudflare kontrolu a přihlášení. Heslo ani cookies se "
    "neukládají do dashboardu."
)
st.warning(
    "Produkční stanice musí mít přihlášenou a odemčenou Windows relaci."
)

try:
    access_token = _token()
    current = _load_status(access_token)
    health = _load_health(access_token)
except DashboardApiError as exc:
    st.error(str(exc))
    st.stop()

left, middle, right = st.columns(3)
left.metric("Stav", interactive_import_status_label(current))
middle.metric(
    "Interaktivní task",
    "Připraven" if current.get("task_registered") else "Není zaregistrován",
)
right.metric(
    "Windows relace",
    "Dostupná" if current.get("interactive_user_available") else "Nedostupná",
)

if current.get("message"):
    st.caption(str(current["message"]))

if current.get("state") == "success":
    columns = st.columns(4)
    columns[0].metric("Načtené řádky", int(current.get("raw_row_count") or 0))
    columns[1].metric("Dokončené relace", int(current.get("completed_row_count") or 0))
    columns[2].metric("Neplatné řádky", int(current.get("invalid_row_count") or 0))
    columns[3].metric("Upsert", int(current.get("upserted_count") or 0))
elif current.get("state") == "error":
    st.error(
        "Import nebyl dokončen. Kategorie: "
        f"{current.get('error_category') or 'interactive_import_error'}."
    )

st.subheader("Databázový stav")
table = health.get("table") if isinstance(health.get("table"), dict) else {}
weekly = (
    health.get("weekly_report_job")
    if isinstance(health.get("weekly_report_job"), dict)
    else {}
)
database_columns = st.columns(3)
database_columns[0].metric("Relace v databázi", int(table.get("total_session_count") or 0))
database_columns[1].metric(
    "Chybějící UTC konec",
    int(table.get("missing_ended_at_utc_count") or 0),
)
database_columns[2].metric(
    "Týdenní report",
    "OK" if weekly.get("status") == "ok" else "Vyžaduje kontrolu",
)

confirm = st.checkbox(
    "Jsem přihlášen(a) na odemčené produkční stanici a chci otevřít "
    "interaktivní přihlášení.",
    disabled=not interactive_import_can_start(current),
)
if st.button(
    "Přihlásit",
    type="primary",
    disabled=not confirm or not interactive_import_can_start(current),
):
    try:
        start_smartfuelpass_interactive_import(access_token)
    except DashboardApiError as exc:
        st.error(str(exc))
    else:
        _load_status.clear()
        st.success("Interaktivní okno bylo vyžádáno na produkční stanici.")
        st.rerun()

if st.button("Obnovit stav"):
    _load_status.clear()
    st.rerun()

if interactive_import_is_active(current):
    time.sleep(2)
    _load_status.clear()
    st.rerun()
