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
from moduly.apps.dashboard.vodomery_shared import (
    format_consumption_dataframe,
    format_consumption_with_unit,
    format_value,
    normalize_date_range,
    render_page_styles,
    round_consumption_columns,
)
from moduly.mereni.elektromery.database.models import (
    Elektromer_areal_Zarizeni,
    Mereni_elektromery,
)


MAX_IDENT_OPTIONS = 500
TIME_SEMANTICS_COLUMNS = (
    "source_date",
    "time_utc",
    "time_basis",
    "source_timezone",
    "source_utc_offset_minutes",
    "time_fold",
    "timestamp_position",
)


def get_elektromery_access_context() -> tuple[bool, tuple[str, ...]]:
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
        query = session.query(Mereni_elektromery.identifikace).filter(
            Mereni_elektromery.identifikace.is_not(None),
            Mereni_elektromery.platne.is_(True),
        ).distinct()
        if not user_is_admin:
            query = query.filter(Mereni_elektromery.identifikace.in_(allowed_devices))
        rows = query.order_by(Mereni_elektromery.identifikace).limit(MAX_IDENT_OPTIONS).all()
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
        start_dt, end_dt = build_datetime_range(start_date, end_date)
        rows = (
            session.query(
                Mereni_elektromery.date,
                Mereni_elektromery.identifikace,
                Mereni_elektromery.seriove_cislo,
                Mereni_elektromery.objem,
                Mereni_elektromery.delta,
                Mereni_elektromery.zdroj,
                Mereni_elektromery.platne,
                Mereni_elektromery.synthetic,
                Mereni_elektromery.gap_detected,
                Mereni_elektromery.reset_detected,
                Mereni_elektromery.source_date,
                Mereni_elektromery.time_utc,
                Mereni_elektromery.time_basis,
                Mereni_elektromery.source_timezone,
                Mereni_elektromery.source_utc_offset_minutes,
                Mereni_elektromery.time_fold,
                Mereni_elektromery.timestamp_position,
            )
            .filter(
                Mereni_elektromery.identifikace == identifikace,
                Mereni_elektromery.date >= start_dt,
                Mereni_elektromery.date <= end_dt,
                Mereni_elektromery.platne.is_(True),
            )
            .order_by(Mereni_elektromery.date.asc(), Mereni_elektromery.zdroj.asc())
            .all()
        )
        return pd.DataFrame(
            [
                {
                    "date": row.date,
                    "identifikace": row.identifikace,
                    "seriove_cislo": row.seriove_cislo,
                    "vt": None,
                    "nt": None,
                    "total": row.objem,
                    "delta": row.delta,
                    "zdroj": row.zdroj,
                    "platne": row.platne,
                    "synthetic": row.synthetic,
                    "gap_detected": row.gap_detected,
                    "reset_detected": row.reset_detected,
                    "source_date": row.source_date,
                    "time_utc": row.time_utc,
                    "time_basis": row.time_basis,
                    "source_timezone": row.source_timezone,
                    "source_utc_offset_minutes": row.source_utc_offset_minutes,
                    "time_fold": row.time_fold,
                    "timestamp_position": row.timestamp_position,
                }
                for row in rows
            ],
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
        "foto": device.foto,
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


def resolve_device_photo_path(photo_value: object) -> Path | None:
    return resolve_photo_path(photo_value, project_root=PROJECT_ROOT)


def build_device_photo_data_uri(photo_path: Path | None) -> str | None:
    return build_photo_data_uri(photo_path)


def render_device_photo(device_detail: dict[str, object] | None) -> bool:
    return render_clickable_device_photo(
        device_detail,
        project_root=PROJECT_ROOT,
        aria_label="Zvětšit fotografii elektroměru",
    )


def format_energy_metric(value: object, unit: str = "kWh", signed: bool = False) -> str:
    return format_consumption_with_unit(value, unit=unit, signed=signed)


def uses_ote_delta_source(df: pd.DataFrame) -> bool:
    if df.empty or "zdroj" not in df.columns:
        return False

    sources = {
        str(value).strip().upper()
        for value in df["zdroj"]
        if pd.notna(value) and str(value).strip()
    }
    return sources == {"OTE"}


def build_delta_consumption_summary(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()

    prepared = df.copy()
    date_values = prepared["date"] if "date" in prepared.columns else pd.Series(dtype="datetime64[ns]")
    date_series = pd.to_datetime(date_values, errors="coerce")
    consumption_source = "spotreba" if "spotreba" in prepared.columns else "delta"
    consumption_values = prepared[consumption_source] if consumption_source in prepared.columns else pd.Series(dtype=float)
    consumption = pd.to_numeric(consumption_values, errors="coerce").fillna(0.0)

    return pd.DataFrame(
        [
            {
                "Zdroj": "OTE" if uses_ote_delta_source(prepared) else "Delta",
                "První měření": date_series.min(),
                "Poslední měření": date_series.max(),
                "Počet měření": int(date_series.notna().sum()),
                "Spotřeba z delta": round(float(consumption.sum()), 3),
            }
        ]
    )


def prepare_measurements(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    for column in (
        "date",
        "identifikace",
        "seriove_cislo",
        "vt",
        "nt",
        "total",
        "delta",
        "zdroj",
        "platne",
        "synthetic",
        "gap_detected",
        "reset_detected",
        *TIME_SEMANTICS_COLUMNS,
    ):
        if column not in prepared.columns:
            prepared[column] = pd.NA

    prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared["source_date"] = pd.to_datetime(prepared["source_date"], errors="coerce")
    utc_time = pd.to_datetime(prepared["time_utc"], utc=True, errors="coerce")
    prepared["time_utc"] = utc_time
    prepared["chart_time"] = utc_time.dt.tz_convert("Europe/Prague").dt.tz_localize(None)
    prepared.loc[prepared["chart_time"].isna(), "chart_time"] = prepared.loc[prepared["chart_time"].isna(), "date"]
    for column in ("vt", "nt", "total", "delta"):
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
    prepared["seriove_cislo"] = prepared["seriove_cislo"].astype("string")
    prepared = prepared.dropna(subset=["date"]).sort_values("chart_time").reset_index(drop=True)

    if prepared.empty:
        return prepared

    prepared["stav_celkem"] = prepared["total"]
    missing_total = prepared["stav_celkem"].isna()
    prepared.loc[missing_total & prepared["vt"].notna() & prepared["nt"].notna(), "stav_celkem"] = (
        prepared["vt"] + prepared["nt"]
    )
    prepared.loc[prepared["stav_celkem"].isna(), "stav_celkem"] = prepared["vt"]

    diff_from_total = prepared["stav_celkem"].diff()
    serial_changed = prepared["seriove_cislo"].ne(prepared["seriove_cislo"].shift())
    if not serial_changed.empty:
        serial_changed.iloc[0] = False
    state_reset = (
        diff_from_total.lt(0).fillna(False)
        & prepared["stav_celkem"].notna()
        & prepared["stav_celkem"].shift().notna()
    )
    stored_reset = prepared["reset_detected"].map(lambda value: bool(value) if pd.notna(value) else False)
    reset_detected = state_reset | serial_changed.fillna(False) | stored_reset
    prepared["reset_detected"] = reset_detected

    source_delta_available = prepared["delta"].notna()
    prepared["spotreba"] = diff_from_total.fillna(0.0)
    prepared.loc[source_delta_available, "spotreba"] = prepared.loc[source_delta_available, "delta"]
    prepared.loc[prepared["spotreba"] < 0, "spotreba"] = 0.0

    for state_column, consumption_column in (("vt", "spotreba_vt"), ("nt", "spotreba_nt")):
        prepared[consumption_column] = prepared[state_column].diff().fillna(0.0)
        prepared.loc[prepared[consumption_column] < 0, consumption_column] = 0.0
        prepared.loc[prepared[state_column].isna(), consumption_column] = 0.0

    reset_without_source_delta = prepared["reset_detected"] & ~source_delta_available
    for column in ("spotreba", "spotreba_vt", "spotreba_nt"):
        prepared.loc[reset_without_source_delta, column] = 0.0
        prepared[column] = prepared[column].round(3)

    prepared["kumulovana_spotreba"] = prepared["spotreba"].cumsum().round(3)
    return prepared


def build_change_table(df: pd.DataFrame) -> pd.DataFrame:
    if len(df) < 2:
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    previous_row = df.iloc[0]
    for _, row in df.iloc[1:].iterrows():
        current_serial = row["seriove_cislo"]
        previous_serial = previous_row["seriove_cislo"]
        serial_changed = (
            pd.notna(current_serial)
            and pd.notna(previous_serial)
            and current_serial != previous_serial
        )
        current_state = row["stav_celkem"]
        previous_state = previous_row["stav_celkem"]
        total_reset = (
            pd.notna(current_state)
            and pd.notna(previous_state)
            and current_state < previous_state
        )
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
    time_axis_column = (
        "chart_time"
        if "chart_time" in history_df.columns and history_df["chart_time"].notna().any()
        else "date"
    )
    working_df = history_df.dropna(subset=[time_axis_column]).copy()
    if working_df.empty:
        return pd.DataFrame()

    daily_history = (
        working_df.set_index(time_axis_column)
        .resample("D")
        .agg(spotreba=("spotreba", "sum"))
        .reset_index()
        .rename(columns={time_axis_column: "date"})
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

    time_axis_column = (
        "chart_time"
        if "chart_time" in history_df.columns and history_df["chart_time"].notna().any()
        else "date"
    )
    working_df = history_df.dropna(subset=[time_axis_column]).copy()
    if working_df.empty:
        return {"monthly": None, "weekly": None, "weekday": {}}

    daily_totals = (
        working_df.set_index(time_axis_column)
        .resample("D")
        .agg(spotreba=("spotreba", "sum"))
        .reset_index()
        .rename(columns={time_axis_column: "date"})
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
