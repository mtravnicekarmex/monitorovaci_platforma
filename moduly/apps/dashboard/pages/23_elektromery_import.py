from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
import re
import sys

from sqlalchemy.exc import SQLAlchemyError
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.auth import require_page_access
from moduly.apps.dashboard.vodomery_shared import render_page_styles
from moduly.mereni.elektromery.database.binary_ts_import import (
    BinaryMeterFileConfig,
    BinaryMeterManualImportResult,
    DOUBLE_SIZE_BYTES,
    load_binary_import_state,
    load_binary_meter_config,
    manual_import_binary_meter_payload,
    source_key_from_binary_file_name,
    summarize_parsed_file,
    parse_binary_meter_file,
)
from moduly.mereni.elektromery.database.time_semantics import BINARY_TIME_SEMANTICS


UPLOAD_DIALOG_OPEN_KEY = "elektromery_binary_import_dialog_open"
PENDING_UPLOAD_KEY = "elektromery_binary_import_pending_upload"
LAST_RESULT_KEY = "elektromery_binary_import_last_result"
FLASH_KEY = "elektromery_binary_import_flash"
UPLOAD_WIDGET_KEY = "elektromery_binary_import_upload"


st.set_page_config(
    page_title="Elektromery - Import",
    page_icon="📥",
    layout="wide",
)


require_page_access("elektromery_import")


def _default_source_name(source_key: str) -> str:
    normalized_key = re.sub(r"[^A-Za-z0-9_]+", "_", source_key).strip("_").upper()
    return f"BINARY_{normalized_key}"[:20]


