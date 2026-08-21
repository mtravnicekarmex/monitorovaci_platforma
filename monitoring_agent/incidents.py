from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from .client import CURRENT_ENDPOINT_KEYS, Observation


INCIDENT_RULE_VERSION = 1
INCIDENT_KIND_ENDPOINT = "endpoint"
INCIDENT_KIND_TARGET_WIDE = "target_wide_outage"
INCIDENT_KIND_OBSERVER = "observer_self_health"
INCIDENT_KIND_BLIND_SPOT = "supervision_center_blind_spot"
INCIDENT_STATUS_CANDIDATE = "candidate"
INCIDENT_STATUS_ACTIVE = "active"
INCIDENT_STATUS_RESOLVED = "resolved"

RETRYABLE_TRANSPORT_FAILURES = {"connection_error", "timeout"}
OBSERVER_CONTRACT_FAILURES = {"http_error", "schema_error", "tls_error"}
PAYLOAD_PROBLEM_STATUSES = {"degraded", "error", "unavailable"}
FACADE_ENDPOINT_KEYS = tuple(
    endpoint_key
    for endpoint_key in CURRENT_ENDPOINT_KEYS
    if endpoint_key != "external_web"
)
SEVERITY_RANK = {"warning": 1, "critical": 2}


@dataclass(frozen=True)
class EndpointObservationFact:
    endpoint_key: str
    transport_status: str
    http_status: int | None = None
    payload_status: str | None = None

    def __post_init__(self) -> None:
        if not self.endpoint_key.strip():
            raise ValueError("endpoint key is required")
        if not self.transport_status.strip():
            raise ValueError("transport status is required")
        if (
            self.http_status is not None
            and (
                isinstance(self.http_status, bool)
                or not isinstance(self.http_status, int)
                or self.http_status < 100
                or self.http_status > 599
            )
        ):
            raise ValueError("HTTP status must be an integer HTTP status or None")
        if self.payload_status is not None and not self.payload_status.strip():
            raise ValueError("payload status must not be empty")


@dataclass(frozen=True)
class CycleSnapshot:
    cycle_sequence: int
    observed_at: datetime
    endpoint_observations: tuple[EndpointObservationFact, ...]
    historical: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.cycle_sequence, bool)
            or not isinstance(self.cycle_sequence, int)
            or self.cycle_sequence < 1
        ):
            raise ValueError("cycle sequence must be a positive integer")
        _require_aware_datetime(self.observed_at, context="cycle observed_at")
        observations = tuple(self.endpoint_observations)
        if not observations:
            raise ValueError("cycle snapshot requires at least one endpoint")
        endpoint_keys = [item.endpoint_key for item in observations]
        if len(endpoint_keys) != len(set(endpoint_keys)):
            raise ValueError("cycle snapshot contains duplicate endpoint keys")
        object.__setattr__(self, "endpoint_observations", observations)

    @classmethod
    def from_observations(
        cls,
        observations: Iterable[Observation],
        *,
        historical: bool = False,
    ) -> CycleSnapshot:
        resolved = tuple(observations)
        if not resolved:
            raise ValueError("cycle snapshot requires at least one observation")
        cycle_sequences = {item.cycle_sequence for item in resolved}
        if len(cycle_sequences) != 1:
            raise ValueError("observations must belong to one cycle sequence")
        observed_at = max(
            _parse_datetime(item.poll_finished_at, context="observation finish")
            for item in resolved
        )
        return cls(
            cycle_sequence=resolved[0].cycle_sequence,
            observed_at=observed_at,
            endpoint_observations=tuple(
                EndpointObservationFact(
                    endpoint_key=item.endpoint_key,
                    transport_status=item.transport_status,
                    http_status=item.http_status,
                    payload_status=_payload_status(item.payload),
                )
                for item in resolved
            ),
            historical=historical,
        )


