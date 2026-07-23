import datetime
import importlib.util
import json
from pathlib import Path

from moduly.mereni.vodomery.vodomery_prediction_backfill import (
    VodomeryBackfillDryRunResult,
    VodomeryBackfillDryRunWeekResult,
    VodomeryBackfillIdentifierHistory,
    VodomeryBackfillVerifyCandidateMetrics,
    VodomeryBackfillVerifyProfileSource,
    VodomeryBackfillVerifyResult,
    VodomeryBackfillWriteResult,
    VodomeryBackfillWriteWeekResult,
    build_calendar_week_period,
    build_vodomery_backfill_plan,
)


def _load_cli_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "vodomery_prediction_backfill.py"
    )
    spec = importlib.util.spec_from_file_location(
        "vodomery_prediction_backfill_cli",
        script_path,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sample_plan():
    return build_vodomery_backfill_plan(
        [
            VodomeryBackfillIdentifierHistory(
                identifier="A_V1",
                first_measurement_at=datetime.datetime(2024, 1, 1),
                last_measurement_at=datetime.datetime(2024, 2, 15),
            )
        ],
        start_date=datetime.datetime(2024, 1, 1),
        end_date=datetime.datetime(2024, 2, 15),
        max_weeks=1,
    )


def test_plan_report_is_aggregate_only():
    cli = _load_cli_module()
    report = cli.build_plan_report(_sample_plan())

    assert report["mode"] == "plan"
    assert report["identifier_count"] == 1
    assert report["identifier_week_count"] == 1
    assert report["candidate_metric_row_estimate"] == 3
    assert "A_V1" not in json.dumps(report, default=str)


def test_dry_run_report_includes_week_aggregates_without_identifiers():
    cli = _load_cli_module()
    plan = _sample_plan()
    week = VodomeryBackfillDryRunWeekResult(
        forecast_period=build_calendar_week_period(datetime.datetime(2024, 2, 5)),
        planned_identifier_count=1,
        calculated_identifier_count=1,
        candidate_metric_row_count=3,
        selected_decision_count=1,
        selected_profile_pair_count=1,
    )
    result = VodomeryBackfillDryRunResult(
        archive_run_id="dry-run-001",
        plan=plan,
        weeks=(week,),
    )

    report = cli.build_dry_run_report(result)

    assert report["mode"] == "dry_run"
    assert report["archive_run_id"] == "dry-run-001"
    assert report["calculated_week_count"] == 1
    assert report["weeks"][0]["candidate_metric_row_count"] == 3
    assert "A_V1" not in json.dumps(report, default=str)


def test_write_report_includes_insert_counts_without_identifiers():
    cli = _load_cli_module()
    plan = _sample_plan()
    week = VodomeryBackfillWriteWeekResult(
        forecast_period=build_calendar_week_period(datetime.datetime(2024, 2, 5)),
        planned_identifier_count=1,
        calculated_identifier_count=1,
        candidate_metric_row_count=3,
        selected_decision_count=1,
        selected_profile_pair_count=1,
        inserted_candidate_metric_count=3,
        inserted_profile_snapshot_count=650,
    )
    result = VodomeryBackfillWriteResult(
        archive_run_id="write-001",
        plan=plan,
        weeks=(week,),
    )

    report = cli.build_write_report(result)

    assert report["mode"] == "write"
    assert report["archive_run_id"] == "write-001"
    assert report["committed_week_count"] == 1
    assert report["inserted_candidate_metric_count"] == 3
    assert report["inserted_profile_snapshot_count"] == 650
    assert "A_V1" not in json.dumps(report, default=str)


def test_verify_report_includes_archive_aggregates_without_identifiers():
    cli = _load_cli_module()
    result = VodomeryBackfillVerifyResult(
        start_date=datetime.datetime(2024, 2, 1),
        end_date=datetime.datetime(2024, 3, 1),
        archive_version=1,
        profile_sources=(
            VodomeryBackfillVerifyProfileSource(
                archive_source="historical_backfill",
                archive_version=1,
                profile_row_count=1300,
                identifier_count=2,
                forecast_week_count=1,
                identifier_week_count=2,
            ),
        ),
        candidate_metrics=VodomeryBackfillVerifyCandidateMetrics(
            archive_version=1,
            metric_row_count=6,
            identifier_count=2,
            forecast_week_count=1,
            identifier_week_count=2,
            selected_metric_row_count=2,
        ),
        missing_tables=("monitoring.prediction_profile_snapshots",),
    )

    report = cli.build_verify_report(result)

    assert report["mode"] == "verify"
    assert report["missing_tables"] == ["monitoring.prediction_profile_snapshots"]
    assert report["profile_row_count"] == 1300
    assert report["candidate_metrics"]["metric_row_count"] == 6
    assert "A_V1" not in json.dumps(report, default=str)


def test_plan_command_prints_json_without_live_database(monkeypatch, capsys):
    cli = _load_cli_module()
    captured = {}

    def fake_plan(**kwargs):
        captured.update(kwargs)
        return _sample_plan()

    monkeypatch.setattr(
        cli,
        "plan_vodomery_prediction_backfill",
        fake_plan,
    )

    exit_code = cli.main(
        [
            "plan",
            "--start-date",
            "2024-02-01",
            "--history-start-date",
            "2024-01-01",
            "--end-date",
            "2024-02-15",
            "--identifikace",
            "A_V1",
            "--max-weeks",
            "1",
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["mode"] == "plan"
    assert payload["identifier_week_count"] == 1
    assert captured["start_date"] == datetime.datetime(2024, 2, 1)
    assert captured["history_start_date"] == datetime.datetime(2024, 1, 1)
    assert "A_V1" not in output


def test_write_command_prints_json_without_live_database(monkeypatch, capsys):
    cli = _load_cli_module()
    plan = _sample_plan()
    write_result = VodomeryBackfillWriteResult(
        archive_run_id="write-001",
        plan=plan,
        weeks=(
            VodomeryBackfillWriteWeekResult(
                forecast_period=build_calendar_week_period(datetime.datetime(2024, 2, 5)),
                planned_identifier_count=1,
                calculated_identifier_count=1,
                candidate_metric_row_count=3,
                selected_decision_count=1,
                selected_profile_pair_count=1,
                inserted_candidate_metric_count=3,
                inserted_profile_snapshot_count=650,
            ),
        ),
    )
    monkeypatch.setattr(
        cli,
        "plan_vodomery_prediction_backfill",
        lambda **kwargs: plan,
    )
    monkeypatch.setattr(
        cli,
        "write_vodomery_prediction_backfill",
        lambda plan, *, archive_run_id: write_result,
    )

    exit_code = cli.main(
        [
            "write",
            "--end-date",
            "2024-02-15",
            "--identifikace",
            "A_V1",
            "--max-weeks",
            "1",
            "--archive-run-id",
            "write-001",
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["mode"] == "write"
    assert payload["inserted_profile_snapshot_count"] == 650
    assert "A_V1" not in output


def test_verify_command_prints_json_without_live_database(monkeypatch, capsys):
    cli = _load_cli_module()
    verify_result = VodomeryBackfillVerifyResult(
        start_date=datetime.datetime(2024, 2, 1),
        end_date=datetime.datetime(2024, 3, 1),
        archive_version=1,
        profile_sources=(
            VodomeryBackfillVerifyProfileSource(
                archive_source="historical_backfill",
                archive_version=1,
                profile_row_count=1300,
                identifier_count=2,
                forecast_week_count=1,
                identifier_week_count=2,
            ),
        ),
        candidate_metrics=VodomeryBackfillVerifyCandidateMetrics(
            archive_version=1,
            metric_row_count=6,
            identifier_count=2,
            forecast_week_count=1,
            identifier_week_count=2,
            selected_metric_row_count=2,
        ),
    )
    monkeypatch.setattr(
        cli,
        "verify_vodomery_prediction_backfill",
        lambda **kwargs: verify_result,
    )

    exit_code = cli.main(
        [
            "verify",
            "--start-date",
            "2024-02-01",
            "--end-date",
            "2024-03-01",
            "--identifikace",
            "A_V1",
        ]
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert exit_code == 0
    assert payload["mode"] == "verify"
    assert payload["profile_row_count"] == 1300
    assert "A_V1" not in output
