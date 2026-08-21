from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import time
from uuid import uuid4

from .audit import StateAuditError, build_state_audit
from .client import HealthClient
from .incident_store import IncidentStoreError
from .observer import run_observation_cycle
from .runtime_delivery import run_runtime_delivery
from .runtime_shadow import (
    apply_shadow_incident_cycle,
    build_incident_store,
    summarize_shadow_incident_snapshot,
)
from .settings import RuntimeSettings
from .store import ObserverStore, StateRetentionError, StateWriterLockError


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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument(
        "--check-config",
        action="store_true",
        help="Validate configuration and exit without network or state writes.",
    )
    mode.add_argument(
        "--audit-state",
        action="store_true",
        help="Print a sanitized read-only aggregate of agent-owned state.",
    )
    return parser


def _run_polling_process(
    *,
    args: argparse.Namespace,
    settings: RuntimeSettings,
    client: HealthClient,
    store: ObserverStore,
    run_id: str,
) -> int:
    store.append_lifecycle(
        observer_instance_id=settings.instance_id,
        run_id=run_id,
        event="process_started",
        reason="observer_started",
    )
    exit_reason = "observer_error"
    cycle_sequence = 0
    try:
        while True:
            cycle_sequence += 1
            cycle_started = time.monotonic()
            observations = run_observation_cycle(
                client=client,
                store=store,
                observer_instance_id=settings.instance_id,
                run_id=run_id,
                cycle_sequence=cycle_sequence,
                endpoint_keys=settings.endpoint_keys,
            )
            incident_store = build_incident_store(settings)
            shadow_summary = apply_shadow_incident_cycle(
                settings=settings,
                observations=observations,
                incident_store=incident_store,
            )
            delivery_summary = run_runtime_delivery(
                settings=settings,
                env_file=args.env_file,
                store=incident_store,
            )
            if delivery_summary.state_changed:
                shadow_summary = summarize_shadow_incident_snapshot(
                    incident_store.load(),
                    incident_rule_version=shadow_summary.incident_rule_version,
                    transition_count=shadow_summary.transition_count,
                    delivery_enabled=settings.delivery_automation_enabled,
                )
            store.retain_recent_observations(
                max_records=settings.max_observation_records
            )
            cycle_event = {
                "event": "observation_cycle",
                "observation_count": len(observations),
                "shadow_incidents": shadow_summary.to_dict(),
                "transport_statuses": sorted(
                    {item.transport_status for item in observations}
                ),
            }
            if delivery_summary.enabled:
                cycle_event["delivery"] = delivery_summary.to_dict()
            print(
                json.dumps(
                    cycle_event,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                flush=True,
            )
            if args.once:
                exit_reason = "once_completed"
                return 0
            time.sleep(
                calculate_next_cycle_delay(
                    poll_interval_seconds=settings.poll_interval_seconds,
                    cycle_elapsed_seconds=time.monotonic() - cycle_started,
                    poll_jitter_seconds=settings.poll_jitter_seconds,
                )
            )
    except KeyboardInterrupt:
        exit_reason = "keyboard_interrupt"
        return 130
    finally:
        store.append_lifecycle(
            observer_instance_id=settings.instance_id,
            run_id=run_id,
            event="process_stopped",
            reason=exit_reason,
        )


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

    if args.audit_state:
        try:
            audit = build_state_audit(settings)
        except StateAuditError as exc:
            raise SystemExit(f"state audit error: {exc}") from exc
        print(json.dumps(audit, separators=(",", ":"), sort_keys=True))
        return 0

    run_id = str(uuid4())
    try:
        client = HealthClient(
            base_url=settings.base_url,
            external_web_url=settings.external_web_url,
            observer_instance_id=settings.instance_id,
            run_id=run_id,
            observation_contract_version=settings.observation_contract_version,
            endpoint_set_version=settings.endpoint_set_version,
            timeout_seconds=settings.timeout_seconds,
            max_attempts=settings.max_attempts,
            retry_backoff_seconds=settings.retry_backoff_seconds,
            bearer_credential=settings.bearer_credential,
        )
    except ValueError as exc:
        raise SystemExit(f"client setup error: {exc}") from exc
    store = ObserverStore(settings.state_dir)
    try:
        with store.writer_lock():
            return _run_polling_process(
                args=args,
                settings=settings,
                client=client,
                store=store,
                run_id=run_id,
            )
    except StateWriterLockError as exc:
        raise SystemExit(f"agent startup error: {exc}") from exc
    except (IncidentStoreError, StateRetentionError) as exc:
        raise SystemExit(f"agent runtime error: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