@dataclass(frozen=True)
class IncidentRules:
    rule_version: int = INCIDENT_RULE_VERSION
    endpoint_open_cycles: int = 2
    endpoint_recovery_cycles: int = 2
    target_wide_open_cycles: int = 2
    target_wide_recovery_cycles: int = 2
    observer_open_cycles: int = 1
    observer_recovery_cycles: int = 2
    blind_spot_open_cycles: int = 1
    blind_spot_recovery_cycles: int = 1
    blind_spot_after_seconds: float = 130.0
    recurrence_cooldown_cycles: int = 1

    def __post_init__(self) -> None:
        for name in (
            "endpoint_open_cycles",
            "endpoint_recovery_cycles",
            "target_wide_open_cycles",
            "target_wide_recovery_cycles",
            "observer_open_cycles",
            "observer_recovery_cycles",
            "blind_spot_open_cycles",
            "blind_spot_recovery_cycles",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(self.recurrence_cooldown_cycles, bool)
            or not isinstance(self.recurrence_cooldown_cycles, int)
            or self.recurrence_cooldown_cycles < 0
        ):
            raise ValueError("recurrence_cooldown_cycles must not be negative")
        if self.blind_spot_after_seconds <= 0:
            raise ValueError("blind_spot_after_seconds must be positive")

    def rule_table(self) -> dict[str, dict[str, object]]:
        return {
            INCIDENT_KIND_ENDPOINT: {
                "open_after_consecutive_cycles": self.endpoint_open_cycles,
                "recover_after_consecutive_healthy_cycles": (
                    self.endpoint_recovery_cycles
                ),
            },
            INCIDENT_KIND_TARGET_WIDE: {
                "open_after_consecutive_cycles": self.target_wide_open_cycles,
                "recover_after_consecutive_healthy_cycles": (
                    self.target_wide_recovery_cycles
                ),
                "suppresses": "retryable facade endpoint incidents in the same cycle",
            },
            INCIDENT_KIND_OBSERVER: {
                "open_after_consecutive_cycles": self.observer_open_cycles,
                "recover_after_consecutive_healthy_cycles": (
                    self.observer_recovery_cycles
                ),
            },
            INCIDENT_KIND_BLIND_SPOT: {
                "open_after_consecutive_cycles": self.blind_spot_open_cycles,
                "recover_after_consecutive_healthy_cycles": (
                    self.blind_spot_recovery_cycles
                ),
                "stale_after_seconds": self.blind_spot_after_seconds,
            },
        }


@dataclass(frozen=True)
class IncidentCondition:
    kind: str
    subject: str
    severity: str
    reason: str
    observed_at: datetime
    cycle_sequence: int | None

    def __post_init__(self) -> None:
        if self.kind not in {
            INCIDENT_KIND_ENDPOINT,
            INCIDENT_KIND_TARGET_WIDE,
            INCIDENT_KIND_OBSERVER,
            INCIDENT_KIND_BLIND_SPOT,
        }:
            raise ValueError("incident kind is invalid")
        if not self.subject.strip():
            raise ValueError("incident subject is required")
        if self.severity not in SEVERITY_RANK:
            raise ValueError("incident severity is invalid")
        if not self.reason.strip():
            raise ValueError("incident reason is required")
        _require_aware_datetime(self.observed_at, context="condition observed_at")
        if self.cycle_sequence is not None and (
            isinstance(self.cycle_sequence, bool)
            or not isinstance(self.cycle_sequence, int)
            or self.cycle_sequence < 1
        ):
            raise ValueError("condition cycle sequence must be positive or None")

    @property
    def incident_key(self) -> str:
        return f"{self.kind}:{self.subject}"


