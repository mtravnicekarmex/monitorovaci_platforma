import datetime

import pytest
from sqlalchemy.dialects import postgresql

from moduly.mereni.prediction import (
    ARCHIVE_SOURCE_HISTORICAL_BACKFILL,
    ARCHIVE_SOURCE_WEEKLY_REBUILD,
    PredictionBackfillCandidateMetric,
    PredictionForecastCadence,
    PredictionForecastPeriod,
    PredictionMetricSummary,
    PredictionProfileSnapshot,
    PredictionSelectedModelDecision,
    PredictionSelectedModelSnapshot,
    PredictionSelectionFallbackReason,
    SELECTION_MODE_ACTIVE,
    SELECTION_MODE_DRY_RUN,
    build_insert_prediction_backfill_candidate_metrics_statement,
    build_insert_prediction_profile_snapshots_statement,
    build_insert_selected_model_snapshots_statement,
    build_selected_model_snapshot_lookup_statement,
    decision_to_selected_model_snapshot_row,
    load_selected_model_decision,
    normalize_archive_source,
    normalize_selection_mode,
    persist_prediction_backfill_candidate_metrics,
    persist_prediction_profile_snapshots,
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


def _profile_snapshot_row() -> dict[str, object]:
    return {
        "medium_key": "vodomery",
        "identifier": "L1_V1",
        "forecast_period_start": datetime.datetime(2026, 7, 13),
        "forecast_period_end": datetime.datetime(2026, 7, 20),
        "forecast_cadence": "weekly",
        "forecast_period_label": "2026-W29",
        "archive_source": ARCHIVE_SOURCE_WEEKLY_REBUILD,
        "archive_version": 1,
        "selection_mode": SELECTION_MODE_ACTIVE,
        "selection_run_id": 29,
        "archive_run_id": None,
        "model_version": 2,
        "model_key": "adaptive_strategy",
        "model_name": "Model 2 - adaptive strategy",
        "global_model_version": 3,
        "global_model_key": "recency_weighted_blend",
        "global_model_name": "Model 3 - recency weighted blend",
        "uses_fallback": False,
        "fallback_reason": "none",
        "interval_minutes": 60,
        "day_of_week": 0,
        "slot": 8,
        "expected_mean": 0.25,
        "expected_median": 0.2,
        "expected_p10": 0.05,
        "expected_p90": 0.5,
        "expected_std": 0.1,
        "sample_size": 12,
        "created_at": datetime.datetime(2026, 7, 13, 4, 15),
    }


def _backfill_candidate_metric_row() -> dict[str, object]:
    return {
        "medium_key": "vodomery",
        "identifier": "L1_V1",
        "forecast_period_start": datetime.datetime(2026, 7, 13),
        "forecast_period_end": datetime.datetime(2026, 7, 20),
        "forecast_cadence": "weekly",
        "forecast_period_label": "2026-W29",
        "archive_version": 1,
        "archive_run_id": "backfill-20260713-001",
        "model_version": 2,
        "model_key": "adaptive_strategy",
        "model_name": "Model 2 - adaptive strategy",
        "selection_enabled": True,
        "selected": True,
        "eligible": True,
        "rank_by_policy": 1,
        "fallback_reason": None,
        "validation_total_count": 100,
        "matched_validation_count": 96,
        "coverage": 0.96,
        "mae": 0.1,
        "rmse": 0.2,
        "bias": -0.03,
        "wape": 0.15,
        "training_window_start": datetime.datetime(2026, 4, 13),
        "training_window_end": datetime.datetime(2026, 6, 13),
        "validation_window_start": datetime.datetime(2026, 6, 13),
        "validation_window_end": datetime.datetime(2026, 7, 13),
        "created_at": datetime.datetime(2026, 7, 13, 4, 15),
    }


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


def test_profile_snapshot_table_has_selected_profile_identity():
    table = PredictionProfileSnapshot.__table__
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.name == "uq_prediction_profile_snapshots_identity"
    }

    assert table.schema == "monitoring"
    assert (
        "medium_key",
        "identifier",
        "forecast_period_start",
        "forecast_period_end",
        "forecast_cadence",
        "archive_source",
        "archive_version",
        "selection_mode",
        "interval_minutes",
        "day_of_week",
        "slot",
    ) in unique_column_sets
    assert all("model_version" not in columns for columns in unique_column_sets)


def test_profile_snapshot_expected_mean_is_required_but_bands_are_optional():
    table = PredictionProfileSnapshot.__table__

    assert table.c.expected_mean.nullable is False
    assert table.c.expected_median.nullable is True
    assert table.c.expected_p10.nullable is True
    assert table.c.expected_p90.nullable is True
    assert table.c.expected_std.nullable is True


