from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from .client import HealthClient
from .config import AgentConfig
from .observer import run_observation_cycle
from .store import ObserverStore


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the read-only monitoring observer in test mode."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate configuration and exit without network or state writes.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        config = AgentConfig.load(args.config)
    except ValueError as exc:
        raise SystemExit(f"configuration error: {exc}") from exc

    if args.check_config:
        print(
            json.dumps(
                {
                    "config_version": config.config_version,
                    "endpoint_count": len(config.endpoint_keys),
                    "event": "configuration_valid",
                    "mode": config.mode,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 0

    client = HealthClient(
        base_url=config.base_url,
        observer_instance_id=config.instance_id,
        timeout_seconds=config.timeout_seconds,
    )
    store = ObserverStore(config.state_dir)

    while True:
        observations = run_observation_cycle(
            client=client,
            store=store,
            observer_instance_id=config.instance_id,
            endpoint_keys=config.endpoint_keys,
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
        time.sleep(config.poll_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
