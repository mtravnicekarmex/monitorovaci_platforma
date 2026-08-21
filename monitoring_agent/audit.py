from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .client import (
    CONTRACT_VERSION,
    CONTRACT_ENDPOINT_SET_VERSIONS,
    ENDPOINT_SETS,
)
from .incident_store import IncidentStoreError
from .runtime_shadow import (
    build_incident_store,
    summarize_shadow_incident_snapshot,
)
from .settings import RuntimeSettings
from .store import LIFECYCLE_CONTRACT_VERSION, LIFECYCLE_EVENT_REASONS


AUDIT_CONTRACT_VERSION = 8
TIMING_TOLERANCE_SECONDS = 2.0
TRANSPORT_STATUSES = {
    "connection_error",
    "http_error",
    "schema_error",
    "success",
    "tls_error",
    "timeout",
}
RETRYABLE_TRANSPORT_STATUSES = {"connection_error", "timeout"}
NON_RETRYABLE_FAILURE_STATUSES = {"http_error", "schema_error", "tls_error"}
OBSERVATION_KEYS_V2 = {
    "observation_id",
    "observer_instance_id",
    "run_id",
    "cycle_id",
    "cycle_sequence",
    "endpoint_key",
    "poll_started_at",
    "poll_finished_at",
    "http_status",
    "transport_status",
    "attempt_count",
    "contract_version",
    "source_checked_at",
    "payload",
}
OBSERVATION_KEYS_V3 = OBSERVATION_KEYS_V2 | {"endpoint_set_version"}
OBSERVATION_KEYS_V4 = OBSERVATION_KEYS_V3 | {"clock_skew_seconds"}
HEARTBEAT_KEYS = {
    "observer_instance_id",
    "run_id",
    "recorded_at",
    "process_id",
    "status",
    "cycle_id",
    "cycle_started_at",
    "cycle_finished_at",
    "observation_count",
    "transport_failure_count",
}
LIFECYCLE_KEYS = {
    "lifecycle_contract_version",
    "event_id",
    "observer_instance_id",
    "run_id",
    "process_id",
    "event",
    "reason",
    "recorded_at",
}


class StateAuditError(ValueError):
    """Agent-owned state could not be audited without ambiguity."""


@dataclass(frozen=True)
class _AuditObservation:
    observer_instance_id: str
    run_id: str
    cycle_id: str
    cycle_sequence: int
    contract_version: int
    endpoint_set_version: int
    endpoint_key: str
    poll_started_at: datetime
    poll_finished_at: datetime
    transport_status: str
    attempt_count: int


@dataclass(frozen=True)
class _CycleSummary:
    run_id: str
    cycle_id: str
    cycle_sequence: int
    endpoint_set_version: int
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    transport_failure_count: int
    self_health: str
    outcome: str


@dataclass(frozen=True)
class _IntervalDiagnostic:
    ending_cycle_index: int
    interval_seconds: float
    previous_cycle_duration_seconds: float
    previous_cycle_outcome: str
    expected_minimum_seconds: float
    allowed_maximum_seconds: float
    excess_beyond_allowed_seconds: float
    classification: str


@dataclass(frozen=True)
class _CrossRunIntervalDiagnostic:
    ending_cycle_index: int
    interval_seconds: float
    previous_cycle_duration_seconds: float
    previous_cycle_outcome: str
    classification: str


@dataclass(frozen=True)
class _HeartbeatSummary:
    observer_instance_id: str
    run_id: str
    cycle_id: str
    status: str
    cycle_started_at: datetime
    cycle_finished_at: datetime | None
    observation_count: int
    transport_failure_count: int
    process_id_present: bool


@dataclass(frozen=True)
class _LifecycleRecord:
    event_id: str
    observer_instance_id: str
    run_id: str
    process_id: int
    event: str
    reason: str
    recorded_at: datetime


