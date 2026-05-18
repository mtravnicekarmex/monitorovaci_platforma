from __future__ import annotations

import datetime
from pathlib import Path
import sys

import pandas as pd
import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.db.connect import get_session_pg
from moduly.apps.dashboard.vodomery_shared import (
    format_consumption_with_unit,
    format_value,
    normalize_date_range,
    render_page_styles,
)
from moduly.apps.smartfuelpass.database.models import SmartFuelPassRelace


ALL_FILTER_LABEL = "Vše"
MAX_FILTER_OPTIONS = 500


def build_datetime_range(start_date: datetime.date, end_date: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(end_date, datetime.time.max)
    return start_dt, end_dt


@st.cache_data(ttl=60)
def load_location_options() -> list[str]:
    session = get_session_pg()
    try:
        rows = (
            session.query(SmartFuelPassRelace.lokace)
            .filter(SmartFuelPassRelace.lokace.is_not(None))
            .distinct()
            .order_by(SmartFuelPassRelace.lokace.asc())
            .limit(MAX_FILTER_OPTIONS)
            .all()
        )
        return [str(row[0]) for row in rows if row[0]]
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_tariff_options() -> list[str]:
    session = get_session_pg()
    try:
        rows = (
            session.query(SmartFuelPassRelace.tarif)
            .filter(SmartFuelPassRelace.tarif.is_not(None))
            .distinct()
            .order_by(SmartFuelPassRelace.tarif.asc())
            .limit(MAX_FILTER_OPTIONS)
            .all()
        )
        return [str(row[0]) for row in rows if row[0]]
    finally:
        session.close()


@st.cache_data(ttl=60)
def load_charge_sessions(
    start_date: datetime.date,
    end_date: datetime.date,
    lokace: str | None,
    tarif: str | None,
) -> pd.DataFrame:
    session = get_session_pg()
    try:
        start_dt, end_dt = build_datetime_range(start_date, end_date)
        query = session.query(
            SmartFuelPassRelace.id_relace,
            SmartFuelPassRelace.kwh,
            SmartFuelPassRelace.tarif,
            SmartFuelPassRelace.battery_status,
            SmartFuelPassRelace.suma,
            SmartFuelPassRelace.started_at,
            SmartFuelPassRelace.ended_at,
            SmartFuelPassRelace.source_started_at,
            SmartFuelPassRelace.source_ended_at,
            SmartFuelPassRelace.started_at_utc,
            SmartFuelPassRelace.ended_at_utc,
            SmartFuelPassRelace.time_basis,
            SmartFuelPassRelace.source_timezone,
            SmartFuelPassRelace.started_utc_offset_minutes,
            SmartFuelPassRelace.ended_utc_offset_minutes,
            SmartFuelPassRelace.lokace,
            SmartFuelPassRelace.rychlost_nabijeni,
            SmartFuelPassRelace.imported_at,
        ).filter(
            SmartFuelPassRelace.started_at >= start_dt,
            SmartFuelPassRelace.started_at <= end_dt,
        )
        if lokace:
            query = query.filter(SmartFuelPassRelace.lokace == lokace)
        if tarif:
            query = query.filter(SmartFuelPassRelace.tarif == tarif)
        rows = query.order_by(
            SmartFuelPassRelace.started_at.asc(),
            SmartFuelPassRelace.id_relace.asc(),
        ).all()
        return pd.DataFrame(
            [
                {
                    "id_relace": row.id_relace,
                    "kwh": row.kwh,
                    "tarif": row.tarif,
                    "battery_status": row.battery_status,
                    "suma": row.suma,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                    "source_started_at": row.source_started_at,
                    "source_ended_at": row.source_ended_at,
                    "started_at_utc": row.started_at_utc,
                    "ended_at_utc": row.ended_at_utc,
                    "time_basis": row.time_basis,
                    "source_timezone": row.source_timezone,
                    "started_utc_offset_minutes": row.started_utc_offset_minutes,
                    "ended_utc_offset_minutes": row.ended_utc_offset_minutes,
                    "lokace": row.lokace,
                    "rychlost_nabijeni": row.rychlost_nabijeni,
                    "imported_at": row.imported_at,
                }
                for row in rows
            ]
        )
    finally:
        session.close()


def prepare_charge_sessions(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    for column in (
        "id_relace",
        "kwh",
        "tarif",
        "battery_status",
        "suma",
        "started_at",
        "ended_at",
        "source_started_at",
        "source_ended_at",
        "started_at_utc",
        "ended_at_utc",
        "time_basis",
        "source_timezone",
        "started_utc_offset_minutes",
        "ended_utc_offset_minutes",
        "lokace",
        "rychlost_nabijeni",
        "imported_at",
    ):
        if column not in prepared.columns:
            prepared[column] = pd.NA

    for column in ("started_at", "ended_at", "source_started_at", "source_ended_at", "started_at_utc", "ended_at_utc", "imported_at"):
        prepared[column] = pd.to_datetime(prepared[column], errors="coerce")
    for column in ("kwh", "battery_status", "suma", "rychlost_nabijeni"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    prepared["id_relace"] = prepared["id_relace"].astype("string")
    prepared["lokace"] = prepared["lokace"].astype("string")
    prepared["tarif"] = prepared["tarif"].astype("string")
    prepared = prepared.dropna(subset=["started_at", "ended_at", "id_relace"]).sort_values("started_at").reset_index(drop=True)
    if prepared.empty:
        return prepared

    duration_minutes = (
        (prepared["ended_at"] - prepared["started_at"]).dt.total_seconds().div(60)
    )
    prepared["duration_minutes"] = duration_minutes.clip(lower=0).round(1)
    return prepared


def summarize_charge_sessions(df: pd.DataFrame) -> dict[str, object]:
    if df.empty:
        return {
            "session_count": 0,
            "total_kwh": 0.0,
            "total_suma": 0.0,
            "average_speed": None,
        }

    speed_series = pd.to_numeric(df["rychlost_nabijeni"], errors="coerce").dropna()
    return {
        "session_count": int(len(df)),
        "total_kwh": round(float(pd.to_numeric(df["kwh"], errors="coerce").fillna(0.0).sum()), 3),
        "total_suma": round(float(pd.to_numeric(df["suma"], errors="coerce").fillna(0.0).sum()), 2),
        "average_speed": round(float(speed_series.mean()), 3) if not speed_series.empty else None,
    }


def build_daily_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", "session_count", "kwh", "suma"])

    summary = (
        df.assign(date=df["started_at"].dt.floor("D"))
        .groupby("date", as_index=False)
        .agg(
            session_count=("id_relace", "count"),
            kwh=("kwh", "sum"),
            suma=("suma", "sum"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )
    for column, decimals in (("kwh", 3), ("suma", 2)):
        summary[column] = pd.to_numeric(summary[column], errors="coerce").round(decimals)
    return summary


def format_charge_energy(value: object) -> str:
    return format_consumption_with_unit(value, unit="kWh")


def format_charge_speed(value: object) -> str:
    return format_consumption_with_unit(value, unit="kW")


def format_charge_currency(value: object) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value):
        return "-"
    return f"{numeric_value:.2f} Kč"


def _format_decimal(value: object, decimals: int) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return "-"
    if pd.isna(numeric_value):
        return "-"
    return f"{numeric_value:.{decimals}f}"


def format_charge_sessions_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    formatted = df.rename(
        columns={
            "started_at": "Začátek",
            "ended_at": "Konec",
            "duration_minutes": "Trvání [min]",
            "id_relace": "ID relace",
            "lokace": "Lokace",
            "kwh": "Odebráno [kWh]",
            "suma": "Suma [Kč]",
            "tarif": "Tarif",
            "battery_status": "Baterie [%]",
            "rychlost_nabijeni": "Rychlost [kW]",
            "imported_at": "Importováno",
        }
    ).copy()

    for column in ("Začátek", "Konec", "Importováno"):
        formatted[column] = formatted[column].map(format_value)
    formatted["Trvání [min]"] = formatted["Trvání [min]"].map(lambda value: _format_decimal(value, 1))
    formatted["Odebráno [kWh]"] = formatted["Odebráno [kWh]"].map(lambda value: _format_decimal(value, 3))
    formatted["Suma [Kč]"] = formatted["Suma [Kč]"].map(format_charge_currency)
    formatted["Rychlost [kW]"] = formatted["Rychlost [kW]"].map(lambda value: _format_decimal(value, 3))
    formatted["Baterie [%]"] = formatted["Baterie [%]"].map(
        lambda value: "-" if pd.isna(value) else str(int(round(float(value))))
    )
    return formatted[
        [
            "Začátek",
            "Konec",
            "Trvání [min]",
            "ID relace",
            "Lokace",
            "Odebráno [kWh]",
            "Suma [Kč]",
            "Tarif",
            "Baterie [%]",
            "Rychlost [kW]",
            "Importováno",
        ]
    ].copy()
