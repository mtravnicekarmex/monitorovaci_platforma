import logging
import time
import requests

from datetime import datetime, timedelta, date
from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert
from core.db.connect import ENGINE_PG, get_session_pg
from moduly.apps.meteo.database.models import MeteoForecastHourly, MeteoHourly
from app.time_utils import utc_now_naive

# ==============================
# 🔧 KONFIGURACE
# ==============================

INITIAL_START_DATE = date(2023, 1, 1)

LAT = 50.0755
LON = 14.4378

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

REQUEST_TIMEOUT = 10
MAX_RETRIES = 3
FORECAST_DAYS = 7

FORECAST_HOURLY_VARIABLES = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "snowfall",
    "cloud_cover",
    "wind_speed_10m",
    "surface_pressure",
)


def ensure_meteo_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        _ensure_meteo_hourly_table(conn)
        _ensure_meteo_forecast_hourly_table(conn)


def _ensure_meteo_hourly_table(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS monitoring.meteo_hourly (
                datetime_hour TIMESTAMP WITHOUT TIME ZONE PRIMARY KEY,
                temperature NUMERIC(5, 2) NOT NULL,
                apparent_temperature NUMERIC(5, 2),
                relative_humidity NUMERIC(5, 2),
                precipitation NUMERIC(6, 2),
                snowfall NUMERIC(6, 2),
                cloud_cover NUMERIC(5, 2),
                wind_speed NUMERIC(5, 2),
                surface_pressure NUMERIC(7, 2),
                heating_degree_hours NUMERIC(5, 2) NOT NULL,
                cooling_degree_hours NUMERIC(5, 2) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_meteo_hourly_datetime_hour
            ON monitoring.meteo_hourly (datetime_hour)
            """
        )
    )


def _ensure_meteo_forecast_hourly_table(conn) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS monitoring.meteo_forecast_hourly (
                datetime_hour TIMESTAMP WITHOUT TIME ZONE PRIMARY KEY,
                forecast_run_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                temperature NUMERIC(5, 2) NOT NULL,
                apparent_temperature NUMERIC(5, 2),
                relative_humidity NUMERIC(5, 2),
                precipitation NUMERIC(6, 2),
                snowfall NUMERIC(6, 2),
                cloud_cover NUMERIC(5, 2),
                wind_speed NUMERIC(5, 2),
                surface_pressure NUMERIC(7, 2),
                heating_degree_hours NUMERIC(5, 2) NOT NULL,
                cooling_degree_hours NUMERIC(5, 2) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_meteo_forecast_hourly_run_at
            ON monitoring.meteo_forecast_hourly (forecast_run_at)
            """
        )
    )


# ==============================
# 📡 API FETCH
# ==============================

def fetch_day_from_api(target_date: date):
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "precipitation",
            "snowfall",
            "cloudcover",
            "windspeed_10m",
            "surface_pressure",
        ]),
        "start_date": target_date.isoformat(),
        "end_date": target_date.isoformat(),
        "timezone": "UTC"
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                OPEN_METEO_URL,
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logging.warning(
                f"Meteo fetch failed ({attempt+1}/{MAX_RETRIES}) "
                f"for {target_date}: {e}"
            )
            time.sleep(2 ** attempt)

    raise RuntimeError(f"Meteo fetch failed permanently for {target_date}")


def fetch_forecast_from_api(*, forecast_days: int = FORECAST_DAYS):
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": ",".join(FORECAST_HOURLY_VARIABLES),
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                OPEN_METEO_FORECAST_URL,
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logging.warning(
                f"Meteo forecast fetch failed ({attempt+1}/{MAX_RETRIES}): {e}"
            )
            time.sleep(2 ** attempt)

    raise RuntimeError("Meteo forecast fetch failed permanently")


# ==============================
# 💾 UPSERT DO DB
# ==============================

