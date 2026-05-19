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
from moduly.apps.dashboard.time_semantics import TIME_SEMANTICS_COLUMNS, local_date_range_to_utc
from moduly.apps.dashboard.vodomery_shared import (
    filter_min_duration_events,
    format_consumption_dataframe,
    format_consumption_with_unit,
    format_value,
    normalize_date_range,
    prepare_event_display_dataframe,
    render_filter_summary,
    render_page_styles,
    require_dashboard_api_token,
    round_consumption_columns,
)
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    Plynomer_areal_Zarizeni,
)


MAX_IDENT_OPTIONS = 500


def get_plynomery_access_context() -> tuple[bool, tuple[str, ...]]:
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
            session.query(Mereni_plynomery.identifikace)
            .filter(Mereni_plynomery.identifikace.is_not(None))
            .filter(Mereni_plynomery.platne.is_(True))
            .distinct()
        )
        if not user_is_admin:
            query = query.filter(Mereni_plynomery.identifikace.in_(allowed_devices))
        rows = query.order_by(Mereni_plynomery.identifikace).limit(MAX_IDENT_OPTIONS).all()
        return [row[0] for row in rows if row[0]]
    finally:
        session.close()


def build_datetime_range(start_date: datetime.date, end_date: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(end_date, datetime.time.max)
    return start_dt, end_dt


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
                Mereni_plynomery.date,
                Mereni_plynomery.identifikace,
                Mereni_plynomery.seriove_cislo,
                Mereni_plynomery.objem,
                Mereni_plynomery.delta,
                Mereni_plynomery.zdroj,
                Mereni_plynomery.platne,
                Mereni_plynomery.interval_minutes,
                Mereni_plynomery.day_of_week,
                Mereni_plynomery.slot,
                Mereni_plynomery.nocni_odber,
                Mereni_plynomery.gap_detected,
                Mereni_plynomery.synthetic,
                Mereni_plynomery.reset_detected,
                Mereni_plynomery.source_date,
                Mereni_plynomery.time_utc,
                Mereni_plynomery.time_basis,
                Mereni_plynomery.source_timezone,
                Mereni_plynomery.source_utc_offset_minutes,
                Mereni_plynomery.time_fold,
                Mereni_plynomery.timestamp_position,
            )
            .filter(
                Mereni_plynomery.identifikace == identifikace,
                Mereni_plynomery.time_utc >= start_utc,
                Mereni_plynomery.time_utc < end_utc,
            )
            .order_by(Mereni_plynomery.time_utc.asc(), Mereni_plynomery.id.asc())
            .all()
        )
        return pd.DataFrame(
            rows,
            columns=[
                "date",
                "identifikace",
                "seriove_cislo",
                "objem",
                "delta",
                "zdroj",
                "platne",
                "interval_minutes",
                "day_of_week",
                "slot",
                "nocni_odber",
                "gap_detected",
                "synthetic",
                "reset_detected",
                *TIME_SEMANTICS_COLUMNS,
            ],
        )
    finally:
        session.close()


def _serialize_device_detail(device: Plynomer_areal_Zarizeni) -> dict[str, object]:
    return {
        "identifikace": device.identifikace,
        "seriove_cislo": device.seriove_cislo,
        "mbus": device.MBUS,
        "objekt": device.objekt,
        "patro": device.patro,
        "mistnost": device.mistnost,
        "umisteni": device.umisteni,
        "napaji": device.napaji,
        "koncovy_odberatel": device.koncovy_odberatel,
        "platnost_cejchu": device.platnost_cejchu,
        "poznamka": device.poznamka_plynomery,
        "foto": device.foto,
    }


@st.cache_data(ttl=60)
def load_device_detail(identifikace: str, allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object] | None:
    if not user_is_admin and identifikace not in allowed_devices:
        return None

    session_ms = get_session_ms()
    try:
        device = (
            session_ms.query(Plynomer_areal_Zarizeni)
            .filter(Plynomer_areal_Zarizeni.identifikace == identifikace)
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
        aria_label="Zvětšit fotografii plynoměru",
    )