def test_backfill_candidate_metric_table_has_versioned_identity():
    table = PredictionBackfillCandidateMetric.__table__
    unique_column_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.name == "uq_prediction_backfill_candidate_metrics_identity"
    }

    assert table.schema == "monitoring"
    assert (
        "medium_key",
        "identifier",
        "forecast_period_start",
        "forecast_period_end",
        "forecast_cadence",
        "archive_version",
        "model_version",
    ) in unique_column_sets
    assert all("archive_run_id" not in columns for columns in unique_column_sets)


def test_backfill_candidate_metric_required_and_optional_columns():
    table = PredictionBackfillCandidateMetric.__table__

    assert table.c.archive_run_id.nullable is False
    assert table.c.model_key.nullable is False
    assert table.c.model_name.nullable is False
    assert table.c.selection_enabled.nullable is False
    assert table.c.selected.nullable is False
    assert table.c.eligible.nullable is False
    assert table.c.validation_total_count.nullable is False
    assert table.c.matched_validation_count.nullable is False
    assert table.c.coverage.nullable is False
    assert table.c.rank_by_policy.nullable is True
    assert table.c.wape.nullable is True


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


def test_build_insert_profile_snapshot_statement_preserves_historical_rows():
    statement = build_insert_prediction_profile_snapshots_statement(
        [_profile_snapshot_row()]
    )
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "INSERT INTO monitoring.prediction_profile_snapshots" in compiled_sql
    assert "ON CONFLICT" in compiled_sql
    assert "DO NOTHING" in compiled_sql
    assert "archive_source" in compiled_sql
    assert "archive_version" in compiled_sql
    assert "model_version" in compiled_sql


def test_build_insert_backfill_candidate_metric_statement_preserves_versions():
    statement = build_insert_prediction_backfill_candidate_metrics_statement(
        [_backfill_candidate_metric_row()]
    )
    compiled_sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "INSERT INTO monitoring.prediction_backfill_candidate_metrics" in compiled_sql
    assert "ON CONFLICT" in compiled_sql
    assert "DO NOTHING" in compiled_sql
    assert "archive_version" in compiled_sql
    assert "archive_run_id" in compiled_sql
    assert "rank_by_policy" in compiled_sql


def test_persist_prediction_profile_snapshots_returns_inserted_count():
    captured = {}

    class FakeResult:
        rowcount = 2

    class FakeSession:
        def execute(self, statement):
            captured["statement"] = statement
            return FakeResult()

    inserted_count = persist_prediction_profile_snapshots(
        FakeSession(),
        [_profile_snapshot_row(), {**_profile_snapshot_row(), "slot": 9}],
    )

    assert inserted_count == 2
    assert captured["statement"].table.name == "prediction_profile_snapshots"


def test_persist_prediction_profile_snapshots_skips_empty_batches():
    class FakeSession:
        def execute(self, statement):
            raise AssertionError("empty batches should not hit the database")

    assert persist_prediction_profile_snapshots(FakeSession(), []) == 0


def test_persist_prediction_backfill_candidate_metrics_returns_inserted_count():
    captured = {}

    class FakeResult:
        rowcount = 3

    class FakeSession:
        def execute(self, statement):
            captured["statement"] = statement
            return FakeResult()

    inserted_count = persist_prediction_backfill_candidate_metrics(
        FakeSession(),
        [
            _backfill_candidate_metric_row(),
            {**_backfill_candidate_metric_row(), "model_version": 1},
            {**_backfill_candidate_metric_row(), "model_version": 3},
        ],
    )

    assert inserted_count == 3
    assert captured["statement"].table.name == "prediction_backfill_candidate_metrics"


def test_persist_prediction_backfill_candidate_metrics_skips_empty_batches():
    class FakeSession:
        def execute(self, statement):
            raise AssertionError("empty batches should not hit the database")

    assert persist_prediction_backfill_candidate_metrics(FakeSession(), []) == 0


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


def test_normalize_archive_source_accepts_only_supported_sources():
    assert normalize_archive_source(" weekly_rebuild ") == ARCHIVE_SOURCE_WEEKLY_REBUILD
    assert (
        normalize_archive_source("historical_backfill")
        == ARCHIVE_SOURCE_HISTORICAL_BACKFILL
    )

    with pytest.raises(ValueError, match="Unsupported prediction archive source"):
        normalize_archive_source("candidate_dry_run")
