import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from moduly.apps.dashboard.overview_weather import (
    describe_weather_code,
    format_overview_date,
    normalize_overview_weather_payload,
)


def test_describe_weather_code_groups_conditions():
    assert describe_weather_code(0) == ("Jasno", "clear")
    assert describe_weather_code(63) == ("Déšť", "rain")
    assert describe_weather_code(75) == ("Sníh", "snow")
    assert describe_weather_code(95) == ("Bouřka", "storm")
    assert describe_weather_code("invalid") == ("Bez dat", "unknown")


def test_format_overview_date_uses_expected_label():
    assert format_overview_date(datetime.date(2026, 4, 22)) == "Středa 22. 4. 2026"


def test_normalize_overview_weather_payload_filters_today_from_current_hour():
    payload = {
        "current": {
            "time": "2026-04-22T13:15",
            "temperature_2m": 14.2,
            "apparent_temperature": 13.4,
            "relative_humidity_2m": 58,
            "weather_code": 2,
            "wind_speed_10m": 18.6,
        },
        "daily": {
            "time": [
                "2026-04-22",
                "2026-04-23",
                "2026-04-24",
                "2026-04-25",
                "2026-04-26",
                "2026-04-27",
                "2026-04-28",
            ],
            "weather_code": [2, 1, 3, 63, 75, 95, 0],
            "temperature_2m_max": [15.0, 17.0, 16.5, 13.0, 7.5, 11.0, 18.0],
            "temperature_2m_min": [8.0, 7.0, 9.0, 6.0, -1.0, 5.0, 9.0],
            "precipitation_probability_max": [25, 10, 30, 70, 55, 60, 5],
            "cloud_cover_mean": [45, 20, 55, 88, 76, 64, 10],
            "sunset": [
                "2026-04-22T19:58",
                "2026-04-23T19:59",
                "2026-04-24T20:01",
                "2026-04-25T20:02",
                "2026-04-26T20:04",
                "2026-04-27T20:05",
                "2026-04-28T20:07",
            ],
        },
        "hourly": {
            "time": [
                "2026-04-22T12:00",
                "2026-04-22T13:00",
                "2026-04-22T14:00",
                "2026-04-23T00:00",
            ],
            "temperature_2m": [12.8, 14.0, 14.5, 9.5],
            "weather_code": [3, 2, 1, 0],
            "precipitation_probability": [30, 20, 10, 5],
            "cloud_cover": [88, 52, 18, 0],
        },
    }

    snapshot = normalize_overview_weather_payload(
        payload,
        now=datetime.datetime(2026, 4, 22, 13, 27),
    )

    assert snapshot.current_temperature == 14.2
    assert snapshot.apparent_temperature == 13.4
    assert snapshot.relative_humidity == 58.0
    assert snapshot.condition_label == "Polojasno"
    assert snapshot.condition_key == "clouds"
    assert snapshot.wind_speed == 18.6
    assert snapshot.sunset_at == datetime.datetime(2026, 4, 22, 19, 58)
    assert [point.day_label for point in snapshot.daily_forecast] == ["Čt", "Pá", "So", "Ne", "Po"]
    assert snapshot.daily_forecast[0].target_date == datetime.date(2026, 4, 23)
    assert snapshot.daily_forecast[0].temperature_max == 17.0
    assert snapshot.daily_forecast[0].temperature_min == 7.0
    assert snapshot.daily_forecast[0].precipitation_probability_max == 10.0
    assert snapshot.daily_forecast[0].cloud_cover_mean == 20.0
    assert snapshot.daily_forecast[-1].target_date == datetime.date(2026, 4, 27)
    assert [point.time_label for point in snapshot.hourly_forecast] == ["13:00", "14:00"]
    assert snapshot.hourly_forecast[0].temperature == 14.0
    assert snapshot.hourly_forecast[0].precipitation_probability == 20.0
    assert snapshot.hourly_forecast[0].cloud_cover == 52.0
    assert snapshot.hourly_forecast[1].condition_key == "clear"
    assert snapshot.hourly_forecast[1].cloud_cover == 18.0