def build_state_audit(settings: RuntimeSettings) -> dict[str, object]:
    observations_path = settings.state_dir / "observations.jsonl"
    heartbeat_path = settings.state_dir / "observer_heartbeat.json"
    lifecycle_path = settings.state_dir / "observer_lifecycle.jsonl"
    incident_state_path = settings.state_dir / "incident_state.json"
    if not observations_path.is_file():
        raise StateAuditError("observations file is unavailable")

    transport_status_counts: Counter[str] = Counter()
    attempt_count_counts: Counter[int] = Counter()
    observation_counts_by_run: Counter[str] = Counter()
    attempt_over_limit_counts_by_run: Counter[str] = Counter()
    retryable_not_exhausted_counts_by_run: Counter[str] = Counter()
    non_retryable_retried_counts_by_run: Counter[str] = Counter()
    success_after_retry_counts_by_run: Counter[str] = Counter()
    contract_version_counts: Counter[int] = Counter()
    endpoint_set_version_counts: Counter[int] = Counter()
    self_health_counts: Counter[str] = Counter()
    cycle_outcome_counts: Counter[str] = Counter()
    transition_counts: Counter[str] = Counter()
    instance_ids: set[str] = set()
    observation_run_ids: set[str] = set()

    total_observation_count = 0
    attempt_over_limit_count = 0
    retryable_not_exhausted_count = 0
    non_retryable_retried_count = 0
    success_after_retry_count = 0
    endpoint_sequence_mismatch_count = 0
    cycle_sequence_mismatch_count = 0
    incomplete_cycle_count = 0
    incomplete_observation_count = 0
    process_run_transition_count = 0
    process_run_reentry_count = 0
    mixed_transport_status_cycle_count = 0
    overlap_count = 0
    early_start_count = 0
    late_beyond_jitter_count = 0
    interval_count = 0
    interval_total = 0.0
    interval_min: float | None = None
    interval_max: float | None = None
    cross_run_interval_count = 0
    cross_run_interval_total = 0.0
    cross_run_interval_min: float | None = None
    cross_run_interval_max: float | None = None
    cross_run_overlap_count = 0
    cycle_duration_total = 0.0
    cycle_duration_min: float | None = None
    cycle_duration_max: float | None = None
    cycle_duration_beyond_budget_count = 0
    longest_cycle_index: int | None = None
    longest_cycle: _CycleSummary | None = None
    longest_cycle_budget: float | None = None
    longest_interval: _IntervalDiagnostic | None = None
    largest_late_interval: _IntervalDiagnostic | None = None
    longest_cross_run_interval: _CrossRunIntervalDiagnostic | None = None
    first_degraded_cycle_index: int | None = None
    first_recovery_cycle_index: int | None = None
    complete_cycle_count = 0
    max_attempt_count = 0
    pending_cycle: list[_AuditObservation] = []
    last_cycle_sequence_by_run: dict[str, int] = {}
    completed_run_ids: set[str] = set()
    previous_cycle: _CycleSummary | None = None
    last_cycle: _CycleSummary | None = None
    configured_timeout_cycle_budget = _configured_timeout_cycle_budget(settings)

    try:
        handle = observations_path.open("r", encoding="utf-8")
    except OSError as exc:
        raise StateAuditError("observations file could not be read") from exc

    with handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise StateAuditError(
                    f"observation line {line_number} is unexpectedly empty"
                )
            observation = _parse_observation(raw_line, line_number=line_number)
            total_observation_count += 1
            transport_status_counts[observation.transport_status] += 1
            attempt_count_counts[observation.attempt_count] += 1
            contract_version_counts[observation.contract_version] += 1
            endpoint_set_version_counts[observation.endpoint_set_version] += 1
            instance_ids.add(observation.observer_instance_id)
            observation_run_ids.add(observation.run_id)
            observation_counts_by_run[observation.run_id] += 1
            max_attempt_count = max(max_attempt_count, observation.attempt_count)

            if observation.attempt_count > settings.max_attempts:
                attempt_over_limit_count += 1
                attempt_over_limit_counts_by_run[observation.run_id] += 1
            if (
                observation.transport_status in RETRYABLE_TRANSPORT_STATUSES
                and observation.attempt_count != settings.max_attempts
            ):
                retryable_not_exhausted_count += 1
                retryable_not_exhausted_counts_by_run[observation.run_id] += 1
            if (
                observation.transport_status in NON_RETRYABLE_FAILURE_STATUSES
                and observation.attempt_count != 1
            ):
                non_retryable_retried_count += 1
                non_retryable_retried_counts_by_run[observation.run_id] += 1
            if (
                observation.transport_status == "success"
                and observation.attempt_count > 1
            ):
                success_after_retry_count += 1
                success_after_retry_counts_by_run[observation.run_id] += 1

            if pending_cycle and (
                observation.run_id != pending_cycle[0].run_id
                or observation.cycle_id != pending_cycle[0].cycle_id
            ):
                incomplete_cycle_count += 1
                incomplete_observation_count += len(pending_cycle)
                pending_cycle = []

            if (
                pending_cycle
                and observation.endpoint_set_version
                != pending_cycle[0].endpoint_set_version
            ):
                raise StateAuditError(
                    f"observation line {line_number} changes endpoint set within a cycle"
                )

            if not pending_cycle:
                previous_sequence = last_cycle_sequence_by_run.get(
                    observation.run_id
                )
                expected_sequence = (
                    1 if previous_sequence is None else previous_sequence + 1
                )
                if observation.cycle_sequence != expected_sequence:
                    cycle_sequence_mismatch_count += 1
                last_cycle_sequence_by_run[observation.run_id] = (
                    observation.cycle_sequence
                )

            pending_cycle.append(observation)
            expected_endpoint_keys = ENDPOINT_SETS[
                pending_cycle[0].endpoint_set_version
            ]
            if len(pending_cycle) < len(expected_endpoint_keys):
                continue

            complete_cycle_count += 1
            actual_endpoint_keys = tuple(item.endpoint_key for item in pending_cycle)
            if actual_endpoint_keys != expected_endpoint_keys:
                endpoint_sequence_mismatch_count += 1
            if len({item.cycle_sequence for item in pending_cycle}) != 1:
                cycle_sequence_mismatch_count += 1

            cycle = _summarize_cycle(pending_cycle)
            cycle_timeout_budget = _configured_timeout_cycle_budget(
                settings,
                endpoint_count=len(expected_endpoint_keys),
            )
            cycle_duration_total += cycle.duration_seconds
            cycle_duration_min = (
                cycle.duration_seconds
                if cycle_duration_min is None
                else min(cycle_duration_min, cycle.duration_seconds)
            )
            if cycle_duration_max is None or cycle.duration_seconds > cycle_duration_max:
                cycle_duration_max = cycle.duration_seconds
                longest_cycle_index = complete_cycle_count
                longest_cycle = cycle
                longest_cycle_budget = cycle_timeout_budget
            if (
                cycle.duration_seconds - TIMING_TOLERANCE_SECONDS
                > cycle_timeout_budget
            ):
                cycle_duration_beyond_budget_count += 1
            self_health_counts[cycle.self_health] += 1
            cycle_outcome_counts[cycle.outcome] += 1
            if len({item.transport_status for item in pending_cycle}) > 1:
                mixed_transport_status_cycle_count += 1

            if first_degraded_cycle_index is None and cycle.self_health == "degraded":
                first_degraded_cycle_index = complete_cycle_count

            if previous_cycle is not None:
                transition = f"{previous_cycle.self_health}_to_{cycle.self_health}"
                transition_counts[transition] += 1
                if (
                    first_recovery_cycle_index is None
                    and previous_cycle.self_health == "degraded"
                    and cycle.self_health == "healthy"
                ):
                    first_recovery_cycle_index = complete_cycle_count

                interval = (
                    cycle.started_at - previous_cycle.started_at
                ).total_seconds()
                if cycle.run_id != previous_cycle.run_id:
                    process_run_transition_count += 1
                    if cycle.run_id in completed_run_ids:
                        process_run_reentry_count += 1
                    cross_run_interval_count += 1
                    cross_run_interval_total += interval
                    cross_run_interval_min = (
                        interval
                        if cross_run_interval_min is None
                        else min(cross_run_interval_min, interval)
                    )
                    cross_run_interval_max = (
                        interval
                        if cross_run_interval_max is None
                        else max(cross_run_interval_max, interval)
                    )
                    if cycle.started_at < previous_cycle.finished_at:
                        cross_run_overlap_count += 1
                    cross_run_diagnostic = _build_cross_run_interval_diagnostic(
                        ending_cycle_index=complete_cycle_count,
                        interval_seconds=interval,
                        previous_cycle=previous_cycle,
                    )
                    if (
                        longest_cross_run_interval is None
                        or interval
                        > longest_cross_run_interval.interval_seconds
                    ):
                        longest_cross_run_interval = cross_run_diagnostic
                else:
                    interval_count += 1
                    interval_total += interval
                    interval_min = (
                        interval
                        if interval_min is None
                        else min(interval_min, interval)
                    )
                    interval_max = (
                        interval
                        if interval_max is None
                        else max(interval_max, interval)
                    )
                    if cycle.started_at < previous_cycle.finished_at:
                        overlap_count += 1
                    expected_minimum = max(
                        settings.poll_interval_seconds,
                        previous_cycle.duration_seconds,
                    )
                    interval_diagnostic = _build_interval_diagnostic(
                        ending_cycle_index=complete_cycle_count,
                        interval_seconds=interval,
                        previous_cycle=previous_cycle,
                        settings=settings,
                    )
                    if (
                        longest_interval is None
                        or interval > longest_interval.interval_seconds
                    ):
                        longest_interval = interval_diagnostic
                    if interval + TIMING_TOLERANCE_SECONDS < expected_minimum:
                        early_start_count += 1
                    if (
                        interval - TIMING_TOLERANCE_SECONDS
                        > expected_minimum + settings.poll_jitter_seconds
                    ):
                        late_beyond_jitter_count += 1
                        if (
                            largest_late_interval is None
                            or interval_diagnostic.excess_beyond_allowed_seconds
                            > largest_late_interval.excess_beyond_allowed_seconds
                        ):
                            largest_late_interval = interval_diagnostic

            previous_cycle = cycle
            completed_run_ids.add(cycle.run_id)
            last_cycle = cycle
            pending_cycle = []

    trailing_observation_count = len(pending_cycle)
    heartbeat = _read_heartbeat(heartbeat_path)
    current_run_observation_count = observation_counts_by_run[heartbeat.run_id]
    current_run_attempt_over_limit_count = attempt_over_limit_counts_by_run[
        heartbeat.run_id
    ]
    current_run_retryable_not_exhausted_count = (
        retryable_not_exhausted_counts_by_run[heartbeat.run_id]
    )
    current_run_non_retryable_retried_count = (
        non_retryable_retried_counts_by_run[heartbeat.run_id]
    )
    current_run_success_after_retry_count = success_after_retry_counts_by_run[
        heartbeat.run_id
    ]
    in_progress_cycle_count = 0
    in_progress_observation_count = 0
    trailing_cycle_classification: str | None = None
    if pending_cycle:
        if (
            heartbeat.status == "polling"
            and heartbeat.run_id == pending_cycle[0].run_id
            and heartbeat.cycle_id == pending_cycle[0].cycle_id
        ):
            in_progress_cycle_count = 1
            in_progress_observation_count = len(pending_cycle)
            trailing_cycle_classification = "current_polling_cycle"
        else:
            incomplete_cycle_count += 1
            incomplete_observation_count += len(pending_cycle)
            trailing_cycle_classification = "incomplete_or_snapshot_race"
    lifecycle_records = _read_lifecycle(lifecycle_path)
    lifecycle_audit = _summarize_lifecycle(
        lifecycle_records=lifecycle_records,
        observation_run_ids=observation_run_ids,
        observation_instance_ids=instance_ids,
        current_run_id=heartbeat.run_id,
    )
    shadow_incident_audit = _summarize_shadow_incidents(
        settings,
        incident_state_present=incident_state_path.is_file(),
    )
    heartbeat_instance_matches = (
        heartbeat.observer_instance_id in instance_ids if instance_ids else None
    )
    heartbeat_matches_last_cycle: bool | None = None
    if heartbeat.status != "polling" and last_cycle is not None:
        heartbeat_matches_last_cycle = (
            heartbeat.run_id == last_cycle.run_id
            and heartbeat.cycle_id == last_cycle.cycle_id
            and
            heartbeat.cycle_started_at <= last_cycle.started_at
            and heartbeat.cycle_finished_at is not None
            and heartbeat.cycle_finished_at >= last_cycle.finished_at
            and heartbeat.observation_count
            == len(ENDPOINT_SETS[last_cycle.endpoint_set_version])
            and heartbeat.transport_failure_count
            == last_cycle.transport_failure_count
            and heartbeat.status == last_cycle.self_health
        )

    return {
        "audit_contract_version": AUDIT_CONTRACT_VERSION,
        "event": "agent_state_audit",
        "configuration": {
            "endpoint_count": len(settings.endpoint_keys),
            "endpoint_set_version": settings.endpoint_set_version,
            "max_attempts": settings.max_attempts,
            "request_timeout_seconds": settings.timeout_seconds,
            "retry_backoff_seconds": settings.retry_backoff_seconds,
            "poll_interval_seconds": settings.poll_interval_seconds,
            "poll_jitter_seconds": settings.poll_jitter_seconds,
            "configured_timeout_cycle_budget_seconds": _rounded(
                configured_timeout_cycle_budget
            ),
        },
        "observations": {
            "total_count": total_observation_count,
            "complete_cycle_count": complete_cycle_count,
            "trailing_observation_count": trailing_observation_count,
            "incomplete_cycle_count": incomplete_cycle_count,
            "incomplete_observation_count": incomplete_observation_count,
            "in_progress_cycle_count": in_progress_cycle_count,
            "in_progress_observation_count": in_progress_observation_count,
            "trailing_cycle_classification": trailing_cycle_classification,
            "observer_instance_count": len(instance_ids),
            "process_run_count": len(observation_run_ids),
            "transport_status_counts": dict(sorted(transport_status_counts.items())),
            "attempt_count_counts": {
                str(key): value for key, value in sorted(attempt_count_counts.items())
            },
            "contract_version_counts": {
                str(key): value for key, value in sorted(contract_version_counts.items())
            },
            "endpoint_set_version_counts": {
                str(key): value
                for key, value in sorted(endpoint_set_version_counts.items())
            },
            "max_attempt_count": max_attempt_count,
            "attempt_over_limit_count": attempt_over_limit_count,
            "retryable_not_exhausted_count": retryable_not_exhausted_count,
            "non_retryable_retried_count": non_retryable_retried_count,
            "success_after_retry_count": success_after_retry_count,
            "attempt_bounds_valid": attempt_over_limit_count == 0,
            "retry_contract_valid": (
                retryable_not_exhausted_count == 0
                and non_retryable_retried_count == 0
            ),
            "current_run": {
                "observation_count": current_run_observation_count,
                "attempt_over_limit_count": (
                    current_run_attempt_over_limit_count
                ),
                "retryable_not_exhausted_count": (
                    current_run_retryable_not_exhausted_count
                ),
                "non_retryable_retried_count": (
                    current_run_non_retryable_retried_count
                ),
                "success_after_retry_count": (
                    current_run_success_after_retry_count
                ),
                "attempt_bounds_valid": (
                    current_run_attempt_over_limit_count == 0
                ),
                "retry_contract_valid": (
                    current_run_retryable_not_exhausted_count == 0
                    and current_run_non_retryable_retried_count == 0
                ),
            },
        },
        "cycles": {
            "endpoint_sequence_mismatch_count": endpoint_sequence_mismatch_count,
            "endpoint_sequence_valid": endpoint_sequence_mismatch_count == 0,
            "cycle_sequence_mismatch_count": cycle_sequence_mismatch_count,
            "cycle_sequence_valid": cycle_sequence_mismatch_count == 0,
            "process_run_transition_count": process_run_transition_count,
            "process_run_reentry_count": process_run_reentry_count,
            "single_writer_observation_history_valid": (
                process_run_reentry_count == 0
            ),
            "self_health_counts": dict(sorted(self_health_counts.items())),
            "outcome_counts": dict(sorted(cycle_outcome_counts.items())),
            "mixed_transport_status_count": mixed_transport_status_cycle_count,
            "first_degraded_cycle_index": first_degraded_cycle_index,
            "first_recovery_cycle_index": first_recovery_cycle_index,
            "transition_counts": dict(sorted(transition_counts.items())),
        },
        "timing": {
            "interval_count": interval_count,
            "interval_min_seconds": _rounded(interval_min),
            "interval_max_seconds": _rounded(interval_max),
            "interval_average_seconds": _rounded(
                interval_total / interval_count if interval_count else None
            ),
            "overlap_count": overlap_count,
            "early_start_count": early_start_count,
            "late_beyond_jitter_count": late_beyond_jitter_count,
            "cross_run_interval_count": cross_run_interval_count,
            "cross_run_interval_min_seconds": _rounded(cross_run_interval_min),
            "cross_run_interval_max_seconds": _rounded(cross_run_interval_max),
            "cross_run_interval_average_seconds": _rounded(
                cross_run_interval_total / cross_run_interval_count
                if cross_run_interval_count
                else None
            ),
            "cross_run_overlap_count": cross_run_overlap_count,
            "longest_cross_run_interval": _serialize_cross_run_interval(
                longest_cross_run_interval
            ),
            "tolerance_seconds": TIMING_TOLERANCE_SECONDS,
            "cycle_duration_count": complete_cycle_count,
            "cycle_duration_min_seconds": _rounded(cycle_duration_min),
            "cycle_duration_max_seconds": _rounded(cycle_duration_max),
            "cycle_duration_average_seconds": _rounded(
                cycle_duration_total / complete_cycle_count
                if complete_cycle_count
                else None
            ),
            "cycle_duration_beyond_configured_budget_count": (
                cycle_duration_beyond_budget_count
            ),
            "longest_cycle": _serialize_longest_cycle(
                cycle_index=longest_cycle_index,
                cycle=longest_cycle,
                configured_timeout_cycle_budget=longest_cycle_budget,
            ),
            "longest_interval": _serialize_interval(longest_interval),
            "largest_late_interval": _serialize_interval(largest_late_interval),
        },
        "latest_heartbeat": {
            "status": heartbeat.status,
            "observation_count": heartbeat.observation_count,
            "transport_failure_count": heartbeat.transport_failure_count,
            "process_id_present": heartbeat.process_id_present,
            "observer_instance_matches_observations": heartbeat_instance_matches,
            "run_matches_last_complete_cycle": (
                heartbeat.run_id == last_cycle.run_id if last_cycle else None
            ),
            "matches_last_complete_cycle": heartbeat_matches_last_cycle,
        },
        "lifecycle": lifecycle_audit,
        "shadow_incidents": shadow_incident_audit,
        "evidence_gaps": [
            "heartbeat_transition_history_not_persisted",
        ],
    }


