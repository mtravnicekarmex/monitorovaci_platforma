from __future__ import annotations

import datetime

import pytest
from sqlalchemy.dialects import postgresql

from moduly.mereni.kalorimetry.database.models import (
    KalorimetryModelSelectionRun,
    KalorimetryProfilesAnomaly,
)
from moduly.mereni.kalorimetry.prediction_adapter import (
    KalorimetryPredictionAdapter,
    build_kalorimetry_observations_statement,
    build_kalorimetry_weather_observations_statement,
    profile_point_to_kalorimetry_row,
    serialize_kalorimetry_observation,
    serialize_kalorimetry_selection_metadata,
)
from moduly.mereni.prediction import PredictionProfilePoint, PredictionTimeWindow


class FakeSession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_kalorimetry_adapter_models_use_dedicated_monitoring_tables():
    assert KalorimetryProfilesAnomaly.__tablename__ == "kalorimetry_anomaly_profiles"
    assert KalorimetryProfilesAnomaly.__table__.schema == "monitoring"
    assert {
        "identifikace",
        "interval_minutes",
        "day_of_week",
        "slot",
        "median",
        "mean",
        "p10",
        "p90",
        "std",
        "model_version",
        "sample_size",
    }.issubset(KalorimetryProfilesAnomaly.__table__.c.keys())
    assert (
        KalorimetryModelSelectionRun.__tablename__
        == "kalorimetry_model_selection_runs"
    )
    assert KalorimetryModelSelectionRun.__table__.schema == "monitoring"


def valid_row(**overrides):
    row = {
        "measurement_id": 42,
        "identifikace": "KAL-01",
        "date": datetime.datetime(2026, 7, 29, 8, 45),
        "delta": 2.5,
        "interval_minutes": 15,
        "day_of_week": 2,
        "slot": 35,
        "spotreba_energie": 12345.0,
        "objem": 678.0,
        "nocni_odber": False,
        "zdroj": "AREAL",
        "time_utc": datetime.datetime(2026, 7, 29, 6, 45, tzinfo=datetime.UTC),
        "platne": True,
        "reset_detected": False,
        "synthetic": False,
        "gap_detected": False,
    }
    row.update(overrides)
    return row


def test_kalorimetry_adapter_uses_injected_active_model_loader():
    session = FakeSession()
    calls = []

    def load_active_model(*, session, default):
        calls.append((session, default))
        return 2

    adapter = KalorimetryPredictionAdapter(
        session_factory=lambda: session,
        active_model_loader=load_active_model,
    )

    assert adapter.get_active_model_version() == 2
    assert calls == [(session, 1)]
    assert session.closed is True


def test_build_kalorimetry_observations_statement_matches_quality_contract():
    window = PredictionTimeWindow(
        start=datetime.datetime(2026, 6, 1),
        end=datetime.datetime(2026, 7, 1),
    )
    statement = build_kalorimetry_observations_statement(
        window,
        identifiers=["KAL-01", "KAL-01", "KAL-02", ""],
    )
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert 'FROM monitoring."Mereni_kalorimetry_vse"' in compiled_sql
    assert '"Mereni_kalorimetry_vse".platne IS true' in compiled_sql
    assert '"Mereni_kalorimetry_vse".reset_detected IS false' in compiled_sql
    assert '"Mereni_kalorimetry_vse".synthetic IS false' in compiled_sql
    assert '"Mereni_kalorimetry_vse".gap_detected IS false' in compiled_sql
    assert '"Mereni_kalorimetry_vse".delta IS NOT NULL' in compiled_sql
    assert '"Mereni_kalorimetry_vse".delta >= ' in compiled_sql
    assert '"Mereni_kalorimetry_vse".interval_minutes > ' in compiled_sql
    assert '"Mereni_kalorimetry_vse".date >= ' in compiled_sql
    assert '"Mereni_kalorimetry_vse".date < ' in compiled_sql
    assert '"Mereni_kalorimetry_vse".identifikace IN ' in compiled_sql
    assert len(statement.compile().params["identifikace_1"]) == 2


