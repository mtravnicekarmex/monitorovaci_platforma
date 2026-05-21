from __future__ import annotations

import datetime
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
from sqlalchemy import func


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


def normalize_revize_payload(
    *,
    budova: object,
    datum: object,
    delka_platnosti: object,
    datum_platnosti: object,
    typ_zarizeni: object = None,
    nazev_revize: object = None,
    dodavatel: object = None,
    servisni_smlouva: object = None,
    soubor: object = None,
    poznamka: object = None,
) -> dict[str, object]:
    try:
        validity_years = Decimal(str(delka_platnosti).strip().replace(",", "."))
    except Exception as exc:
        raise ValueError("Pole Delka platnosti musi byt cislo.") from exc

    if validity_years <= 0:
        raise ValueError("Pole Delka platnosti musi byt kladne cislo.")
    if validity_years > Decimal("99.99"):
        raise ValueError("Pole Delka platnosti muze byt nejvyse 99.99.")

    return {
        "budova": _clean_required_text(budova, "Budova", max_length=50),
        "datum": _coerce_date(datum, "Datum revize"),
        "delka_platnosti": validity_years,
        "datum_platnosti": _coerce_date(datum_platnosti, "Platna do", required=False),
        "typ_zarizeni": _clean_optional_text(typ_zarizeni, max_length=100),
        "nazev_revize": _clean_optional_text(nazev_revize, max_length=255),
        "dodavatel": _clean_optional_text(dodavatel, max_length=200),
        "servisni_smlouva": _clean_optional_text(servisni_smlouva, max_length=500),
        "soubor": _clean_optional_text(soubor, max_length=500),
        "poznamka": _clean_optional_text(poznamka),
    }


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
        return _revize_to_dict(record)
    finally:
        session.close()


def create_revize_record(payload: dict[str, object]) -> int:
    session = get_session_pg()
    try:
        record = Revize(**payload)
        session.add(record)
        session.commit()
        return int(record.id)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_revize_record(revize_id: int, payload: dict[str, object]) -> None:
    session = get_session_pg()
    try:
        record = session.get(Revize, int(revize_id))
        if record is None:
            raise ValueError(f"Revize s ID {revize_id} nebyla nalezena.")
        for field, value in payload.items():
            setattr(record, field, value)
        session.commit()
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
                }
                for row in rows
            ]
        )
    finally:
        session.close()
