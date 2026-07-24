import datetime
from types import SimpleNamespace

from moduly.mereni.vodomery.vodomery_prediction_backfill import (
    VodomeryBackfillDryRunWeekResult,
    VodomeryBackfillIdentifierHistory,
    dry_run_vodomery_prediction_backfill,
    build_calendar_week_period,
    build_vodomery_backfill_plan,
    ceil_calendar_week_start,
    floor_calendar_week_start,
    plan_vodomery_prediction_backfill,
    write_vodomery_prediction_backfill,
    verify_vodomery_prediction_backfill,
)
from moduly.mereni.vodomery import vodomery_prediction
from moduly.mereni.vodomery import vodomery_prediction_backfill as backfill


def test_calendar_week_boundaries_use_monday_midnight():
    value = datetime.datetime(2024, 1, 3, 14, 30)

    assert floor_calendar_week_start(value) == datetime.datetime(2024, 1, 1)
    assert ceil_calendar_week_start(value) == datetime.datetime(2024, 1, 8)
    assert ceil_calendar_week_start(datetime.datetime(2024, 1, 8)) == datetime.datetime(
        2024,
        1,
        8,
    )


def test_build_calendar_week_period_uses_full_monday_week():
    period = build_calendar_week_period(datetime.datetime(2024, 1, 10, 8, 15))

    assert period.start == datetime.datetime(2024, 1, 8)
    assert period.end == datetime.datetime(2024, 1, 15)
    assert period.cadence.value == "weekly"
    assert period.label == "2024-01-08 - 2024-01-15"


def test_build_backfill_plan_applies_one_month_history_gate():
    plan = build_vodomery_backfill_plan(
        [
            VodomeryBackfillIdentifierHistory(
                identifier="L1_V1",
                first_measurement_at=datetime.datetime(2024, 1, 10, 8, 0),
                last_measurement_at=datetime.datetime(2024, 3, 5, 12, 0),
            )
        ],
        start_date=datetime.datetime(2024, 1, 1),
        end_date=datetime.datetime(2024, 3, 1),
    )

    assert [item.forecast_period.start for item in plan.items] == [
        datetime.datetime(2024, 2, 12),
        datetime.datetime(2024, 2, 19),
        datetime.datetime(2024, 2, 26),
    ]
    assert plan.identifier_count == 1
    assert plan.forecast_week_count == 3
    assert plan.identifier_week_count == 3
    assert plan.candidate_metric_row_estimate == 9


def test_build_backfill_plan_stops_after_identifier_last_measurement_week():
    plan = build_vodomery_backfill_plan(
        [
            VodomeryBackfillIdentifierHistory(
                identifier="L1_V1",
                first_measurement_at=datetime.datetime(2024, 1, 1),
                last_measurement_at=datetime.datetime(2024, 2, 13, 12, 0),
            )
        ],
        start_date=datetime.datetime(2024, 1, 1),
        end_date=datetime.datetime(2024, 3, 1),
    )

    assert [item.forecast_period.start for item in plan.items] == [
        datetime.datetime(2024, 2, 5),
        datetime.datetime(2024, 2, 12),
    ]


def test_build_backfill_plan_skips_existing_weekly_rebuild_periods():
    plan = build_vodomery_backfill_plan(
        [
            VodomeryBackfillIdentifierHistory(
                identifier="L1_V1",
                first_measurement_at=datetime.datetime(2024, 1, 1),
                last_measurement_at=datetime.datetime(2024, 2, 20),
            )
        ],
        start_date=datetime.datetime(2024, 1, 1),
        end_date=datetime.datetime(2024, 2, 20),
        existing_weekly_rebuild_periods={("L1_V1", datetime.datetime(2024, 2, 5))},
    )

    assert [item.forecast_period.start for item in plan.items] == [
        datetime.datetime(2024, 2, 12),
        datetime.datetime(2024, 2, 19),
    ]
    assert plan.skipped_counts == {"weekly_rebuild_exists": 1}


def test_build_backfill_plan_limits_identifiers_and_weeks_per_identifier():
    plan = build_vodomery_backfill_plan(
        [
            VodomeryBackfillIdentifierHistory(
                identifier="B_V1",
                first_measurement_at=datetime.datetime(2024, 1, 1),
                last_measurement_at=datetime.datetime(2024, 3, 1),
            ),
            VodomeryBackfillIdentifierHistory(
                identifier="A_V1",
                first_measurement_at=datetime.datetime(2024, 1, 1),
                last_measurement_at=datetime.datetime(2024, 3, 1),
            ),
        ],
        start_date=datetime.datetime(2024, 1, 1),
        end_date=datetime.datetime(2024, 3, 1),
        max_identifiers=1,
        max_weeks=2,
    )

    assert {item.identifier for item in plan.items} == {"A_V1"}
    assert [item.forecast_period.start for item in plan.items] == [
        datetime.datetime(2024, 2, 5),
        datetime.datetime(2024, 2, 12),
    ]


