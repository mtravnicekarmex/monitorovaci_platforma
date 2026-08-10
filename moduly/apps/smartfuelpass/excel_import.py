from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO
import re
import unicodedata
from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.db.connect import get_session_pg
from moduly.apps.smartfuelpass.database.db_init import ensure_smartfuelpass_tables
from moduly.apps.smartfuelpass.database.models import SmartFuelPassRelace
from moduly.mereni.time_semantics import build_time_columns


SMARTFUELPASS_SOURCE_NAME = "SMARTFUELPASS"
COMPLETED_STATUS = "dokonceno"
ROW_STATUS_NEW = "new"
ROW_STATUS_EXISTING = "existing"
ROW_STATUS_EXISTING_WITH_DIFFERENCES = "existing_with_differences"
ROW_STATUS_IGNORED = "ignored"

_EMPTY_MARKERS = {"", "-", "nan", "none", "null", "nat"}
_DATETIME_PATTERN = re.compile(
    r"\d{1,2}\.\d{1,2}\.\d{4}\s+\d{1,2}:\d{2}(?::\d{2})?"
)
_REQUIRED_HEADER_KEYS = {
    "purchase_id",
    "status",
    "energy_kwh",
    "started_at",
    "ended_at",
    "location",
    "amount",
}
_COLUMN_ALIASES = {
    "public_id": ("Veřejné ID",),
    "external_cpo_id": ("ID v externím CPO systému",),
    "status": ("Stav",),
    "energy_kwh": ("Energie",),
    "purchase_id": ("Nákup",),
    "additional_payment": ("Dodatečná inkasní platba",),
    "started_at": ("Čas spuštění",),
    "ended_at": ("Čas ukončení",),
    "charging_duration": ("Trvání nabíjení",),
    "location": ("Název EV lokace",),
    "operator": ("Operator", "Operátor"),
    "connector_id": ("Konektor EVSE ID",),
    "charge_point_identifier": ("Identifikátor nabíjecího bodu",),
    "power": ("Výkon",),
    "current_ampere": ("Proud [A]",),
    "voltage": ("Napětí [V]",),
    "format": ("Format", "Formát"),
    "power_type": ("Typ výkonu",),
    "tariff": ("Název tarifu",),
    "amount": ("Suma",),
    "commission": ("Provize",),
    "amount_without_commission": ("Částka bez provize",),
    "currency": ("Měna",),
    "adhoc": ("AdHoc nabíjení",),
}


class SmartFuelPassExcelImportError(ValueError):
    """Raised when the SmartFuelPass Excel file cannot be parsed safely."""


@dataclass(frozen=True)
class SmartFuelPassExcelParsedRow:
    source_row_number: int
    raw_status: str | None
    id_relace: str | None
    kwh: Decimal | None
    suma: Decimal | None
    started_at: datetime | None
    ended_at: datetime | None
    lokace: str | None
    connector_id: str | None
    tarif: str | None
    is_completed: bool
    validation_errors: tuple[str, ...]
    db_row: dict[str, Any] | None


@dataclass(frozen=True)
class SmartFuelPassExcelPreviewRow:
    source_row_number: int
    row_status: str
    status_label: str
    existing_in_db: bool
    can_import: bool
    note: str
    id_relace: str | None
    raw_status: str | None
    started_at: datetime | None
    ended_at: datetime | None
    lokace: str | None
    connector_id: str | None
    kwh: float | None
    suma: float | None
    tarif: str | None
    difference_fields: tuple[str, ...]


def _canonical_text(value: object) -> str:
    text = str(value).replace("\xa0", " ")
    normalized = unicodedata.normalize("NFKD", text)
    without_marks = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", without_marks).strip().casefold()


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    text = re.sub(r"\s+", " ", str(value).replace("\xa0", " ")).strip()
    if _canonical_text(text) in _EMPTY_MARKERS:
        return None
    return text


def _canonical_aliases() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for key, labels in _COLUMN_ALIASES.items():
        for label in labels:
            aliases[_canonical_text(label)] = key
    return aliases


def _find_header_row(raw_dataframe: pd.DataFrame) -> int:
    aliases = _canonical_aliases()
    max_rows = min(100, len(raw_dataframe))
    for row_index in range(max_rows):
        row_values = {
            aliases[_canonical_text(value)]
            for value in raw_dataframe.iloc[row_index].tolist()
            if _clean_text(value) is not None and _canonical_text(value) in aliases
        }
        if _REQUIRED_HEADER_KEYS.issubset(row_values):
            return row_index
    raise SmartFuelPassExcelImportError(
        "V XLSX souboru nebyl nalezen řádek hlavičky ChargingSessions."
    )


