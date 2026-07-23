from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from moduly.mereni.vodomery.vodomery_prediction_backfill import (
    BACKFILL_DEFAULT_ARCHIVE_VERSION,
    BACKFILL_DEFAULT_START,
    dry_run_vodomery_prediction_backfill,
    plan_vodomery_prediction_backfill,
    verify_vodomery_prediction_backfill,
    write_vodomery_prediction_backfill,
)


def _parse_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Expected date in YYYY-MM-DD format, got {value!r}."
        ) from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or dry-run historical vodomery prediction backfill. "
            "Outputs aggregate JSON only."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_scope_arguments(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--start-date",
            type=_parse_date,
            default=BACKFILL_DEFAULT_START,
            help="Inclusive backfill start date in YYYY-MM-DD format.",
        )
        command_parser.add_argument(
            "--history-start-date",
            type=_parse_date,
            default=None,
            help=(
                "Inclusive measurement history lower bound in YYYY-MM-DD format. "
                "Defaults to --start-date."
            ),
        )
        command_parser.add_argument(
            "--end-date",
            type=_parse_date,
            required=True,
            help="Exclusive backfill end date in YYYY-MM-DD format.",
        )
        command_parser.add_argument(
            "--identifikace",
            action="append",
            default=None,
            help=(
                "Limit to one identifier. Can be repeated. "
                "Identifiers are not printed in output."
            ),
        )
        command_parser.add_argument(
            "--archive-version",
            type=int,
            default=BACKFILL_DEFAULT_ARCHIVE_VERSION,
            help="Backfill archive version.",
        )
        command_parser.add_argument(
            "--max-identifiers",
            type=int,
            default=None,
            help="Maximum identifiers to include after sorting.",
        )
        command_parser.add_argument(
            "--max-weeks",
            type=int,
            default=None,
            help="Maximum forecast weeks per identifier.",
        )
        command_parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indentation. Use 0 for compact output.",
        )

    def add_verify_arguments(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument(
            "--start-date",
            type=_parse_date,
            default=BACKFILL_DEFAULT_START,
            help="Inclusive verification start date in YYYY-MM-DD format.",
        )
        command_parser.add_argument(
            "--end-date",
            type=_parse_date,
            required=True,
            help="Exclusive verification end date in YYYY-MM-DD format.",
        )
        command_parser.add_argument(
            "--identifikace",
            action="append",
            default=None,
            help=(
                "Limit to one identifier. Can be repeated. "
                "Identifiers are not printed in output."
            ),
        )
        command_parser.add_argument(
            "--archive-version",
            type=int,
            default=BACKFILL_DEFAULT_ARCHIVE_VERSION,
            help="Backfill archive version to verify.",
        )
        command_parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indentation. Use 0 for compact output.",
        )

    plan_parser = subparsers.add_parser("plan", help="Build aggregate backfill plan.")
    add_scope_arguments(plan_parser)

    dry_run_parser = subparsers.add_parser(
        "dry-run",
        help="Run calculations without writes and print aggregate results.",
    )
    add_scope_arguments(dry_run_parser)
    dry_run_parser.add_argument(
        "--archive-run-id",
        required=True,
        help="Audit id for this dry-run execution.",
    )

    write_parser = subparsers.add_parser(
        "write",
        help="Write historical backfill rows and print aggregate results.",
    )
    add_scope_arguments(write_parser)
    write_parser.add_argument(
        "--archive-run-id",
        required=True,
        help="Audit id for this write execution.",
    )

    verify_parser = subparsers.add_parser(
        "verify",
        help="Read aggregate archive coverage without calculations or writes.",
    )
    add_verify_arguments(verify_parser)

    return parser


def _build_plan(args: argparse.Namespace):
    return plan_vodomery_prediction_backfill(
        start_date=args.start_date,
        end_date=args.end_date,
        history_start_date=args.history_start_date,
        identifiers=tuple(args.identifikace or ()),
        archive_version=args.archive_version,
        max_identifiers=args.max_identifiers,
        max_weeks=args.max_weeks,
    )


def build_plan_report(plan) -> dict[str, Any]:
    first_period_start = None
    last_period_end = None
    if plan.items:
        first_period_start = min(item.forecast_period.start for item in plan.items)
        last_period_end = max(item.forecast_period.end for item in plan.items)

    return {
        "mode": "plan",
        "start_date": plan.start_date,
        "end_date": plan.end_date,
        "archive_version": plan.archive_version,
        "model_versions": list(plan.model_versions),
        "identifier_count": plan.identifier_count,
        "forecast_week_count": plan.forecast_week_count,
        "identifier_week_count": plan.identifier_week_count,
        "candidate_metric_row_estimate": plan.candidate_metric_row_estimate,
        "first_forecast_period_start": first_period_start,
        "last_forecast_period_end": last_period_end,
        "skipped_counts": dict(plan.skipped_counts),
    }


