from __future__ import annotations

import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db.connect import get_session_ms, get_session_pg
from moduly.apps.dashboard.auth import get_allowed_devices, is_admin
from moduly.apps.dashboard.device_photo import (
    build_photo_data_uri,
    render_clickable_device_photo,
    resolve_photo_path,
)
from moduly.apps.dashboard.time_semantics import (
    TIME_SEMANTICS_COLUMNS,
    add_chart_time,
    local_date_range_to_utc,
)
from moduly.apps.dashboard.vodomery_shared import (
    format_consumption_dataframe,
    format_consumption_with_unit,
    format_value,
    normalize_date_range,
    render_page_styles,
    round_consumption_columns,
)
from moduly.mereni.time_semantics import build_time_columns
from moduly.mereni.kalorimetry.database.models import (
    Kalorimetr_areal_Zarizeni,
    Mereni_kalorimetry,
)


MAX_IDENT_OPTIONS = 500
KALORIMETRY_SOURCE_NAME = "KALORIMETRY"


def get_kalorimetry_access_context() -> tuple[bool, tuple[str, ...]]:
    user_is_admin = is_admin()
    allowed_devices = get_allowed_devices()
    if not user_is_admin and not allowed_devices:
        st.warning("Prihlasenemu uzivateli nejsou prirazena zadna zarizeni.")
        st.stop()
    return user_is_admin, allowed_devices


@st.cache_data(ttl=60)
def load_ident_options(allowed_devices: tuple[str, ...], user_is_admin: bool) -> list[str]:
    session = get_session_pg()
    try:
        query = (
            session.query(Mereni_kalorimetry.identifikace)
            .filter(Mereni_kalorimetry.identifikace.is_not(None))
            .filter(Mereni_kalorimetry.platne.is_(True))
            .distinct()
        )
        if not user_is_admin:
            query = query.filter(Mereni_kalorimetry.identifikace.in_(allowed_devices))
        rows = query.order_by(Mereni_kalorimetry.identifikace).limit(MAX_IDENT_OPTIONS).all()
        return [row[0] for row in rows if row[0]]
    finally:
        session.close()


def build_datetime_range(start_date: datetime.date, end_date: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(end_date, datetime.time.max)
    return start_dt, end_dt


def _empty_time_columns() -> dict[str, object]:
    return {column: None for column in TIME_SEMANTICS_COLUMNS}


def add_time_semantics_columns(df: pd.DataFrame, *, date_column: str = "date") -> pd.DataFrame:
    prepared = df.copy()
    for column in TIME_SEMANTICS_COLUMNS:
        if column not in prepared.columns:
            prepared[column] = pd.NA

    if prepared.empty or date_column not in prepared.columns:
        return prepared

    timestamps = pd.to_datetime(prepared[date_column], errors="coerce")
    time_records = []
    for timestamp in timestamps:
        if pd.isna(timestamp):
            time_records.append(_empty_time_columns())
            continue
        source_date = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
        time_records.append(build_time_columns(source_date, KALORIMETRY_SOURCE_NAME))

    time_df = pd.DataFrame(time_records, index=prepared.index)
    for column in TIME_SEMANTICS_COLUMNS:
        prepared[column] = prepared[column].where(prepared[column].notna(), time_df[column])
    prepared["time_utc"] = pd.to_datetime(prepared["time_utc"], utc=True, errors="coerce")
    return add_chart_time(prepared)


@st.cache_data(ttl=60)
def load_measurement_series(
    identifikace: str,
    start_date: datetime.date,
    end_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> pd.DataFrame:
    if not user_is_admin and identifikace not in allowed_devices:
        return pd.DataFrame()

    session = get_session_pg()
    try:
        start_utc, end_utc = local_date_range_to_utc(start_date, end_date)
        rows = (
            session.query(
                Mereni_kalorimetry.date,
                Mereni_kalorimetry.identifikace,
                Mereni_kalorimetry.seriove_cislo,
                Mereni_kalorimetry.spotreba_energie,
                Mereni_kalorimetry.objem,
                Mereni_kalorimetry.platne,
                Mereni_kalorimetry.delta,
                Mereni_kalorimetry.gap_detected,
                Mereni_kalorimetry.synthetic,
                Mereni_kalorimetry.reset_detected,
                Mereni_kalorimetry.zdroj,
                Mereni_kalorimetry.source_date,
                Mereni_kalorimetry.time_utc,
                Mereni_kalorimetry.time_basis,
                Mereni_kalorimetry.source_timezone,
                Mereni_kalorimetry.source_utc_offset_minutes,
                Mereni_kalorimetry.time_fold,
                Mereni_kalorimetry.timestamp_position,
            )
            .filter(
                Mereni_kalorimetry.identifikace == identifikace,
                Mereni_kalorimetry.time_utc >= start_utc,
                Mereni_kalorimetry.time_utc < end_utc,
            )
            .order_by(Mereni_kalorimetry.time_utc.asc())
            .all()
        )
        measurements = pd.DataFrame(
            rows,
            columns=[
                "date",
                "identifikace",
                "seriove_cislo",
                "spotreba_energie",
                "objem",
                "platne",
                "delta",
                "gap_detected",
                "synthetic",
                "reset_detected",
                "zdroj",
                "source_date",
                "time_utc",
                "time_basis",
                "source_timezone",
                "source_utc_offset_minutes",
                "time_fold",
                "timestamp_position",
            ],
        )
        return add_time_semantics_columns(measurements)
    finally:
        session.close()


def _serialize_device_detail(device: Kalorimetr_areal_Zarizeni) -> dict[str, object]:
    return {
        "identifikace": device.identifikace,
        "seriove_cislo": device.seriove_cislo,
        "mbus": device.MBUS,
        "objekt": device.objekt,
        "patro": device.patro,
        "mistnost": device.mistnost,
        "umisteni": device.umisteni,
        "napaji": device.napaji,
        "zdroj": device.zdroj,
        "zdroj_mereni": device.zdroj_mereni,
        "koncovy_odberatel": device.koncovy_odberatel,
        "platnost_cejchu": device.platnost_cejchu,
        "poznamka": device.poznamka_kalorimetry,
        "foto": device.foto,
    }


@st.cache_data(ttl=60)
def load_device_detail(identifikace: str, allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object] | None:
    if not user_is_admin and identifikace not in allowed_devices:
        return None

    session_ms = get_session_ms()
    try:
        device = (
            session_ms.query(Kalorimetr_areal_Zarizeni)
            .filter(Kalorimetr_areal_Zarizeni.identifikace == identifikace)
            .one_or_none()
        )
        if device is None:
            return None
        return _serialize_device_detail(device)
    finally:
        session_ms.close()


def resolve_device_photo_path(photo_value: object) -> Path | None:
    return resolve_photo_path(photo_value, project_root=PROJECT_ROOT)


def build_device_photo_data_uri(photo_path: Path | None) -> str | None:
    return build_photo_data_uri(photo_path)


def render_device_photo(device_detail: dict[str, object] | None) -> bool:
    return render_clickable_device_photo(
        device_detail,
        project_root=PROJECT_ROOT,
        aria_label="Zvětšit fotografii kalorimetru",
    )


def format_energy_metric(value: object) -> str:
    return format_consumption_with_unit(value, unit="").strip()