def _load_excel_dataframe(content: bytes) -> tuple[pd.DataFrame, int]:
    if not content:
        raise SmartFuelPassExcelImportError("XLSX soubor je prázdný.")

    try:
        workbook = pd.ExcelFile(BytesIO(content))
    except Exception as exc:
        raise SmartFuelPassExcelImportError(
            "XLSX soubor se nepodařilo otevřít."
        ) from exc

    sheet_name = next(
        (
            name
            for name in workbook.sheet_names
            if _canonical_text(name) == "chargingsessions"
        ),
        workbook.sheet_names[0],
    )

    try:
        raw_dataframe = pd.read_excel(
            workbook,
            sheet_name=sheet_name,
            header=None,
            dtype=object,
        )
        header_row_index = _find_header_row(raw_dataframe)
        dataframe = pd.read_excel(
            workbook,
            sheet_name=sheet_name,
            header=header_row_index,
            dtype=object,
        )
    except SmartFuelPassExcelImportError:
        raise
    except Exception as exc:
        raise SmartFuelPassExcelImportError(
            "XLSX soubor se nepodařilo načíst do tabulky."
        ) from exc

    return dataframe, header_row_index


def _resolve_columns(dataframe: pd.DataFrame) -> dict[str, str]:
    aliases = _canonical_aliases()
    resolved: dict[str, str] = {}
    for column in dataframe.columns:
        canonical = _canonical_text(column)
        if canonical in aliases and aliases[canonical] not in resolved:
            resolved[aliases[canonical]] = column

    missing = sorted(_REQUIRED_HEADER_KEYS - set(resolved))
    if missing:
        raise SmartFuelPassExcelImportError(
            "XLSX soubor neobsahuje povinné sloupce: " + ", ".join(missing)
        )
    return resolved


def _row_is_empty(row: pd.Series, columns: dict[str, str]) -> bool:
    return all(_clean_text(row.get(column)) is None for column in columns.values())


def _parse_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))

    text = _clean_text(value)
    if text is None:
        return None
    cleaned = re.sub(r"[^0-9,.\-]", "", text.replace(" ", ""))
    if not cleaned or cleaned in {"-", ".", ","}:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)

    text = _clean_text(value)
    if text is None:
        return None
    match = _DATETIME_PATTERN.search(text)
    if match:
        text = match.group(0)
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        return None
    if isinstance(parsed, pd.Timestamp):
        return parsed.to_pydatetime().replace(tzinfo=None)
    if isinstance(parsed, datetime):
        return parsed.replace(tzinfo=None)
    return None


def _normalize_location(value: object) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    text = re.sub(r"\s+null\s*$", "", text, flags=re.IGNORECASE).strip()
    parts = [part.strip() for part in re.split(r"\s+-\s+", text) if part.strip()]
    if len(parts) >= 2:
        return f"{parts[0]} - {parts[1]}"
    return text or None


def _normalize_text_field(value: object) -> str | None:
    text = _clean_text(value)
    if text is None:
        return None
    return text


def _round_decimal(value: Decimal, exponent: str) -> Decimal:
    return value.quantize(Decimal(exponent), rounding=ROUND_HALF_UP)


def _build_interval_time_columns(started_at: datetime, ended_at: datetime) -> dict[str, Any]:
    started_columns = build_time_columns(started_at, SMARTFUELPASS_SOURCE_NAME)
    ended_columns = build_time_columns(ended_at, SMARTFUELPASS_SOURCE_NAME)
    return {
        "source_started_at": started_columns["source_date"],
        "source_ended_at": ended_columns["source_date"],
        "started_at_utc": started_columns["time_utc"],
        "ended_at_utc": ended_columns["time_utc"],
        "time_basis": started_columns["time_basis"],
        "source_timezone": started_columns["source_timezone"],
        "started_utc_offset_minutes": started_columns["source_utc_offset_minutes"],
        "ended_utc_offset_minutes": ended_columns["source_utc_offset_minutes"],
        "started_time_fold": started_columns["time_fold"],
        "ended_time_fold": ended_columns["time_fold"],
        "timestamp_position": started_columns["timestamp_position"],
    }


