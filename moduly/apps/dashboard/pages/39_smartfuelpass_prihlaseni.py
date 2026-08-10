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
    get_system_smartfuelpass_health,
    import_smartfuelpass_excel_records,
    preview_smartfuelpass_excel_import,
)
from moduly.apps.dashboard.auth import get_auth_token, require_page_access


st.set_page_config(
    page_title="Import",
    page_icon="📥",
    layout="wide",
)
require_page_access("smartfuelpass_interactive_login")


def _token() -> str:
    token = get_auth_token()
    if not token:
        raise DashboardApiError("Chybí přihlášení k dashboard API.")
    return token


@st.cache_data(ttl=30)
def _load_health(access_token: str) -> dict[str, object]:
    return get_system_smartfuelpass_health(access_token)


def _preview_dataframe(rows: list[dict[str, object]]) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for row in rows:
        records.append(
            {
                "Řádek": row.get("source_row_number"),
                "Stav importu": row.get("status_label"),
                "ID relace": row.get("id_relace"),
                "Stav v XLSX": row.get("raw_status"),
                "Začátek": row.get("started_at"),
                "Konec": row.get("ended_at"),
                "Lokace": row.get("lokace"),
                "Konektor": row.get("connector_id"),
                "kWh": row.get("kwh"),
                "Suma": row.get("suma"),
                "Tarif": row.get("tarif"),
                "Poznámka": row.get("note"),
            }
        )
    return pd.DataFrame.from_records(records)


def _render_database_state(health: dict[str, object]) -> None:
    st.subheader("Databázový stav")
    table = health.get("table") if isinstance(health.get("table"), dict) else {}
    weekly = (
        health.get("weekly_report_job")
        if isinstance(health.get("weekly_report_job"), dict)
        else {}
    )
    database_columns = st.columns(3)
    database_columns[0].metric(
        "Relace v databázi",
        int(table.get("total_session_count") or 0),
    )
    database_columns[1].metric(
        "Chybějící UTC konec",
        int(table.get("missing_ended_at_utc_count") or 0),
    )
    database_columns[2].metric(
        "Týdenní report",
        "OK" if weekly.get("status") == "ok" else "Vyžaduje kontrolu",
    )


st.title("Import")
st.caption(
    "SmartFuelPass relace se nově plní ručně z exportu ChargingSessions (.xlsx). "
    "Preview databázi nemění; tlačítko importuje pouze nové dokončené relace. "
    "Relace, které už v databázi existují, se jen označí a nikdy se nepřepisují."
)

try:
    access_token = _token()
    health = _load_health(access_token)
except DashboardApiError as exc:
    st.error(str(exc))
    st.stop()

_render_database_state(health)

uploaded_file = st.file_uploader(
    "Vyberte XLSX soubor",
    type=["xlsx"],
    accept_multiple_files=False,
)

if uploaded_file is None:
    st.info("Nahrajte export ChargingSessions ve formátu .xlsx.")
    st.stop()

file_bytes = uploaded_file.getvalue()
filename = uploaded_file.name

try:
    with st.spinner("Načítám a porovnávám XLSX s databází…"):
        preview = preview_smartfuelpass_excel_import(
            access_token,
            filename=filename,
            content=file_bytes,
        )
except DashboardApiError as exc:
    st.error(str(exc))
    st.stop()

st.subheader("Preview importu")
metrics = st.columns(5)
metrics[0].metric("Řádky v XLSX", int(preview.get("raw_row_count") or 0))
metrics[1].metric("Dokončené", int(preview.get("completed_row_count") or 0))
metrics[2].metric("Nové", int(preview.get("new_row_count") or 0))
metrics[3].metric("Již v DB", int(preview.get("existing_row_count") or 0))
metrics[4].metric("Ignorované", int(preview.get("ignored_row_count") or 0))

rows = [dict(row) for row in preview.get("rows", []) if isinstance(row, dict)]
preview_table = _preview_dataframe(rows)
st.dataframe(
    preview_table,
    use_container_width=True,
    hide_index=True,
)

importable_count = int(preview.get("importable_row_count") or 0)
button_label = "Importovat nové záznamy"
if importable_count:
    button_label = f"Importovat nové záznamy ({importable_count})"

if st.button(
    button_label,
    type="primary",
    disabled=importable_count == 0,
):
    try:
        with st.spinner("Ukládám nové relace do databáze…"):
            result = import_smartfuelpass_excel_records(
                access_token,
                filename=filename,
                content=file_bytes,
            )
    except DashboardApiError as exc:
        st.error(str(exc))
    else:
        _load_health.clear()
        st.success(
            "Import dokončen. Uloženo "
            f"{int(result.get('inserted_count') or 0)} nových záznamů."
        )
        if int(result.get("existing_with_differences_count") or 0):
            st.warning(
                "Některé existující relace se liší od XLSX. Podle pravidla importu "
                "se nepřepisovaly."
            )
