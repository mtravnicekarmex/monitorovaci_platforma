from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from uuid import uuid4

from .client import APPROVED_ENDPOINTS, HealthClient, Observation
from .store import ObserverStore


def run_observation_cycle(
    *,
    client: HealthClient,
    store: ObserverStore,
    observer_instance_id: str,
    endpoint_keys: Iterable[str] | None = None,
) -> tuple[Observation, ...]:
    resolved_keys = tuple(endpoint_keys or APPROVED_ENDPOINTS)
    cycle_id = str(uuid4())
    cycle_started_at = datetime.now(timezone.utc).isoformat()
    store.write_heartbeat(
        observer_instance_id=observer_instance_id,
        status="polling",
        cycle_id=cycle_id,
        cycle_started_at=cycle_started_at,
    )
    observations: list[Observation] = []
    for endpoint_key in resolved_keys:
        observation = client.poll(endpoint_key)
        store.append(observation)
        observations.append(observation)
    transport_failure_count = sum(
        observation.transport_status != "success" for observation in observations
    )
    store.write_heartbeat(
        observer_instance_id=observer_instance_id,
        status="healthy" if transport_failure_count == 0 else "degraded",
        cycle_id=cycle_id,
        cycle_started_at=cycle_started_at,
        cycle_finished_at=datetime.now(timezone.utc).isoformat(),
        observation_count=len(observations),
        transport_failure_count=transport_failure_count,
    )
    return tuple(observations)
