from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from local_monitoring_agents.database_availability import (
    DEFAULT_DATABASE_AVAILABILITY_LOCAL_AGENT_STATE_FILE,
    DEFAULT_MAX_SERVICES,
    DEFAULT_RECENT_WINDOW_SECONDS,
    DEFAULT_STALE_AFTER_SECONDS,
    DatabaseAvailabilityLocalAgentError,
    run_database_availability_local_agent_once,
    summarize_database_availability_local_agent,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local database-availability monitoring agent once. The "
            "agent reads the local scheduler availability SQLite store "
            "read-only and writes only its own bounded sanitized state."
        )
    )
    parser.add_argument("--db-file", type=Path)
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_DATABASE_AVAILABILITY_LOCAL_AGENT_STATE_FILE,
    )
    parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=DEFAULT_STALE_AFTER_SECONDS,
    )
    parser.add_argument(
        "--recent-window-seconds",
        type=float,
        default=DEFAULT_RECENT_WINDOW_SECONDS,
    )
    parser.add_argument("--max-services", type=int, default=DEFAULT_MAX_SERVICES)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        snapshot = run_database_availability_local_agent_once(
            db_file=args.db_file,
            state_file=args.state_file,
            stale_after_seconds=args.stale_after_seconds,
            recent_window_seconds=args.recent_window_seconds,
            max_services=args.max_services,
        )
    except (OSError, DatabaseAvailabilityLocalAgentError, ValueError) as exc:
        raise SystemExit(
            f"database availability local agent error: {exc}"
        ) from exc

    sys.stdout.write(
        json.dumps(
            summarize_database_availability_local_agent(snapshot),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
