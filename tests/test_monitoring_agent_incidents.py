from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json

from monitoring_agent.client import CURRENT_ENDPOINT_KEYS, Observation
from monitoring_agent.incidents import (
    CycleSnapshot,
    EndpointObservationFact,
    IncidentRules,
    classify_cycle_conditions,
    evaluate_incident_lifecycle,
)


BASE_TIME = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
FACADE_ENDPOINT_KEYS = tuple(
    endpoint_key
    for endpoint_key in CURRENT_ENDPOINT_KEYS
    if endpoint_key != "external_web"
)


def _cycle(
    sequence: int,
    *,
    transport: dict[str, str] | None = None,
    payload_status: dict[str, str] | None = None,
    historical: bool = False,
    seconds_between_cycles: int = 60,
) -> CycleSnapshot:
    transport = transport or {}
    payload_status = payload_status or {}
    return CycleSnapshot(
        cycle_sequence=sequence,
        observed_at=BASE_TIME + timedelta(seconds=seconds_between_cycles * sequence),
        historical=historical,
        endpoint_observations=tuple(
            EndpointObservationFact(
                endpoint_key=endpoint_key,
                transport_status=transport.get(endpoint_key, "success"),
                http_status=(
                    200
                    if transport.get(endpoint_key, "success") == "success"
                    else None
                ),
                payload_status=payload_status.get(endpoint_key, "ok"),
            )
            for endpoint_key in CURRENT_ENDPOINT_KEYS
        ),
    )


def _transitions_for(evaluation, incident_key: str):
    return [
        transition
        for transition in evaluation.transitions
        if transition.incident_key == incident_key
    ]


def test_incident_lifecycle_opens_updates_and_recovers_endpoint_incident():
    incident_key = "endpoint:system_database"

    evaluation = evaluate_incident_lifecycle(
        [
            _cycle(1, payload_status={"system_database": "degraded"}),
            _cycle(2, payload_status={"system_database": "degraded"}),
            _cycle(3, payload_status={"system_database": "degraded"}),
            _cycle(4),
            _cycle(5),
        ]
    )

    transitions = _transitions_for(evaluation, incident_key)
    assert [(item.action, item.reason, item.status) for item in transitions] == [
        ("suppressed", "confirmation_threshold_not_met", "candidate"),
        ("opened", "endpoint_payload_status:degraded", "active"),
        ("updated", "endpoint_payload_status:degraded", "active"),
        ("updated", "recovery_confirmation_pending", "active"),
        ("recovered", "recovery_confirmed", "resolved"),
    ]
    state = evaluation.state_by_key()[incident_key]
    assert state.status == "resolved"
    assert state.failure_count == 3
    assert state.recovery_count == 2
    assert state.occurrence_count == 1


def test_incident_lifecycle_reopens_after_confirmed_recurrence():
    rules = IncidentRules(recurrence_cooldown_cycles=1)
    incident_key = "endpoint:system_database"
    initial = evaluate_incident_lifecycle(
        [
            _cycle(1, payload_status={"system_database": "degraded"}),
            _cycle(2, payload_status={"system_database": "degraded"}),
            _cycle(3),
            _cycle(4),
        ],
        rules=rules,
    )

    recurrent = evaluate_incident_lifecycle(
        [
            _cycle(6, payload_status={"system_database": "degraded"}),
            _cycle(7, payload_status={"system_database": "degraded"}),
        ],
        previous_states=initial.states,
        rules=rules,
    )

    transitions = _transitions_for(recurrent, incident_key)
    assert [(item.action, item.reason, item.status) for item in transitions] == [
        ("suppressed", "confirmation_threshold_not_met", "candidate"),
        ("reopened", "endpoint_payload_status:degraded", "active"),
    ]
    state = recurrent.state_by_key()[incident_key]
    assert state.status == "active"
    assert state.occurrence_count == 2


