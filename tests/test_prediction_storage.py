import datetime

import pytest
from sqlalchemy.dialects import postgresql

from moduly.mereni.prediction import (
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionMetricSummary,
    PredictionSelectedModelDecision,
    PredictionSelectedModelSnapshot,
    PredictionSelectionFallbackReason,
    SELECTION_MODE_ACTIVE,
    SELECTION_MODE_DRY_RUN,
    build_insert_selected_model_snapshots_statement,
    build_selected_model_snapshot_lookup_statement,
    decision_to_selected_model_snapshot_row,
    load_selected_model_decision,
    normalize_selection_mode,
    persist_selected_model_decisions,
    selected_model_snapshot_row_to_decision,
)


def _weekly_period() -> PredictionForecastPeriod:
    return PredictionForecastPeriod(
        start=datetime.datetime(2026, 7, 13),
        end=datetime.datetime(2026, 7, 20),
        cadence=PredictionForecastCadence.WEEKLY,
        label="2026-W29",
    )


def _decision() -> PredictionSelectedModelDecision:
    return PredictionSelectedModelDecision(
        medium_key="vodomery",
        identifier="L1_V1",
        forecast_period=_weekly_period(),
        selection_run_id=29,
        selected_model_version=2,
        selected_model_key="adaptive_strategy",
        selected_model_name="Model 2 - adaptive strategy",
        global_model_version=3,
        global_model_key="recency_weighted_blend",
        global_model_name="Model 3 - recency weighted blend",
        metrics=PredictionMetricSummary(
            validation_total_count=100,
            matched_validation_count=96,
            coverage=0.96,
            mae=0.1,
            rmse=0.2,
            bias=-0.03,
            wape=0.15,
        ),
        created_at=datetime.datetime(2026, 7, 9, 9, 0),
        metadata={"source": "unit_test"},
    )


def test_selected_model_snapshot_table_has_generic_identity():
    table = PredictionSelectedModelSnapshot.__table__
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.name == "uq_prediction_selected_model_snapshots_identity"
    }

    assert table.schema == "monitoring"
    assert (
        "medium_key",
        "identifier",
        "forecast_period_start",
        "forecast_period_end",
        "forecast_cadence",
        "selection_mode",
    ) in unique_column_sets


def test_decision_to_snapshot_row_serializes_decision_and_metrics():
    row = decision_to_selected_model_snapshot_row(
        _decision(),
        selection_mode=SELECTION_MODE_DRY_RUN,
    )

    assert row["medium_key"] == "vodomery"
    assert row["identifier"] == "L1_V1"
    assert row["forecast_period_start"] == datetime.datetime(2026, 7, 13)
    assert row["forecast_period_end"] == datetime.datetime(2026, 7, 20)
    assert row["forecast_cadence"] == "weekly"
    assert row["forecast_period_label"] == "2026-W29"
    assert row["selection_mode"] == "dry_run"
    assert row["selection_run_id"] == 29
    assert row["selected_model_version"] == 2
    assert row["selected_model_key"] == "adaptive_strategy"
    assert row["global_model_version"] == 3
    assert row["global_model_key"] == "recency_weighted_blend"
    assert row["fallback_reason"] == "none"
    assert row["uses_fallback"] is False
    assert row["validation_total_count"] == 100
    assert row["matched_validation_count"] == 96
    assert row["coverage"] == 0.96
    assert row["wape"] == 0.15
    assert row["metadata_json"] == '{"source": "unit_test"}'
    assert row["created_at"] == datetime.datetime(2026, 7, 9, 9, 0)


def test_decision_to_snapshot_row_serializes_global_fallback():
    fallback_decision = PredictionSelectedModelDecision(
        medium_key="vodomery",
        identifier="L1_V1",
        forecast_period=_weekly_period(),
        selection_run_id=29,
        selected_model_version=3,
        selected_model_key="recency_weighted_blend",
        selected_model_name="Model 3 - recency weighted blend",
        global_model_version=3,
        global_model_key="recency_weighted_blend",
        global_model_name="Model 3 - recency weighted blend",
        fallback_reason=PredictionSelectionFallbackReason.NO_ELIGIBLE_CANDIDATE,
    )

    row = decision_to_selected_model_snapshot_row(
        fallback_decision,
        selection_mode=SELECTION_MODE_ACTIVE,
    )

    assert row["selection_mode"] == "active"
    assert row["uses_fallback"] is True
    assert row["fallback_reason"] == "no_eligible_candidate"
    assert row["validation_total_count"] is None


