from __future__ import annotations

from collections.abc import Iterable

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
    observations: list[Observation] = []
    for endpoint_key in resolved_keys:
        observation = client.poll(endpoint_key)
        store.append(observation)
        observations.append(observation)
    store.write_heartbeat(observer_instance_id=observer_instance_id)
    return tuple(observations)
