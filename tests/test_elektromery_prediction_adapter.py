import datetime

from sqlalchemy.dialects import postgresql

from moduly.mereni.elektromery.prediction_adapter import (
    ElektromeryPredictionAdapter,
    aggregate_monthly_consumption,
    build_elektromery_observations_statement,
    serialize_elektromery_observation,
)
from moduly.mereni.prediction import PredictionObservation, PredictionTimeWindow


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_elektromery_adapter_returns_default_active_model_without_db_lookup():
    session = FakeSession()
    adapter = ElektromeryPredictionAdapter(
        session_factory=lambda: session,
        default_model_version=2,
    )

    assert adapter.get_active_model_version() == 2
    assert adapter.load_selection_metadata() is None
    assert session.closed is False


def test_build_elektromery_observations_statement_uses_monthly_consumption_filters():
    window = PredictionTimeWindow(
        start=datetime.datetime(2026, 6, 1),
        end=datetime.datetime(2026, 7, 1),
    )

    statement = build_elektromery_observations_statement(
        window,
        identifiers=["E1", "E1", "E2"],
    )
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert 'FROM monitoring."Mereni_elektromery_vse"' in compiled_sql
    assert '"Mereni_elektromery_vse".platne IS true' in compiled_sql
    assert '"Mereni_elektromery_vse".reset_detected IS false' in compiled_sql
    assert '"Mereni_elektromery_vse".delta IS NOT NULL' in compiled_sql
    assert '"Mereni_elektromery_vse".delta >= ' in compiled_sql
    assert '"Mereni_elektromery_vse".date >= ' in compiled_sql
    assert '"Mereni_elektromery_vse".date < ' in compiled_sql
    assert '"Mereni_elektromery_vse".synthetic IS false' not in compiled_sql
    assert '"Mereni_elektromery_vse".identifikace IN ' in compiled_sql
    assert len(statement.compile().params["identifikace_1"]) == 2


def test_serialize_elektromery_observation_preserves_source_and_gap_features():
    timestamp = datetime.datetime(2026, 6, 3, 12, 15)
    row = {
        "measurement_id": 42,
        "identifikace": "E1",
        "date": timestamp,
        "delta": 1.25,
        "interval_minutes": 15,
        "day_of_week": 2,
        "slot": 49,
        "objem": None,
        "nocni_odber": False,
        "gap_detected": True,
        "synthetic": True,
        "zdroj": "SOFTLINK",
        "time_utc": datetime.datetime(2026, 6, 3, 10, 15, tzinfo=datetime.timezone.utc),
    }

    observation = serialize_elektromery_observation(row)

    assert observation.identifier == "E1"
    assert observation.timestamp == timestamp
    assert observation.actual_value == 1.25
    assert observation.interval_minutes == 15
    assert observation.features["zdroj"] == "SOFTLINK"
    assert observation.features["gap_detected"] is True
    assert observation.features["synthetic"] is True


def test_aggregate_monthly_consumption_prefers_detailed_source_over_softlink():
    observations = (
        _observation("E1", datetime.datetime(2026, 6, 1, 0, 0), 100.0, "SOFTLINK"),
        _observation("E1", datetime.datetime(2026, 6, 1, 0, 15), 10.0, "BINARY_19891"),
        _observation("E1", datetime.datetime(2026, 6, 1, 0, 30), 15.0, "BINARY_19891"),
        _observation("E2", datetime.datetime(2026, 6, 2, 0, 0), 8.0, "SOFTLINK"),
    )

    rows = aggregate_monthly_consumption(observations)

    assert [(row.identifier, row.consumption_kwh, row.selected_source_kind) for row in rows] == [
        ("E1", 25.0, "detailed"),
        ("E2", 8.0, "softlink"),
    ]
    assert rows[0].measurement_count == 2
    assert rows[0].source_names == ("BINARY_19891",)


def _observation(
    identifier: str,
    timestamp: datetime.datetime,
    actual_value: float,
    source_name: str,
) -> PredictionObservation:
    return PredictionObservation(
        identifier=identifier,
        timestamp=timestamp,
        actual_value=actual_value,
        interval_minutes=15,
        day_of_week=timestamp.weekday(),
        slot=timestamp.hour * 4 + timestamp.minute // 15,
        features={"zdroj": source_name},
    )
