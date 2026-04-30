from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import require_page_access
from moduly.mereni.elektromery.database.hlavni_xlsx_import import (
    MainMeterImportIssue,
    ParsedMainMeterWorkbook,
    build_unknown_identification_issues,
    import_main_meter_xlsx,
    parse_main_meter_xlsx,
)


UPLOAD_KEY = "elektromery_import_xlsx"


st.set_page_config(
    page_title="Elektroměry - Import XLSX",
    page_icon="📤",
    layout="wide",
)


require_page_access("elektromery_import")


def format_datetime(value: object) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return "-"
    return timestamp.strftime("%d.%m.%Y %H:%M")


def issue_to_row(issue: MainMeterImportIssue) -> dict[str, object]:
    return {
        "Řádek": issue.row_number,
        "Identifikace": issue.identifikace,
        "Datum": format_datetime(issue.date),
        "Zpráva": issue.message,
    }


def build_devices_dataframe(parsed: ParsedMainMeterWorkbook) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Identifikace": device.identifikace,
                "Sériové číslo": device.seriove_cislo,
                "Excel sloupec": device.column_index,
            }
            for device in parsed.devices
        ]
    )


def build_measurements_dataframe(parsed: ParsedMainMeterWorkbook, limit: int = 100) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Řádek": measurement.row_number,
                "Identifikace": measurement.identifikace,
                "Sériové číslo": measurement.seriove_cislo,
                "Datum": measurement.date,
                "Objem": measurement.objem,
            }
            for measurement in parsed.measurements[:limit]
        ]
    )


def build_issues_dataframe(issues: tuple[MainMeterImportIssue, ...]) -> pd.DataFrame:
    return pd.DataFrame([issue_to_row(issue) for issue in issues])


def render_import_preview(
    parsed: ParsedMainMeterWorkbook,
    identification_errors: tuple[MainMeterImportIssue, ...] = (),
) -> None:
    measurement_count = len(parsed.measurements)
    date_values = [measurement.date for measurement in parsed.measurements]
    all_errors = parsed.errors + identification_errors

    metric_cols = st.columns(5)
    metric_cols[0].metric("List", parsed.sheet_name)
    metric_cols[1].metric("Měřidla", len(parsed.devices))
    metric_cols[2].metric("Měření k importu", measurement_count)
    metric_cols[3].metric("Chyby", len(all_errors))
    metric_cols[4].metric("Varování", len(parsed.warnings))

    if date_values:
        st.caption(
            "Rozsah dat: "
            f"{format_datetime(min(date_values))} - {format_datetime(max(date_values))}"
        )

    st.info(
        "Hodnoty z XLSX jsou intervalová spotřeba. Import se uloží jako raw data do PostgreSQL "
        "`dbo.Mereni_elektromery_OTE`; do provozní elektroměrové tabulky `dbo.Mereni_elektromery` "
        "se tímto krokem nic nezapisuje."
    )

    with st.container(border=True):
        st.subheader("Měřidla v souboru")
        devices_df = build_devices_dataframe(parsed)
        if devices_df.empty:
            st.info("V souboru nebyla nalezena žádná měřidla.")
        else:
            st.dataframe(devices_df, width="stretch", hide_index=True)

    if all_errors:
        with st.container(border=True):
            st.subheader("Chyby")
            st.dataframe(build_issues_dataframe(all_errors), width="stretch", hide_index=True)

    if parsed.warnings:
        with st.container(border=True):
            st.subheader("Varování")
            st.dataframe(build_issues_dataframe(parsed.warnings), width="stretch", hide_index=True)

    with st.container(border=True):
        st.subheader("Náhled měření")
        measurements_df = build_measurements_dataframe(parsed)
        if measurements_df.empty:
            st.info("Soubor neobsahuje žádná validní měření.")
        else:
            st.dataframe(measurements_df, width="stretch", hide_index=True)


def render_import_result(file_bytes: bytes, source_file: str) -> None:
    result = import_main_meter_xlsx(file_bytes, source_file=source_file)
    if result.errors:
        st.error("Import nebyl uložen. Oprav chyby a nahraj soubor znovu.")
        st.dataframe(build_issues_dataframe(result.errors), width="stretch", hide_index=True)
        return

    st.cache_data.clear()
    st.success("Import byl uložen do databáze.")
    metric_cols = st.columns(4)
    metric_cols[0].metric("Vložená měření", result.inserted_measurements)
    metric_cols[1].metric("Přeskočené duplicity", result.skipped_existing_measurements)
    metric_cols[2].metric("Konflikty", result.conflict_measurements)
    metric_cols[3].metric("Vytvoření tabulky", "Ano" if result.created_table else "Ne")

    if result.archived_file_path:
        st.info(f"Soubor byl archivován: `{result.archived_file_path}`")

    if result.warnings:
        st.dataframe(build_issues_dataframe(result.warnings), width="stretch", hide_index=True)


def render_dashboard() -> None:
    st.title("Import hlavních elektroměrů")
    st.caption("XLSX raw import hlavních elektroměrů do PostgreSQL tabulky `dbo.Mereni_elektromery_OTE`.")

    uploaded_file = st.file_uploader(
        "XLSX soubor",
        type=["xlsx"],
        key=UPLOAD_KEY,
    )
    if uploaded_file is None:
        st.info("Nahraj XLSX soubor s hlavními elektroměry.")
        return

    file_bytes = uploaded_file.getvalue()
    parsed = parse_main_meter_xlsx(file_bytes)
    identification_errors = () if parsed.errors else build_unknown_identification_issues(parsed)
    render_import_preview(parsed, identification_errors)

    import_disabled = bool(parsed.errors or identification_errors) or not parsed.measurements
    if st.button("Importovat do databáze", type="primary", disabled=import_disabled):
        render_import_result(file_bytes, uploaded_file.name)


try:
    render_dashboard()
except (SQLAlchemyError, ValueError) as exc:
    st.error("Import elektroměrů se nepodařilo zpracovat.")
    st.exception(exc)