@dataclass(frozen=True)
class IncidentState:
    incident_key: str
    kind: str
    subject: str
    status: str
    severity: str
    opened_at: datetime | None
    last_observed_at: datetime
    recovered_at: datetime | None = None
    opened_cycle_sequence: int | None = None
    recovered_cycle_sequence: int | None = None
    last_cycle_sequence: int | None = None
    failure_count: int = 0
    recovery_count: int = 0
    occurrence_count: int = 0
    last_reason: str = ""

    def __post_init__(self) -> None:
        if not self.incident_key.strip():
            raise ValueError("incident key is required")
        if self.status not in {
            INCIDENT_STATUS_CANDIDATE,
            INCIDENT_STATUS_ACTIVE,
            INCIDENT_STATUS_RESOLVED,
        }:
            raise ValueError("incident status is invalid")
        if self.severity not in SEVERITY_RANK:
            raise ValueError("incident severity is invalid")
        _require_aware_datetime(self.last_observed_at, context="last observed at")
        if self.opened_at is not None:
            _require_aware_datetime(self.opened_at, context="opened at")
        if self.recovered_at is not None:
            _require_aware_datetime(self.recovered_at, context="recovered at")

    def to_dict(self) -> dict[str, object]:
        return {
            "failure_count": self.failure_count,
            "incident_key": self.incident_key,
            "kind": self.kind,
            "last_cycle_sequence": self.last_cycle_sequence,
            "last_observed_at": _format_datetime(self.last_observed_at),
            "last_reason": self.last_reason,
            "occurrence_count": self.occurrence_count,
            "opened_at": _format_datetime(self.opened_at),
            "opened_cycle_sequence": self.opened_cycle_sequence,
            "recovered_at": _format_datetime(self.recovered_at),
            "recovered_cycle_sequence": self.recovered_cycle_sequence,
            "recovery_count": self.recovery_count,
            "severity": self.severity,
            "status": self.status,
            "subject": self.subject,
        }


@dataclass(frozen=True)
class IncidentTransition:
    incident_key: str
    action: str
    kind: str
    subject: str
    severity: str
    status: str
    reason: str
    observed_at: datetime
    cycle_sequence: int | None
    failure_count: int
    recovery_count: int
    occurrence_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "cycle_sequence": self.cycle_sequence,
            "failure_count": self.failure_count,
            "incident_key": self.incident_key,
            "kind": self.kind,
            "observed_at": _format_datetime(self.observed_at),
            "occurrence_count": self.occurrence_count,
            "reason": self.reason,
            "recovery_count": self.recovery_count,
            "severity": self.severity,
            "status": self.status,
            "subject": self.subject,
        }


@dataclass(frozen=True)
class IncidentEvaluation:
    rule_version: int
    transitions: tuple[IncidentTransition, ...]
    states: tuple[IncidentState, ...]

    def state_by_key(self) -> dict[str, IncidentState]:
        return {state.incident_key: state for state in self.states}

    def to_dict(self) -> dict[str, object]:
        return {
            "event": "incident_lifecycle_evaluation",
            "rule_version": self.rule_version,
            "states": [state.to_dict() for state in self.states],
            "transitions": [
                transition.to_dict() for transition in self.transitions
            ],
        }


DEFAULT_INCIDENT_RULES = IncidentRules()


def classify_cycle_conditions(cycle: CycleSnapshot) -> tuple[IncidentCondition, ...]:
    facts_by_endpoint = {
        fact.endpoint_key: fact for fact in cycle.endpoint_observations
    }
    conditions: list[IncidentCondition] = []
    facade_facts = [
        facts_by_endpoint[endpoint_key]
        for endpoint_key in FACADE_ENDPOINT_KEYS
        if endpoint_key in facts_by_endpoint
    ]
    if (
        len(facade_facts) >= 3
        and len(facade_facts)
        == sum(
            1
            for fact in facade_facts
            if fact.transport_status in RETRYABLE_TRANSPORT_FAILURES
        )
    ):
        conditions.append(
            IncidentCondition(
                kind=INCIDENT_KIND_TARGET_WIDE,
                subject="facade_transport",
                severity="critical",
                reason="all_facade_endpoints_retryable_transport_failure",
                observed_at=cycle.observed_at,
                cycle_sequence=cycle.cycle_sequence,
            )
        )

    observer_failure_count = 0
    observer_failure_statuses: set[str] = set()
    for fact in cycle.endpoint_observations:
        if (
            fact.endpoint_key in FACADE_ENDPOINT_KEYS
            and fact.transport_status in OBSERVER_CONTRACT_FAILURES
        ):
            observer_failure_count += 1
            observer_failure_statuses.add(fact.transport_status)
            continue
        if _is_endpoint_problem(fact):
            conditions.append(
                IncidentCondition(
                    kind=INCIDENT_KIND_ENDPOINT,
                    subject=fact.endpoint_key,
                    severity=_endpoint_severity(fact),
                    reason=_endpoint_reason(fact),
                    observed_at=cycle.observed_at,
                    cycle_sequence=cycle.cycle_sequence,
                )
            )

    if observer_failure_count:
        conditions.append(
            IncidentCondition(
                kind=INCIDENT_KIND_OBSERVER,
                subject="facade_contract",
                severity="warning",
                reason=(
                    "facade_contract_or_authentication_failure:"
                    + ",".join(sorted(observer_failure_statuses))
                ),
                observed_at=cycle.observed_at,
                cycle_sequence=cycle.cycle_sequence,
            )
        )
    return tuple(sorted(conditions, key=lambda item: item.incident_key))


