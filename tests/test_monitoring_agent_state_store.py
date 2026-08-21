from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

import pytest

from monitoring_agent.client import CURRENT_ENDPOINT_KEYS, Observation
from monitoring_agent.incident_store import (
    IncidentStateStore,
    IncidentStoreError,
    IncidentStoreLimits,
    OUTBOX_DEAD_LETTER,
)
from monitoring_agent.incidents import (
    CycleSnapshot,
    EndpointObservationFact,
    evaluate_incident_lifecycle,
)
from monitoring_agent.store import ObserverStore, StateRetentionError


BASE_TIME = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)


def _cycle(
    sequence: int,
    *,
    payload_status: dict[str, str] | None = None,
) -> CycleSnapshot:
    payload_status = payload_status or {}
    return CycleSnapshot(
        cycle_sequence=sequence,
        observed_at=BASE_TIME + timedelta(seconds=60 * sequence),
        endpoint_observations=tuple(
            EndpointObservationFact(
                endpoint_key=endpoint_key,
                transport_status="success",
                http_status=200,
                payload_status=payload_status.get(endpoint_key, "ok"),
            )
            for endpoint_key in CURRENT_ENDPOINT_KEYS
        ),
    )


def _opened_endpoint_evaluation(endpoint_key: str = "system_database"):
    return evaluate_incident_lifecycle(
        [
            _cycle(1, payload_status={endpoint_key: "degraded"}),
            _cycle(2, payload_status={endpoint_key: "degraded"}),
        ]
    )


def _observation(
    *,
    endpoint_key: str,
    cycle_sequence: int,
    cycle_id: str,
    started_at: datetime,
    run_id: str = "private-run",
) -> Observation:
    return Observation(
        observation_id=f"private-observation-{endpoint_key}-{cycle_sequence}",
        observer_instance_id="private-instance",
        run_id=run_id,
        cycle_id=cycle_id,
        cycle_sequence=cycle_sequence,
        endpoint_key=endpoint_key,
        poll_started_at=started_at.isoformat(),
        poll_finished_at=(started_at + timedelta(seconds=1)).isoformat(),
        http_status=200,
        transport_status="success",
        attempt_count=1,
        contract_version=4,
        endpoint_set_version=3,
        source_checked_at=None,
        clock_skew_seconds=None,
        payload={"status": "ok"},
    )


def _append_observation_cycle(
    store: ObserverStore,
    *,
    sequence: int,
    run_id: str = "private-run",
) -> None:
    cycle_id = f"private-cycle-{sequence}"
    started_at = BASE_TIME + timedelta(seconds=sequence * 60)
    for endpoint_index, endpoint_key in enumerate(CURRENT_ENDPOINT_KEYS):
        store.append(
            _observation(
                endpoint_key=endpoint_key,
                cycle_sequence=sequence,
                cycle_id=cycle_id,
                started_at=started_at + timedelta(seconds=endpoint_index),
                run_id=run_id,
            )
        )


def test_incident_store_persists_states_transitions_and_outbox_after_restart(
    tmp_path,
):
    store = IncidentStateStore(tmp_path)
    evaluation = _opened_endpoint_evaluation()

    snapshot = store.apply_evaluation(
        evaluation,
        report_references={"endpoint:system_database": "report:database:open"},
        now=BASE_TIME,
    )
    reloaded = IncidentStateStore(tmp_path).load()

    assert snapshot.to_dict() == reloaded.to_dict()
    assert reloaded.state_by_key()["endpoint:system_database"].status == "active"
    assert len(reloaded.transition_records) == 2
    assert len(reloaded.outbox_items) == 1
    outbox_item = reloaded.outbox_items[0]
    assert outbox_item.status == "pending"
    assert outbox_item.report_reference == "report:database:open"
    assert reloaded.to_dict()["delivery_enabled"] is False
    serialized = json.dumps(reloaded.to_dict(), sort_keys=True)
    assert "private" not in serialized
    assert "BEARER" not in serialized


def test_incident_store_deduplicates_delivery_intents_by_idempotency_key(
    tmp_path,
):
    store = IncidentStateStore(tmp_path)
    evaluation = _opened_endpoint_evaluation()

    first = store.apply_evaluation(evaluation, now=BASE_TIME)
    second = store.apply_evaluation(evaluation, now=BASE_TIME + timedelta(seconds=1))

    assert len(first.outbox_items) == 1
    assert len(second.outbox_items) == 1
    assert (
        first.outbox_items[0].idempotency_key
        == second.outbox_items[0].idempotency_key
    )


