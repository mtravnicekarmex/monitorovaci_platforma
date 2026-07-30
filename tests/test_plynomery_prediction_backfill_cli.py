import datetime
import importlib.util
import json
from pathlib import Path

from moduly.mereni.plynomery import plynomery_prediction_backfill as backfill


def _load_cli():
    path = Path(__file__).resolve().parents[1] / "scripts" / "plynomery_prediction_backfill.py"
    spec = importlib.util.spec_from_file_location("plynomery_backfill_cli", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _plan():
    return backfill.build_plynomery_backfill_plan(
        [
            backfill.PlynomeryBackfillIdentifierHistory(
                identifier="P_A1",
                first_measurement_at=datetime.datetime(2025, 11, 25),
                last_measurement_at=datetime.datetime(2026, 7, 27),
            )
        ],
        start_date=datetime.datetime(2026, 4, 21),
        end_date=datetime.datetime(2026, 5, 4),
    )


def test_plan_report_is_aggregate_only():
    report = _load_cli().build_plan_report(_plan())

    assert report["identifier_count"] == 1
    assert report["forecast_week_count"] == 2
    assert report["candidate_metric_row_estimate"] == 4
    assert "P_A1" not in json.dumps(report, default=str)


def test_write_report_includes_decision_count_without_identifiers():
    cli = _load_cli()
    plan = _plan()
    week = backfill.PlynomeryBackfillWriteWeekResult(
        forecast_period=backfill.build_calendar_week_period(
            datetime.datetime(2026, 4, 20)
        ),
        planned_identifier_count=1,
        calculated_identifier_count=1,
        candidate_metric_row_count=2,
        selected_decision_count=1,
        selected_profile_pair_count=1,
        inserted_selected_decision_count=1,
        inserted_candidate_metric_count=2,
        inserted_profile_snapshot_count=672,
    )
    result = backfill.PlynomeryBackfillWriteResult(
        archive_run_id="write-001",
        plan=plan,
        weeks=(week,),
    )

    report = cli.build_write_report(result)

    assert report["inserted_selected_decision_count"] == 1
    assert report["inserted_candidate_metric_count"] == 2
    assert report["inserted_profile_snapshot_count"] == 672
    assert "P_A1" not in json.dumps(report, default=str)
