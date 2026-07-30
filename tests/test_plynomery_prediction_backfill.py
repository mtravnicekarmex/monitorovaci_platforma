import datetime
from types import SimpleNamespace

from moduly.mereni.plynomery import plynomery_prediction
from moduly.mereni.plynomery import plynomery_prediction_backfill as backfill


def _history(
    identifier="P_A1",
    *,
    first=datetime.datetime(2025, 11, 25, 10),
    last=datetime.datetime(2026, 7, 27, 23),
):
    return backfill.PlynomeryBackfillIdentifierHistory(
        identifier=identifier,
        first_measurement_at=first,
        last_measurement_at=last,
    )


def _plan(*, max_weeks=None):
    return backfill.build_plynomery_backfill_plan(
        [_history()],
        start_date=datetime.datetime(2026, 4, 21),
        end_date=datetime.datetime(2026, 7, 27),
        max_weeks=max_weeks,
    )


def test_plan_starts_with_calendar_week_containing_requested_date():
    plan = _plan(max_weeks=2)

    assert [item.forecast_period.start for item in plan.items] == [
        datetime.datetime(2026, 4, 20),
        datetime.datetime(2026, 4, 27),
    ]
    assert plan.identifier_count == 1
    assert plan.forecast_week_count == 2
    assert plan.candidate_metric_row_estimate == 4
    assert plan.model_versions == (1, 2)


def test_plan_requires_three_months_of_identifier_history():
    plan = backfill.build_plynomery_backfill_plan(
        [
            _history(
                first=datetime.datetime(2026, 2, 1),
                last=datetime.datetime(2026, 7, 27),
            )
        ],
        start_date=datetime.datetime(2026, 4, 21),
        end_date=datetime.datetime(2026, 7, 27),
        max_weeks=1,
    )

    assert plan.items[0].forecast_period.start == datetime.datetime(2026, 5, 4)


def test_plan_skips_existing_weekly_rebuild_period():
    plan = backfill.build_plynomery_backfill_plan(
        [_history()],
        start_date=datetime.datetime(2026, 4, 21),
        end_date=datetime.datetime(2026, 5, 4),
        existing_weekly_rebuild_periods={
            ("P_A1", datetime.datetime(2026, 4, 27))
        },
    )

    assert [item.forecast_period.start for item in plan.items] == [
        datetime.datetime(2026, 4, 20)
    ]
    assert plan.skipped_counts == {"weekly_rebuild_exists": 1}