def test_incident_store_suppresses_redundant_updated_transition_records(
    tmp_path,
):
    store = IncidentStateStore(tmp_path)
    opened = store.apply_evaluation(
        _opened_endpoint_evaluation("system_scheduler"),
        now=BASE_TIME,
    )

    first_update = store.apply_evaluation(
        evaluate_incident_lifecycle(
            [_cycle(3, payload_status={"system_scheduler": "degraded"})],
            previous_states=opened.state_by_key(),
        ),
        now=BASE_TIME + timedelta(minutes=3),
    )
    second_update = store.apply_evaluation(
        evaluate_incident_lifecycle(
            [_cycle(4, payload_status={"system_scheduler": "degraded"})],
            previous_states=first_update.state_by_key(),
        ),
        now=BASE_TIME + timedelta(minutes=4),
    )
    changed_reason = store.apply_evaluation(
        evaluate_incident_lifecycle(
            [_cycle(5, payload_status={"system_scheduler": "error"})],
            previous_states=second_update.state_by_key(),
        ),
        now=BASE_TIME + timedelta(minutes=5),
    )

    assert [
        record["transition"]["action"]
        for record in changed_reason.transition_records
    ] == ["suppressed", "opened", "updated", "updated"]
    assert [
        record["transition"]["reason"]
        for record in changed_reason.transition_records
    ] == [
        "confirmation_threshold_not_met",
        "endpoint_payload_status:degraded",
        "endpoint_payload_status:degraded",
        "endpoint_payload_status:error",
    ]
    state = changed_reason.state_by_key()["endpoint:system_scheduler"]
    assert state.failure_count == 5
    assert state.last_cycle_sequence == 5
    assert len(changed_reason.outbox_items) == 1
    assert changed_reason.outbox_items[0].action == "opened"


def test_outbox_claim_retry_and_dead_letter_state_is_persisted(tmp_path):
    limits = IncidentStoreLimits(
        max_delivery_attempts=2,
        retry_backoff_seconds=30,
    )
    store = IncidentStateStore(tmp_path, limits=limits)
    store.apply_evaluation(_opened_endpoint_evaluation(), now=BASE_TIME)

    claimed = store.claim_due_delivery_intents(
        claim_id="worker-1",
        now=BASE_TIME,
    )
    assert len(claimed) == 1
    assert claimed[0].status == "in_progress"
    assert store.claim_due_delivery_intents(
        claim_id="worker-2",
        now=BASE_TIME,
    ) == ()

    retry_snapshot = store.record_delivery_result(
        idempotency_key=claimed[0].idempotency_key,
        claim_id="worker-1",
        succeeded=False,
        error_code="smtp_unavailable",
        now=BASE_TIME + timedelta(seconds=1),
    )
    retry_item = retry_snapshot.outbox_by_key()[claimed[0].idempotency_key]
    assert retry_item.status == "pending"
    assert retry_item.attempt_count == 1
    assert retry_item.last_error_code == "smtp_unavailable"
    assert retry_item.next_attempt_at == BASE_TIME + timedelta(seconds=31)

    claimed_again = store.claim_due_delivery_intents(
        claim_id="worker-1",
        now=BASE_TIME + timedelta(seconds=31),
    )
    dead_letter_snapshot = store.record_delivery_result(
        idempotency_key=claimed_again[0].idempotency_key,
        claim_id="worker-1",
        succeeded=False,
        error_code="smtp_unavailable",
        now=BASE_TIME + timedelta(seconds=32),
    )
    dead_letter = dead_letter_snapshot.outbox_by_key()[
        claimed_again[0].idempotency_key
    ]
    assert dead_letter.status == "dead_letter"
    assert dead_letter.attempt_count == 2
    assert dead_letter.claim_id is None
    assert dead_letter.claimed_at is None


def test_outbox_claim_can_filter_exact_report_reference(tmp_path):
    store = IncidentStateStore(tmp_path)
    store.apply_evaluation(
        _opened_endpoint_evaluation("system_database"),
        now=BASE_TIME,
    )
    snapshot = store.apply_evaluation(
        _opened_endpoint_evaluation("system_proxy"),
        now=BASE_TIME + timedelta(seconds=1),
    )
    report_reference_by_incident = {
        item.incident_key: item.report_reference for item in snapshot.outbox_items
    }

    claimed = store.claim_due_delivery_intents(
        claim_id="worker-1",
        now=BASE_TIME + timedelta(seconds=2),
        report_reference=report_reference_by_incident["endpoint:system_proxy"],
    )

    assert [item.incident_key for item in claimed] == ["endpoint:system_proxy"]
    outbox_by_incident = {
        item.incident_key: item for item in store.load().outbox_items
    }
    assert outbox_by_incident["endpoint:system_proxy"].status == "in_progress"
    assert outbox_by_incident["endpoint:system_database"].status == "pending"


def test_outbox_abandoned_claim_recovers_after_claim_timeout(tmp_path):
    store = IncidentStateStore(
        tmp_path,
        limits=IncidentStoreLimits(claim_timeout_seconds=10),
    )
    store.apply_evaluation(_opened_endpoint_evaluation(), now=BASE_TIME)
    claimed = store.claim_due_delivery_intents(
        claim_id="worker-1",
        now=BASE_TIME,
    )

    recovered = store.recover_abandoned_claims(
        now=BASE_TIME + timedelta(seconds=11)
    )

    item = recovered.outbox_by_key()[claimed[0].idempotency_key]
    assert item.status == "pending"
    assert item.claim_id is None
    assert item.claimed_at is None
    assert item.next_attempt_at == BASE_TIME + timedelta(seconds=11)