def _build_db_row(
    *,
    id_relace: str,
    kwh: Decimal,
    suma: Decimal,
    started_at: datetime,
    ended_at: datetime,
    lokace: str,
    connector_id: str | None,
    tarif: str | None,
) -> dict[str, Any]:
    duration_seconds = Decimal(str((ended_at - started_at).total_seconds()))
    speed = None
    if duration_seconds > 0:
        speed = _round_decimal(kwh * Decimal(3600) / duration_seconds, "0.001")

    return {
        "id_relace": id_relace,
        "kwh": float(_round_decimal(kwh, "0.001")),
        "tarif": tarif,
        "battery_status": None,
        "suma": float(_round_decimal(suma, "0.01")),
        "connector_id": connector_id,
        "started_at": started_at,
        "ended_at": ended_at,
        **_build_interval_time_columns(started_at, ended_at),
        "lokace": lokace,
        "rychlost_nabijeni": None if speed is None else float(speed),
    }


def _parse_excel_row(
    row: pd.Series,
    *,
    source_row_number: int,
    columns: dict[str, str],
) -> SmartFuelPassExcelParsedRow:
    raw_status = _normalize_text_field(row.get(columns["status"]))
    id_relace = _normalize_text_field(row.get(columns["purchase_id"]))
    kwh = _parse_decimal(row.get(columns["energy_kwh"]))
    suma = _parse_decimal(row.get(columns["amount"]))
    started_at = _parse_datetime(row.get(columns["started_at"]))
    ended_at = _parse_datetime(row.get(columns["ended_at"]))
    lokace = _normalize_location(row.get(columns["location"]))
    connector_id = _normalize_text_field(row.get(columns.get("connector_id", "")))
    tarif = _normalize_text_field(row.get(columns.get("tariff", "")))
    is_completed = _canonical_text(raw_status or "") == COMPLETED_STATUS

    errors: list[str] = []
    if not is_completed:
        errors.append("Stav není Dokončeno.")
    else:
        if not id_relace:
            errors.append("Chybí Nákup / ID relace.")
        if kwh is None:
            errors.append("Chybí energie.")
        elif kwh < 0:
            errors.append("Energie je záporná.")
        if suma is None:
            errors.append("Chybí Suma.")
        elif suma < 0:
            errors.append("Suma je záporná.")
        if started_at is None:
            errors.append("Chybí nebo nejde přečíst Čas spuštění.")
        if ended_at is None:
            errors.append("Chybí nebo nejde přečíst Čas ukončení.")
        if started_at is not None and ended_at is not None and ended_at <= started_at:
            errors.append("Čas ukončení není po času spuštění.")
        if not lokace:
            errors.append("Chybí Název EV lokace.")

    db_row = None
    if not errors and id_relace and kwh is not None and suma is not None and started_at and ended_at and lokace:
        db_row = _build_db_row(
            id_relace=id_relace,
            kwh=kwh,
            suma=suma,
            started_at=started_at,
            ended_at=ended_at,
            lokace=lokace,
            connector_id=connector_id,
            tarif=tarif,
        )

    return SmartFuelPassExcelParsedRow(
        source_row_number=source_row_number,
        raw_status=raw_status,
        id_relace=id_relace,
        kwh=kwh,
        suma=suma,
        started_at=started_at,
        ended_at=ended_at,
        lokace=lokace,
        connector_id=connector_id,
        tarif=tarif,
        is_completed=is_completed,
        validation_errors=tuple(errors),
        db_row=db_row,
    )


def parse_smartfuelpass_excel_rows(content: bytes) -> list[SmartFuelPassExcelParsedRow]:
    dataframe, header_row_index = _load_excel_dataframe(content)
    columns = _resolve_columns(dataframe)
    rows: list[SmartFuelPassExcelParsedRow] = []
    first_data_row_number = header_row_index + 2
    for dataframe_index, row in dataframe.iterrows():
        if _row_is_empty(row, columns):
            continue
        rows.append(
            _parse_excel_row(
                row,
                source_row_number=first_data_row_number + int(dataframe_index),
                columns=columns,
            )
        )
    return rows


def _existing_value(existing_row: object, field_name: str) -> object:
    if isinstance(existing_row, dict):
        return existing_row.get(field_name)
    return getattr(existing_row, field_name, None)


