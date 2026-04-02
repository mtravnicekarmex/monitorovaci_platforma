from __future__ import annotations

import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db.connect import get_session_ms
from moduly.apps.dashboard.auth import get_allowed_devices, is_admin
from moduly.apps.dashboard.vodomery_shared import (
    format_consumption_dataframe,
    format_consumption_with_unit,
    format_value,
    normalize_date_range,
    render_page_styles,
    round_consumption_columns,
)
from moduly.mereni.kalorimetry.database.models import (
    Kalorimetr_areal_Mereni,
    Kalorimetr_areal_Zarizeni,
)


MAX_IDENT_OPTIONS = 500


def get_kalorimetry_access_context() -> tuple[bool, tuple[str, ...]]:
    user_is_admin = is_admin()
    allowed_devices = get_allowed_devices()
    if not user_is_admin and not allowed_devices:
        st.warning("Prihlasenemu uzivateli nejsou prirazena zadna zarizeni.")
        st.stop()
    return user_is_admin, allowed_devices


@st.cache_data(ttl=60)
def load_ident_options(allowed_devices: tuple[str, ...], user_is_admin: bool) -> list[str]:
    session = get_session_ms()
    try:
        query = session.query(Kalorimetr_areal_Mereni.identifikace).distinct()
        if not user_is_admin:
            query = query.filter(Kalorimetr_areal_Mereni.identifikace.in_(allowed_devices))
        rows = query.order_by(Kalorimetr_areal_Mereni.identifikace).limit(MAX_IDENT_OPTIONS).all()
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

    session = get_session_ms()
    try:
        start_dt, end_dt = build_datetime_range(start_date, end_date)
        rows = (
            session.query(
                Kalorimetr_areal_Mereni.date,
                Kalorimetr_areal_Mereni.identifikace,
                Kalorimetr_areal_Mereni.seriove_cislo,
                Kalorimetr_areal_Mereni.spotreba_energie,
                Kalorimetr_areal_Mereni.objem,
                Kalorimetr_areal_Mereni.platne,
            )
            .filter(
                Kalorimetr_areal_Mereni.identifikace == identifikace,
                Kalorimetr_areal_Mereni.date >= start_dt,
                Kalorimetr_areal_Mereni.date <= end_dt,
            )
            .order_by(Kalorimetr_areal_Mereni.date.asc())
            .all()
        )
        return pd.DataFrame(
            rows,
            columns=["date", "identifikace", "seriove_cislo", "spotreba_energie", "objem", "platne"],
        )
    finally:
        session.close()


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
        }
    finally:
        session_ms.close()


def format_energy_metric(value: object) -> str:
    return format_consumption_with_unit(value, unit="").strip()
