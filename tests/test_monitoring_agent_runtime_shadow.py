from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from monitoring_agent.client import CURRENT_ENDPOINT_KEYS, Observation
from monitoring_agent.incident_store import IncidentStoreError, IncidentStateStore
from monitoring_agent.runtime_shadow import (
    SHADOW_RUNTIME_MODE,
    apply_shadow_incident_cycle,
    build_incident_store_limits,
)
from monitoring_agent.settings import RuntimeSettings


BASE_TIME = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)


def _settings(tmp_path) -> RuntimeSettings:
    return RuntimeSettings(
        env_contract_version=3,
        mode="test",
        instance_id="center-test",
        base_url="http://127.0.0.1:8020",
        external_web_url="http://127.0.0.1:8020",
        state_dir=tmp_path / "state",
        timeout_seconds=2.0,
        max_attempts=3,
        retry_backoff_seconds=0.5,
        poll_interval_seconds=60.0,
        poll_jitter_seconds=5.0,
        endpoint_keys=CURRENT_ENDPOINT_KEYS,
        endpoint_set_version=3,
        observation_contract_version=4,
        max_observation_records=10_000,
        max_incident_states=200,
        max_incident_transition_records=2_000,
        max_outbox_items=1_000,
        outbox_max_attempts=3,
        outbox_retry_backoff_seconds=300.0,
        outbox_claim_timeout_seconds=600.0,
        bearer_credential="t" * 48,
    )


def _observations(
    sequence: int,
    *,
    payload_status: dict[str, str] | None = None,
    transport: dict[str, str] | None = None,
) -> tuple[Observation, ...]:
    payload_status = payload_status or {}
    transport = transport or {}
    cycle_id = f"private-cycle-{sequence}"
    started_at = BASE_TIME + timedelta(seconds=60 * sequence)
    return tuple(
        Observation(
            observation_id=f"private-observation-{sequence}-{endpoint_key}",
            observer_instance_id="private-instance",
            run_id="private-run",
            cycle_id=cycle_id,
            cycle_sequence=sequence,
            endpoint_key=endpoint_key,
            poll_started_at=(started_at + timedelta(seconds=index)).isoformat(),
            poll_finished_at=(
                started_at + timedelta(seconds=index + 1)
            ).isoformat(),
            http_status=(
                200 if transport.get(endpoint_key, "success") == "success" else None
            ),
            transport_status=transport.get(endpoint_key, "success"),
            attempt_count=1,
            contract_version=4,
            endpoint_set_version=3,
            source_checked_at=None,
            clock_skew_seconds=None,
            payload={"status": payload_status.get(endpoint_key, "ok")},
        )
        for index, endpoint_key in enumerate(CURRENT_ENDPOINT_KEYS)
    )


def test_shadow_runtime_creates_empty_disabled_state_for_healthy_cycle(tmp_path):
    settings = _settings(tmp_path)

    summary = apply_shadow_incident_cycle(
        settings=settings,
        observations=_observations(1),
        now=BASE_TIME,
    )

    assert summary.to_dict() == {
        "active_state_count": 0,
        "candidate_state_count": 0,
        "contract_version": 1,
        "delivery_enabled": False,
        "incident_rule_version": 1,
        "mode": SHADOW_RUNTIME_MODE,
        "outbox_count": 0,
        "outbox_dead_letter_count": 0,
        "outbox_in_progress_count": 0,
        "outbox_pending_count": 0,
        "outbox_sent_count": 0,
        "resolved_state_count": 0,
        "state_count": 0,
        "transition_count": 0,
        "transition_record_count": 0,
        "updated_at": BASE_TIME.isoformat(),
    }
    snapshot = IncidentStateStore(
        settings.state_dir,
        limits=build_incident_store_limits(settings),
    ).load()
    assert snapshot.to_dict()["delivery_enabled"] is False
    assert snapshot.states == ()
    assert snapshot.outbox_items == ()


def test_shadow_runtime_persists_confirmed_incident_and_pending_intent(tmp_path):
    settings = _settings(tmp_path)

    first = apply_shadow_incident_cycle(
        settings=settings,
        observations=_observations(1, payload_status={"system_database": "degraded"}),
        now=BASE_TIME,
    )
    second = apply_shadow_incident_cycle(
        settings=settings,
        observations=_observations(2, payload_status={"system_database": "degraded"}),
        now=BASE_TIME + timedelta(seconds=60),
    )

    assert first.candidate_state_count == 1
    assert first.outbox_pending_count == 0
    assert second.active_state_count == 1
    assert second.candidate_state_count == 0
    assert second.outbox_pending_count == 1
    assert second.transition_record_count == 2
    snapshot = IncidentStateStore(settings.state_dir).load()
    assert snapshot.state_by_key()["endpoint:system_database"].status == "active"
    assert snapshot.outbox_items[0].incident_key == "endpoint:system_database"
    serialized = json.dumps(snapshot.to_dict(), sort_keys=True)
    assert "private-observation" not in serialized
    assert "Bearer" not in serialized


def test_shadow_runtime_records_recovery_intent_without_sending(tmp_path):
    settings = _settings(tmp_path)
    apply_shadow_incident_cycle(
        settings=settings,
        observations=_observations(1, payload_status={"system_proxy": "degraded"}),
        now=BASE_TIME,
    )
    apply_shadow_incident_cycle(
        settings=settings,
        observations=_observations(2, payload_status={"system_proxy": "degraded"}),
        now=BASE_TIME + timedelta(seconds=60),
    )
    apply_shadow_incident_cycle(
        settings=settings,
        observations=_observations(3),
        now=BASE_TIME + timedelta(seconds=120),
    )

    recovered = apply_shadow_incident_cycle(
        settings=settings,
        observations=_observations(4),
        now=BASE_TIME + timedelta(seconds=180),
    )

    assert recovered.resolved_state_count == 1
    assert recovered.outbox_pending_count == 2
    snapshot = IncidentStateStore(settings.state_dir).load()
    assert {item.action for item in snapshot.outbox_items} == {"opened", "recovered"}
    assert {item.status for item in snapshot.outbox_items} == {"pending"}


def test_shadow_runtime_fails_closed_without_overwriting_corrupt_state(tmp_path):
    settings = _settings(tmp_path)
    settings.state_dir.mkdir(parents=True)
    state_path = settings.state_dir / "incident_state.json"
    state_path.write_text("{not-json", encoding="utf-8")
    before = state_path.read_bytes()

    with pytest.raises(IncidentStoreError):
        apply_shadow_incident_cycle(
            settings=settings,
            observations=_observations(1),
            now=BASE_TIME,
        )

    assert state_path.read_bytes() == before