def _decimal_values_match(
    expected: object,
    actual: object,
    exponent: str,
) -> bool:
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    try:
        expected_decimal = _round_decimal(Decimal(str(expected)), exponent)
        actual_decimal = _round_decimal(Decimal(str(actual)), exponent)
    except InvalidOperation:
        return False
    return expected_decimal == actual_decimal


def _datetime_values_match(expected: object, actual: object) -> bool:
    if expected is None and actual is None:
        return True
    if expected is None or actual is None:
        return False
    if isinstance(expected, pd.Timestamp):
        expected = expected.to_pydatetime()
    if isinstance(actual, pd.Timestamp):
        actual = actual.to_pydatetime()
    if not isinstance(expected, datetime) or not isinstance(actual, datetime):
        return False
    expected_normalized = expected.replace(second=0, microsecond=0, tzinfo=None)
    actual_normalized = actual.replace(second=0, microsecond=0, tzinfo=None)
    return expected_normalized == actual_normalized


def _text_values_match(expected: object, actual: object) -> bool:
    return (_clean_text(expected) or "") == (_clean_text(actual) or "")


def _difference_fields(
    parsed_row: SmartFuelPassExcelParsedRow,
    existing_row: object,
) -> tuple[str, ...]:
    if parsed_row.db_row is None:
        return ()

    differences: list[str] = []
    numeric_fields = {
        "kwh": "0.001",
        "suma": "0.01",
        "rychlost_nabijeni": "0.001",
    }
    datetime_fields = ("started_at", "ended_at")
    text_fields = ("lokace", "connector_id", "tarif")

    for field_name, exponent in numeric_fields.items():
        if not _decimal_values_match(
            parsed_row.db_row.get(field_name),
            _existing_value(existing_row, field_name),
            exponent,
        ):
            differences.append(field_name)
    for field_name in datetime_fields:
        if not _datetime_values_match(
            parsed_row.db_row.get(field_name),
            _existing_value(existing_row, field_name),
        ):
            differences.append(field_name)
    for field_name in text_fields:
        if not _text_values_match(
            parsed_row.db_row.get(field_name),
            _existing_value(existing_row, field_name),
        ):
            differences.append(field_name)

    return tuple(differences)


def _preview_row(
    parsed_row: SmartFuelPassExcelParsedRow,
    existing_rows_by_id: dict[str, object],
) -> SmartFuelPassExcelPreviewRow:
    existing_row = (
        existing_rows_by_id.get(parsed_row.id_relace)
        if parsed_row.id_relace is not None
        else None
    )
    existing_in_db = existing_row is not None

    if parsed_row.db_row is not None and not existing_in_db:
        row_status = ROW_STATUS_NEW
        status_label = "Nový"
        note = "Připraveno k importu."
        can_import = True
        differences: tuple[str, ...] = ()
    elif parsed_row.db_row is not None and existing_in_db:
        differences = _difference_fields(parsed_row, existing_row)
        can_import = False
        if differences:
            row_status = ROW_STATUS_EXISTING_WITH_DIFFERENCES
            status_label = "Již v databázi – rozdíly"
            note = (
                "Neimportuje se; existující relace se nemění. Rozdíly: "
                + ", ".join(differences)
                + "."
            )
        else:
            row_status = ROW_STATUS_EXISTING
            status_label = "Již v databázi"
            note = "Neimportuje se; relace už je v databázi."
    else:
        row_status = ROW_STATUS_IGNORED
        status_label = "Ignorováno"
        can_import = False
        differences = ()
        note = " ".join(parsed_row.validation_errors) or "Řádek není importovatelný."

    return SmartFuelPassExcelPreviewRow(
        source_row_number=parsed_row.source_row_number,
        row_status=row_status,
        status_label=status_label,
        existing_in_db=existing_in_db,
        can_import=can_import,
        note=note,
        id_relace=parsed_row.id_relace,
        raw_status=parsed_row.raw_status,
        started_at=parsed_row.started_at,
        ended_at=parsed_row.ended_at,
        lokace=parsed_row.lokace,
        connector_id=parsed_row.connector_id,
        kwh=None if parsed_row.kwh is None else float(_round_decimal(parsed_row.kwh, "0.001")),
        suma=None if parsed_row.suma is None else float(_round_decimal(parsed_row.suma, "0.01")),
        tarif=parsed_row.tarif,
        difference_fields=differences,
    )