def evaluate_incident_lifecycle(
    cycles: Sequence[CycleSnapshot],
    *,
    previous_states: Mapping[str, IncidentState] | Iterable[IncidentState] | None = None,
    rules: IncidentRules = DEFAULT_INCIDENT_RULES,
    now: datetime | None = None,
) -> IncidentEvaluation:
    if now is not None:
        _require_aware_datetime(now, context="evaluation now")
    ordered_cycles = tuple(cycles)
    _require_chronological_cycles(ordered_cycles)
    states = _normalize_previous_states(previous_states)
    transitions: list[IncidentTransition] = []

    for cycle in ordered_cycles:
        cycle_conditions = classify_cycle_conditions(cycle)
        if cycle.historical:
            transitions.extend(
                _suppressed_transition(
                    condition,
                    reason="historical_evidence_only",
                )
                for condition in cycle_conditions
            )
            continue
        active_conditions, suppressed_conditions = _suppress_endpoint_noise(
            cycle_conditions
        )
        transitions.extend(suppressed_conditions)
        states, cycle_transitions = _advance_states(
            states=states,
            conditions=active_conditions,
            observed_at=cycle.observed_at,
            cycle_sequence=cycle.cycle_sequence,
            rules=rules,
        )
        transitions.extend(cycle_transitions)

    if now is not None:
        latest_cycle = ordered_cycles[-1] if ordered_cycles else None
        condition = _blind_spot_condition(
            latest_cycle=latest_cycle,
            now=now,
            rules=rules,
        )
        conditions = () if condition is None else (condition,)
        states, stale_transitions = _advance_states(
            states=states,
            conditions=conditions,
            observed_at=now,
            cycle_sequence=(
                None if latest_cycle is None else latest_cycle.cycle_sequence
            ),
            rules=rules,
            only_kind=INCIDENT_KIND_BLIND_SPOT,
        )
        transitions.extend(stale_transitions)

    return IncidentEvaluation(
        rule_version=rules.rule_version,
        transitions=tuple(transitions),
        states=tuple(sorted(states.values(), key=lambda item: item.incident_key)),
    )


def _advance_states(
    *,
    states: dict[str, IncidentState],
    conditions: Sequence[IncidentCondition],
    observed_at: datetime,
    cycle_sequence: int | None,
    rules: IncidentRules,
    only_kind: str | None = None,
) -> tuple[dict[str, IncidentState], tuple[IncidentTransition, ...]]:
    condition_by_key = {condition.incident_key: condition for condition in conditions}
    relevant_state_keys = {
        key
        for key, state in states.items()
        if only_kind is None or state.kind == only_kind
    }
    all_keys = sorted(relevant_state_keys | set(condition_by_key))
    next_states = dict(states)
    transitions: list[IncidentTransition] = []
    for incident_key in all_keys:
        state = next_states.get(incident_key)
        condition = condition_by_key.get(incident_key)
        if condition is not None:
            new_state, transition = _advance_failing_condition(
                state=state,
                condition=condition,
                rules=rules,
            )
            next_states[incident_key] = new_state
            transitions.append(transition)
            continue
        if state is None:
            continue
        new_state, transition = _advance_recovery_condition(
            state=state,
            observed_at=observed_at,
            cycle_sequence=cycle_sequence,
            rules=rules,
        )
        if new_state is None:
            next_states.pop(incident_key, None)
        else:
            next_states[incident_key] = new_state
        if transition is not None:
            transitions.append(transition)
    return next_states, tuple(transitions)