def build_dry_run_report(result) -> dict[str, Any]:
    return {
        "mode": "dry_run",
        "archive_run_id": result.archive_run_id,
        "plan": build_plan_report(result.plan),
        "calculated_week_count": result.calculated_week_count,
        "candidate_metric_row_count": result.candidate_metric_row_count,
        "selected_decision_count": result.selected_decision_count,
        "selected_profile_pair_count": result.selected_profile_pair_count,
        "weeks": [
            {
                "forecast_period_start": week.forecast_period.start,
                "forecast_period_end": week.forecast_period.end,
                "planned_identifier_count": week.planned_identifier_count,
                "calculated_identifier_count": week.calculated_identifier_count,
                "candidate_metric_row_count": week.candidate_metric_row_count,
                "selected_decision_count": week.selected_decision_count,
                "selected_profile_pair_count": week.selected_profile_pair_count,
                "skipped_counts": dict(week.skipped_counts),
            }
            for week in result.weeks
        ],
    }


def build_write_report(result) -> dict[str, Any]:
    return {
        "mode": "write",
        "archive_run_id": result.archive_run_id,
        "plan": build_plan_report(result.plan),
        "committed_week_count": result.committed_week_count,
        "inserted_candidate_metric_count": result.inserted_candidate_metric_count,
        "inserted_profile_snapshot_count": result.inserted_profile_snapshot_count,
        "weeks": [
            {
                "forecast_period_start": week.forecast_period.start,
                "forecast_period_end": week.forecast_period.end,
                "planned_identifier_count": week.planned_identifier_count,
                "calculated_identifier_count": week.calculated_identifier_count,
                "candidate_metric_row_count": week.candidate_metric_row_count,
                "selected_decision_count": week.selected_decision_count,
                "selected_profile_pair_count": week.selected_profile_pair_count,
                "inserted_candidate_metric_count": (
                    week.inserted_candidate_metric_count
                ),
                "inserted_profile_snapshot_count": (
                    week.inserted_profile_snapshot_count
                ),
                "skipped_counts": dict(week.skipped_counts),
            }
            for week in result.weeks
        ],
    }


def build_verify_report(result) -> dict[str, Any]:
    return {
        "mode": "verify",
        "start_date": result.start_date,
        "end_date": result.end_date,
        "archive_version": result.archive_version,
        "missing_tables": list(result.missing_tables),
        "profile_row_count": result.profile_row_count,
        "profile_identifier_week_count": result.profile_identifier_week_count,
        "profile_sources": [
            {
                "archive_source": source.archive_source,
                "archive_version": source.archive_version,
                "profile_row_count": source.profile_row_count,
                "identifier_count": source.identifier_count,
                "forecast_week_count": source.forecast_week_count,
                "identifier_week_count": source.identifier_week_count,
            }
            for source in result.profile_sources
        ],
        "candidate_metrics": {
            "archive_version": result.candidate_metrics.archive_version,
            "metric_row_count": result.candidate_metrics.metric_row_count,
            "identifier_count": result.candidate_metrics.identifier_count,
            "forecast_week_count": result.candidate_metrics.forecast_week_count,
            "identifier_week_count": result.candidate_metrics.identifier_week_count,
            "selected_metric_row_count": (
                result.candidate_metrics.selected_metric_row_count
            ),
        },
    }


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "plan":
        plan = _build_plan(args)
        report = build_plan_report(plan)
    elif args.command == "dry-run":
        plan = _build_plan(args)
        dry_run = dry_run_vodomery_prediction_backfill(
            plan,
            archive_run_id=args.archive_run_id,
        )
        report = build_dry_run_report(dry_run)
    elif args.command == "write":
        plan = _build_plan(args)
        write_result = write_vodomery_prediction_backfill(
            plan,
            archive_run_id=args.archive_run_id,
        )
        report = build_write_report(write_result)
    elif args.command == "verify":
        verify_result = verify_vodomery_prediction_backfill(
            start_date=args.start_date,
            end_date=args.end_date,
            archive_version=args.archive_version,
            identifiers=tuple(args.identifikace or ()),
        )
        report = build_verify_report(verify_result)
    else:
        parser.error(f"Unknown command: {args.command}")

    indent = None if args.indent == 0 else args.indent
    print(json.dumps(report, default=_json_default, ensure_ascii=False, indent=indent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