def _summarize_shadow_incidents(
    settings: RuntimeSettings,
    *,
    incident_state_present: bool,
) -> dict[str, object]:
    try:
        snapshot = build_incident_store(settings).load()
    except IncidentStoreError as exc:
        raise StateAuditError("incident state file could not be audited") from exc
    summary = summarize_shadow_incident_snapshot(
        snapshot,
        incident_rule_version=1,
        delivery_enabled=settings.delivery_automation_enabled,
    ).to_dict()
    summary.pop("transition_count")
    return {
        **summary,
        "history_valid": True,
        "present": incident_state_present,
    }


def _configured_timeout_cycle_budget(
    settings: RuntimeSettings,
    *,
    endpoint_count: int | None = None,
) -> float:
    retry_backoff_budget = sum(
        settings.retry_backoff_seconds * (2**attempt_index)
        for attempt_index in range(settings.max_attempts - 1)
    )
    per_endpoint_budget = (
        settings.timeout_seconds * settings.max_attempts + retry_backoff_budget
    )
    return per_endpoint_budget * (
        len(settings.endpoint_keys) if endpoint_count is None else endpoint_count
    )


def _build_interval_diagnostic(
    *,
    ending_cycle_index: int,
    interval_seconds: float,
    previous_cycle: _CycleSummary,
    settings: RuntimeSettings,
) -> _IntervalDiagnostic:
    expected_minimum = max(
        settings.poll_interval_seconds,
        previous_cycle.duration_seconds,
    )
    allowed_maximum = (
        expected_minimum
        + settings.poll_jitter_seconds
        + TIMING_TOLERANCE_SECONDS
    )
    if interval_seconds > allowed_maximum:
        classification = "unexplained_between_cycles_or_clock_discontinuity"
    elif previous_cycle.duration_seconds > settings.poll_interval_seconds:
        classification = "long_running_previous_cycle"
    else:
        classification = "scheduled_interval"
    return _IntervalDiagnostic(
        ending_cycle_index=ending_cycle_index,
        interval_seconds=interval_seconds,
        previous_cycle_duration_seconds=previous_cycle.duration_seconds,
        previous_cycle_outcome=previous_cycle.outcome,
        expected_minimum_seconds=expected_minimum,
        allowed_maximum_seconds=allowed_maximum,
        excess_beyond_allowed_seconds=max(0.0, interval_seconds - allowed_maximum),
        classification=classification,
    )