def test_plan_backfill_can_load_history_before_batch_start(monkeypatch):
    captured = {}

    class FakeSession:
        def close(self):
            captured["closed"] = True

    def fake_history(session, *, start_date, identifiers=None):
        captured["history_start_date"] = start_date
        return (
            VodomeryBackfillIdentifierHistory(
                identifier="A_V1",
                first_measurement_at=datetime.datetime(2024, 1, 1),
                last_measurement_at=datetime.datetime(2024, 3, 20),
            ),
        )

    monkeypatch.setattr(backfill, "get_session_pg", lambda: FakeSession())
    monkeypatch.setattr(
        backfill,
        "load_vodomery_backfill_identifier_history",
        fake_history,
    )

    plan = plan_vodomery_prediction_backfill(
        start_date=datetime.datetime(2024, 3, 1),
        end_date=datetime.datetime(2024, 4, 1),
        history_start_date=datetime.datetime(2024, 1, 1),
    )

    assert captured["history_start_date"] == datetime.datetime(2024, 1, 1)
    assert captured["closed"] is True
    assert [item.forecast_period.start for item in plan.items] == [
        datetime.datetime(2024, 3, 4),
        datetime.datetime(2024, 3, 11),
        datetime.datetime(2024, 3, 18),
    ]


def test_dry_run_backfill_calculates_week_and_rolls_back(monkeypatch):
    plan = build_vodomery_backfill_plan(
        [
            VodomeryBackfillIdentifierHistory(
                identifier="A_V1",
                first_measurement_at=datetime.datetime(2024, 1, 1),
                last_measurement_at=datetime.datetime(2024, 2, 10),
            )
        ],
        start_date=datetime.datetime(2024, 1, 1),
        end_date=datetime.datetime(2024, 2, 10),
    )
    definitions = {
        version: vodomery_prediction.CandidateModelDefinition(
            model_version=version,
            model_key=f"model_{version}",
            model_name=f"Model {version}",
            training_window_months=3,
            validation_window_months=1,
            selection_enabled=True,
        )
        for version in (1, 2, 3)
    }
    wape_by_model = {1: 0.3, 2: 0.1, 3: 0.2}

    def fake_rebuild_candidate(session, *, definition, windows):
        return vodomery_prediction.ModelPerformanceSummary(
            model_version=definition.model_version,
            model_key=definition.model_key,
            model_name=definition.model_name,
            training_window_months=3,
            validation_window_months=1,
            selection_enabled=True,
            validation_total_count=100,
            matched_validation_count=100,
            coverage=1.0,
            mae=wape_by_model[definition.model_version],
            rmse=wape_by_model[definition.model_version] + 0.1,
            bias=0.0,
            profile_count=10,
        )

    def fake_rolling(session, *, definition, reference_end):
        metrics = vodomery_prediction.PredictionMetricSummary(
            validation_total_count=80,
            matched_validation_count=80,
            coverage=1.0,
            mae=wape_by_model[definition.model_version],
            rmse=wape_by_model[definition.model_version] + 0.1,
            bias=0.0,
            wape=wape_by_model[definition.model_version],
        )
        return SimpleNamespace(
            metrics=metrics,
            device_metrics=(
                vodomery_prediction.DeviceModelPerformanceSummary(
                    identifikace="A_V1",
                    model_version=definition.model_version,
                    model_key=definition.model_key,
                    model_name=definition.model_name,
                    selection_enabled=True,
                    rolling_backtest_fold_count=8,
                    rolling_validation_total_count=80,
                    rolling_matched_validation_count=80,
                    rolling_coverage=1.0,
                    rolling_mae=wape_by_model[definition.model_version],
                    rolling_rmse=wape_by_model[definition.model_version] + 0.1,
                    rolling_bias=0.0,
                    rolling_wape=wape_by_model[definition.model_version],
                ),
            ),
        )

    class FakeSession:
        def __init__(self):
            self.rollback_count = 0

        def rollback(self):
            self.rollback_count += 1

    fake_session = FakeSession()
    monkeypatch.setattr(
        vodomery_prediction,
        "_get_candidate_model_definition",
        lambda version: definitions[version],
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "_build_windows_for_definition",
        lambda definition, reference_time: SimpleNamespace(reference_time=reference_time),
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "_rebuild_candidate_model",
        fake_rebuild_candidate,
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "_run_candidate_rolling_weekly_backtest_with_devices",
        fake_rolling,
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "_load_deployable_profile_pairs",
        lambda session, device_summaries: {
            ("A_V1", summary.model_version)
            for summary in device_summaries
        },
    )
    monkeypatch.setattr(
        vodomery_prediction,
        "_build_selected_prediction_profile_snapshot_rows",
        lambda session, decisions, **kwargs: tuple(
            {
                "identifier": decision.identifier,
                "model_version": decision.selected_model_version,
            }
            for decision in decisions
        ),
    )

    result = dry_run_vodomery_prediction_backfill(
        plan,
        archive_run_id="dry-run-001",
        session=fake_session,
    )

    assert fake_session.rollback_count == 1
    assert result.calculated_week_count == 1
    assert result.candidate_metric_row_count == 3
    assert result.selected_decision_count == 1
    assert result.selected_profile_pair_count == 1
    week = result.weeks[0]
    assert week.forecast_period.start == datetime.datetime(2024, 2, 5)
    assert week.planned_identifier_count == 1
    assert week.calculated_identifier_count == 1
    assert week.skipped_counts == {}


