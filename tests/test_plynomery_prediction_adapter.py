import datetime

from sqlalchemy.dialects import postgresql

from moduly.mereni.plynomery.prediction_adapter import (
    PlynomeryPredictionAdapter,
    build_plynomery_observations_statement,
    profile_point_to_plynomery_row,
    serialize_plynomery_observation,
    serialize_plynomery_selection_metadata,
)
from moduly.mereni.prediction import PredictionProfilePoint, PredictionTimeWindow


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_plynomery_adapter_uses_injected_active_model_loader():
    session = FakeSession()
    calls = []

    def load_active_model(*, session, default):
        calls.append((session, default))
        return 2

    adapter = PlynomeryPredictionAdapter(
        session_factory=lambda: session,
        active_model_loader=load_active_model,
    )

    assert adapter.get_active_model_version() == 2
    assert calls == [(session, 1)]
    assert session.closed is True


def test_build_plynomery_observations_statement_uses_current_quality_filters():
    window = PredictionTimeWindow(
        start=datetime.datetime(2026, 6, 1),
        end=datetime.datetime(2026, 7, 1),
    )
    statement = build_plynomery_observations_statement(
        window,
        identifiers=["P1", "P1", "P2"],
    )
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert 'FROM monitoring."Mereni_plynomery_vse"' in compiled_sql
    assert '"Mereni_plynomery_vse".synthetic IS false' in compiled_sql
    assert '"Mereni_plynomery_vse".platne IS true' in compiled_sql
    assert '"Mereni_plynomery_vse".reset_detected IS false' in compiled_sql
    assert '"Mereni_plynomery_vse".delta IS NOT NULL' in compiled_sql
    assert '"Mereni_plynomery_vse".date >= ' in compiled_sql
    assert '"Mereni_plynomery_vse".date < ' in compiled_sql
    assert '"Mereni_plynomery_vse".identifikace IN ' in compiled_sql
    assert len(statement.compile().params["identifikace_1"]) == 2


def test_serialize_plynomery_observation_preserves_prediction_fields_and_features():
    timestamp = datetime.datetime(2026, 6, 3, 12, 15)
    row = {
        "measurement_id": 42,
        "identifikace": "P1",
        "date": timestamp,
        "delta": 1.25,
        "interval_minutes": 60,
        "day_of_week": 2,
        "slot": 13,
        "objem": 1234.5,
        "nocni_odber": False,
        "zdroj": "AREAL",
        "time_utc": datetime.datetime(2026, 6, 3, 10, 15, tzinfo=datetime.timezone.utc),
    }

    observation = serialize_plynomery_observation(row)

    assert observation.identifier == "P1"
    assert observation.timestamp == timestamp
    assert observation.actual_value == 1.25
    assert observation.interval_minutes == 60
    assert observation.day_of_week == 2
    assert observation.slot == 13
    assert observation.features["measurement_id"] == 42
    assert observation.features["objem"] == 1234.5
    assert observation.features["zdroj"] == "AREAL"


def test_serialize_plynomery_selection_metadata_uses_existing_selection_windows():
    row = {
        "selection_run_id": 13,
        "selected_model_version": 2,
        "selected_model_name": "Model 2 - weather adjusted baseline",
        "train_start": datetime.datetime(2026, 3, 1),
        "train_end": datetime.datetime(2026, 6, 1),
        "validation_start": datetime.datetime(2026, 6, 1),
        "validation_end": datetime.datetime(2026, 7, 1),
        "deploy_start": datetime.datetime(2026, 3, 1),
        "deploy_end": datetime.datetime(2026, 7, 1),
        "created_at": datetime.datetime(2026, 7, 6, 4, 10),
    }

    metadata = serialize_plynomery_selection_metadata(row)

    assert metadata.medium_key == "plynomery"
    assert metadata.selection_run_id == 13
    assert metadata.selected_model_version == 2
    assert metadata.train.label == "train"
    assert metadata.validation.start == row["validation_start"]
    assert metadata.deploy.end == row["deploy_end"]


def test_profile_point_to_plynomery_row_matches_existing_profile_table_columns():
    profile = PredictionProfilePoint(
        identifier="P1",
        interval_minutes=60,
        day_of_week=1,
        slot=5,
        expected_mean=1.1,
        expected_median=1.0,
        expected_p10=0.1,
        expected_p90=2.0,
        expected_std=0.0,
        sample_size=9,
        model_version=999,
    )

    assert profile_point_to_plynomery_row(profile, model_version=4) == {
        "identifikace": "P1",
        "interval_minutes": 60,
        "day_of_week": 1,
        "slot": 5,
        "median": 1.0,
        "mean": 1.1,
        "p10": 0.1,
        "p90": 2.0,
        "std": 0.0001,
        "model_version": 4,
        "sample_size": 9,
    }