def test_target_wide_outage_suppresses_facade_endpoint_transport_noise():
    outage_transport = {
        endpoint_key: "connection_error" for endpoint_key in FACADE_ENDPOINT_KEYS
    }

    evaluation = evaluate_incident_lifecycle(
        [
            _cycle(1, transport=outage_transport),
            _cycle(2, transport=outage_transport),
        ]
    )

    target_transitions = _transitions_for(
        evaluation, "target_wide_outage:facade_transport"
    )
    assert [(item.action, item.status) for item in target_transitions] == [
        ("suppressed", "candidate"),
        ("opened", "active"),
    ]
    endpoint_suppressed = [
        transition
        for transition in evaluation.transitions
        if transition.kind == "endpoint"
        and transition.reason == "suppressed_by_target_wide_outage"
    ]
    assert len(endpoint_suppressed) == len(FACADE_ENDPOINT_KEYS) * 2
    state_keys = set(evaluation.state_by_key())
    assert state_keys == {"target_wide_outage:facade_transport"}


def test_observer_self_health_opens_for_facade_contract_failures_and_recovers():
    incident_key = "observer_self_health:facade_contract"

    evaluation = evaluate_incident_lifecycle(
        [
            _cycle(1, transport={"system_runtime": "schema_error"}),
            _cycle(2),
            _cycle(3),
        ]
    )

    assert [condition.incident_key for condition in classify_cycle_conditions(
        _cycle(1, transport={"system_runtime": "schema_error"})
    )] == [incident_key]
    transitions = _transitions_for(evaluation, incident_key)
    assert [(item.action, item.reason, item.status) for item in transitions] == [
        (
            "opened",
            "facade_contract_or_authentication_failure:schema_error",
            "active",
        ),
        ("updated", "recovery_confirmation_pending", "active"),
        ("recovered", "recovery_confirmed", "resolved"),
    ]
    assert evaluation.state_by_key()[incident_key].status == "resolved"


def test_supervision_blind_spot_uses_deterministic_now_and_recovers_from_fresh_cycle():
    rules = IncidentRules(blind_spot_after_seconds=130)
    stale_evaluation = evaluate_incident_lifecycle(
        [_cycle(1)],
        rules=rules,
        now=BASE_TIME + timedelta(seconds=240),
    )

    incident_key = "supervision_center_blind_spot:observer_freshness"
    stale_transitions = _transitions_for(stale_evaluation, incident_key)
    assert [(item.action, item.reason, item.status) for item in stale_transitions] == [
        ("opened", "latest_cycle_stale", "active"),
    ]

    recovered = evaluate_incident_lifecycle(
        [_cycle(4)],
        previous_states=stale_evaluation.states,
        rules=rules,
        now=BASE_TIME + timedelta(seconds=250),
    )

    recovered_transitions = _transitions_for(recovered, incident_key)
    assert [
        (item.action, item.reason, item.status) for item in recovered_transitions
    ] == [("recovered", "recovery_confirmed", "resolved")]
    assert recovered.state_by_key()[incident_key].status == "resolved"


def test_historical_evidence_is_qualified_and_suppressed():
    evaluation = evaluate_incident_lifecycle(
        [
            _cycle(
                1,
                transport={"system_runtime": "schema_error"},
                historical=True,
            )
        ]
    )

    assert [(item.action, item.reason) for item in evaluation.transitions] == [
        ("suppressed", "historical_evidence_only")
    ]
    assert evaluation.states == ()


def test_cycle_snapshot_from_observations_uses_only_sanitized_payload_status():
    observed_at = BASE_TIME + timedelta(seconds=1)
    observation = Observation(
        observation_id="private-observation-id",
        observer_instance_id="private-instance",
        run_id="private-run",
        cycle_id="private-cycle",
        cycle_sequence=1,
        endpoint_key="system_database",
        poll_started_at=BASE_TIME.isoformat(),
        poll_finished_at=observed_at.isoformat(),
        http_status=200,
        transport_status="success",
        attempt_count=1,
        contract_version=4,
        endpoint_set_version=3,
        source_checked_at=None,
        clock_skew_seconds=None,
        payload={"status": "degraded", "private_payload": "must-not-leak"},
    )

    snapshot = CycleSnapshot.from_observations([observation])
    evaluation = evaluate_incident_lifecycle([snapshot, snapshot])

    assert snapshot.endpoint_observations[0].payload_status == "degraded"
    serialized = json.dumps(evaluation.to_dict(), sort_keys=True)
    assert "private" not in serialized
    assert "must-not-leak" not in serialized
