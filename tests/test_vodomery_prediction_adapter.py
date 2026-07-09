import datetime

from sqlalchemy.dialects import postgresql

from moduly.mereni.prediction import PredictionProfilePoint, PredictionTimeWindow
from moduly.mereni.vodomery.prediction_adapter import (
    VodomeryPredictionAdapter,
    build_vodomery_observations_statement,
    profile_point_to_vodomery_row,
    serialize_vodomery_observation,
    serialize_vodomery_selection_metadata,
)


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_vodomery_adapter_uses_injected_active_model_loader():
    session = FakeSession()
    calls = []

    def load_active_model(*, session, default):
        calls.append((session, default))
        return 3

    adapter = VodomeryPredictionAdapter(
        session_factory=lambda: session,
        active_model_loader=load_active_model,
    )

    assert adapter.get_active_model_version() == 3
    assert calls == [(session, 1)]
    assert session.closed is True


def test_build_vodomery_observations_statement_uses_current_quality_filters():
    window = PredictionTimeWindow(
        start=datetime.datetime(2026, 6, 1),
        end=datetime.datetime(2026, 7, 1),
    )
    statement = build_vodomery_observations_statement(
        window,
        identifiers=["L1_V1", "L1_V1", "A_V1"],
    )
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert 'FROM monitoring."Mereni_vodomery_vse"' in compiled_sql
    assert '"Mereni_vodomery_vse".synthetic IS false' in compiled_sql
    assert '"Mereni_vodomery_vse".platne IS true' in compiled_sql
    assert '"Mereni_vodomery_vse".reset_detected IS false' in compiled_sql
    assert '"Mereni_vodomery_vse".delta IS NOT NULL' in compiled_sql
    assert '"Mereni_vodomery_vse".date >= ' in compiled_sql
    assert '"Mereni_vodomery_vse".date < ' in compiled_sql
    assert '"Mereni_vodomery_vse".identifikace IN ' in compiled_sql
    assert len(statement.compile().params["identifikace_1"]) == 2


def test_serialize_vodomery_observation_preserves_prediction_fields_and_features():
    timestamp = datetime.datetime(2026, 6, 3, 12, 15)
    row = {
        "measurement_id": 42,
        "identifikace": "L1_V1",
        "date": timestamp,
        "delta": 0.125,
        "interval_minutes": 15,
        "day_of_week": 2,
        "slot": 49,
        "objem": 1234.5,
        "nocni_odber": False,
        "zdroj": "AREAL",
        "time_utc": datetime.datetime(2026, 6, 3, 10, 15, tzinfo=datetime.timezone.utc),
    }

    observation = serialize_vodomery_observation(row)

    assert observation.identifier == "L1_V1"
    assert observation.timestamp == timestamp
    assert observation.actual_value == 0.125
    assert observation.interval_minutes == 15
    assert observation.day_of_week == 2
    assert observation.slot == 49
    assert observation.features["measurement_id"] == 42
    assert observation.features["objem"] == 1234.5
    assert observation.features["zdroj"] == "AREAL"


def test_serialize_vodomery_selection_metadata_uses_existing_selection_windows():
    row = {
        "selection_run_id": 7,
        "selected_model_version": 3,
        "selected_model_name": "Model 3 - recency weighted blend",
        "train_start": datetime.datetime(2026, 3, 1),
        "train_end": datetime.datetime(2026, 6, 1),
        "validation_start": datetime.datetime(2026, 6, 1),
        "validation_end": datetime.datetime(2026, 7, 1),
        "deploy_start": datetime.datetime(2026, 3, 1),
        "deploy_end": datetime.datetime(2026, 7, 1),
        "created_at": datetime.datetime(2026, 7, 6, 4, 10),
    }

    metadata = serialize_vodomery_selection_metadata(row)

    assert metadata.medium_key == "vodomery"
    assert metadata.selection_run_id == 7
    assert metadata.selected_model_version == 3
    assert metadata.train.label == "train"
    assert metadata.validation.start == row["validation_start"]
    assert metadata.deploy.end == row["deploy_end"]


def test_profile_point_to_vodomery_row_matches_existing_profile_table_columns():
    profile = PredictionProfilePoint(
        identifier="L1_V1",
        interval_minutes=15,
        day_of_week=1,
        slot=32,
        expected_mean=0.11,
        expected_median=0.1,
        expected_p10=0.01,
        expected_p90=0.2,
        expected_std=0.0,
        sample_size=9,
        model_version=999,
    )

    assert profile_point_to_vodomery_row(profile, model_version=4) == {
        "identifikace": "L1_V1",
        "interval_minutes": 15,
        "day_of_week": 1,
        "slot": 32,
        "median": 0.1,
        "mean": 0.11,
        "p10": 0.01,
        "p90": 0.2,
        "std": 0.0001,
        "model_version": 4,
        "sample_size": 9,
    }