def test_write_backfill_persists_week_and_commits(monkeypatch):
    plan = build_vodomery_backfill_plan(
        [
            VodomeryBackfillIdentifierHistory(
                identifier="A_V1",
                first_measurement_at=datetime.datetime(2024, 1, 1),
                last_measurement_at=datetime.datetime(2024, 2, 10),
            )
        ],
        start_date=datetime.datetime(2024, 1, 1),
        end_date=datetime.datetime(2024, 2, 10),
    )
    summary = VodomeryBackfillDryRunWeekResult(
        forecast_period=build_calendar_week_period(datetime.datetime(2024, 2, 5)),
        planned_identifier_count=1,
        calculated_identifier_count=1,
        candidate_metric_row_count=3,
        selected_decision_count=1,
        selected_profile_pair_count=1,
    )
    calculation = backfill._BackfillWeekCalculation(
        summary=summary,
        selected_decisions=(SimpleNamespace(identifier="A_V1"),),
        candidate_metric_rows=({"identifier": "A_V1", "model_version": 2},),
        selected_profile_snapshot_rows=(
            {"identifier": "A_V1", "forecast_period_start": datetime.datetime(2024, 2, 5)},
        ),
    )

    class FakeSession:
        def __init__(self):
            self.commit_count = 0
            self.rollback_count = 0

        def commit(self):
            self.commit_count += 1

        def rollback(self):
            self.rollback_count += 1

    fake_session = FakeSession()
    captured = {}

    def fake_persist_candidate_metrics(session, rows):
        captured["candidate_rows"] = tuple(rows)
        return 3

    def fake_persist_profile_snapshots(session, decisions, **kwargs):
        captured["profile_rows"] = tuple(decisions)
        return len(decisions)

    monkeypatch.setattr(
        backfill,
        "_calculate_vodomery_backfill_week",
        lambda *args, **kwargs: calculation,
    )
    monkeypatch.setattr(
        backfill,
        "persist_prediction_backfill_candidate_metrics",
        fake_persist_candidate_metrics,
    )
    monkeypatch.setattr(
        backfill,
        "persist_prediction_profile_snapshots",
        fake_persist_profile_snapshots,
    )

    result = write_vodomery_prediction_backfill(
        plan,
        archive_run_id="write-001",
        session=fake_session,
    )

    assert fake_session.commit_count == 1
    assert fake_session.rollback_count == 1
    assert result.committed_week_count == 1
    assert result.inserted_candidate_metric_count == 3
    assert result.inserted_profile_snapshot_count == 1
    assert captured["profile_rows"][0]["identifier"] == "A_V1"