def _preview_response(
    *,
    filename: str | None,
    parsed_rows: list[SmartFuelPassExcelParsedRow],
    existing_rows_by_id: dict[str, object],
) -> dict[str, Any]:
    rows = [_preview_row(row, existing_rows_by_id) for row in parsed_rows]
    new_row_count = sum(1 for row in rows if row.row_status == ROW_STATUS_NEW)
    existing_row_count = sum(
        1
        for row in rows
        if row.row_status in {ROW_STATUS_EXISTING, ROW_STATUS_EXISTING_WITH_DIFFERENCES}
    )
    existing_with_differences_count = sum(
        1 for row in rows if row.row_status == ROW_STATUS_EXISTING_WITH_DIFFERENCES
    )
    ignored_row_count = sum(1 for row in rows if row.row_status == ROW_STATUS_IGNORED)
    invalid_completed_row_count = sum(
        1 for row in parsed_rows if row.is_completed and row.validation_errors
    )
    not_completed_row_count = sum(1 for row in parsed_rows if not row.is_completed)

    return {
        "filename": filename,
        "raw_row_count": len(parsed_rows),
        "completed_row_count": sum(1 for row in parsed_rows if row.is_completed),
        "new_row_count": new_row_count,
        "existing_row_count": existing_row_count,
        "existing_with_differences_count": existing_with_differences_count,
        "ignored_row_count": ignored_row_count,
        "invalid_completed_row_count": invalid_completed_row_count,
        "not_completed_row_count": not_completed_row_count,
        "importable_row_count": new_row_count,
        "inserted_count": None,
        "rows": [row.__dict__ for row in rows],
    }


def _load_existing_rows(
    db_session: Session,
    parsed_rows: list[SmartFuelPassExcelParsedRow],
) -> dict[str, SmartFuelPassRelace]:
    ids = sorted({row.id_relace for row in parsed_rows if row.id_relace})
    if not ids:
        return {}
    existing_rows = (
        db_session.query(SmartFuelPassRelace)
        .filter(SmartFuelPassRelace.id_relace.in_(ids))
        .all()
    )
    return {row.id_relace: row for row in existing_rows}


def build_smartfuelpass_excel_preview(
    *,
    content: bytes,
    filename: str | None = None,
    db_session: Session | None = None,
) -> dict[str, Any]:
    owns_session = db_session is None
    session = db_session or get_session_pg()
    try:
        parsed_rows = parse_smartfuelpass_excel_rows(content)
        existing_rows_by_id = _load_existing_rows(session, parsed_rows)
        return _preview_response(
            filename=filename,
            parsed_rows=parsed_rows,
            existing_rows_by_id=existing_rows_by_id,
        )
    finally:
        if owns_session:
            session.close()


def _new_rows_for_import(
    parsed_rows: list[SmartFuelPassExcelParsedRow],
    existing_rows_by_id: dict[str, object],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for parsed_row in parsed_rows:
        if (
            parsed_row.db_row is not None
            and parsed_row.id_relace is not None
            and parsed_row.id_relace not in existing_rows_by_id
        ):
            rows.append(parsed_row.db_row)
    return rows


def insert_new_smartfuelpass_excel_rows(
    db_session: Session,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0

    stmt = insert(SmartFuelPassRelace).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["id_relace"])
    result = db_session.execute(stmt)
    return int(result.rowcount or 0)


def import_smartfuelpass_excel_records(
    *,
    content: bytes,
    filename: str | None = None,
    db_session: Session | None = None,
) -> dict[str, Any]:
    ensure_smartfuelpass_tables()

    owns_session = db_session is None
    session = db_session or get_session_pg()
    try:
        parsed_rows = parse_smartfuelpass_excel_rows(content)
        existing_rows_by_id = _load_existing_rows(session, parsed_rows)
        rows_to_insert = _new_rows_for_import(parsed_rows, existing_rows_by_id)
        inserted_count = insert_new_smartfuelpass_excel_rows(session, rows_to_insert)
        session.commit()

        refreshed_existing_rows_by_id = _load_existing_rows(session, parsed_rows)
        response = _preview_response(
            filename=filename,
            parsed_rows=parsed_rows,
            existing_rows_by_id=refreshed_existing_rows_by_id,
        )
        response["inserted_count"] = inserted_count
        response["requested_insert_count"] = len(rows_to_insert)
        response["skipped_existing_count"] = response["existing_row_count"]
        response["skipped_ignored_count"] = response["ignored_row_count"]
        return response
    except Exception:
        session.rollback()
        raise
    finally:
        if owns_session:
            session.close()
