from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import requests

from app.time_utils import prague_now_naive


OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OVERVIEW_WEATHER_LAT = 50.0755
OVERVIEW_WEATHER_LON = 14.4378
OVERVIEW_WEATHER_TIMEZONE = "Europe/Prague"
OVERVIEW_WEATHER_TIMEOUT_SECONDS = 8

CURRENT_WEATHER_VARIABLES = (
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "weather_code",
    "wind_speed_10m",
)
HOURLY_WEATHER_VARIABLES = (
    "temperature_2m",
    "weather_code",
    "precipitation_probability",
    "cloud_cover",
)
DAILY_WEATHER_VARIABLES = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "cloud_cover_mean",
    "sunset",
)

WEEKDAY_NAMES = (
    "Pondělí",
    "Úterý",
    "Středa",
    "Čtvrtek",
    "Pátek",
    "Sobota",
    "Neděle",
)


@dataclass(frozen=True)
class OverviewWeatherHour:
    timestamp: datetime
    time_label: str
    temperature: float | None
    weather_code: int | None
    condition_label: str
    condition_key: str
    precipitation_probability: float | None
    cloud_cover: float | None


@dataclass(frozen=True)
class OverviewWeatherDay:
    target_date: date
    day_label: str
    date_label: str
    weather_code: int | None
    condition_label: str
    condition_key: str
    temperature_max: float | None
    temperature_min: float | None
    precipitation_probability_max: float | None
    cloud_cover_mean: float | None


@dataclass(frozen=True)
class OverviewWeatherSnapshot:
    observed_at: datetime
    current_temperature: float | None
    apparent_temperature: float | None
    relative_humidity: float | None
    weather_code: int | None
    condition_label: str
    condition_key: str
    wind_speed: float | None
    sunset_at: datetime | None
    daily_forecast: tuple[OverviewWeatherDay, ...]
    hourly_forecast: tuple[OverviewWeatherHour, ...]


def describe_weather_code(weather_code: object) -> tuple[str, str]:
    try:
        code = int(weather_code)
    except (TypeError, ValueError):
        return ("Bez dat", "unknown")

    if code == 0:
        return ("Jasno", "clear")
    if code == 1:
        return ("Převážně jasno", "clear")
    if code == 2:
        return ("Polojasno", "clouds")
    if code == 3:
        return ("Zataženo", "clouds")
    if code in {45, 48}:
        return ("Mlha", "fog")
    if code in {51, 53, 55, 56, 57}:
        return ("Mrholení", "rain")
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return ("Déšť", "rain")
    if code in {71, 73, 75, 77, 85, 86}:
        return ("Sníh", "snow")
    if code in {95, 96, 99}:
        return ("Bouřka", "storm")
    return ("Proměnlivo", "clouds")


def format_overview_date(target_date: date) -> str:
    weekday_label = WEEKDAY_NAMES[target_date.weekday()]
    return f"{weekday_label} {target_date.day}. {target_date.month}. {target_date.year}"


def format_overview_day_label(target_date: date) -> str:
    return WEEKDAY_NAMES[target_date.weekday()][:2]