def _advance_failing_condition(
    *,
    state: IncidentState | None,
    condition: IncidentCondition,
    rules: IncidentRules,
) -> tuple[IncidentState, IncidentTransition]:
    open_threshold = _open_threshold(condition.kind, rules)
    if state is not None and state.status == INCIDENT_STATUS_ACTIVE:
        severity = _max_severity(state.severity, condition.severity)
        updated = replace(
            state,
            severity=severity,
            last_observed_at=condition.observed_at,
            last_cycle_sequence=condition.cycle_sequence,
            failure_count=state.failure_count + 1,
            recovery_count=0,
            last_reason=condition.reason,
        )
        return updated, _transition(
            state=updated,
            action="updated",
            reason=condition.reason,
            observed_at=condition.observed_at,
            cycle_sequence=condition.cycle_sequence,
        )

    if state is not None and state.status == INCIDENT_STATUS_RESOLVED:
        if _inside_recurrence_cooldown(
            state=state,
            condition=condition,
            rules=rules,
        ):
            return state, _transition(
                state=state,
                action="suppressed",
                reason="recurrence_cooldown_active",
                observed_at=condition.observed_at,
                cycle_sequence=condition.cycle_sequence,
            )
        failure_count = 1
        occurrence_count = state.occurrence_count
        opened_at = state.opened_at
        opened_cycle_sequence = state.opened_cycle_sequence
        recovered_at = state.recovered_at
        recovered_cycle_sequence = state.recovered_cycle_sequence
    elif state is not None and state.status == INCIDENT_STATUS_CANDIDATE:
        failure_count = state.failure_count + 1
        occurrence_count = state.occurrence_count
        opened_at = state.opened_at
        opened_cycle_sequence = state.opened_cycle_sequence
        recovered_at = state.recovered_at
        recovered_cycle_sequence = state.recovered_cycle_sequence
    else:
        failure_count = 1
        occurrence_count = 0
        opened_at = None
        opened_cycle_sequence = None
        recovered_at = None
        recovered_cycle_sequence = None

    if failure_count >= open_threshold:
        action = "opened" if occurrence_count == 0 else "reopened"
        new_occurrence_count = occurrence_count + 1
        opened_at = condition.observed_at
        opened_cycle_sequence = condition.cycle_sequence
        status = INCIDENT_STATUS_ACTIVE
        recovered_at = None
        recovered_cycle_sequence = None
    else:
        action = "suppressed"
        new_occurrence_count = occurrence_count
        status = INCIDENT_STATUS_CANDIDATE
    new_state = IncidentState(
        incident_key=condition.incident_key,
        kind=condition.kind,
        subject=condition.subject,
        status=status,
        severity=condition.severity,
        opened_at=opened_at,
        last_observed_at=condition.observed_at,
        recovered_at=recovered_at,
        opened_cycle_sequence=opened_cycle_sequence,
        recovered_cycle_sequence=recovered_cycle_sequence,
        last_cycle_sequence=condition.cycle_sequence,
        failure_count=failure_count,
        recovery_count=0,
        occurrence_count=new_occurrence_count,
        last_reason=condition.reason,
    )
    return new_state, _transition(
        state=new_state,
        action=action,
        reason=(
            condition.reason
            if action in {"opened", "updated", "reopened"}
            else "confirmation_threshold_not_met"
        ),
        observed_at=condition.observed_at,
        cycle_sequence=condition.cycle_sequence,
    )


