from __future__ import annotations

import datetime
import io
import os
from pathlib import Path
import sys
import webbrowser

import pandas as pd
import streamlit as st

from app.time_utils import prague_today


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.revize_shared import (
    REVIZE_DISPLAY_COLUMNS,
    REVIZE_STATUS_ALL,
    REVIZE_STATUS_OPTIONS,
    build_revize_metrics,
    filter_revize_dataframe,
    load_revize_rows,
    prepare_revize_dataframe,
)
from moduly.apps.dashboard.vodomery_shared import render_page_styles


st.set_page_config(
    page_title="Revize - Přehled",
    page_icon="📋",
    layout="wide",
)


require_page_access("revize_overview")


BUILDINGS_KEY = "revize_overview_buildings"
DEVICE_TYPES_KEY = "revize_overview_device_types"
STATUS_KEY = "revize_overview_status"
SEARCH_KEY = "revize_overview_search"
APPLIED_KEY = "revize_overview_applied"


def render_revize_header() -> None:
    render_page_styles()
    st.markdown(
        """
        <div class="vodomery-hero">
            <div class="vodomery-eyebrow">Evidence</div>
            <h1 style="margin: 0;">Revize</h1>
            <div class="vodomery-subtitle">Přehled platností, dodavatelů a návazných dokumentů pro budovy F a G.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    buffer = io.BytesIO()
    export_df = df.copy()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        export_df.to_excel(writer, sheet_name=sheet_name, index=False)
        worksheet = writer.sheets[sheet_name]
        for idx, column in enumerate(export_df.columns):
            if export_df.empty:
                max_width = len(str(column)) + 2
            else:
                series_width = export_df[column].astype(str).str.len().max()
                max_width = max(len(str(column)), int(series_width)) + 2
            worksheet.set_column(idx, idx, min(max_width, 48))
    buffer.seek(0)
    return buffer.getvalue()


def build_export_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=[
                "Budova",
                "Název revize",
                "Typ zařízení",
                "Datum revize",
                "Platná do",
                "Stav",
                "Dní do konce",
                "Dodavatel",
                "Navázaná zařízení",
                "Soubor",
                "Servisní smlouva",
                "Poznámka",
            ]
        )

    export_df = pd.DataFrame(
        {
            "Budova": df["Budova"],
            "Název revize": df["Název revize"],
            "Typ zařízení": df["Typ zařízení"],
            "Datum revize": df["Datum revize"],
            "Platná do": df["Platná do"],
            "Stav": df["Stav"],
            "Dní do konce": df["Dní do konce"],
            "Dodavatel": df["Dodavatel"],
            "Navázaná zařízení": df["Navázaná zařízení"],
            "Soubor": df["soubor"].fillna("-"),
            "Servisní smlouva": df["servisni_smlouva"].fillna("-"),
            "Poznámka": df["Poznámka"],
        }
    )
    return export_df


def init_overview_state(prepared_df: pd.DataFrame) -> None:
    building_options = sorted(
        {
            str(value)
            for value in prepared_df["budova"].dropna().tolist()
            if str(value).strip()
        }
    )
    type_options = sorted(
        {
            str(value)
            for value in prepared_df["typ_zarizeni"].dropna().tolist()
            if str(value).strip()
        }
    )

    st.session_state.setdefault(BUILDINGS_KEY, building_options)
    st.session_state.setdefault(DEVICE_TYPES_KEY, type_options)
    st.session_state.setdefault(STATUS_KEY, REVIZE_STATUS_ALL)
    st.session_state.setdefault(SEARCH_KEY, "")
    st.session_state.setdefault(APPLIED_KEY, False)

    if not st.session_state.get(BUILDINGS_KEY):
        st.session_state[BUILDINGS_KEY] = building_options
    if not st.session_state.get(DEVICE_TYPES_KEY):
        st.session_state[DEVICE_TYPES_KEY] = type_options


def render_sidebar_filters(prepared_df: pd.DataFrame) -> tuple[list[str], list[str], str, str]:
    init_overview_state(prepared_df)

    building_options = sorted(
        {
            str(value)
            for value in prepared_df["budova"].dropna().tolist()
            if str(value).strip()
        }
    )
    type_options = sorted(
        {
            str(value)
            for value in prepared_df["typ_zarizeni"].dropna().tolist()
            if str(value).strip()
        }
    )

    with st.sidebar:
        st.markdown("---")
        st.subheader("Filtry")
        with st.form("revize_overview_filters"):
            selected_buildings = st.multiselect("Budova", building_options, key=BUILDINGS_KEY)
            selected_types = st.multiselect("Typ zařízení", type_options, key=DEVICE_TYPES_KEY)
            selected_status = st.selectbox("Stav platnosti", REVIZE_STATUS_OPTIONS, key=STATUS_KEY)
            search_text = st.text_input("Hledat", placeholder="název, dodavatel, soubor...", key=SEARCH_KEY)
            apply_filters = st.form_submit_button("Načíst data", width="stretch")

    if apply_filters:
        st.session_state[APPLIED_KEY] = True

    return selected_buildings, selected_types, selected_status, search_text


def render_metrics(metrics: dict[str, int]) -> None:
    metric_cols = st.columns(5)
    metric_cols[0].metric("Revize celkem", metrics["total"])
    metric_cols[1].metric("Po platnosti", metrics["expired"])
    metric_cols[2].metric("Do 30 dní", metrics["due_soon"])
    metric_cols[3].metric("Platné", metrics["valid"])
    metric_cols[4].metric("Bez souboru", metrics["missing_file"])


def normalize_open_target(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == "-":
        return None
    return text


def open_external_target(target: str) -> tuple[bool, str]:
    normalized_target = target.strip()
    if not normalized_target:
        return False, "Cíl pro otevření není k dispozici."

    lowered = normalized_target.casefold()
    is_url = lowered.startswith(("http://", "https://", "file://"))
    if not is_url and not Path(normalized_target).exists():
        return False, f"Soubor nebyl nalezen: {normalized_target}"

    try:
        if hasattr(os, "startfile"):
            os.startfile(normalized_target)
        else:
            webbrowser.open(normalized_target)
    except OSError as exc:
        return False, f"Nepodařilo se otevřít cíl: {exc}"

    return True, f"Otevřeno: {normalized_target}"


def resolve_selected_row(df: pd.DataFrame, table_state: object) -> pd.Series | None:
    if df.empty or table_state is None:
        return None

    selection = getattr(table_state, "selection", None)
    rows = getattr(selection, "rows", None) if selection is not None else None
    if rows is None and isinstance(table_state, dict):
        selection = table_state.get("selection") or {}
        rows = selection.get("rows", [])
    if not rows:
        return None

    row_index = rows[0]
    if not isinstance(row_index, int) or row_index < 0 or row_index >= len(df):
        return None
    return df.iloc[row_index]


def render_row_actions(filtered_df: pd.DataFrame, table_state: object) -> None:
    selected_row = resolve_selected_row(filtered_df, table_state)
    if selected_row is None:
        st.caption("Vyberte jeden řádek v tabulce pro otevření souboru nebo servisní smlouvy.")
        return

    selected_name = str(selected_row.get("Název revize") or selected_row.get("nazev_revize") or "-")
    selected_file = normalize_open_target(selected_row.get("soubor"))
    selected_contract = normalize_open_target(selected_row.get("servisni_smlouva"))

    info_col, file_col, contract_col = st.columns([3, 1, 1], vertical_alignment="bottom")
    with info_col:
        st.markdown(f"**Vybraná revize:** {selected_name}")
        if selected_file:
            st.caption(selected_file)

    with file_col:
        if st.button(
            "Otevřít soubor",
            key=f"revize_open_file_{selected_row.get('id')}",
            width="stretch",
            disabled=selected_file is None,
        ):
            success, message = open_external_target(selected_file)
            if success:
                st.success(message)
            else:
                st.error(message)

    with contract_col:
        if st.button(
            "Otevřít smlouvu",
            key=f"revize_open_contract_{selected_row.get('id')}",
            width="stretch",
            disabled=selected_contract is None,
        ):
            success, message = open_external_target(selected_contract)
            if success:
                st.success(message)
            else:
                st.error(message)


def render_dashboard() -> None:
    render_revize_header()

    raw_df = load_revize_rows()
    prepared_df = prepare_revize_dataframe(raw_df, reference_date=prague_today())
    selected_buildings, selected_types, selected_status, search_text = render_sidebar_filters(prepared_df)

    st.caption("Filtr se aplikuje až po kliknutí na `Načíst data` v sidebaru.")

    if not st.session_state.get(APPLIED_KEY):
        st.info("Klikněte na `Načíst data` pro zobrazení přehledu revizí.")
        return

    filtered_df = filter_revize_dataframe(
        prepared_df,
        buildings=selected_buildings,
        device_types=selected_types,
        status=selected_status,
        search_text=search_text,
    )

    render_metrics(build_revize_metrics(filtered_df))

    with st.container(border=True):
        header_col, action_col = st.columns([4, 1])
        with header_col:
            st.subheader("Přehled revizí")
            st.caption(
                "Řazení zvýrazňuje nejdříve propadlé a brzy končící revize. Export obsahuje i plné cesty k souborům."
            )
        with action_col:
            export_df = build_export_dataframe(filtered_df)
            st.download_button(
                "Export XLSX",
                data=dataframe_to_excel_bytes(export_df, "Revize"),
                file_name=f"revize_prehled_{prague_today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )

        if filtered_df.empty:
            st.info("Pro zadané filtry nebyly nalezeny žádné revize.")
            return

        display_df = filtered_df[REVIZE_DISPLAY_COLUMNS].copy()
        table_state = st.dataframe(
            display_df,
            width="stretch",
            hide_index=True,
            key="revize_overview_table",
            on_select="rerun",
            selection_mode="single-row",
        )
        render_row_actions(filtered_df, table_state)


render_dashboard()