def test_write_backfill_rolls_back_week_on_error(monkeypatch):
    plan = build_vodomery_backfill_plan(
        [
            VodomeryBackfillIdentifierHistory(
                identifier="A_V1",
                first_measurement_at=datetime.datetime(2024, 1, 1),
                last_measurement_at=datetime.datetime(2024, 2, 10),
            )
        ],
        start_date=datetime.datetime(2024, 1, 1),
        end_date=datetime.datetime(2024, 2, 10),
    )
    calculation = backfill._BackfillWeekCalculation(
        summary=VodomeryBackfillDryRunWeekResult(
            forecast_period=build_calendar_week_period(datetime.datetime(2024, 2, 5)),
            planned_identifier_count=1,
            calculated_identifier_count=1,
            candidate_metric_row_count=3,
            selected_decision_count=1,
            selected_profile_pair_count=1,
        ),
        selected_decisions=(SimpleNamespace(identifier="A_V1"),),
        candidate_metric_rows=({"identifier": "A_V1", "model_version": 2},),
        selected_profile_snapshot_rows=(
            {"identifier": "A_V1", "forecast_period_start": datetime.datetime(2024, 2, 5)},
        ),
    )

    class FakeSession:
        def __init__(self):
            self.commit_count = 0
            self.rollback_count = 0

        def commit(self):
            self.commit_count += 1

        def rollback(self):
            self.rollback_count += 1

    fake_session = FakeSession()
    monkeypatch.setattr(
        backfill,
        "_calculate_vodomery_backfill_week",
        lambda *args, **kwargs: calculation,
    )

    def fail_candidate_metrics(session, rows):
        raise RuntimeError("insert failed")

    monkeypatch.setattr(
        backfill,
        "persist_prediction_backfill_candidate_metrics",
        fail_candidate_metrics,
    )

    try:
        write_vodomery_prediction_backfill(
            plan,
            archive_run_id="write-001",
            session=fake_session,
        )
    except RuntimeError as exc:
        assert "insert failed" in str(exc)
    else:
        raise AssertionError("write errors should propagate")

    assert fake_session.commit_count == 0
    assert fake_session.rollback_count == 2


def test_verify_backfill_reads_aggregate_archive_counts():
    class FakeMappings:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

        def one(self):
            return self._rows[0]

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return FakeMappings(self._rows)

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def execute(self, statement, params=None):
            self.calls += 1
            if self.calls == 1:
                return FakeResult(
                    [
                        {
                            "profile_table": "monitoring.prediction_profile_snapshots",
                            "metric_table": (
                                "monitoring.prediction_backfill_candidate_metrics"
                            ),
                        }
                    ]
                )
            if self.calls == 2:
                return FakeResult(
                    [
                        {
                            "archive_source": "historical_backfill",
                            "archive_version": 1,
                            "profile_row_count": 1300,
                            "identifier_count": 2,
                            "forecast_week_count": 1,
                            "identifier_week_count": 2,
                        },
                        {
                            "archive_source": "weekly_rebuild",
                            "archive_version": 1,
                            "profile_row_count": 650,
                            "identifier_count": 1,
                            "forecast_week_count": 1,
                            "identifier_week_count": 1,
                        },
                    ]
                )
            return FakeResult(
                [
                    {
                        "metric_row_count": 6,
                        "identifier_count": 2,
                        "forecast_week_count": 1,
                        "identifier_week_count": 2,
                        "selected_metric_row_count": 2,
                    }
                ]
            )

    result = verify_vodomery_prediction_backfill(
        start_date=datetime.datetime(2024, 2, 1),
        end_date=datetime.datetime(2024, 3, 1),
        archive_version=1,
        identifiers=("A_V1",),
        session=FakeSession(),
    )

    assert result.profile_row_count == 1950
    assert result.profile_identifier_week_count == 3
    assert len(result.profile_sources) == 2
    assert result.candidate_metrics.metric_row_count == 6
    assert result.candidate_metrics.selected_metric_row_count == 2
    assert result.missing_tables == ()


def test_verify_backfill_reports_missing_archive_tables():
    class FakeMappings:
        def __init__(self, rows):
            self._rows = rows

        def one(self):
            return self._rows[0]

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def mappings(self):
            return FakeMappings(self._rows)

    class FakeSession:
        def execute(self, statement, params=None):
            return FakeResult(
                [
                    {
                        "profile_table": None,
                        "metric_table": None,
                    }
                ]
            )

    result = verify_vodomery_prediction_backfill(
        start_date=datetime.datetime(2024, 2, 1),
        end_date=datetime.datetime(2024, 3, 1),
        archive_version=1,
        session=FakeSession(),
    )

    assert result.profile_row_count == 0
    assert result.candidate_metrics.metric_row_count == 0
    assert result.missing_tables == (
        "monitoring.prediction_profile_snapshots",
        "monitoring.prediction_backfill_candidate_metrics",
    )