def _build_cross_run_interval_diagnostic(
    *,
    ending_cycle_index: int,
    interval_seconds: float,
    previous_cycle: _CycleSummary,
) -> _CrossRunIntervalDiagnostic:
    return _CrossRunIntervalDiagnostic(
        ending_cycle_index=ending_cycle_index,
        interval_seconds=interval_seconds,
        previous_cycle_duration_seconds=previous_cycle.duration_seconds,
        previous_cycle_outcome=previous_cycle.outcome,
        classification="process_run_transition",
    )


def _serialize_longest_cycle(
    *,
    cycle_index: int | None,
    cycle: _CycleSummary | None,
    configured_timeout_cycle_budget: float | None,
) -> dict[str, object] | None:
    if (
        cycle_index is None
        or cycle is None
        or configured_timeout_cycle_budget is None
    ):
        return None
    return {
        "cycle_index": cycle_index,
        "duration_seconds": _rounded(cycle.duration_seconds),
        "outcome": cycle.outcome,
        "endpoint_set_version": cycle.endpoint_set_version,
        "configured_timeout_budget_seconds": _rounded(
            configured_timeout_cycle_budget
        ),
        "excess_beyond_configured_budget_seconds": _rounded(
            max(0.0, cycle.duration_seconds - configured_timeout_cycle_budget)
        ),
    }


