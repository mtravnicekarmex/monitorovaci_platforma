from __future__ import annotations

import datetime
from collections.abc import Iterable
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.apps.dashboard.api_client import (
    DashboardApiError,
    get_manometry_device_detail as api_get_manometry_device_detail,
    get_manometry_devices as api_get_manometry_devices,
    get_manometry_measurement_series as api_get_manometry_measurement_series,
)
from moduly.apps.dashboard.auth import get_allowed_devices, get_auth_token, is_admin
from moduly.apps.dashboard.vodomery_shared import format_value, normalize_date_range, render_page_styles


MAX_IDENT_OPTIONS = 500
KPA_PER_BAR = 100.0
DEFAULT_PRESSURE_COLUMNS = (
    "hodnota",
    "tlak_min",
    "tlak_max",
    "tlak_prumer",
    "tlak_posledni",
    "Tlak",
    "Tlak min",
    "Tlak max",
    "Tlak prumer",
    "Posledni tlak",
)


def get_manometry_access_context() -> tuple[bool, tuple[str, ...]]:
    user_is_admin = is_admin()
    allowed_devices = get_allowed_devices()
    if not user_is_admin and not allowed_devices:
        st.warning("Prihlasenemu uzivateli nejsou prirazena zadna zarizeni.")
        st.stop()
    return user_is_admin, allowed_devices


def require_dashboard_api_token() -> str:
    access_token = get_auth_token()
    if not access_token:
        raise DashboardApiError("Chybi bearer token pro dashboard API.")
    return access_token


def convert_pressure_value_to_bar(value: object) -> float | None:
    if value is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(numeric_value):
        return None
    return numeric_value / KPA_PER_BAR


def convert_pressure_columns_to_bar(
    df: pd.DataFrame,
    columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    converted = df.copy()
    target_columns = tuple(columns or DEFAULT_PRESSURE_COLUMNS)
    for column in target_columns:
        if column in converted.columns:
            converted[column] = pd.to_numeric(converted[column], errors="coerce") / KPA_PER_BAR
    return converted


@st.cache_data(ttl=60)
def load_ident_options(allowed_devices: tuple[str, ...], user_is_admin: bool) -> list[str]:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    return api_get_manometry_devices(access_token, limit=MAX_IDENT_OPTIONS)


@st.cache_data(ttl=60)
def load_measurement_series(
    identifikace: str,
    start_date: datetime.date,
    end_date: datetime.date,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> pd.DataFrame:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    rows = api_get_manometry_measurement_series(
        access_token,
        identifikace=identifikace,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    df = pd.DataFrame(
        rows,
        columns=[
            "date",
            "identifikace",
            "seriove_cislo",
            "hodnota",
            "platne",
        ],
    )
    return convert_pressure_columns_to_bar(df, columns=("hodnota",))


@st.cache_data(ttl=60)
def load_device_detail(
    identifikace: str,
    allowed_devices: tuple[str, ...],
    user_is_admin: bool,
) -> dict[str, object] | None:
    del allowed_devices, user_is_admin
    access_token = require_dashboard_api_token()
    device_detail = api_get_manometry_device_detail(
        access_token,
        identifikace=identifikace,
    )
    if device_detail is None:
        return None
    converted_detail = dict(device_detail)
    for column in ("min_pressure", "max_pressure"):
        converted_detail[column] = convert_pressure_value_to_bar(converted_detail.get(column))
    return converted_detail


def format_pressure_number(value: object, signed: bool = False) -> str:
    if value is None:
        return "-"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return format_value(value)
    if pd.isna(numeric_value):
        return "-"
    if abs(numeric_value) < 0.0005:
        numeric_value = 0.0
    return f"{numeric_value:+.3f}" if signed else f"{numeric_value:.3f}"


def format_pressure_with_unit(value: object, unit: str = "bar", signed: bool = False) -> str:
    formatted = format_pressure_number(value, signed=signed)
    if formatted == "-":
        return formatted
    return f"{formatted} {unit}"


def round_pressure_columns(df: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    rounded = df.copy()
    target_columns = tuple(columns or DEFAULT_PRESSURE_COLUMNS)
    for column in target_columns:
        if column in rounded.columns:
            rounded[column] = pd.to_numeric(rounded[column], errors="coerce").round(3)
    return rounded


def format_pressure_dataframe(df: pd.DataFrame, columns: Iterable[str] | None = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    formatted = df.copy()
    target_columns = tuple(columns or DEFAULT_PRESSURE_COLUMNS)
    for column in target_columns:
        if column in formatted.columns:
            formatted[column] = pd.to_numeric(formatted[column], errors="coerce").map(format_pressure_number)
    return formatted