def test_weather_observations_join_leakage_safe_trailing_hdd_window():
    window = PredictionTimeWindow(
        start=datetime.datetime(2026, 1, 1),
        end=datetime.datetime(2026, 2, 1),
    )
    statement = build_kalorimetry_weather_observations_statement(window)
    compiled = statement.compile(dialect=postgresql.dialect())
    compiled_sql = str(compiled)

    assert "monitoring.meteo_hourly" in compiled_sql
    assert "ROWS BETWEEN " in compiled_sql
    assert compiled.params["param_1"] == 23
    assert "CURRENT ROW" in compiled_sql
    assert "hdd_24h" in compiled_sql
    assert '"Mereni_kalorimetry_vse".synthetic IS false' in compiled_sql
    assert '"Mereni_kalorimetry_vse".gap_detected IS false' in compiled_sql


def test_serialize_kalorimetry_observation_uses_energy_delta_and_preserves_state_features():
    row = valid_row()

    observation = serialize_kalorimetry_observation(row)

    assert observation.identifier == "KAL-01"
    assert observation.timestamp == row["date"]
    assert observation.actual_value == 2.5
    assert observation.interval_minutes == 15
    assert observation.day_of_week == 2
    assert observation.slot == 35
    assert observation.features["measurement_id"] == 42
    assert observation.features["spotreba_energie"] == 12345.0
    assert observation.features["objem"] == 678.0
    assert observation.features["zdroj"] == "AREAL"


def test_serialize_weather_observation_preserves_hdd_feature():
    observation = serialize_kalorimetry_observation(
        valid_row(hdd_24h=4.25)
    )

    assert observation.features["hdd_24h"] == 4.25


@pytest.mark.parametrize(
    "overrides",
    [
        {"platne": False},
        {"reset_detected": True},
        {"synthetic": True},
        {"gap_detected": True},
        {"delta": None},
        {"delta": -0.1},
        {"delta": float("inf")},
        {"spotreba_energie": float("nan")},
    ],
)
def test_serializer_refuses_rows_outside_the_pure_quality_contract(overrides):
    with pytest.raises(ValueError, match="model-input quality"):
        serialize_kalorimetry_observation(valid_row(**overrides))


def test_serialize_kalorimetry_selection_metadata_uses_selection_windows():
    row = {
        "selection_run_id": 5,
        "selected_model_version": 1,
        "selected_model_name": "Kalorimetry calendar baseline",
        "train_start": datetime.datetime(2026, 3, 1),
        "train_end": datetime.datetime(2026, 6, 1),
        "validation_start": datetime.datetime(2026, 6, 1),
        "validation_end": datetime.datetime(2026, 7, 1),
        "deploy_start": datetime.datetime(2026, 7, 27),
        "deploy_end": datetime.datetime(2026, 8, 3),
        "created_at": datetime.datetime(2026, 7, 27, 6, 10),
    }

    metadata = serialize_kalorimetry_selection_metadata(row)

    assert metadata.medium_key == "kalorimetry"
    assert metadata.selection_run_id == 5
    assert metadata.selected_model_version == 1
    assert metadata.train.label == "train"
    assert metadata.validation.start == row["validation_start"]
    assert metadata.deploy.end == row["deploy_end"]


def test_profile_point_to_kalorimetry_row_clamps_negative_expected_energy():
    profile = PredictionProfilePoint(
        identifier="KAL-01",
        interval_minutes=15,
        day_of_week=1,
        slot=32,
        expected_mean=-0.11,
        expected_median=-0.1,
        expected_p10=-0.2,
        expected_p90=0.3,
        expected_std=0.0,
        sample_size=9,
        model_version=999,
    )

    assert profile_point_to_kalorimetry_row(profile, model_version=1) == {
        "identifikace": "KAL-01",
        "interval_minutes": 15,
        "day_of_week": 1,
        "slot": 32,
        "median": 0.0,
        "mean": 0.0,
        "p10": 0.0,
        "p90": 0.3,
        "std": 0.0001,
        "model_version": 1,
        "sample_size": 9,
    }