def _parse_optional_int(value: str, label: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError(f"{label} musi byt cele cislo.") from exc


def _format_datetime(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M:%S")
    return "-"


def _store_flash(level: str, message: str) -> None:
    st.session_state[FLASH_KEY] = {"level": level, "message": message}


def _render_flash() -> None:
    flash = st.session_state.pop(FLASH_KEY, None)
    if not isinstance(flash, dict):
        return
    level = str(flash.get("level") or "info")
    message = str(flash.get("message") or "").strip()
    if message:
        getattr(st, level, st.info)(message)


def _clear_dialog_state() -> None:
    st.session_state[UPLOAD_DIALOG_OPEN_KEY] = False
    st.session_state.pop(PENDING_UPLOAD_KEY, None)


def _payload_summary(payload: bytes) -> dict[str, object]:
    return {
        "Velikost souboru": f"{len(payload):,} B".replace(",", " "),
        "Vzorku celkem": len(payload) // DOUBLE_SIZE_BYTES if len(payload) % DOUBLE_SIZE_BYTES == 0 else "-",
    }


def _render_result(result: BinaryMeterManualImportResult) -> None:
    import_result = result.import_result
    backfill_result = result.backfill_result

    st.subheader("Posledni import")
    metric_cols = st.columns(5)
    metric_cols[0].metric("Zdroj", import_result.config.source_name)
    metric_cols[1].metric("Novych vzorku", import_result.parsed_sample_count)
    metric_cols[2].metric("Platnych delta hodnot", import_result.finite_measurements)
    metric_cols[3].metric("Raw vlozeno", import_result.inserted_raw_measurements)
    metric_cols[4].metric("Monitoring pripraveno", import_result.monitoring_rows)

    detail_cols = st.columns(4)
    detail_cols[0].metric("Predchozi sample", import_result.previous_last_sample_index)
    detail_cols[1].metric("Novy sample", import_result.new_last_sample_index)
    detail_cols[2].metric("Preskoceno NaN/Inf", import_result.skipped_non_finite_count)
    detail_cols[3].metric(
        "Backfill do monitoringu",
        0 if backfill_result is None else backfill_result.monitoring_rows_added,
    )


def _validate_upload(file_name: str, payload: bytes) -> str:
    if not str(file_name).lower().endswith(".ts"):
        raise ValueError("Nahraj soubor s priponou .ts.")
    if not payload:
        raise ValueError("Soubor je prazdny.")
    if len(payload) % DOUBLE_SIZE_BYTES != 0:
        raise ValueError(f"Velikost .ts souboru musi byt delitelna {DOUBLE_SIZE_BYTES} bajty.")
    return source_key_from_binary_file_name(file_name)


def _set_pending_upload(file_name: str, source_key: str, payload: bytes, config: BinaryMeterFileConfig | None) -> None:
    st.session_state[PENDING_UPLOAD_KEY] = {
        "file_name": file_name,
        "source_key": source_key,
        "payload": payload,
        "uploaded_at": datetime.now(),
        "config": config,
    }


def _run_import(config: BinaryMeterFileConfig, payload: bytes, *, register_new_source: bool) -> None:
    result = manual_import_binary_meter_payload(
        config,
        payload,
        source_mtime=datetime.now(),
        register_new_source=register_new_source,
        write_to_monitoring=True,
    )
    st.session_state[LAST_RESULT_KEY] = result
    _store_flash(
        "success",
        (
            f"Import {config.source_name} dokoncen. "
            f"Raw vlozeno: {result.import_result.inserted_raw_measurements}, "
            f"monitoring pripraveno: {result.import_result.monitoring_rows}."
        ),
    )
    _clear_dialog_state()
    st.rerun()


def _handle_uploaded_file(uploaded_file) -> None:
    if uploaded_file is None:
        st.warning("Vyber .ts soubor pro import.")
        return

    payload = uploaded_file.getvalue()
    source_key = _validate_upload(uploaded_file.name, payload)
    state = load_binary_import_state(source_key)
    config = load_binary_meter_config(source_key, enabled_only=False)

    if state is None or config is None:
        _set_pending_upload(uploaded_file.name, source_key, payload, config)
        if state is None:
            st.info("Soubor nema zaznam v dbo.elektromery_binary_import_state. Dopln metadata zdroje.")
        else:
            st.warning("Soubor ma importni stav, ale chybi konfigurace zdroje. Dopln metadata.")
        st.rerun()
        return

    _run_import(config, payload, register_new_source=False)


def _build_config_from_form(
    *,
    source_key: str,
    file_name: str,
    identifikace: str,
    seriove_cislo: str,
    first_date: date,
    first_time: time,
    timestamp_offset_minutes: int,
    interval_minutes: int,
    source_name: str,
    double_format: str,
    time_basis: str,
    source_timezone: str,
    source_utc_offset_minutes: str,
    timestamp_position: str,
    time_fold: str,
) -> BinaryMeterFileConfig:
    source_name = source_name.strip()
    identifikace = identifikace.strip()
    double_format = double_format.strip() or "<d"
    time_basis = time_basis.strip() or BINARY_TIME_SEMANTICS.time_basis
    source_timezone = source_timezone.strip() or BINARY_TIME_SEMANTICS.source_timezone
    timestamp_position = timestamp_position.strip() or BINARY_TIME_SEMANTICS.timestamp_position

    if not identifikace:
        raise ValueError("Identifikace je povinna.")
    if not source_name:
        raise ValueError("Nazev zdroje je povinny.")
    if len(source_name) > 20:
        raise ValueError("Nazev zdroje musi mit nejvyse 20 znaku kvuli sloupci zdroj.")
    if interval_minutes <= 0:
        raise ValueError("Interval musi byt kladne cislo.")

    return BinaryMeterFileConfig(
        key=source_key,
        file_name=file_name,
        identifikace=identifikace,
        seriove_cislo=_parse_optional_int(seriove_cislo, "Seriove cislo"),
        first_timestamp=datetime.combine(first_date, first_time),
        timestamp_offset=timedelta(minutes=int(timestamp_offset_minutes)),
        interval_minutes=int(interval_minutes),
        source_name=source_name,
        double_format=double_format,
        time_basis=time_basis,
        source_timezone=source_timezone,
        source_utc_offset_minutes=_parse_optional_int(
            source_utc_offset_minutes,
            "UTC offset v minutach",
        ),
        timestamp_position=timestamp_position,
        time_fold=_parse_optional_int(time_fold, "Fold"),
    )


def _render_registration_form(pending: dict[str, object]) -> None:
    file_name = str(pending["file_name"])
    source_key = str(pending["source_key"])
    payload = bytes(pending["payload"])
    existing_config = pending.get("config")
    config = existing_config if isinstance(existing_config, BinaryMeterFileConfig) else None

    st.caption(f"Soubor `{file_name}` bude registrovan jako source_key `{source_key}`.")
    summary = _payload_summary(payload)
    st.write(f"Velikost: {summary['Velikost souboru']} | Vzorku: {summary['Vzorku celkem']}")

    default_first = config.first_timestamp if config is not None else datetime(2024, 7, 1)
    with st.form("elektromery_binary_new_source_form"):
        identifikace = st.text_input(
            "Identifikace elektromeru",
            value="" if config is None else config.identifikace,
        )
        source_name = st.text_input(
            "Nazev zdroje v monitoring.Mereni_elektromery_vse",
            value=_default_source_name(source_key) if config is None else config.source_name,
        )
        serial_col, interval_col = st.columns(2)
        with serial_col:
            seriove_cislo = st.text_input(
                "Seriove cislo",
                value="" if config is None or config.seriove_cislo is None else str(config.seriove_cislo),
            )
        with interval_col:
            interval_minutes = st.number_input(
                "Interval [min]",
                min_value=1,
                step=1,
                value=15 if config is None else int(config.interval_minutes),
            )

        time_cols = st.columns(3)
        with time_cols[0]:
            first_date = st.date_input("Cas vzorku 0 - datum", value=default_first.date())
        with time_cols[1]:
            first_time = st.time_input("Cas vzorku 0 - cas", value=default_first.time())
        with time_cols[2]:
            timestamp_offset_minutes = st.number_input(
                "Offset timestampu [min]",
                step=1,
                value=0 if config is None else int(config.timestamp_offset.total_seconds() // 60),
            )

        advanced = st.expander("Casova metadata a format")
        with advanced:
            meta_cols = st.columns(3)
            with meta_cols[0]:
                double_format = st.text_input(
                    "Double format",
                    value="<d" if config is None else config.double_format,
                )
            with meta_cols[1]:
                time_basis = st.text_input(
                    "Time basis",
                    value=BINARY_TIME_SEMANTICS.time_basis if config is None else config.time_basis,
                )
            with meta_cols[2]:
                source_timezone = st.text_input(
                    "Source timezone",
                    value=BINARY_TIME_SEMANTICS.source_timezone if config is None else config.source_timezone,
                )
            offset_cols = st.columns(3)
            with offset_cols[0]:
                source_utc_offset_minutes = st.text_input(
                    "UTC offset [min]",
                    value=(
                        str(BINARY_TIME_SEMANTICS.source_utc_offset_minutes)
                        if config is None
                        else "" if config.source_utc_offset_minutes is None else str(config.source_utc_offset_minutes)
                    ),
                )
            with offset_cols[1]:
                timestamp_position = st.text_input(
                    "Timestamp position",
                    value=(
                        BINARY_TIME_SEMANTICS.timestamp_position
                        if config is None
                        else config.timestamp_position
                    ),
                )
            with offset_cols[2]:
                time_fold = st.text_input(
                    "Fold",
                    value="" if config is None or config.time_fold is None else str(config.time_fold),
                )

        action_cols = st.columns(2)
        with action_cols[0]:
            save = st.form_submit_button("Ulozit a importovat", type="primary", width="stretch")
        with action_cols[1]:
            cancel = st.form_submit_button("Zrusit", width="stretch")

    if cancel:
        _clear_dialog_state()
        st.rerun()
    if not save:
        return

    try:
        new_config = _build_config_from_form(
            source_key=source_key,
            file_name=file_name,
            identifikace=identifikace,
            seriove_cislo=seriove_cislo,
            first_date=first_date,
            first_time=first_time,
            timestamp_offset_minutes=int(timestamp_offset_minutes),
            interval_minutes=int(interval_minutes),
            source_name=source_name,
            double_format=double_format,
            time_basis=time_basis,
            source_timezone=source_timezone,
            source_utc_offset_minutes=source_utc_offset_minutes,
            timestamp_position=timestamp_position,
            time_fold=time_fold,
        )
        parsed = parse_binary_meter_file(new_config, payload)
        if parsed.finite_count == 0:
            raise ValueError("Soubor neobsahuje zadnou konecnou hodnotu pro import.")
        _run_import(new_config, payload, register_new_source=True)
    except (ValueError, SQLAlchemyError) as exc:
        st.error(str(exc))


def _render_upload_step() -> None:
    uploaded_file = st.file_uploader(
        ".ts soubor",
        type=["ts"],
        key=UPLOAD_WIDGET_KEY,
        help="Source key se bere z nazvu souboru bez pripony, napr. 19891.ts -> 19891.",
    )
    if uploaded_file is not None:
        try:
            payload = uploaded_file.getvalue()
            source_key = _validate_upload(uploaded_file.name, payload)
            st.caption(f"Detekovany source_key: `{source_key}`")
            config = load_binary_meter_config(source_key, enabled_only=False)
            if config is not None:
                parsed = parse_binary_meter_file(config, payload)
                summary = summarize_parsed_file(parsed)
                st.write(
                    f"Vzorku: {summary['sample_count']} | "
                    f"platnych hodnot: {summary['finite_count']} | "
                    f"posledni cas: {_format_datetime(summary['last_timestamp'])}"
                )
            else:
                summary = _payload_summary(payload)
                st.write(f"Velikost: {summary['Velikost souboru']} | Vzorku: {summary['Vzorku celkem']}")
        except (ValueError, SQLAlchemyError) as exc:
            st.warning(str(exc))

    action_cols = st.columns(2)
    import_clicked = action_cols[0].button("Import", type="primary", width="stretch")
    close_clicked = action_cols[1].button("Zavrit", width="stretch")

    if close_clicked:
        _clear_dialog_state()
        st.rerun()
    if import_clicked:
        try:
            _handle_uploaded_file(uploaded_file)
        except (ValueError, SQLAlchemyError) as exc:
            st.error(str(exc))


def _render_import_dialog_body() -> None:
    pending = st.session_state.get(PENDING_UPLOAD_KEY)
    if isinstance(pending, dict):
        _render_registration_form(pending)
        return
    _render_upload_step()


def _open_import_dialog() -> None:
    if hasattr(st, "dialog"):
        st.dialog("Import .ts souboru")(_render_import_dialog_body)()
        return
    with st.container(border=True):
        st.subheader("Import .ts souboru")
        _render_import_dialog_body()


def render_dashboard() -> None:
    render_page_styles()
    st.title("Import elektromeru")
    st.caption(
        "Rucni import binarnich .ts souboru do dbo.Mereni_elektromery_BINARY "
        "a okamzite propsani rozdilovych dat do monitoring.Mereni_elektromery_vse."
    )
    _render_flash()

    action_cols = st.columns((1.4, 4.6))
    with action_cols[0]:
        if st.button("Nacist .ts soubor", type="primary", width="stretch"):
            st.session_state[UPLOAD_DIALOG_OPEN_KEY] = True
            st.session_state.pop(PENDING_UPLOAD_KEY, None)

    last_result = st.session_state.get(LAST_RESULT_KEY)
    if isinstance(last_result, BinaryMeterManualImportResult):
        _render_result(last_result)
    else:
        st.info("Import spustis pres tlacitko Nacist .ts soubor.")

    if st.session_state.get(UPLOAD_DIALOG_OPEN_KEY):
        _open_import_dialog()


render_dashboard()
