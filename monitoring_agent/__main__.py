from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time

from .client import HealthClient
from .observer import run_observation_cycle
from .settings import RuntimeSettings
from .store import ObserverStore


def calculate_next_cycle_delay(
    *,
    poll_interval_seconds: float,
    cycle_elapsed_seconds: float,
    poll_jitter_seconds: float,
    uniform_fn=random.uniform,
) -> float:
    base_delay = max(0.0, poll_interval_seconds - cycle_elapsed_seconds)
    jitter = uniform_fn(0.0, poll_jitter_seconds)
    return base_delay + jitter


def _build_parser(*, default_env_file: Path | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the read-only monitoring observer in test mode."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=default_env_file,
        required=default_env_file is None,
        help="ACL-restricted local .env file; defaults beside the runner script.",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate configuration and exit without network or state writes.",
    )
    return parser


def main(*, default_env_file: Path | None = None) -> int:
    args = _build_parser(default_env_file=default_env_file).parse_args()
    try:
        settings = RuntimeSettings.load(args.env_file)
    except ValueError as exc:
        raise SystemExit(f"environment error: {exc}") from exc

    if args.check_config:
        print(
            json.dumps(
                {
                    "event": "configuration_valid",
                    **settings.safe_summary(),
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0

    try:
        client = HealthClient(
            base_url=settings.base_url,
            observer_instance_id=settings.instance_id,
            timeout_seconds=settings.timeout_seconds,
            max_attempts=settings.max_attempts,
            retry_backoff_seconds=settings.retry_backoff_seconds,
            bearer_credential=settings.bearer_credential,
        )
    except ValueError as exc:
        raise SystemExit(f"client setup error: {exc}") from exc
    store = ObserverStore(settings.state_dir)

    while True:
        cycle_started = time.monotonic()
        observations = run_observation_cycle(
            client=client,
            store=store,
            observer_instance_id=settings.instance_id,
            endpoint_keys=settings.endpoint_keys,
        )
        print(
            json.dumps(
                {
                    "event": "observation_cycle",
                    "observation_count": len(observations),
                    "transport_statuses": sorted(
                        {item.transport_status for item in observations}
                    ),
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            flush=True,
        )
        if args.once:
            return 0
        time.sleep(
            calculate_next_cycle_delay(
                poll_interval_seconds=settings.poll_interval_seconds,
                cycle_elapsed_seconds=time.monotonic() - cycle_started,
                poll_jitter_seconds=settings.poll_jitter_seconds,
            )
        )


if __name__ == "__main__":
    raise SystemExit(main())