def test_build_insert_snapshot_statement_preserves_historical_rows():
    row = decision_to_selected_model_snapshot_row(_decision())
    statement = build_insert_selected_model_snapshots_statement([row])
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "INSERT INTO monitoring.prediction_selected_model_snapshots" in compiled_sql
    assert "ON CONFLICT" in compiled_sql
    assert "DO NOTHING" in compiled_sql
    assert "medium_key" in compiled_sql
    assert "identifier" in compiled_sql
    assert "forecast_period_start" in compiled_sql
    assert "selection_mode" in compiled_sql


def test_persist_selected_model_decisions_returns_inserted_count():
    captured = {}

    class FakeResult:
        rowcount = 1

    class FakeSession:
        def execute(self, statement):
            captured["statement"] = statement
            return FakeResult()

    inserted_count = persist_selected_model_decisions(
        FakeSession(),
        [_decision()],
        selection_mode=SELECTION_MODE_DRY_RUN,
    )

    assert inserted_count == 1
    assert captured["statement"].table.name == "prediction_selected_model_snapshots"


def test_persist_selected_model_decisions_skips_empty_batches():
    class FakeSession:
        def execute(self, statement):
            raise AssertionError("empty batches should not hit the database")

    assert persist_selected_model_decisions(FakeSession(), []) == 0


def test_snapshot_row_to_decision_round_trips_storage_payload():
    row = decision_to_selected_model_snapshot_row(_decision())

    decision = selected_model_snapshot_row_to_decision(row)

    assert decision.medium_key == "vodomery"
    assert decision.identifier == "L1_V1"
    assert decision.forecast_period.cadence is PredictionForecastCadence.WEEKLY
    assert decision.selected_model_version == 2
    assert decision.global_model_version == 3
    assert decision.uses_fallback is False
    assert decision.metrics is not None
    assert decision.metrics.matched_validation_count == 96
    assert decision.metrics.wape == 0.15
    assert decision.metadata == {"source": "unit_test"}


def test_build_lookup_statement_targets_active_snapshot_by_default():
    statement = build_selected_model_snapshot_lookup_statement(
        medium_key="vodomery",
        identifier="L1_V1",
        forecast_period=_weekly_period(),
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    compiled_sql = str(compiled)

    assert "FROM monitoring.prediction_selected_model_snapshots" in compiled_sql
    assert compiled.params["medium_key_1"] == "vodomery"
    assert compiled.params["identifier_1"] == "L1_V1"
    assert compiled.params["selection_mode_1"] == "active"


def test_load_selected_model_decision_returns_none_when_snapshot_is_missing():
    class EmptyMappings:
        def first(self):
            return None

    class EmptyResult:
        def mappings(self):
            return EmptyMappings()

    class FakeSession:
        def execute(self, statement):
            return EmptyResult()

    assert (
        load_selected_model_decision(
            FakeSession(),
            medium_key="vodomery",
            identifier="L1_V1",
            forecast_period=_weekly_period(),
        )
        is None
    )


def test_load_selected_model_decision_deserializes_found_snapshot():
    row = decision_to_selected_model_snapshot_row(_decision())

    class Mappings:
        def first(self):
            return row

    class Result:
        def mappings(self):
            return Mappings()

    class FakeSession:
        def execute(self, statement):
            return Result()

    decision = load_selected_model_decision(
        FakeSession(),
        medium_key="vodomery",
        identifier="L1_V1",
        forecast_period=_weekly_period(),
        selection_mode=SELECTION_MODE_DRY_RUN,
    )

    assert decision is not None
    assert decision.selected_model_key == "adaptive_strategy"
    assert decision.metrics is not None
    assert decision.metrics.validation_total_count == 100


def test_normalize_selection_mode_rejects_unknown_values():
    with pytest.raises(ValueError, match="Unsupported prediction selection mode"):
        normalize_selection_mode("shadow")