def test_outbox_operator_skip_parks_pending_items_without_delivery_attempt(tmp_path):
    store = IncidentStateStore(tmp_path)
    store.apply_evaluation(
        _opened_endpoint_evaluation("system_database"),
        now=BASE_TIME,
    )
    snapshot = store.apply_evaluation(
        _opened_endpoint_evaluation("system_proxy"),
        now=BASE_TIME + timedelta(seconds=10),
    )

    skipped = store.skip_pending_delivery_intents(
        now=BASE_TIME + timedelta(seconds=20),
        created_before=BASE_TIME + timedelta(seconds=5),
        limit=10,
    )

    assert [item.incident_key for item in skipped] == ["endpoint:system_database"]
    skipped_item = store.load().outbox_by_key()[skipped[0].idempotency_key]
    retained_pending = [
        item
        for item in store.load().outbox_items
        if item.idempotency_key != skipped[0].idempotency_key
    ][0]
    assert skipped_item.status == OUTBOX_DEAD_LETTER
    assert skipped_item.last_error_code == "operator_skipped"
    assert skipped_item.attempt_count == 0
    assert skipped_item.last_attempt_at is None
    assert skipped_item.claim_id is None
    assert skipped_item.claimed_at is None
    assert skipped_item.updated_at == BASE_TIME + timedelta(seconds=20)
    assert retained_pending.status == "pending"
    assert store.claim_due_delivery_intents(
        claim_id="worker-1",
        now=BASE_TIME + timedelta(seconds=21),
    )[0].idempotency_key == retained_pending.idempotency_key
    assert len(snapshot.outbox_items) == 2


def test_outbox_operator_skip_requires_filter_or_cutoff(tmp_path):
    store = IncidentStateStore(tmp_path)
    store.apply_evaluation(_opened_endpoint_evaluation(), now=BASE_TIME)

    with pytest.raises(ValueError, match="skip requires"):
        store.skip_pending_delivery_intents(
            now=BASE_TIME + timedelta(seconds=1),
            limit=1,
        )

    assert store.load().outbox_items[0].status == "pending"


def test_incident_store_retention_bounds_transition_and_sent_outbox_history(
    tmp_path,
):
    store = IncidentStateStore(
        tmp_path,
        limits=IncidentStoreLimits(
            max_transition_records=1,
            max_outbox_items=1,
        ),
    )
    evaluation = _opened_endpoint_evaluation()

    snapshot = store.apply_evaluation(evaluation, now=BASE_TIME)
    claimed = store.claim_due_delivery_intents(
        claim_id="worker-1",
        now=BASE_TIME,
    )
    store.record_delivery_result(
        idempotency_key=claimed[0].idempotency_key,
        claim_id="worker-1",
        succeeded=True,
        now=BASE_TIME + timedelta(seconds=1),
    )
    retained = store.load()

    assert len(retained.transition_records) == 1
    assert len(retained.outbox_items) == 1
    assert retained.outbox_items[0].status == "sent"


def test_incident_store_corrupt_state_fails_closed_without_overwrite(tmp_path):
    state_path = tmp_path / "incident_state.json"
    state_path.write_text("private-invalid-json", encoding="utf-8")
    store = IncidentStateStore(tmp_path)

    with pytest.raises(IncidentStoreError, match="cannot be read"):
        store.apply_evaluation(_opened_endpoint_evaluation(), now=BASE_TIME)

    assert state_path.read_text(encoding="utf-8") == "private-invalid-json"


def test_observer_store_retains_recent_complete_observation_cycles(tmp_path):
    store = ObserverStore(tmp_path)
    _append_observation_cycle(store, sequence=1)
    _append_observation_cycle(store, sequence=2)
    _append_observation_cycle(store, sequence=3)

    store.retain_recent_observations(max_records=18)

    observations = [
        json.loads(line)
        for line in store.observations_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(observations) == 18
    assert {item["cycle_sequence"] for item in observations[:9]} == {2}
    assert {item["cycle_sequence"] for item in observations[9:]} == {3}


def test_observer_store_corrupt_observation_retention_fails_closed(tmp_path):
    store = ObserverStore(tmp_path)
    _append_observation_cycle(store, sequence=1)
    original = store.observations_path.read_text(encoding="utf-8")
    with store.observations_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("private-invalid-json\n")

    with pytest.raises(StateRetentionError, match="invalid JSON"):
        store.retain_recent_observations(max_records=9)

    assert store.observations_path.read_text(encoding="utf-8") == (
        original + "private-invalid-json\n"
    )
