from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_monitoring_agents.database_availability import (
    DEFAULT_DATABASE_AVAILABILITY_LOCAL_AGENT_STATE_FILE,
    DatabaseAvailabilityLocalAgentError,
    run_database_availability_local_agent_once,
    summarize_database_availability_local_agent,
)
from local_monitoring_agents.scheduler_metrics import (
    DEFAULT_SCHEDULER_METRICS_LOCAL_AGENT_STATE_FILE,
    SchedulerMetricsLocalAgentError,
    run_scheduler_metrics_local_agent_once,
    summarize_scheduler_metrics_local_agent,
)


AGENT_DATABASE_AVAILABILITY = "database_availability"
AGENT_SCHEDULER_METRICS = "scheduler_metrics"
DEFAULT_AGENT_ORDER = (
    AGENT_DATABASE_AVAILABILITY,
    AGENT_SCHEDULER_METRICS,
)
STATUS_ORDER = {
    "ok": 0,
    "degraded": 1,
    "unavailable": 2,
    "error": 3,
}


@dataclass(frozen=True)
class _AgentRunSpec:
    key: str
    run: Callable[[argparse.Namespace], dict[str, object]]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run approved local monitoring agents once. Each agent reads only "
            "its approved local source and writes only its own sanitized "
            "agent-owned state."
        )
    )
    parser.add_argument(
        "--agent",
        action="append",
        choices=DEFAULT_AGENT_ORDER,
        help=(
            "Run only the selected local agent. May be repeated. Defaults to "
            "all approved local agents in deterministic order."
        ),
    )
    parser.add_argument("--database-availability-db-file", type=Path)
    parser.add_argument(
        "--database-availability-state-file",
        type=Path,
        default=DEFAULT_DATABASE_AVAILABILITY_LOCAL_AGENT_STATE_FILE,
    )
    parser.add_argument("--scheduler-metrics-file", type=Path)
    parser.add_argument(
        "--scheduler-metrics-state-file",
        type=Path,
        default=DEFAULT_SCHEDULER_METRICS_LOCAL_AGENT_STATE_FILE,
    )
    parser.add_argument("--scheduler-heartbeat-ttl-seconds", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    selected_agents = tuple(dict.fromkeys(args.agent or DEFAULT_AGENT_ORDER))
    specs = _agent_specs()
    results: list[dict[str, object]] = []
    for agent_key in selected_agents:
        try:
            results.append(specs[agent_key].run(args))
        except (
            OSError,
            DatabaseAvailabilityLocalAgentError,
            SchedulerMetricsLocalAgentError,
            ValueError,
        ) as exc:
            raise SystemExit(
                f"local monitoring agent runner error: {agent_key}: {exc}"
            ) from exc

    payload = {
        "agent_count": len(results),
        "agents": results,
        "event": "local_monitoring_agents_cycle",
        "runner_version": 1,
        "status": _overall_status(results),
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    sys.stdout.write("\n")
    return 0


def _agent_specs() -> dict[str, _AgentRunSpec]:
    return {
        AGENT_DATABASE_AVAILABILITY: _AgentRunSpec(
            key=AGENT_DATABASE_AVAILABILITY,
            run=_run_database_availability,
        ),
        AGENT_SCHEDULER_METRICS: _AgentRunSpec(
            key=AGENT_SCHEDULER_METRICS,
            run=_run_scheduler_metrics,
        ),
    }


def _run_database_availability(args: argparse.Namespace) -> dict[str, object]:
    snapshot = run_database_availability_local_agent_once(
        db_file=args.database_availability_db_file,
        state_file=args.database_availability_state_file,
    )
    summary = summarize_database_availability_local_agent(snapshot)
    return _safe_result(summary)


def _run_scheduler_metrics(args: argparse.Namespace) -> dict[str, object]:
    snapshot = run_scheduler_metrics_local_agent_once(
        metrics_file=args.scheduler_metrics_file,
        state_file=args.scheduler_metrics_state_file,
        heartbeat_ttl_seconds=args.scheduler_heartbeat_ttl_seconds,
    )
    summary = summarize_scheduler_metrics_local_agent(snapshot)
    return _safe_result(summary)


def _safe_result(summary: dict[str, object]) -> dict[str, object]:
    allowed = {
        "agent_key",
        "contract_version",
        "degraded_job_count",
        "delivered_event_count_24h",
        "error_job_count",
        "event",
        "failure_count_24h",
        "job_count",
        "mode",
        "pending_event_count",
        "recent_transition_count",
        "scheduler_running",
        "service_count",
        "source_metrics_present",
        "source_schema_valid",
        "source_store_present",
        "stale_service_count",
        "status",
        "success_count_24h",
        "unavailable_service_count",
    }
    return {key: summary[key] for key in sorted(allowed & set(summary))}


def _overall_status(results: list[dict[str, object]]) -> str:
    if not results:
        return "error"
    return max(
        (str(result.get("status", "error")) for result in results),
        key=lambda status: STATUS_ORDER.get(status, STATUS_ORDER["error"]),
    )


if __name__ == "__main__":
    raise SystemExit(main())