def _advance_recovery_condition(
    *,
    state: IncidentState,
    observed_at: datetime,
    cycle_sequence: int | None,
    rules: IncidentRules,
) -> tuple[IncidentState | None, IncidentTransition | None]:
    if state.status == INCIDENT_STATUS_CANDIDATE:
        if state.occurrence_count > 0 and state.recovered_at is not None:
            return replace(
                state,
                status=INCIDENT_STATUS_RESOLVED,
                last_observed_at=observed_at,
                last_cycle_sequence=cycle_sequence,
                failure_count=0,
                recovery_count=0,
                last_reason="recurrence_candidate_cleared",
            ), None
        return None, None
    if state.status == INCIDENT_STATUS_RESOLVED:
        return state, None
    recovery_count = state.recovery_count + 1
    if recovery_count >= _recovery_threshold(state.kind, rules):
        recovered = replace(
            state,
            status=INCIDENT_STATUS_RESOLVED,
            last_observed_at=observed_at,
            recovered_at=observed_at,
            recovered_cycle_sequence=cycle_sequence,
            last_cycle_sequence=cycle_sequence,
            recovery_count=recovery_count,
            last_reason="recovery_confirmed",
        )
        return recovered, _transition(
            state=recovered,
            action="recovered",
            reason="recovery_confirmed",
            observed_at=observed_at,
            cycle_sequence=cycle_sequence,
        )
    updated = replace(
        state,
        last_observed_at=observed_at,
        last_cycle_sequence=cycle_sequence,
        recovery_count=recovery_count,
        last_reason="recovery_confirmation_pending",
    )
    return updated, _transition(
        state=updated,
        action="updated",
        reason="recovery_confirmation_pending",
        observed_at=observed_at,
        cycle_sequence=cycle_sequence,
    )


def _suppress_endpoint_noise(
    conditions: Sequence[IncidentCondition],
) -> tuple[tuple[IncidentCondition, ...], tuple[IncidentTransition, ...]]:
    has_target_wide = any(
        condition.kind == INCIDENT_KIND_TARGET_WIDE for condition in conditions
    )
    active: list[IncidentCondition] = []
    suppressed: list[IncidentTransition] = []
    for condition in conditions:
        if (
            has_target_wide
            and condition.kind == INCIDENT_KIND_ENDPOINT
            and condition.subject in FACADE_ENDPOINT_KEYS
            and condition.reason == "endpoint_retryable_transport_failure"
        ):
            suppressed.append(
                _suppressed_transition(
                    condition,
                    reason="suppressed_by_target_wide_outage",
                )
            )
        else:
            active.append(condition)
    return tuple(active), tuple(suppressed)


def _suppressed_transition(
    condition: IncidentCondition,
    *,
    reason: str,
) -> IncidentTransition:
    return IncidentTransition(
        incident_key=condition.incident_key,
        action="suppressed",
        kind=condition.kind,
        subject=condition.subject,
        severity=condition.severity,
        status="suppressed",
        reason=reason,
        observed_at=condition.observed_at,
        cycle_sequence=condition.cycle_sequence,
        failure_count=0,
        recovery_count=0,
        occurrence_count=0,
    )


def _transition(
    *,
    state: IncidentState,
    action: str,
    reason: str,
    observed_at: datetime,
    cycle_sequence: int | None,
) -> IncidentTransition:
    return IncidentTransition(
        incident_key=state.incident_key,
        action=action,
        kind=state.kind,
        subject=state.subject,
        severity=state.severity,
        status=state.status,
        reason=reason,
        observed_at=observed_at,
        cycle_sequence=cycle_sequence,
        failure_count=state.failure_count,
        recovery_count=state.recovery_count,
        occurrence_count=state.occurrence_count,
    )


def _blind_spot_condition(
    *,
    latest_cycle: CycleSnapshot | None,
    now: datetime,
    rules: IncidentRules,
) -> IncidentCondition | None:
    if latest_cycle is None:
        return IncidentCondition(
            kind=INCIDENT_KIND_BLIND_SPOT,
            subject="observer_freshness",
            severity="critical",
            reason="no_complete_cycle_observed",
            observed_at=now,
            cycle_sequence=None,
        )
    age_seconds = (now - latest_cycle.observed_at).total_seconds()
    if age_seconds <= rules.blind_spot_after_seconds:
        return None
    return IncidentCondition(
        kind=INCIDENT_KIND_BLIND_SPOT,
        subject="observer_freshness",
        severity="critical",
        reason="latest_cycle_stale",
        observed_at=now,
        cycle_sequence=latest_cycle.cycle_sequence,
    )


def _normalize_previous_states(
    previous_states: Mapping[str, IncidentState] | Iterable[IncidentState] | None,
) -> dict[str, IncidentState]:
    if previous_states is None:
        return {}
    states = (
        tuple(previous_states.values())
        if isinstance(previous_states, Mapping)
        else tuple(previous_states)
    )
    resolved: dict[str, IncidentState] = {}
    for state in states:
        if state.incident_key in resolved:
            raise ValueError("duplicate incident state")
        resolved[state.incident_key] = state
    return resolved


