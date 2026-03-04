import logging
import time
import requests

from datetime import datetime, timedelta, date
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from core.db.connect import get_session_pg
from moduly.meteo.database.models import MeteoHourly
from app.time_utils import utc_now_naive

# ==============================
# 🔧 KONFIGURACE
# ==============================

INITIAL_START_DATE = date(2023, 1, 1)

LAT = 50.0755
LON = 14.4378

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

REQUEST_TIMEOUT = 10
MAX_RETRIES = 3


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


# ==============================
# 🔄 HLAVNÍ SYNC LOGIKA
# ==============================

def run_meteo_sync(db_session):
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


# if __name__ == "__main__":
#     db_session = get_session_pg()
#     try:
#         run_meteo_sync(db_session)
#     finally:
#         db_session.close()


def meteo_sync(db_session=get_session_pg()):
    try:
        run_meteo_sync(db_session)
    finally:
        db_session.close()



meteo_sync()