def _serialize_cross_run_interval(
    diagnostic: _CrossRunIntervalDiagnostic | None,
) -> dict[str, object] | None:
    if diagnostic is None:
        return None
    return {
        "ending_cycle_index": diagnostic.ending_cycle_index,
        "interval_seconds": _rounded(diagnostic.interval_seconds),
        "previous_cycle_duration_seconds": _rounded(
            diagnostic.previous_cycle_duration_seconds
        ),
        "previous_cycle_outcome": diagnostic.previous_cycle_outcome,
        "classification": diagnostic.classification,
    }


def _serialize_interval(
    diagnostic: _IntervalDiagnostic | None,
) -> dict[str, object] | None:
    if diagnostic is None:
        return None
    return {
        "ending_cycle_index": diagnostic.ending_cycle_index,
        "interval_seconds": _rounded(diagnostic.interval_seconds),
        "previous_cycle_duration_seconds": _rounded(
            diagnostic.previous_cycle_duration_seconds
        ),
        "previous_cycle_outcome": diagnostic.previous_cycle_outcome,
        "expected_minimum_seconds": _rounded(
            diagnostic.expected_minimum_seconds
        ),
        "allowed_maximum_seconds": _rounded(diagnostic.allowed_maximum_seconds),
        "excess_beyond_allowed_seconds": _rounded(
            diagnostic.excess_beyond_allowed_seconds
        ),
        "classification": diagnostic.classification,
    }


