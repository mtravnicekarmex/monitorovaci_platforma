from __future__ import annotations

import base64
import datetime
from html import escape
import io
import json
import os
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname
import webbrowser

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from sqlalchemy.exc import SQLAlchemyError

from app.time_utils import prague_today


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import is_admin, require_page_access
from moduly.apps.dashboard.device_list_shared import _full_dataframe_height
from moduly.apps.dashboard.revize_shared import (
    REVIZE_BUILDING_OPTIONS,
    REVIZE_DISPLAY_COLUMNS,
    REVIZE_STATUS_ALL,
    REVIZE_STATUS_OPTIONS,
    build_revize_metrics,
    calculate_revize_valid_until,
    create_revize_record,
    filter_revize_dataframe,
    load_revize_rows,
    load_revize_record_values,
    normalize_revize_payload,
    parse_revize_linked_device_ids,
    prepare_revize_dataframe,
    update_revize_record,
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
CREATE_OPEN_KEY = "revize_overview_create_open"
EDIT_OPEN_KEY = "revize_overview_edit_open"
EDIT_RECORD_ID_KEY = "revize_overview_edit_record_id"
SUCCESS_KEY = "revize_overview_success"
PDF_PREVIEW_TARGET_KEY = "revize_overview_pdf_preview_target"
PDF_PREVIEW_NAME_KEY = "revize_overview_pdf_preview_name"
PDF_PREVIEW_RECORD_ID_KEY = "revize_overview_pdf_preview_record_id"
PDF_PREVIEW_MAX_BYTES = 50 * 1024 * 1024
PDF_PREVIEW_HEIGHT = 760
PATH_PREFIX_FALLBACKS: tuple[tuple[str, str], ...] = (
    ("P:\\", "\\\\SERVER1A\\Company\\"),
)


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
                series_width = export_df[column].astype("string").fillna("").str.len().max()
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


def _dataframe_option_values(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    return sorted(
        {
            str(value).strip()
            for value in df[column].dropna().tolist()
            if str(value).strip()
        }
    )


def init_overview_state(prepared_df: pd.DataFrame) -> None:
    building_options = _dataframe_option_values(prepared_df, "budova")
    type_options = _dataframe_option_values(prepared_df, "typ_zarizeni")

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

    building_options = _dataframe_option_values(prepared_df, "budova")
    type_options = _dataframe_option_values(prepared_df, "typ_zarizeni")

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


def _is_http_url(target: str) -> bool:
    return target.casefold().startswith(("http://", "https://"))


def _is_file_uri(target: str) -> bool:
    return target.casefold().startswith("file://")


def _path_from_file_uri(target: str) -> Path:
    parsed = urlparse(target)
    path = url2pathname(unquote(parsed.path))
    if parsed.netloc:
        return Path(f"//{parsed.netloc}{path}")
    return Path(path)


def _local_target_path(target: str) -> Path:
    if _is_file_uri(target):
        return _path_from_file_uri(target)
    return Path(target)


def _local_path_candidates(target: str) -> list[Path]:
    base_path = _local_target_path(target)
    candidates = [base_path]
    base_text = str(base_path)

    for source_prefix, replacement_prefix in PATH_PREFIX_FALLBACKS:
        if base_text.casefold().startswith(source_prefix.casefold()):
            relative_path = base_text[len(source_prefix):].lstrip("\\/")
            candidates.append(Path(f"{replacement_prefix}{relative_path}"))

    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        candidate_key = str(candidate).casefold()
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        unique_candidates.append(candidate)
    return unique_candidates


def _resolve_existing_local_path(target: str) -> Path | None:
    for candidate in _local_path_candidates(target):
        if candidate.exists():
            return candidate
    return None


def _format_missing_path_message(target: str) -> str:
    candidates = _local_path_candidates(target)
    if len(candidates) <= 1:
        return f"Soubor nebyl nalezen: {target}"
    attempted_paths = "; ".join(str(candidate) for candidate in candidates)
    return f"Soubor nebyl nalezen. Zkoušené cesty: {attempted_paths}"


def open_external_target(target: str) -> tuple[bool, str]:
    normalized_target = target.strip()
    if not normalized_target:
        return False, "Cíl pro otevření není k dispozici."

    open_target = normalized_target
    if not _is_http_url(normalized_target):
        resolved_path = _resolve_existing_local_path(normalized_target)
        if resolved_path is None:
            return False, _format_missing_path_message(normalized_target)
        open_target = str(resolved_path)

    try:
        if hasattr(os, "startfile"):
            os.startfile(open_target)
        else:
            webbrowser.open(open_target)
    except OSError as exc:
        return False, f"Nepodařilo se otevřít cíl: {exc}"

    if open_target != normalized_target:
        return True, f"Otevřeno: {open_target}"
    return True, f"Otevřeno: {normalized_target}"


def _pdf_target_suffix(target: str) -> str:
    if _is_http_url(target) or _is_file_uri(target):
        return Path(urlparse(target).path).suffix.casefold()
    return Path(target).suffix.casefold()


def is_pdf_preview_target(target: object) -> bool:
    normalized_target = normalize_open_target(target)
    if normalized_target is None:
        return False
    return _pdf_target_suffix(normalized_target) == ".pdf"


def build_pdf_preview_source(target: str) -> tuple[str | None, str | None, str | None]:
    normalized_target = target.strip()
    if not normalized_target:
        return None, None, "PDF soubor není k dispozici."

    if not is_pdf_preview_target(normalized_target):
        return None, None, "Náhled je dostupný pouze pro PDF soubory."

    if _is_http_url(normalized_target):
        return "url", normalized_target, None

    pdf_path = _resolve_existing_local_path(normalized_target)
    if pdf_path is None:
        return None, None, _format_missing_path_message(normalized_target)
    if not pdf_path.is_file():
        return None, None, f"Cíl není soubor: {normalized_target}"

    file_size = pdf_path.stat().st_size
    if file_size > PDF_PREVIEW_MAX_BYTES:
        max_mb = PDF_PREVIEW_MAX_BYTES // (1024 * 1024)
        return None, None, f"PDF je příliš velké pro náhled v prohlížeči. Limit je {max_mb} MB."

    encoded_pdf = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    return "base64", encoded_pdf, None


def render_pdf_preview(target: str, title: str) -> None:
    source_kind, source, error_message = build_pdf_preview_source(target)
    if error_message:
        st.error(error_message)
        return
    if source_kind is None or source is None:
        return

    safe_title = escape(title or "PDF náhled")
    if source_kind == "url":
        safe_source = escape(source, quote=True)
        components.html(
            f"""
            <iframe
                title="{safe_title}"
                src="{safe_source}"
                width="100%"
                height="{PDF_PREVIEW_HEIGHT}"
                style="border: 1px solid #d8dee4; border-radius: 6px;"
            ></iframe>
            """,
            height=PDF_PREVIEW_HEIGHT + 24,
        )
        return

    frame_id = f"revize-pdf-preview-{abs(hash(source))}"
    source_json = json.dumps(source)
    title_json = json.dumps(title or "PDF náhled")
    components.html(
        f"""
        <iframe
            id="{frame_id}"
            title="{safe_title}"
            width="100%"
            height="{PDF_PREVIEW_HEIGHT}"
            style="border: 1px solid #d8dee4; border-radius: 6px;"
        ></iframe>
        <script>
        (function() {{
            const base64 = {source_json};
            const binary = atob(base64);
            const bytes = new Uint8Array(binary.length);
            for (let index = 0; index < binary.length; index += 1) {{
                bytes[index] = binary.charCodeAt(index);
            }}
            const blob = new Blob([bytes], {{ type: "application/pdf" }});
            const url = URL.createObjectURL(blob);
            const frame = document.getElementById({json.dumps(frame_id)});
            frame.title = {title_json};
            frame.src = url;
            window.addEventListener("beforeunload", function() {{
                URL.revokeObjectURL(url);
            }});
        }})();
        </script>
        """,
        height=PDF_PREVIEW_HEIGHT + 24,
    )


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
    selected_record_id = str(selected_row.get("id") or "")
    can_preview_pdf = selected_file is not None and is_pdf_preview_target(selected_file)

    info_col, preview_col, file_col, contract_col = st.columns([3, 1, 1, 1], vertical_alignment="bottom")
    with info_col:
        st.markdown(f"**Vybraná revize:** {selected_name}")
        if selected_file:
            st.caption(selected_file)

    with preview_col:
        if st.button(
            "Zobrazit PDF",
            key=f"revize_preview_pdf_{selected_row.get('id')}",
            width="stretch",
            disabled=not can_preview_pdf,
            help=None if can_preview_pdf else "Náhled je dostupný pouze pro PDF ze sloupce Soubor.",
        ):
            st.session_state[PDF_PREVIEW_TARGET_KEY] = selected_file
            st.session_state[PDF_PREVIEW_NAME_KEY] = selected_name
            st.session_state[PDF_PREVIEW_RECORD_ID_KEY] = selected_record_id

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

    preview_target = st.session_state.get(PDF_PREVIEW_TARGET_KEY)
    preview_record_id = st.session_state.get(PDF_PREVIEW_RECORD_ID_KEY)
    if preview_target and preview_record_id == selected_record_id:
        st.markdown("#### Náhled PDF")
        st.caption(str(preview_target))
        render_pdf_preview(str(preview_target), str(st.session_state.get(PDF_PREVIEW_NAME_KEY) or selected_name))


def _as_date(value: object, fallback: datetime.date) -> datetime.date:
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return fallback
        return value.date()
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return fallback
    return parsed.date()


def _as_optional_date(value: object) -> datetime.date | None:
    if value in ("", None):
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.date()
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _as_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    return "" if text == "nan" else text


def _build_select_options(values: list[str] | tuple[str, ...], current_value: object = "") -> list[str]:
    options: list[str] = [""]
    seen: set[str] = {""}

    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        options.append(text)

    current_text = _as_text(current_value).strip()
    if current_text and current_text not in seen:
        options.append(current_text)

    return options


def _select_option_index(options: list[str], current_value: object = "") -> int:
    current_text = _as_text(current_value).strip()
    if current_text in options:
        return options.index(current_text)
    return 0


def _format_select_option(value: str) -> str:
    return "Vyberte..." if value == "" else value


def _format_linked_device_ids(value: object) -> str:
    if value in ("", None):
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(item) for item in value)
    return _as_text(value)


def _infer_validity_months_from_dates(revision_date: datetime.date, valid_until: datetime.date) -> int | None:
    if valid_until <= revision_date:
        return None

    approximate_months = (valid_until.year - revision_date.year) * 12 + valid_until.month - revision_date.month
    candidates = range(max(1, approximate_months - 2), approximate_months + 3)
    best_candidate = min(
        candidates,
        key=lambda months: abs((calculate_revize_valid_until(revision_date, months) - valid_until).days),
    )
    return int(best_candidate)


def _resolve_validity_months(record_values: dict[str, object], revision_date: datetime.date) -> int:
    valid_until = _as_optional_date(record_values.get("datum_platnosti"))
    if valid_until is not None:
        inferred_months = _infer_validity_months_from_dates(revision_date, valid_until)
        if inferred_months is not None:
            return inferred_months

    raw_value = record_values.get("delka_platnosti")
    if raw_value not in ("", None):
        try:
            fallback_months = int(round(float(raw_value)))
        except (TypeError, ValueError):
            fallback_months = 12
        if fallback_months > 0:
            return fallback_months

    return 12


def _build_revize_form_payload(
    *,
    budova: str,
    datum: datetime.date,
    delka_platnosti: int,
    typ_zarizeni: str,
    nazev_revize: str,
    dodavatel: str,
    servisni_smlouva: str,
    soubor: str,
    poznamka: str,
) -> dict[str, object]:
    return normalize_revize_payload(
        budova=budova,
        datum=datum,
        delka_platnosti=delka_platnosti,
        typ_zarizeni=typ_zarizeni,
        nazev_revize=nazev_revize,
        dodavatel=dodavatel,
        servisni_smlouva=servisni_smlouva,
        soubor=soubor,
        poznamka=poznamka,
    )


def _clear_revize_cache_and_rerun(message: str) -> None:
    load_revize_rows.clear()
    st.session_state[SUCCESS_KEY] = message
    st.session_state[CREATE_OPEN_KEY] = False
    st.session_state[EDIT_OPEN_KEY] = False
    st.session_state.pop(EDIT_RECORD_ID_KEY, None)
    st.rerun()


def _render_revize_form(
    *,
    mode: str,
    prepared_df: pd.DataFrame,
    record_values: dict[str, object] | None = None,
) -> None:
    is_edit = mode == "edit"
    record_values = record_values or {}
    today = prague_today()
    revision_date = _as_date(record_values.get("datum"), today)
    validity_months = _resolve_validity_months(record_values, revision_date)
    building_options = _build_select_options(
        [*REVIZE_BUILDING_OPTIONS, *_dataframe_option_values(prepared_df, "budova")],
        record_values.get("budova"),
    )
    device_type_options = _build_select_options(
        _dataframe_option_values(prepared_df, "typ_zarizeni"),
        record_values.get("typ_zarizeni"),
    )

    st.subheader("Upravit revizi" if is_edit else "Nová revize")
    with st.form(f"revize_overview_{mode}_form"):
        row_1 = st.columns(3)
        with row_1[0]:
            budova = st.selectbox(
                "Budova *",
                building_options,
                index=_select_option_index(building_options, record_values.get("budova")),
                format_func=_format_select_option,
            )
        with row_1[1]:
            datum = st.date_input("Datum revize *", value=revision_date)
        with row_1[2]:
            delka_platnosti = st.number_input(
                "Délka platnosti [měsíce] *",
                min_value=1,
                max_value=99,
                value=validity_months,
                step=1,
            )

        row_2 = st.columns(3)
        with row_2[0]:
            datum_platnosti = calculate_revize_valid_until(datum, int(delka_platnosti))
            st.text_input(
                "Platná do",
                value=datum_platnosti.strftime("%d.%m.%Y"),
                disabled=True,
            )
        with row_2[1]:
            typ_zarizeni = st.selectbox(
                "Zařízení",
                device_type_options,
                index=_select_option_index(device_type_options, record_values.get("typ_zarizeni")),
                format_func=_format_select_option,
            )
        with row_2[2]:
            dodavatel = st.text_input("Dodavatel", value=_as_text(record_values.get("dodavatel")))

        nazev_revize = st.text_input("Název revize", value=_as_text(record_values.get("nazev_revize")))
        soubor = st.text_input("Soubor", value=_as_text(record_values.get("soubor")))
        navazane_zarizeni = st.text_input(
            "Navázaná zařízení",
            value=_format_linked_device_ids(record_values.get("linked_device_ids")),
            help="Jedno ID nebo seznam ID oddeleny carkou, mezerou nebo strednikem.",
        )
        servisni_smlouva = st.text_input("Servisní smlouva", value=_as_text(record_values.get("servisni_smlouva")))
        poznamka = st.text_area("Poznámka", value=_as_text(record_values.get("poznamka")))

        save_pressed = st.form_submit_button(
            "Uložit změny" if is_edit else "Uložit do DB",
            type="primary",
            width="stretch",
        )

    if not save_pressed:
        return

    try:
        linked_device_ids = parse_revize_linked_device_ids(navazane_zarizeni)
        payload = _build_revize_form_payload(
            budova=budova,
            datum=datum,
            delka_platnosti=int(delka_platnosti),
            typ_zarizeni=typ_zarizeni,
            nazev_revize=nazev_revize,
            dodavatel=dodavatel,
            servisni_smlouva=servisni_smlouva,
            soubor=soubor,
            poznamka=poznamka,
        )
        if is_edit:
            update_revize_record(int(record_values["id"]), payload, linked_device_ids=linked_device_ids)
            _clear_revize_cache_and_rerun("Revize byla upravena.")
            return
        create_revize_record(payload, linked_device_ids=linked_device_ids)
        _clear_revize_cache_and_rerun("Nová revize byla uložena.")
    except ValueError as exc:
        st.warning(str(exc))
    except SQLAlchemyError as exc:
        st.error("Revizi se nepodarilo ulozit do PostgreSQL.")
        st.exception(exc)


def render_revize_edit_controls(
    filtered_df: pd.DataFrame,
    table_state: object,
    prepared_df: pd.DataFrame,
) -> None:
    user_is_admin = is_admin()
    selected_row = resolve_selected_row(filtered_df, table_state)

    create_col, edit_col, spacer_col = st.columns((1, 1, 4))
    with create_col:
        if st.button(
            "Přidat nový",
            type="primary",
            width="stretch",
            disabled=not user_is_admin,
            help=None if user_is_admin else "Novou revizi může vytvořit pouze admin.",
        ):
            st.session_state[CREATE_OPEN_KEY] = True
            st.session_state[EDIT_OPEN_KEY] = False
            st.session_state.pop(EDIT_RECORD_ID_KEY, None)
    with edit_col:
        if st.button(
            "Upravit",
            width="stretch",
            disabled=not user_is_admin or filtered_df.empty,
            help=None if user_is_admin else "Revizi může upravit pouze admin.",
        ):
            if selected_row is None:
                st.warning("Vyberte jeden řádek v tabulce pro úpravu.")
            else:
                st.session_state[EDIT_RECORD_ID_KEY] = int(selected_row["id"])
                st.session_state[EDIT_OPEN_KEY] = True
                st.session_state[CREATE_OPEN_KEY] = False
    with spacer_col:
        st.write("")

    if st.session_state.get(CREATE_OPEN_KEY, False):
        _render_revize_form(mode="create", prepared_df=prepared_df)

    if st.session_state.get(EDIT_OPEN_KEY, False):
        record_id = st.session_state.get(EDIT_RECORD_ID_KEY)
        if record_id is None:
            st.warning("Vyberte jeden řádek v tabulce pro úpravu.")
            return
        record_values = load_revize_record_values(int(record_id))
        if record_values is None:
            st.warning("Vybraná revize už není dostupná.")
            st.session_state[EDIT_OPEN_KEY] = False
            st.session_state.pop(EDIT_RECORD_ID_KEY, None)
            return
        _render_revize_form(mode="edit", prepared_df=prepared_df, record_values=record_values)


def render_dashboard() -> None:
    render_revize_header()
    success_message = st.session_state.pop(SUCCESS_KEY, None)
    if success_message:
        st.success(str(success_message))

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
            height=_full_dataframe_height(len(display_df)),
            key="revize_overview_table",
            on_select="rerun",
            selection_mode="single-row",
        )
        render_revize_edit_controls(filtered_df, table_state, prepared_df)
        render_row_actions(filtered_df, table_state)


render_dashboard()
