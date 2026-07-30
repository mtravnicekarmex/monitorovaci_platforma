import datetime

from sqlalchemy.dialects import postgresql

from moduly.apps.meteo import meteo_sync
from moduly.apps.meteo.database.models import MeteoForecastHourly


class _Session:
    def __init__(self):
        self.statement = None
        self.commit_count = 0

    def execute(self, statement):
        self.statement = statement

    def commit(self):
        self.commit_count += 1


def _forecast_payload(hours=2):
    times = [
        (datetime.datetime(2026, 8, 2) + datetime.timedelta(hours=offset))
        .isoformat()
        for offset in range(hours)
    ]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [10.0] * hours,
            "apparent_temperature": [9.0] * hours,
            "relative_humidity_2m": [70.0] * hours,
            "precipitation": [0.0] * hours,
            "snowfall": [0.0] * hours,
            "cloud_cover": [20.0] * hours,
            "wind_speed_10m": [2.0] * hours,
            "surface_pressure": [1000.0] * hours,
        }
    }


def test_forecast_horizon_covers_sunday_run_and_following_prague_week():
    assert meteo_sync.FORECAST_DAYS >= 9


def test_forecast_model_archives_run_and_hour_as_composite_identity():
    primary_keys = {
        column.name
        for column in MeteoForecastHourly.__table__.primary_key.columns
    }
    assert primary_keys == {"forecast_run_at", "datetime_hour"}


def test_forecast_upsert_conflicts_only_within_same_run_and_hour():
    session = _Session()
    meteo_sync.upsert_forecast(
        session,
        _forecast_payload(),
        forecast_run_at=datetime.datetime(2026, 8, 2, 0, 15),
    )
    sql = str(
        session.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )
    assert "ON CONFLICT (forecast_run_at, datetime_hour)" in sql
    assert session.commit_count == 1
