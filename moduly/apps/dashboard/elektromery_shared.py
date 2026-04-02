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
from moduly.mereni.elektromery.database.models import (
    Elektromer_areal_Mereni,
    Elektromer_areal_Zarizeni,
)


MAX_IDENT_OPTIONS = 500


def get_elektromery_access_context() -> tuple[bool, tuple[str, ...]]:
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
        query = session.query(Elektromer_areal_Mereni.identifikace).distinct()
        if not user_is_admin:
            query = query.filter(Elektromer_areal_Mereni.identifikace.in_(allowed_devices))
        rows = query.order_by(Elektromer_areal_Mereni.identifikace).limit(MAX_IDENT_OPTIONS).all()
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
                Elektromer_areal_Mereni.date,
                Elektromer_areal_Mereni.identifikace,
                Elektromer_areal_Mereni.seriove_cislo,
                Elektromer_areal_Mereni.vt,
                Elektromer_areal_Mereni.nt,
                Elektromer_areal_Mereni.total,
            )
            .filter(
                Elektromer_areal_Mereni.identifikace == identifikace,
                Elektromer_areal_Mereni.date >= start_dt,
                Elektromer_areal_Mereni.date <= end_dt,
            )
            .order_by(Elektromer_areal_Mereni.date.asc())
            .all()
        )
        return pd.DataFrame(
            rows,
            columns=["date", "identifikace", "seriove_cislo", "vt", "nt", "total"],
        )
    finally:
        session.close()


def _serialize_device_detail(device: Elektromer_areal_Zarizeni) -> dict[str, object]:
    return {
        "identifikace": device.identifikace,
        "seriove_cislo": device.seriove_cislo,
        "softlink_id": device.softlink_id,
        "ean": device.EAN,
        "pozice": device.pozice,
        "podruzny": device.podruzny,
        "mistnost": device.mistnost,
        "umisteni": device.umisteni,
        "napaji": device.napaji,
        "koncovy_odberatel": device.koncovy_odberatel,
        "platnost_cejchu": device.platnost_cejchu,
        "jistic": device.jistic,
        "typ_merice": device.typ_merice,
        "rozvadec": device.rozvadec,
        "typ_tarifu": device.typ_tarifu,
        "platnost_od": device.platnost_od,
        "platnost_do": device.platnost_do,
        "plomb": device.plomb,
        "mis_id": device.mis_id,
        "met_id": device.met_id,
    }


@st.cache_data(ttl=60)
def load_device_detail(identifikace: str, allowed_devices: tuple[str, ...], user_is_admin: bool) -> dict[str, object] | None:
    if not user_is_admin and identifikace not in allowed_devices:
        return None

    session_ms = get_session_ms()
    try:
        device = (
            session_ms.query(Elektromer_areal_Zarizeni)
            .filter(Elektromer_areal_Zarizeni.identifikace == identifikace)
            .one_or_none()
        )
        if device is None:
            return None
        return _serialize_device_detail(device)
    finally:
        session_ms.close()


def format_energy_metric(value: object, unit: str = "kWh", signed: bool = False) -> str:
    return format_consumption_with_unit(value, unit=unit, signed=signed)