def _require_chronological_cycles(cycles: Sequence[CycleSnapshot]) -> None:
    previous: CycleSnapshot | None = None
    for cycle in cycles:
        if previous is not None:
            if cycle.observed_at < previous.observed_at:
                raise ValueError("cycle snapshots must be chronological")
            if cycle.cycle_sequence < previous.cycle_sequence:
                raise ValueError("cycle sequences must not regress")
        previous = cycle


def _is_endpoint_problem(fact: EndpointObservationFact) -> bool:
    if fact.transport_status == "success":
        return fact.payload_status in PAYLOAD_PROBLEM_STATUSES
    if fact.endpoint_key == "external_web":
        return True
    return fact.transport_status in RETRYABLE_TRANSPORT_FAILURES


def _endpoint_reason(fact: EndpointObservationFact) -> str:
    if fact.transport_status != "success":
        if fact.transport_status in RETRYABLE_TRANSPORT_FAILURES:
            return "endpoint_retryable_transport_failure"
        return f"endpoint_transport_failure:{fact.transport_status}"
    return f"endpoint_payload_status:{fact.payload_status}"


def _endpoint_severity(fact: EndpointObservationFact) -> str:
    if fact.endpoint_key in {"external_web", "live"}:
        return "critical"
    if fact.payload_status == "error":
        return "critical"
    return "warning"


def _open_threshold(kind: str, rules: IncidentRules) -> int:
    if kind == INCIDENT_KIND_ENDPOINT:
        return rules.endpoint_open_cycles
    if kind == INCIDENT_KIND_TARGET_WIDE:
        return rules.target_wide_open_cycles
    if kind == INCIDENT_KIND_OBSERVER:
        return rules.observer_open_cycles
    if kind == INCIDENT_KIND_BLIND_SPOT:
        return rules.blind_spot_open_cycles
    raise ValueError("incident kind is invalid")


def _recovery_threshold(kind: str, rules: IncidentRules) -> int:
    if kind == INCIDENT_KIND_ENDPOINT:
        return rules.endpoint_recovery_cycles
    if kind == INCIDENT_KIND_TARGET_WIDE:
        return rules.target_wide_recovery_cycles
    if kind == INCIDENT_KIND_OBSERVER:
        return rules.observer_recovery_cycles
    if kind == INCIDENT_KIND_BLIND_SPOT:
        return rules.blind_spot_recovery_cycles
    raise ValueError("incident kind is invalid")


def _inside_recurrence_cooldown(
    *,
    state: IncidentState,
    condition: IncidentCondition,
    rules: IncidentRules,
) -> bool:
    if rules.recurrence_cooldown_cycles == 0:
        return False
    if (
        state.recovered_cycle_sequence is None
        or condition.cycle_sequence is None
    ):
        return False
    return (
        condition.cycle_sequence - state.recovered_cycle_sequence
        <= rules.recurrence_cooldown_cycles
    )


def _max_severity(left: str, right: str) -> str:
    return left if SEVERITY_RANK[left] >= SEVERITY_RANK[right] else right


def _payload_status(payload: Mapping[str, object]) -> str | None:
    value = payload.get("status")
    return value if isinstance(value, str) else None


def _parse_datetime(value: str, *, context: str) -> datetime:
    try:
        resolved = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{context} must be an ISO datetime") from exc
    _require_aware_datetime(resolved, context=context)
    return resolved.astimezone(timezone.utc)


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{context} must include a timezone")


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


__all__ = [
    "DEFAULT_INCIDENT_RULES",
    "INCIDENT_KIND_BLIND_SPOT",
    "INCIDENT_KIND_ENDPOINT",
    "INCIDENT_KIND_OBSERVER",
    "INCIDENT_KIND_TARGET_WIDE",
    "INCIDENT_RULE_VERSION",
    "CycleSnapshot",
    "EndpointObservationFact",
    "IncidentCondition",
    "IncidentEvaluation",
    "IncidentRules",
    "IncidentState",
    "IncidentTransition",
    "classify_cycle_conditions",
    "evaluate_incident_lifecycle",
]
