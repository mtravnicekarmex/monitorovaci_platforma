from __future__ import annotations

import datetime
import calendar
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
import re
import sys

import pandas as pd
import streamlit as st
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db.connect import get_session_pg
from moduly.evidence.revize.database.models import Revize, Revize_zarizeni


REVIZE_STATUS_ALL = "Vše"
REVIZE_STATUS_EXPIRED = "Po platnosti"
REVIZE_STATUS_DUE_SOON = "Do 30 dní"
REVIZE_STATUS_VALID = "Platné"
REVIZE_STATUS_NO_DATE = "Bez data platnosti"

REVIZE_STATUS_OPTIONS = (
    REVIZE_STATUS_ALL,
    REVIZE_STATUS_EXPIRED,
    REVIZE_STATUS_DUE_SOON,
    REVIZE_STATUS_VALID,
    REVIZE_STATUS_NO_DATE,
)

REVIZE_BUILDING_OPTIONS = ("F", "G")
REVIZE_EVIDENCE_SCHEMA = "evidence"

REVIZE_DISPLAY_COLUMNS = [
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


class RevizeLinkedDeviceValidationError(ValueError):
    def __init__(self, messages: Iterable[str]) -> None:
        self.messages = tuple(messages)
        super().__init__("Navazana zarizeni nelze ulozit:\n- " + "\n- ".join(self.messages))


def _clean_optional_text(value: object, *, max_length: int | None = None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if max_length is not None and len(text) > max_length:
        raise ValueError(f"Hodnota muze mit nejvyse {max_length} znaku.")
    return text


def _clean_required_text(value: object, label: str, *, max_length: int | None = None) -> str:
    text = _clean_optional_text(value, max_length=max_length)
    if text is None:
        raise ValueError(f"Pole {label} je povinne.")
    return text


def _coerce_date(value: object, label: str, *, required: bool = True) -> datetime.date | None:
    if value in ("", None):
        if required:
            raise ValueError(f"Pole {label} je povinne.")
        return None

    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value

    parsed = pd.to_datetime(value, dayfirst=True, errors="coerce")
    if pd.isna(parsed):
        if required:
            raise ValueError(f"Pole {label} nema platny format data.")
        return None
    return parsed.date()


def calculate_revize_valid_until(revision_date: datetime.date, validity_months: int) -> datetime.date:
    target_month_index = revision_date.month - 1 + int(validity_months)
    target_year = revision_date.year + target_month_index // 12
    target_month = target_month_index % 12 + 1
    target_day = min(revision_date.day, calendar.monthrange(target_year, target_month)[1])
    return datetime.date(target_year, target_month, target_day)


def _coerce_validity_months(value: object) -> Decimal:
    try:
        validity_months = Decimal(str(value).strip().replace(",", "."))
    except Exception as exc:
        raise ValueError("Pole Delka platnosti musi byt cislo v mesicich.") from exc

    if validity_months <= 0:
        raise ValueError("Pole Delka platnosti musi byt kladne cislo v mesicich.")
    if validity_months != validity_months.to_integral_value():
        raise ValueError("Pole Delka platnosti musi byt cele cislo v mesicich.")
    if validity_months > Decimal("99"):
        raise ValueError("Pole Delka platnosti muze byt nejvyse 99 mesicu.")

    return validity_months


def normalize_revize_payload(
    *,
    budova: object,
    datum: object,
    delka_platnosti: object,
    datum_platnosti: object = None,
    typ_zarizeni: object = None,
    nazev_revize: object = None,
    dodavatel: object = None,
    servisni_smlouva: object = None,
    soubor: object = None,
    poznamka: object = None,
) -> dict[str, object]:
    normalized_revision_date = _coerce_date(datum, "Datum revize")
    validity_months = _coerce_validity_months(delka_platnosti)

    return {
        "budova": _clean_required_text(budova, "Budova", max_length=50),
        "datum": normalized_revision_date,
        "delka_platnosti": validity_months,
        "datum_platnosti": calculate_revize_valid_until(normalized_revision_date, int(validity_months)),
        "typ_zarizeni": _clean_required_text(typ_zarizeni, "Zarizeni", max_length=100),
        "nazev_revize": _clean_optional_text(nazev_revize, max_length=255),
        "dodavatel": _clean_optional_text(dodavatel, max_length=200),
        "servisni_smlouva": _clean_optional_text(servisni_smlouva, max_length=500),
        "soubor": _clean_optional_text(soubor, max_length=500),
        "poznamka": _clean_optional_text(poznamka),
    }


@st.cache_data(ttl=60)
def load_evidence_device_type_options() -> list[str]:
    session = get_session_pg()
    try:
        rows = session.execute(
            text(
                """
                SELECT t.table_name
                FROM information_schema.tables t
                JOIN information_schema.columns c
                  ON c.table_schema = t.table_schema
                 AND c.table_name = t.table_name
                 AND c.column_name = 'fid'
                WHERE t.table_schema = :schema_name
                  AND t.table_type = 'BASE TABLE'
                ORDER BY t.table_name
                """
            ),
            {"schema_name": REVIZE_EVIDENCE_SCHEMA},
        ).scalars()
        return [str(row) for row in rows]
    finally:
        session.close()


def _parse_positive_device_id_token(token: str) -> tuple[int | None, str | None]:
    if token.isdecimal():
        device_id = int(token)
        if device_id <= 0:
            return None, "musi byt vetsi nez nula"
        return device_id, None

    try:
        device_id = int(token)
    except (TypeError, ValueError):
        return None, "neni cele cislo"

    if device_id <= 0:
        return None, "musi byt vetsi nez nula"

    return None, "pouzijte kladne cele cislo bez znamenka"


def parse_revize_linked_device_ids(value: object) -> list[int]:
    if value is None:
        return []

    text = str(value).strip()
    if not text:
        return []

    tokens = [token for token in re.split(r"[\s,;]+", text) if token]
    linked_device_ids: list[int] = []
    seen: set[int] = set()
    validation_errors: list[str] = []

    for token in tokens:
        device_id, error = _parse_positive_device_id_token(token)
        if error is not None:
            validation_errors.append(f"{token}: {error}")
            continue

        if device_id in seen:
            continue

        seen.add(device_id)
        linked_device_ids.append(device_id)

    if validation_errors:
        raise RevizeLinkedDeviceValidationError(validation_errors)

    return linked_device_ids


def _normalize_linked_device_ids(linked_device_ids: Iterable[int] | None) -> list[int]:
    normalized_ids: list[int] = []
    seen: set[int] = set()

    for raw_value in linked_device_ids or ():
        try:
            device_id = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Navazane zarizeni musi byt kladne cele cislo.") from exc
        if device_id <= 0:
            raise ValueError("Navazane zarizeni musi byt kladne cele cislo.")
        if device_id in seen:
            continue
        seen.add(device_id)
        normalized_ids.append(device_id)

    return normalized_ids


def _quote_pg_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _quote_pg_qualified_name(schema_name: str, table_name: str) -> str:
    return f"{_quote_pg_identifier(schema_name)}.{_quote_pg_identifier(table_name)}"


def _load_evidence_device_table_info(session, table_name: str) -> dict[str, bool] | None:
    row = session.execute(
        text(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM information_schema.tables t
                    WHERE t.table_schema = :schema_name
                      AND t.table_name = :table_name
                      AND t.table_type = 'BASE TABLE'
                ) AS table_exists,
                EXISTS (
                    SELECT 1
                    FROM information_schema.columns c
                    WHERE c.table_schema = :schema_name
                      AND c.table_name = :table_name
                      AND c.column_name = 'fid'
                ) AS has_fid,
                EXISTS (
                    SELECT 1
                    FROM information_schema.columns c
                    WHERE c.table_schema = :schema_name
                      AND c.table_name = :table_name
                      AND c.column_name = 'budova'
                ) AS has_budova
            """
        ),
        {"schema_name": REVIZE_EVIDENCE_SCHEMA, "table_name": table_name},
    ).mappings().one()

    if not row["table_exists"]:
        return None

    return {
        "has_fid": bool(row["has_fid"]),
        "has_budova": bool(row["has_budova"]),
    }


def validate_revize_linked_devices(
    session,
    *,
    budova: object,
    typ_zarizeni: object,
    linked_device_ids: Iterable[int] | None,
) -> list[int]:
    normalized_device_ids = _normalize_linked_device_ids(linked_device_ids)
    normalized_type = _clean_optional_text(typ_zarizeni, max_length=100)
    if normalized_type is None:
        raise RevizeLinkedDeviceValidationError(["Zarizeni: vyberte tabulku ze schematu evidence."])

    table_info = _load_evidence_device_table_info(session, normalized_type)
    if table_info is None:
        raise RevizeLinkedDeviceValidationError(
            [f"{normalized_type}: tabulka evidence.{_quote_pg_identifier(normalized_type)} neexistuje."]
        )
    if not table_info["has_fid"]:
        raise RevizeLinkedDeviceValidationError(
            [f"{normalized_type}: tabulka evidence.{_quote_pg_identifier(normalized_type)} nema sloupec fid."]
        )

    if not normalized_device_ids:
        return []

    normalized_building = _clean_required_text(budova, "Budova", max_length=50)
    qualified_table_name = _quote_pg_qualified_name(REVIZE_EVIDENCE_SCHEMA, normalized_type)
    selected_columns = "fid, budova" if table_info["has_budova"] else "fid"
    rows = session.execute(
        text(
            f"""
            SELECT {selected_columns}
            FROM {qualified_table_name}
            WHERE fid = ANY(:device_ids)
            """
        ),
        {"device_ids": normalized_device_ids},
    ).mappings().all()

    rows_by_fid: dict[int, list[object]] = {device_id: [] for device_id in normalized_device_ids}
    for row in rows:
        row_fid = int(row["fid"])
        if table_info["has_budova"]:
            rows_by_fid.setdefault(row_fid, []).append(row["budova"])
        else:
            rows_by_fid.setdefault(row_fid, []).append(None)

    validation_errors: list[str] = []
    for device_id in normalized_device_ids:
        row_buildings = rows_by_fid.get(device_id, [])
        if not row_buildings:
            validation_errors.append(f"{device_id}: nenalezeno v {qualified_table_name}.fid")
            continue

        if not table_info["has_budova"]:
            continue

        normalized_row_buildings = [
            str(row_building).strip()
            for row_building in row_buildings
            if row_building not in ("", None) and str(row_building).strip()
        ]
        if normalized_building in normalized_row_buildings:
            continue

        if normalized_row_buildings:
            unique_buildings = ", ".join(sorted(set(normalized_row_buildings)))
            validation_errors.append(
                f"{device_id}: patri do budovy {unique_buildings}, ale ve formulari je budova {normalized_building}"
            )
        else:
            validation_errors.append(f"{device_id}: v {qualified_table_name} nema vyplnenou budovu")

    if validation_errors:
        raise RevizeLinkedDeviceValidationError(validation_errors)

    return normalized_device_ids


def _format_date_for_message(value: object) -> str:
    if isinstance(value, datetime.datetime):
        return value.date().strftime("%d.%m.%Y")
    if isinstance(value, datetime.date):
        return value.strftime("%d.%m.%Y")
    return str(value or "-")


def _format_revize_duplicate_message(payload: dict[str, object]) -> str:
    building = payload.get("budova") or "-"
    revision_date = _format_date_for_message(payload.get("datum"))
    file_value = payload.get("soubor") or "bez souboru"
    return f"Revize pro budovu {building}, datum {revision_date} a soubor {file_value} uz existuje."


def _find_duplicate_revize_id(
    session,
    payload: dict[str, object],
    *,
    exclude_revize_id: int | None = None,
) -> int | None:
    statement = session.query(Revize.id).filter(
        Revize.budova == payload.get("budova"),
        Revize.datum == payload.get("datum"),
    )
    if exclude_revize_id is not None:
        statement = statement.filter(Revize.id != int(exclude_revize_id))

    soubor = payload.get("soubor")
    if soubor is None:
        statement = statement.filter(Revize.soubor.is_(None))
    else:
        statement = statement.filter(Revize.soubor == soubor)

    result = statement.first()
    if result is None:
        return None
    return int(result[0])


def _raise_if_duplicate_revize(
    session,
    payload: dict[str, object],
    *,
    exclude_revize_id: int | None = None,
) -> None:
    if _find_duplicate_revize_id(session, payload, exclude_revize_id=exclude_revize_id) is not None:
        raise ValueError(_format_revize_duplicate_message(payload))


def _is_revize_unique_constraint_error(exc: IntegrityError) -> bool:
    return "uq_revize_budova_datum_soubor" in str(exc.orig or exc)


def _revize_to_dict(record: Revize) -> dict[str, object]:
    return {
        "id": record.id,
        "budova": record.budova,
        "datum": record.datum,
        "delka_platnosti": float(record.delka_platnosti) if record.delka_platnosti is not None else None,
        "datum_platnosti": record.datum_platnosti,
        "typ_zarizeni": record.typ_zarizeni,
        "nazev_revize": record.nazev_revize,
        "dodavatel": record.dodavatel,
        "servisni_smlouva": record.servisni_smlouva,
        "soubor": record.soubor,
        "poznamka": record.poznamka,
    }


def classify_revize_status(
    datum_platnosti: object,
    *,
    reference_date: datetime.date,
    due_soon_days: int = 30,
) -> str:
    normalized_date = pd.to_datetime(datum_platnosti, errors="coerce")
    if pd.isna(normalized_date):
        return REVIZE_STATUS_NO_DATE

    expiry_date = normalized_date.date()
    if expiry_date < reference_date:
        return REVIZE_STATUS_EXPIRED
    if expiry_date <= reference_date + datetime.timedelta(days=due_soon_days):
        return REVIZE_STATUS_DUE_SOON
    return REVIZE_STATUS_VALID


def build_link_uri(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    lowered = text.casefold()
    if lowered.startswith(("http://", "https://", "file://")):
        return text

    try:
        path = Path(text)
        if path.is_absolute():
            return path.as_uri()
    except (OSError, ValueError):
        return None

    return None


def summarize_path_value(value: object) -> str:
    if value is None:
        return "-"

    text = str(value).strip()
    if not text:
        return "-"

    if text.casefold().startswith(("http://", "https://", "file://")):
        return text

    try:
        name = Path(text).name
    except OSError:
        return text
    return name or text


def prepare_revize_dataframe(
    df: pd.DataFrame,
    *,
    reference_date: datetime.date,
    due_soon_days: int = 30,
) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=REVIZE_DISPLAY_COLUMNS)

    prepared = df.copy()
    prepared["datum"] = pd.to_datetime(prepared["datum"], errors="coerce")
    prepared["datum_platnosti"] = pd.to_datetime(prepared["datum_platnosti"], errors="coerce")
    prepared["linked_devices"] = pd.to_numeric(prepared["linked_devices"], errors="coerce").fillna(0).astype(int)

    prepared["status"] = prepared["datum_platnosti"].map(
        lambda value: classify_revize_status(
            value,
            reference_date=reference_date,
            due_soon_days=due_soon_days,
        )
    )
    prepared["days_to_expiry"] = (
        prepared["datum_platnosti"].dt.date.map(
            lambda value: (value - reference_date).days if isinstance(value, datetime.date) else None
        )
        if "datum_platnosti" in prepared.columns
        else None
    )
    prepared["soubor_label"] = prepared["soubor"].map(summarize_path_value)
    prepared["soubor_link"] = prepared["soubor"].map(build_link_uri)
    prepared["servisni_smlouva_label"] = prepared["servisni_smlouva"].map(summarize_path_value)
    prepared["servisni_smlouva_link"] = prepared["servisni_smlouva"].map(build_link_uri)
    prepared["status_order"] = prepared["status"].map(
        {
            REVIZE_STATUS_EXPIRED: 0,
            REVIZE_STATUS_DUE_SOON: 1,
            REVIZE_STATUS_VALID: 2,
            REVIZE_STATUS_NO_DATE: 3,
        }
    ).fillna(9)

    prepared = prepared.sort_values(
        by=["status_order", "datum_platnosti", "datum", "nazev_revize"],
        ascending=[True, True, False, True],
        na_position="last",
    ).reset_index(drop=True)

    prepared["Datum revize"] = prepared["datum"].dt.strftime("%d.%m.%Y").fillna("-")
    prepared["Platná do"] = prepared["datum_platnosti"].dt.strftime("%d.%m.%Y").fillna("-")
    prepared["Dní do konce"] = prepared["days_to_expiry"].map(lambda value: "-" if pd.isna(value) else int(value))
    prepared["Budova"] = prepared["budova"].fillna("-")
    prepared["Název revize"] = prepared["nazev_revize"].fillna("-")
    prepared["Typ zařízení"] = prepared["typ_zarizeni"].fillna("-")
    prepared["Stav"] = prepared["status"]
    prepared["Dodavatel"] = prepared["dodavatel"].fillna("-")
    prepared["Navázaná zařízení"] = prepared["linked_devices"]
    prepared["Soubor"] = prepared["soubor_label"]
    prepared["Otevřít soubor"] = prepared["soubor_link"]
    prepared["Servisní smlouva"] = prepared["servisni_smlouva_label"]
    prepared["Otevřít smlouvu"] = prepared["servisni_smlouva_link"]
    prepared["Poznámka"] = prepared["poznamka"].fillna("-")
    return prepared


def filter_revize_dataframe(
    df: pd.DataFrame,
    *,
    buildings: Iterable[str] | None = None,
    device_types: Iterable[str] | None = None,
    status: str = REVIZE_STATUS_ALL,
    search_text: str = "",
) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    filtered = df.copy()

    building_values = [value for value in (buildings or []) if value]
    if building_values:
        filtered = filtered[filtered["budova"].isin(building_values)].copy()

    type_values = [value for value in (device_types or []) if value]
    if type_values:
        filtered = filtered[filtered["typ_zarizeni"].isin(type_values)].copy()

    if status != REVIZE_STATUS_ALL:
        filtered = filtered[filtered["status"] == status].copy()

    normalized_search = search_text.strip().casefold()
    if normalized_search:
        search_columns = (
            "nazev_revize",
            "typ_zarizeni",
            "dodavatel",
            "soubor",
            "servisni_smlouva",
            "poznamka",
        )
        search_mask = pd.Series(False, index=filtered.index)
        for column in search_columns:
            if column not in filtered.columns:
                continue
            search_mask = search_mask | filtered[column].fillna("").astype(str).str.casefold().str.contains(
                normalized_search,
                regex=False,
            )
        filtered = filtered[search_mask].copy()

    return filtered.reset_index(drop=True)


def build_revize_metrics(df: pd.DataFrame) -> dict[str, int]:
    if df.empty:
        return {
            "total": 0,
            "expired": 0,
            "due_soon": 0,
            "valid": 0,
            "missing_file": 0,
        }

    return {
        "total": int(len(df)),
        "expired": int((df["status"] == REVIZE_STATUS_EXPIRED).sum()),
        "due_soon": int((df["status"] == REVIZE_STATUS_DUE_SOON).sum()),
        "valid": int((df["status"] == REVIZE_STATUS_VALID).sum()),
        "missing_file": int(df["soubor"].fillna("").astype(str).str.strip().eq("").sum()),
    }


def load_revize_record_values(revize_id: int) -> dict[str, object] | None:
    session = get_session_pg()
    try:
        record = session.get(Revize, int(revize_id))
        if record is None:
            return None
        values = _revize_to_dict(record)
        linked_rows = (
            session.query(Revize_zarizeni)
            .filter(Revize_zarizeni.revize_id == int(revize_id))
            .order_by(Revize_zarizeni.zarizeni_id.asc())
            .all()
        )
        linked_device_types = sorted({row.typ_zarizeni for row in linked_rows if row.typ_zarizeni})
        values["linked_device_ids"] = [row.zarizeni_id for row in linked_rows]
        values["linked_device_types"] = linked_device_types
        values["linked_device_type"] = linked_device_types[0] if len(linked_device_types) == 1 else None
        return values
    finally:
        session.close()


def _replace_revize_device_links(
    session,
    *,
    revize_id: int,
    budova: object,
    typ_zarizeni: object,
    linked_device_ids: Iterable[int] | None,
) -> None:
    normalized_device_ids = validate_revize_linked_devices(
        session,
        budova=budova,
        typ_zarizeni=typ_zarizeni,
        linked_device_ids=linked_device_ids,
    )
    _write_revize_device_links(
        session,
        revize_id=revize_id,
        typ_zarizeni=typ_zarizeni,
        normalized_device_ids=normalized_device_ids,
    )


def _write_revize_device_links(
    session,
    *,
    revize_id: int,
    typ_zarizeni: object,
    normalized_device_ids: Iterable[int],
) -> None:
    normalized_type = _clean_optional_text(typ_zarizeni, max_length=100)

    session.query(Revize_zarizeni).filter(Revize_zarizeni.revize_id == int(revize_id)).delete(
        synchronize_session=False
    )
    if not normalized_device_ids:
        return

    session.add_all(
        Revize_zarizeni(
            revize_id=int(revize_id),
            typ_zarizeni=normalized_type,
            zarizeni_id=device_id,
        )
        for device_id in normalized_device_ids
    )


def create_revize_record(payload: dict[str, object], linked_device_ids: Iterable[int] | None = None) -> int:
    session = get_session_pg()
    try:
        normalized_device_ids = validate_revize_linked_devices(
            session,
            budova=payload.get("budova"),
            typ_zarizeni=payload.get("typ_zarizeni"),
            linked_device_ids=linked_device_ids,
        )
        _raise_if_duplicate_revize(session, payload)
        record = Revize(**payload)
        session.add(record)
        session.flush()
        _write_revize_device_links(
            session,
            revize_id=int(record.id),
            typ_zarizeni=payload.get("typ_zarizeni"),
            normalized_device_ids=normalized_device_ids,
        )
        session.commit()
        return int(record.id)
    except IntegrityError as exc:
        session.rollback()
        if _is_revize_unique_constraint_error(exc):
            raise ValueError(_format_revize_duplicate_message(payload)) from exc
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_revize_record(
    revize_id: int,
    payload: dict[str, object],
    linked_device_ids: Iterable[int] | None = None,
) -> None:
    session = get_session_pg()
    try:
        record = session.get(Revize, int(revize_id))
        if record is None:
            raise ValueError(f"Revize s ID {revize_id} nebyla nalezena.")

        normalized_device_ids = None
        if linked_device_ids is not None:
            normalized_device_ids = validate_revize_linked_devices(
                session,
                budova=payload.get("budova"),
                typ_zarizeni=payload.get("typ_zarizeni"),
                linked_device_ids=linked_device_ids,
            )
        _raise_if_duplicate_revize(session, payload, exclude_revize_id=int(revize_id))
        for field, value in payload.items():
            setattr(record, field, value)
        if normalized_device_ids is not None:
            _write_revize_device_links(
                session,
                revize_id=int(revize_id),
                typ_zarizeni=payload.get("typ_zarizeni"),
                normalized_device_ids=normalized_device_ids,
            )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if _is_revize_unique_constraint_error(exc):
            raise ValueError(_format_revize_duplicate_message(payload)) from exc
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_revize_rows() -> pd.DataFrame:
    session = get_session_pg()
    try:
        rows = (
            session.query(
                Revize.id.label("id"),
                Revize.budova.label("budova"),
                Revize.datum.label("datum"),
                Revize.delka_platnosti.label("delka_platnosti"),
                Revize.datum_platnosti.label("datum_platnosti"),
                Revize.typ_zarizeni.label("typ_zarizeni"),
                Revize.nazev_revize.label("nazev_revize"),
                Revize.dodavatel.label("dodavatel"),
                Revize.servisni_smlouva.label("servisni_smlouva"),
                Revize.soubor.label("soubor"),
                Revize.poznamka.label("poznamka"),
                func.count(Revize_zarizeni.id).label("linked_devices"),
                func.count(func.distinct(Revize_zarizeni.typ_zarizeni)).label("linked_device_type_count"),
                func.min(Revize_zarizeni.typ_zarizeni).label("linked_device_type"),
            )
            .outerjoin(Revize_zarizeni, Revize.id == Revize_zarizeni.revize_id)
            .group_by(
                Revize.id,
                Revize.budova,
                Revize.datum,
                Revize.delka_platnosti,
                Revize.datum_platnosti,
                Revize.typ_zarizeni,
                Revize.nazev_revize,
                Revize.dodavatel,
                Revize.servisni_smlouva,
                Revize.soubor,
                Revize.poznamka,
            )
            .order_by(Revize.datum_platnosti.asc().nulls_last(), Revize.datum.desc(), Revize.id.desc())
            .all()
        )

        return pd.DataFrame(
            [
                {
                    "id": row.id,
                    "budova": row.budova,
                    "datum": row.datum,
                    "delka_platnosti": float(row.delka_platnosti) if row.delka_platnosti is not None else None,
                    "datum_platnosti": row.datum_platnosti,
                    "typ_zarizeni": row.typ_zarizeni,
                    "nazev_revize": row.nazev_revize,
                    "dodavatel": row.dodavatel,
                    "servisni_smlouva": row.servisni_smlouva,
                    "soubor": row.soubor,
                    "poznamka": row.poznamka,
                    "linked_devices": row.linked_devices,
                    "linked_device_type_count": row.linked_device_type_count,
                    "linked_device_type": row.linked_device_type,
                }
                for row in rows
            ]
        )
    finally:
        session.close()
