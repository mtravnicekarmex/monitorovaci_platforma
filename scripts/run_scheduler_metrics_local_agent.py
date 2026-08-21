from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_monitoring_agents.scheduler_metrics import (
    DEFAULT_MAX_JOBS,
    DEFAULT_SCHEDULER_METRICS_LOCAL_AGENT_STATE_FILE,
    SchedulerMetricsLocalAgentError,
    run_scheduler_metrics_local_agent_once,
    summarize_scheduler_metrics_local_agent,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local scheduler-metrics monitoring agent once. The agent "
            "reads the local scheduler metrics JSON read-only and writes only "
            "its own bounded sanitized state."
        )
    )
    parser.add_argument("--metrics-file", type=Path)
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_SCHEDULER_METRICS_LOCAL_AGENT_STATE_FILE,
    )
    parser.add_argument("--heartbeat-ttl-seconds", type=int, default=300)
    parser.add_argument("--max-jobs", type=int, default=DEFAULT_MAX_JOBS)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        snapshot = run_scheduler_metrics_local_agent_once(
            metrics_file=args.metrics_file,
            state_file=args.state_file,
            heartbeat_ttl_seconds=args.heartbeat_ttl_seconds,
            max_jobs=args.max_jobs,
        )
    except (OSError, SchedulerMetricsLocalAgentError, ValueError) as exc:
        raise SystemExit(f"scheduler metrics local agent error: {exc}") from exc

    sys.stdout.write(
        json.dumps(
            summarize_scheduler_metrics_local_agent(snapshot),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