def prepare_measurements(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    for column in ("vt", "nt", "total"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared["seriove_cislo"] = prepared["seriove_cislo"].astype(str)
    prepared = prepared.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

    if prepared.empty:
        return prepared

    prepared["stav_celkem"] = prepared["total"]
    missing_total = prepared["stav_celkem"].isna()
    prepared.loc[missing_total & prepared["vt"].notna() & prepared["nt"].notna(), "stav_celkem"] = (
        prepared["vt"] + prepared["nt"]
    )
    prepared.loc[prepared["stav_celkem"].isna(), "stav_celkem"] = prepared["vt"]
    prepared = prepared.dropna(subset=["stav_celkem"]).reset_index(drop=True)

    if prepared.empty:
        return prepared

    diff_from_total = prepared["stav_celkem"].diff()
    serial_changed = prepared["seriove_cislo"].ne(prepared["seriove_cislo"].shift())
    reset_detected = diff_from_total.lt(0).fillna(False) | serial_changed.fillna(False)
    prepared["reset_detected"] = reset_detected

    prepared["spotreba"] = diff_from_total.fillna(0.0)
    prepared.loc[prepared["spotreba"] < 0, "spotreba"] = 0.0

    for state_column, consumption_column in (("vt", "spotreba_vt"), ("nt", "spotreba_nt")):
        prepared[consumption_column] = prepared[state_column].diff().fillna(0.0)
        prepared.loc[prepared[consumption_column] < 0, consumption_column] = 0.0
        prepared.loc[prepared[state_column].isna(), consumption_column] = 0.0

    for column in ("spotreba", "spotreba_vt", "spotreba_nt"):
        prepared.loc[prepared["reset_detected"], column] = 0.0
        prepared[column] = prepared[column].round(3)

    prepared["kumulovana_spotreba"] = prepared["spotreba"].cumsum().round(3)
    return prepared


def build_change_table(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 2:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    previous_row = df.iloc[0]
    for _, row in df.iloc[1:].iterrows():
        serial_changed = row["seriove_cislo"] != previous_row["seriove_cislo"]
        total_reset = row["stav_celkem"] < previous_row["stav_celkem"]
        if serial_changed or total_reset:
            rows.append(
                {
                    "Datum": previous_row["date"],
                    "Stav celkem": previous_row["stav_celkem"],
                    "Sériové číslo": previous_row["seriove_cislo"],
                    "Poznámka": "Konečný stav původního elektroměru",
                }
            )
            rows.append(
                {
                    "Datum": row["date"],
                    "Stav celkem": row["stav_celkem"],
                    "Sériové číslo": row["seriove_cislo"],
                    "Poznámka": "Počáteční stav nového nebo resetovaného elektroměru",
                }
            )
        previous_row = row
    return pd.DataFrame(rows)


def build_daily_history(history_df: pd.DataFrame, days: int) -> pd.DataFrame:
    daily_history = (
        history_df.set_index("date")
        .resample("D")
        .agg(spotreba=("spotreba", "sum"))
        .reset_index()
    )
    daily_history = daily_history[daily_history["spotreba"].notna()].copy()
    if daily_history.empty:
        return daily_history
    last_date = daily_history["date"].max()
    start_window = last_date - pd.Timedelta(days=days - 1)
    daily_history = daily_history[daily_history["date"] >= start_window].copy()
    daily_history["day_label"] = daily_history["date"].dt.strftime("%d.%m.")
    return daily_history


def build_average_consumption_summary(history_df: pd.DataFrame) -> dict[str, object]:
    if history_df.empty:
        return {"monthly": None, "weekly": None, "weekday": {}}

    daily_totals = (
        history_df.set_index("date")
        .resample("D")
        .agg(spotreba=("spotreba", "sum"))
        .reset_index()
    )
    daily_totals = daily_totals[daily_totals["spotreba"].notna()].copy()
    if daily_totals.empty:
        return {"monthly": None, "weekly": None, "weekday": {}}

    daily_totals["spotreba"] = pd.to_numeric(daily_totals["spotreba"], errors="coerce").fillna(0.0)
    monthly_totals = (
        daily_totals.assign(month_period=daily_totals["date"].dt.to_period("M"))
        .groupby("month_period")["spotreba"]
        .sum()
    )
    iso_calendar = daily_totals["date"].dt.isocalendar()
    weekly_totals = (
        daily_totals.assign(iso_year=iso_calendar.year, iso_week=iso_calendar.week)
        .groupby(["iso_year", "iso_week"])["spotreba"]
        .sum()
    )
    weekday_totals = (
        daily_totals.assign(day_of_week=daily_totals["date"].dt.dayofweek)
        .groupby("day_of_week")["spotreba"]
        .mean()
    )

    return {
        "monthly": round(float(monthly_totals.mean()), 3) if not monthly_totals.empty else None,
        "weekly": round(float(weekly_totals.mean()), 3) if not weekly_totals.empty else None,
        "weekday": {
            int(day_of_week): round(float(value), 3)
            for day_of_week, value in weekday_totals.items()
        },
    }