def normalize_overview_weather_payload(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> OverviewWeatherSnapshot:
    resolved_now = now or prague_now_naive()
    current_payload = payload.get("current") or {}
    daily_payload = payload.get("daily") or {}
    hourly_payload = payload.get("hourly") or {}

    observed_at = _parse_datetime(current_payload.get("time")) or resolved_now
    current_label, current_key = describe_weather_code(current_payload.get("weather_code"))

    daily_time_values = daily_payload.get("time") or []
    daily_weather_code_values = daily_payload.get("weather_code") or []
    daily_temperature_max_values = daily_payload.get("temperature_2m_max") or []
    daily_temperature_min_values = daily_payload.get("temperature_2m_min") or []
    daily_precipitation_probability_values = daily_payload.get("precipitation_probability_max") or []
    daily_cloud_cover_mean_values = daily_payload.get("cloud_cover_mean") or []
    daily_sunset_values = daily_payload.get("sunset") or []

    daily_points: list[OverviewWeatherDay] = []
    today_sunset_at: datetime | None = None
    daily_row_count = min(
        len(daily_time_values),
        len(daily_weather_code_values),
        len(daily_temperature_max_values),
        len(daily_temperature_min_values),
        len(daily_precipitation_probability_values),
        len(daily_cloud_cover_mean_values),
        len(daily_sunset_values),
    )
    for index in range(daily_row_count):
        target_day = _parse_date(daily_time_values[index])
        if target_day is None:
            continue
        sunset_at = _parse_datetime(daily_sunset_values[index])
        if target_day == resolved_now.date() and sunset_at is not None:
            today_sunset_at = sunset_at
        if target_day <= resolved_now.date():
            continue
        condition_label, condition_key = describe_weather_code(daily_weather_code_values[index])
        daily_points.append(
            OverviewWeatherDay(
                target_date=target_day,
                day_label=format_overview_day_label(target_day),
                date_label=f"{target_day.day}.{target_day.month}.",
                weather_code=_to_int(daily_weather_code_values[index]),
                condition_label=condition_label,
                condition_key=condition_key,
                temperature_max=_to_float(daily_temperature_max_values[index]),
                temperature_min=_to_float(daily_temperature_min_values[index]),
                precipitation_probability_max=_to_float(daily_precipitation_probability_values[index]),
                cloud_cover_mean=_to_float(daily_cloud_cover_mean_values[index]),
            )
        )
        if len(daily_points) >= 5:
            break

    time_values = hourly_payload.get("time") or []
    temperature_values = hourly_payload.get("temperature_2m") or []
    weather_code_values = hourly_payload.get("weather_code") or []
    precipitation_probability_values = hourly_payload.get("precipitation_probability") or []
    cloud_cover_values = hourly_payload.get("cloud_cover") or []

    hourly_points: list[OverviewWeatherHour] = []
    current_hour = resolved_now.replace(minute=0, second=0, microsecond=0)
    row_count = min(
        len(time_values),
        len(temperature_values),
        len(weather_code_values),
        len(precipitation_probability_values),
        len(cloud_cover_values),
    )
    for index in range(row_count):
        timestamp = _parse_datetime(time_values[index])
        if timestamp is None:
            continue
        if timestamp.date() != resolved_now.date():
            continue
        if timestamp < current_hour:
            continue
        condition_label, condition_key = describe_weather_code(weather_code_values[index])
        hourly_points.append(
            OverviewWeatherHour(
                timestamp=timestamp,
                time_label=timestamp.strftime("%H:%M"),
                temperature=_to_float(temperature_values[index]),
                weather_code=_to_int(weather_code_values[index]),
                condition_label=condition_label,
                condition_key=condition_key,
                precipitation_probability=_to_float(precipitation_probability_values[index]),
                cloud_cover=_to_float(cloud_cover_values[index]),
            )
        )

    return OverviewWeatherSnapshot(
        observed_at=observed_at,
        current_temperature=_to_float(current_payload.get("temperature_2m")),
        apparent_temperature=_to_float(current_payload.get("apparent_temperature")),
        relative_humidity=_to_float(current_payload.get("relative_humidity_2m")),
        weather_code=_to_int(current_payload.get("weather_code")),
        condition_label=current_label,
        condition_key=current_key,
        wind_speed=_to_float(current_payload.get("wind_speed_10m")),
        sunset_at=today_sunset_at,
        daily_forecast=tuple(daily_points),
        hourly_forecast=tuple(hourly_points),
    )


def fetch_overview_weather_snapshot(*, now: datetime | None = None) -> OverviewWeatherSnapshot:
    response = requests.get(
        OPEN_METEO_FORECAST_URL,
        params={
            "latitude": OVERVIEW_WEATHER_LAT,
            "longitude": OVERVIEW_WEATHER_LON,
            "timezone": OVERVIEW_WEATHER_TIMEZONE,
            "forecast_days": 6,
            "current": ",".join(CURRENT_WEATHER_VARIABLES),
            "daily": ",".join(DAILY_WEATHER_VARIABLES),
            "hourly": ",".join(HOURLY_WEATHER_VARIABLES),
        },
        timeout=OVERVIEW_WEATHER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return normalize_overview_weather_payload(response.json(), now=now)


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
