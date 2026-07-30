import datetime

from moduly.mereni.kalorimetry import production_dry_run
from moduly.mereni.prediction import PredictionObservation


class _ReadOnlyAdapter:
    def __init__(self, observations):
        self.observations = observations
        self.load_count = 0

    def load_observations(self, window, *, identifiers=None):
        self.load_count += 1
        return tuple(
            row
            for row in self.observations
            if window.start <= row.timestamp < window.end
        )

    def load_weather_observations(self, window, *, identifiers=None):
        self.load_count += 1
        return tuple(
            row
            for row in self.observations
            if window.start <= row.timestamp < window.end
        )

    def __getattr__(self, name):
        if name.startswith(("replace", "persist", "ensure", "commit")):
            raise AssertionError(f"Dry-run attempted write method {name}.")
        raise AttributeError(name)


def _observations():
    rows = []
    cursor = datetime.datetime(2025, 6, 1)
    end = datetime.datetime(2026, 7, 27)
    measurement_id = 1
    while cursor < end:
        rows.append(
            PredictionObservation(
                identifier="K1",
                timestamp=cursor,
                actual_value=float((cursor.hour + 1) % 7),
                interval_minutes=15,
                day_of_week=cursor.weekday(),
                slot=(cursor.hour * 60 + cursor.minute) // 15,
                features={
                    "measurement_id": measurement_id,
                    "hdd_24h": 4.0,
                },
            )
        )
        cursor += datetime.timedelta(minutes=15)
        measurement_id += 1
    return tuple(rows)


def test_production_dry_run_is_read_only_and_returns_aggregate_report(
    monkeypatch,
):
    adapter = _ReadOnlyAdapter(_observations())
    reference = datetime.datetime(2026, 7, 29, 12)
    period = production_dry_run.build_kalorimetry_weekly_forecast_period(
        reference
    )
    required_hours = (
        production_dry_run.required_kalorimetry_forecast_utc_hours(period)
    )
    monkeypatch.setattr(
        production_dry_run,
        "load_latest_forecast_hdd_24h",
        lambda **kwargs: (
            datetime.datetime(2026, 7, 27),
            {hour: 4.0 for hour in required_hours},
        ),
    )

    result = production_dry_run.run_kalorimetry_production_dry_run(
        reference_time=reference,
        adapter=adapter,
    )
    aggregate = result.to_aggregate_dict()

    assert adapter.load_count == 2
    assert aggregate["mode"] == "production_read_only_dry_run"
    assert aggregate["identifier_count"] == 1
    assert aggregate["available_identifier_count"] == 1
    assert aggregate["unavailable_identifier_count"] == 0
    assert aggregate["winner_counts"]
    assert aggregate["observation_count"] > 0
    assert "actual_value" not in aggregate


def test_required_forecast_hours_cover_one_prague_week_once_per_hour():
    period = production_dry_run.build_kalorimetry_weekly_forecast_period(
        datetime.datetime(2026, 7, 29)
    )

    hours = production_dry_run.required_kalorimetry_forecast_utc_hours(period)

    assert len(hours) == 168
    assert hours[0] == datetime.datetime(2026, 7, 26, 22)
    assert hours[-1] == datetime.datetime(2026, 8, 2, 21)


def test_latest_forecast_must_be_issued_before_prague_period_start():
    period = production_dry_run.build_kalorimetry_weekly_forecast_period(
        datetime.datetime(2026, 7, 29)
    )

    class _Result:
        def scalar_one_or_none(self):
            return None

        def all(self):
            return []

    class _Session:
        def __init__(self):
            self.statements = []

        def execute(self, statement):
            self.statements.append(statement)
            return _Result()

        def close(self):
            pass

    session = _Session()
    issued_at, values = production_dry_run.load_latest_forecast_hdd_24h(
        forecast_period=period,
        session_factory=lambda: session,
    )
    compiled = str(session.statements[0].compile())
    assert "forecast_run_at <" in compiled
    assert issued_at is None
    assert values == {}