def upsert_day(session, data):
    rows = []

    hourly = data.get("hourly")
    if not hourly or "time" not in hourly:
        raise RuntimeError("Invalid Open-Meteo response structure")

    for i, dt_str in enumerate(hourly["time"]):
        # 🔥 naive UTC datetime (bez tzinfo)
        dt = datetime.fromisoformat(dt_str)

        temp = hourly["temperature_2m"][i]

        rows.append({
            "datetime_hour": dt,
            "temperature": temp,
            "apparent_temperature": hourly["apparent_temperature"][i],
            "relative_humidity": hourly["relative_humidity_2m"][i],
            "precipitation": hourly["precipitation"][i],
            "snowfall": hourly["snowfall"][i],
            "cloud_cover": hourly["cloudcover"][i],
            "wind_speed": hourly["windspeed_10m"][i],
            "surface_pressure": hourly["surface_pressure"][i],
            "heating_degree_hours": max(0, 18 - temp),
            "cooling_degree_hours": max(0, temp - 22),
        })

    if not rows:
        logging.warning("No hourly rows returned from API")
        return

    stmt = insert(MeteoHourly).values(rows)

    stmt = stmt.on_conflict_do_update(
        index_elements=["datetime_hour"],
        set_={c: stmt.excluded[c] for c in rows[0].keys()}
    )

    session.execute(stmt)
    session.commit()


def upsert_forecast(session, data, *, forecast_run_at: datetime | None = None):
    rows = []
    hourly = data.get("hourly")
    if not hourly or "time" not in hourly:
        raise RuntimeError("Invalid Open-Meteo forecast response structure")

    resolved_forecast_run_at = forecast_run_at or utc_now_naive()
    time_values = hourly["time"]
    for index, dt_str in enumerate(time_values):
        temp = hourly["temperature_2m"][index]
        if temp is None:
            continue

        rows.append(
            {
                "datetime_hour": datetime.fromisoformat(dt_str),
                "forecast_run_at": resolved_forecast_run_at,
                "temperature": temp,
                "apparent_temperature": hourly["apparent_temperature"][index],
                "relative_humidity": hourly["relative_humidity_2m"][index],
                "precipitation": hourly["precipitation"][index],
                "snowfall": hourly["snowfall"][index],
                "cloud_cover": hourly["cloud_cover"][index],
                "wind_speed": hourly["wind_speed_10m"][index],
                "surface_pressure": hourly["surface_pressure"][index],
                "heating_degree_hours": max(0, 18 - temp),
                "cooling_degree_hours": max(0, temp - 22),
            }
        )

    if not rows:
        logging.warning("No hourly forecast rows returned from API")
        return

    stmt = insert(MeteoForecastHourly).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["datetime_hour"],
        set_={c: stmt.excluded[c] for c in rows[0].keys()},
    )
    session.execute(stmt)
    session.commit()


# ==============================
# 🔄 HLAVNÍ SYNC LOGIKA
# ==============================

def run_meteo_sync(db_session):
    ensure_meteo_tables()
    logging.info("Meteo sync started")

    last_dt = db_session.query(
        func.max(MeteoHourly.datetime_hour)
    ).scalar()

    if last_dt:
        start_date = (last_dt + timedelta(hours=1)).date()
    else:
        start_date = INITIAL_START_DATE

    # 🔥 UTC jako naive
    today_utc = utc_now_naive().date()
    end_date = today_utc - timedelta(days=1)

    if start_date > end_date:
        logging.info("Meteo sync: nothing to update")
        return

    current = start_date

    while current <= end_date:
        logging.info(f"Meteo syncing day: {current}")
        data = fetch_day_from_api(current)
        upsert_day(db_session, data)
        current += timedelta(days=1)

    logging.info("Meteo sync finished successfully")


def run_meteo_forecast_sync(db_session, *, forecast_days: int = FORECAST_DAYS):
    ensure_meteo_tables()
    logging.info("Meteo forecast sync started")
    data = fetch_forecast_from_api(forecast_days=forecast_days)
    upsert_forecast(db_session, data)
    logging.info("Meteo forecast sync finished successfully")


# if __name__ == "__main__":
#     db_session = get_session_pg()
#     try:
#         run_meteo_sync(db_session)
#     finally:
#         db_session.close()


def meteo_sync():
    db_session=get_session_pg()
    try:
        run_meteo_sync(db_session)
        run_meteo_forecast_sync(db_session)
    finally:
        db_session.close()