def test_dry_run_calculates_with_gas_candidates_and_rolls_back(monkeypatch):
    plan = _plan(max_weeks=1)
    definitions = {
        version: plynomery_prediction.CandidateModelDefinition(
            model_version=version,
            model_key=f"model_{version}",
            model_name=f"Model {version}",
            training_window_months=3,
            validation_window_months=1,
            selection_enabled=True,
        )
        for version in (1, 2)
    }

    def fake_summary(definition):
        return plynomery_prediction.ModelPerformanceSummary(
            model_version=definition.model_version,
            model_key=definition.model_key,
            model_name=definition.model_name,
            training_window_months=3,
            validation_window_months=1,
            selection_enabled=True,
            validation_total_count=10,
            matched_validation_count=10,
            coverage=1.0,
            mae=float(definition.model_version),
            rmse=float(definition.model_version),
            bias=0.0,
            profile_count=672,
        )

    def fake_rolling(_session, *, definition, reference_end):
        del reference_end
        metric = plynomery_prediction.DeviceModelPerformanceSummary(
            identifikace="P_A1",
            model_version=definition.model_version,
            model_key=definition.model_key,
            model_name=definition.model_name,
            selection_enabled=True,
            rolling_backtest_fold_count=8,
            rolling_validation_total_count=80,
            rolling_matched_validation_count=80,
            rolling_coverage=1.0,
            rolling_mae=float(definition.model_version),
            rolling_rmse=float(definition.model_version),
            rolling_bias=0.0,
            rolling_wape=float(definition.model_version),
        )
        return SimpleNamespace(
            metrics=plynomery_prediction.PredictionMetricSummary(
                validation_total_count=80,
                matched_validation_count=80,
                coverage=1.0,
                mae=float(definition.model_version),
                rmse=float(definition.model_version),
                bias=0.0,
                wape=float(definition.model_version),
            ),
            device_metrics=(metric,),
        )

    decision = SimpleNamespace(
        identifier="P_A1",
        selected_model_version=1,
        fallback_reason=SimpleNamespace(value="none"),
        uses_fallback=False,
    )

    class Session:
        rollback_count = 0

        def rollback(self):
            self.rollback_count += 1

    session = Session()
    monkeypatch.setattr(
        plynomery_prediction,
        "_get_candidate_model_definition",
        lambda version: definitions[version],
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_build_windows_for_definition",
        lambda definition, reference_time: SimpleNamespace(
            definition=definition,
            reference_time=reference_time,
        ),
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_rebuild_candidate_model",
        lambda _session, *, definition, windows: fake_summary(definition),
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_run_candidate_rolling_weekly_backtest_with_devices",
        fake_rolling,
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_load_deployable_profile_catalog",
        lambda _session, summaries: {
            ("P_A1", summary.model_version): (object(),)
            for summary in summaries
        },
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_build_dry_run_selected_model_decisions",
        lambda **_kwargs: (decision,),
    )
    monkeypatch.setattr(
        plynomery_prediction,
        "_build_dry_run_profile_snapshot_rows",
        lambda *args, **kwargs: (
            {"identifier": "P_A1", "model_version": 1},
        ),
    )

    result = backfill.dry_run_plynomery_prediction_backfill(
        plan,
        archive_run_id="gas-backfill-dry-run",
        session=session,
    )

    assert session.rollback_count == 1
    assert result.calculated_week_count == 1
    assert result.candidate_metric_row_count == 2
    assert result.selected_decision_count == 1
    assert result.selected_profile_pair_count == 1


def test_write_persists_decisions_metrics_and_profiles_in_one_week(monkeypatch):
    plan = _plan(max_weeks=1)
    decision = SimpleNamespace(identifier="P_A1")
    calculation = backfill._BackfillWeekCalculation(
        summary=backfill.PlynomeryBackfillDryRunWeekResult(
            forecast_period=backfill.build_calendar_week_period(
                datetime.datetime(2026, 4, 20)
            ),
            planned_identifier_count=1,
            calculated_identifier_count=1,
            candidate_metric_row_count=2,
            selected_decision_count=1,
            selected_profile_pair_count=1,
        ),
        selected_decisions=(decision,),
        candidate_metric_rows=({"model_version": 1}, {"model_version": 2}),
        selected_profile_snapshot_rows=({"slot": 1},),
    )
    calls = []

    class Session:
        def rollback(self):
            calls.append("rollback")

        def commit(self):
            calls.append("commit")

    monkeypatch.setattr(
        backfill,
        "_calculate_plynomery_backfill_week",
        lambda *args, **kwargs: calculation,
    )
    monkeypatch.setattr(
        backfill,
        "persist_selected_model_decisions",
        lambda session, rows, **kwargs: calls.append("decisions") or len(rows),
    )
    monkeypatch.setattr(
        backfill,
        "persist_prediction_backfill_candidate_metrics",
        lambda session, rows: calls.append("metrics") or len(rows),
    )
    monkeypatch.setattr(
        backfill,
        "persist_prediction_profile_snapshots",
        lambda session, rows: calls.append("profiles") or len(rows),
    )

    result = backfill.write_plynomery_prediction_backfill(
        plan,
        archive_run_id="gas-backfill-write",
        session=Session(),
    )

    assert calls == ["rollback", "decisions", "metrics", "profiles", "commit"]
    assert result.inserted_selected_decision_count == 1
    assert result.inserted_candidate_metric_count == 2
    assert result.inserted_profile_snapshot_count == 1