def _parse_observation(raw_line: str, *, line_number: int) -> _AuditObservation:
    try:
        value = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        raise StateAuditError(
            f"observation line {line_number} contains invalid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise StateAuditError(f"observation line {line_number} has an invalid schema")
    contract_version = value.get("contract_version")
    if (
        isinstance(contract_version, bool)
        or not isinstance(contract_version, int)
        or contract_version not in CONTRACT_ENDPOINT_SET_VERSIONS
    ):
        raise StateAuditError(
            f"observation line {line_number} has an unsupported contract"
        )
    expected_keys = {
        2: OBSERVATION_KEYS_V2,
        3: OBSERVATION_KEYS_V3,
        4: OBSERVATION_KEYS_V4,
    }[contract_version]
    if set(value) != expected_keys:
        raise StateAuditError(f"observation line {line_number} has an invalid schema")
    endpoint_set_version = CONTRACT_ENDPOINT_SET_VERSIONS[contract_version]
    if contract_version != 2 and value["endpoint_set_version"] != endpoint_set_version:
        raise StateAuditError(
            f"observation line {line_number} mismatches its contract endpoint set"
        )
    if (
        isinstance(endpoint_set_version, bool)
        or not isinstance(endpoint_set_version, int)
        or endpoint_set_version not in ENDPOINT_SETS
    ):
        raise StateAuditError(
            f"observation line {line_number} has an unsupported endpoint set"
        )
    observation_id = value["observation_id"]
    observer_instance_id = value["observer_instance_id"]
    run_id = value["run_id"]
    cycle_id = value["cycle_id"]
    cycle_sequence = value["cycle_sequence"]
    endpoint_key = value["endpoint_key"]
    transport_status = value["transport_status"]
    attempt_count = value["attempt_count"]
    if not isinstance(observation_id, str) or not observation_id:
        raise StateAuditError(
            f"observation line {line_number} has an invalid observation id"
        )
    if not isinstance(observer_instance_id, str) or not observer_instance_id:
        raise StateAuditError(
            f"observation line {line_number} has an invalid observer instance"
        )
    if not isinstance(run_id, str) or not run_id:
        raise StateAuditError(
            f"observation line {line_number} has an invalid run id"
        )
    if not isinstance(cycle_id, str) or not cycle_id:
        raise StateAuditError(
            f"observation line {line_number} has an invalid cycle id"
        )
    if (
        isinstance(cycle_sequence, bool)
        or not isinstance(cycle_sequence, int)
        or cycle_sequence < 1
    ):
        raise StateAuditError(
            f"observation line {line_number} has an invalid cycle sequence"
        )
    if not isinstance(endpoint_key, str) or not endpoint_key:
        raise StateAuditError(
            f"observation line {line_number} has an invalid endpoint key"
        )
    if endpoint_key not in ENDPOINT_SETS[endpoint_set_version]:
        raise StateAuditError(
            f"observation line {line_number} has an endpoint outside its endpoint set"
        )
    if not isinstance(transport_status, str) or (
        transport_status not in TRANSPORT_STATUSES
    ):
        raise StateAuditError(
            f"observation line {line_number} has an invalid transport status"
        )
    if (
        isinstance(attempt_count, bool)
        or not isinstance(attempt_count, int)
        or attempt_count < 1
    ):
        raise StateAuditError(
            f"observation line {line_number} has an invalid attempt count"
        )
    http_status = value["http_status"]
    if http_status is not None and (
        isinstance(http_status, bool) or not isinstance(http_status, int)
    ):
        raise StateAuditError(
            f"observation line {line_number} has an invalid HTTP status"
        )
    source_checked_at = value["source_checked_at"]
    if source_checked_at is not None and not isinstance(source_checked_at, str):
        raise StateAuditError(
            f"observation line {line_number} has an invalid source timestamp"
        )
    if source_checked_at is not None:
        _parse_datetime(
            source_checked_at,
            context=f"observation line {line_number} source timestamp",
        )
    if contract_version == 4:
        clock_skew_seconds = value["clock_skew_seconds"]
        if clock_skew_seconds is not None and (
            isinstance(clock_skew_seconds, bool)
            or not isinstance(clock_skew_seconds, (int, float))
            or not 0 <= float(clock_skew_seconds) <= 86_400
        ):
            raise StateAuditError(
                f"observation line {line_number} has an invalid clock skew"
            )
    if not isinstance(value["payload"], dict):
        raise StateAuditError(f"observation line {line_number} has an invalid payload")

    started_at = _parse_datetime(
        value["poll_started_at"],
        context=f"observation line {line_number} start",
    )
    finished_at = _parse_datetime(
        value["poll_finished_at"],
        context=f"observation line {line_number} finish",
    )
    if finished_at < started_at:
        raise StateAuditError(
            f"observation line {line_number} finishes before it starts"
        )
    return _AuditObservation(
        observer_instance_id=observer_instance_id,
        run_id=run_id,
        cycle_id=cycle_id,
        cycle_sequence=cycle_sequence,
        contract_version=contract_version,
        endpoint_set_version=endpoint_set_version,
        endpoint_key=endpoint_key,
        poll_started_at=started_at,
        poll_finished_at=finished_at,
        transport_status=transport_status,
        attempt_count=attempt_count,
    )


def _summarize_cycle(observations: list[_AuditObservation]) -> _CycleSummary:
    started_at = observations[0].poll_started_at
    finished_at = max(item.poll_finished_at for item in observations)
    statuses = {item.transport_status for item in observations}
    transport_failure_count = sum(
        item.transport_status != "success" for item in observations
    )
    self_health = "healthy" if transport_failure_count == 0 else "degraded"
    if transport_failure_count == 0:
        outcome = "healthy"
    elif statuses <= RETRYABLE_TRANSPORT_STATUSES:
        outcome = "unreachable"
    elif "success" in statuses:
        outcome = "partial_failure"
    else:
        outcome = "failed"
    return _CycleSummary(
        run_id=observations[0].run_id,
        cycle_id=observations[0].cycle_id,
        cycle_sequence=observations[0].cycle_sequence,
        endpoint_set_version=observations[0].endpoint_set_version,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=(finished_at - started_at).total_seconds(),
        transport_failure_count=transport_failure_count,
        self_health=self_health,
        outcome=outcome,
    )


def _read_heartbeat(path: Path) -> _HeartbeatSummary:
    try:
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StateAuditError("heartbeat file could not be read") from exc
    except json.JSONDecodeError as exc:
        raise StateAuditError("heartbeat file contains invalid JSON") from exc
    if not isinstance(value, dict) or set(value) != HEARTBEAT_KEYS:
        raise StateAuditError("heartbeat file has an invalid schema")
    status = value["status"]
    if not isinstance(status, str) or status not in {
        "polling",
        "healthy",
        "degraded",
    }:
        raise StateAuditError("heartbeat file has an invalid status")
    observer_instance_id = value["observer_instance_id"]
    run_id = value["run_id"]
    cycle_id = value["cycle_id"]
    process_id = value["process_id"]
    if not isinstance(observer_instance_id, str) or not observer_instance_id:
        raise StateAuditError("heartbeat file has an invalid observer instance")
    if not isinstance(run_id, str) or not run_id:
        raise StateAuditError("heartbeat file has an invalid run id")
    if not isinstance(cycle_id, str) or not cycle_id:
        raise StateAuditError("heartbeat file has an invalid cycle id")
    if isinstance(process_id, bool) or not isinstance(process_id, int) or process_id < 1:
        raise StateAuditError("heartbeat file has an invalid process id")
    observation_count = _non_negative_int(
        value["observation_count"], context="heartbeat observation count"
    )
    transport_failure_count = _non_negative_int(
        value["transport_failure_count"], context="heartbeat transport failure count"
    )
    _parse_datetime(value["recorded_at"], context="heartbeat recorded timestamp")
    cycle_started_at = _parse_datetime(
        value["cycle_started_at"], context="heartbeat cycle start"
    )
    cycle_finished_at = (
        None
        if value["cycle_finished_at"] is None
        else _parse_datetime(
            value["cycle_finished_at"], context="heartbeat cycle finish"
        )
    )
    if transport_failure_count > observation_count:
        raise StateAuditError("heartbeat failure count exceeds observation count")
    if status == "polling" and (
        cycle_finished_at is not None
        or observation_count != 0
        or transport_failure_count != 0
    ):
        raise StateAuditError("polling heartbeat has completed-cycle fields")
    if status != "polling" and cycle_finished_at is None:
        raise StateAuditError("completed heartbeat has no cycle finish")
    if cycle_finished_at is not None and cycle_finished_at < cycle_started_at:
        raise StateAuditError("heartbeat cycle finishes before it starts")
    return _HeartbeatSummary(
        observer_instance_id=observer_instance_id,
        run_id=run_id,
        cycle_id=cycle_id,
        status=status,
        cycle_started_at=cycle_started_at,
        cycle_finished_at=cycle_finished_at,
        observation_count=observation_count,
        transport_failure_count=transport_failure_count,
        process_id_present=True,
    )


def _read_lifecycle(path: Path) -> tuple[_LifecycleRecord, ...]:
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise StateAuditError("lifecycle file could not be read") from exc
    records: list[_LifecycleRecord] = []
    event_ids: set[str] = set()
    with handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise StateAuditError(
                    f"lifecycle line {line_number} is unexpectedly empty"
                )
            try:
                value: Any = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise StateAuditError(
                    f"lifecycle line {line_number} contains invalid JSON"
                ) from exc
            if not isinstance(value, dict) or set(value) != LIFECYCLE_KEYS:
                raise StateAuditError(
                    f"lifecycle line {line_number} has an invalid schema"
                )
            contract_version = value["lifecycle_contract_version"]
            if (
                isinstance(contract_version, bool)
                or not isinstance(contract_version, int)
                or contract_version != LIFECYCLE_CONTRACT_VERSION
            ):
                raise StateAuditError(
                    f"lifecycle line {line_number} has an unsupported contract"
                )
            event_id = value["event_id"]
            observer_instance_id = value["observer_instance_id"]
            run_id = value["run_id"]
            event = value["event"]
            reason = value["reason"]
            process_id = value["process_id"]
            if not isinstance(event_id, str) or not event_id:
                raise StateAuditError(
                    f"lifecycle line {line_number} has an invalid event id"
                )
            if event_id in event_ids:
                raise StateAuditError("lifecycle history has a duplicate event id")
            event_ids.add(event_id)
            if (
                not isinstance(observer_instance_id, str)
                or not observer_instance_id
            ):
                raise StateAuditError(
                    f"lifecycle line {line_number} has an invalid observer instance"
                )
            if not isinstance(run_id, str) or not run_id:
                raise StateAuditError(
                    f"lifecycle line {line_number} has an invalid run id"
                )
            if not isinstance(event, str) or event not in LIFECYCLE_EVENT_REASONS:
                raise StateAuditError(
                    f"lifecycle line {line_number} has an invalid event"
                )
            if (
                not isinstance(reason, str)
                or reason not in LIFECYCLE_EVENT_REASONS[event]
            ):
                raise StateAuditError(
                    f"lifecycle line {line_number} has an invalid reason"
                )
            if (
                isinstance(process_id, bool)
                or not isinstance(process_id, int)
                or process_id < 1
            ):
                raise StateAuditError(
                    f"lifecycle line {line_number} has an invalid process id"
                )
            records.append(
                _LifecycleRecord(
                    event_id=event_id,
                    observer_instance_id=observer_instance_id,
                    run_id=run_id,
                    process_id=process_id,
                    event=event,
                    reason=reason,
                    recorded_at=_parse_datetime(
                        value["recorded_at"],
                        context=f"lifecycle line {line_number} timestamp",
                    ),
                )
            )
    if not records:
        raise StateAuditError("lifecycle history is empty")
    return tuple(records)


def _summarize_lifecycle(
    *,
    lifecycle_records: tuple[_LifecycleRecord, ...],
    observation_run_ids: set[str],
    observation_instance_ids: set[str],
    current_run_id: str,
) -> dict[str, object]:
    started_runs: set[str] = set()
    open_runs: set[str] = set()
    lifecycle_run_ids: set[str] = set()
    lifecycle_instance_ids: set[str] = set()
    process_ids_by_run: dict[str, set[int]] = {}
    stop_reason_counts: Counter[str] = Counter()
    process_start_count = 0
    process_stop_count = 0
    duplicate_start_count = 0
    duplicate_stop_count = 0
    orphan_stop_count = 0
    clean_restart_count = 0
    start_while_prior_run_open_count = 0
    prior_open_runs_by_start: list[set[str]] = []
    last_started_run_id: str | None = None
    previous_recorded_at: datetime | None = None
    timestamp_regression_count = 0

    for record in lifecycle_records:
        if (
            previous_recorded_at is not None
            and record.recorded_at < previous_recorded_at
        ):
            timestamp_regression_count += 1
        previous_recorded_at = record.recorded_at
        lifecycle_run_ids.add(record.run_id)
        lifecycle_instance_ids.add(record.observer_instance_id)
        process_ids_by_run.setdefault(record.run_id, set()).add(record.process_id)
        if record.event == "process_started":
            process_start_count += 1
            if record.run_id in started_runs:
                duplicate_start_count += 1
                continue
            if last_started_run_id is not None:
                if open_runs:
                    start_while_prior_run_open_count += 1
                    prior_open_runs_by_start.append(set(open_runs))
                else:
                    clean_restart_count += 1
            started_runs.add(record.run_id)
            open_runs.add(record.run_id)
            last_started_run_id = record.run_id
            continue

        process_stop_count += 1
        stop_reason_counts[record.reason] += 1
        if record.run_id not in started_runs:
            orphan_stop_count += 1
        elif record.run_id not in open_runs:
            duplicate_stop_count += 1
        else:
            open_runs.remove(record.run_id)

    process_id_mismatch_run_count = sum(
        len(process_ids) != 1 for process_ids in process_ids_by_run.values()
    )
    observation_runs_without_start = observation_run_ids - started_runs
    lifecycle_runs_without_observations = started_runs - observation_run_ids
    abandoned_open_runs = open_runs - {current_run_id}
    concurrent_start_count = sum(
        bool(prior_open_runs - open_runs)
        for prior_open_runs in prior_open_runs_by_start
    )
    unclean_restart_count = sum(
        bool(prior_open_runs & open_runs)
        for prior_open_runs in prior_open_runs_by_start
    )
    current_run_has_start = current_run_id in started_runs
    current_run_is_unclosed = current_run_id in open_runs
    current_run_has_stop = (
        current_run_has_start and not current_run_is_unclosed
    )
    observer_instance_matches_observations = (
        lifecycle_instance_ids == observation_instance_ids
    )
    history_valid = (
        duplicate_start_count == 0
        and duplicate_stop_count == 0
        and orphan_stop_count == 0
        and process_id_mismatch_run_count == 0
        and timestamp_regression_count == 0
        and not observation_runs_without_start
        and current_run_has_start
        and observer_instance_matches_observations
    )
    return {
        "contract_version": LIFECYCLE_CONTRACT_VERSION,
        "event_count": len(lifecycle_records),
        "process_start_count": process_start_count,
        "process_stop_count": process_stop_count,
        "distinct_run_count": len(started_runs),
        "observation_run_count": len(observation_run_ids),
        "restart_detected": process_start_count > 1,
        "clean_restart_count": clean_restart_count,
        "start_while_prior_run_open_count": start_while_prior_run_open_count,
        "concurrent_start_count": concurrent_start_count,
        "unclean_restart_count": unclean_restart_count,
        "single_writer_history_valid": concurrent_start_count == 0,
        "unclosed_run_count": len(open_runs),
        "abandoned_unclosed_run_count": len(abandoned_open_runs),
        "duplicate_start_count": duplicate_start_count,
        "duplicate_stop_count": duplicate_stop_count,
        "orphan_stop_count": orphan_stop_count,
        "process_id_mismatch_run_count": process_id_mismatch_run_count,
        "timestamp_regression_count": timestamp_regression_count,
        "observation_runs_without_start_count": len(
            observation_runs_without_start
        ),
        "lifecycle_runs_without_observations_count": len(
            lifecycle_runs_without_observations
        ),
        "observer_instance_count": len(lifecycle_instance_ids),
        "observer_instance_matches_observations": (
            observer_instance_matches_observations
        ),
        "current_run_has_start": current_run_has_start,
        "current_run_has_stop": current_run_has_stop,
        "current_run_is_unclosed": current_run_is_unclosed,
        "stop_reason_counts": dict(sorted(stop_reason_counts.items())),
        "history_valid": history_valid,
    }


def _parse_datetime(value: object, *, context: str) -> datetime:
    if not isinstance(value, str):
        raise StateAuditError(f"{context} is invalid")
    try:
        resolved = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StateAuditError(f"{context} is invalid") from exc
    if resolved.tzinfo is None:
        raise StateAuditError(f"{context} must include a timezone")
    return resolved.astimezone(timezone.utc)


def _non_negative_int(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise StateAuditError(f"{context} is invalid")
    return value


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)
