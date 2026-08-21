from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from .client import Observation
from .incident_store import (
    OUTBOX_DEAD_LETTER,
    OUTBOX_IN_PROGRESS,
    OUTBOX_PENDING,
    OUTBOX_SENT,
    IncidentStateStore,
    IncidentStoreLimits,
    IncidentStoreSnapshot,
)
from .incidents import (
    INCIDENT_STATUS_ACTIVE,
    INCIDENT_STATUS_CANDIDATE,
    INCIDENT_STATUS_RESOLVED,
    CycleSnapshot,
    evaluate_incident_lifecycle,
)
from .settings import RuntimeSettings


SHADOW_RUNTIME_CONTRACT_VERSION = 1
SHADOW_RUNTIME_MODE = "shadow_only"


@dataclass(frozen=True)
class ShadowRuntimeSummary:
    incident_rule_version: int
    state_count: int
    active_state_count: int
    candidate_state_count: int
    resolved_state_count: int
    transition_count: int
    transition_record_count: int
    outbox_count: int
    outbox_pending_count: int
    outbox_in_progress_count: int
    outbox_sent_count: int
    outbox_dead_letter_count: int
    updated_at: datetime | None
    delivery_enabled: bool = False
    mode: str = SHADOW_RUNTIME_MODE
    contract_version: int = SHADOW_RUNTIME_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_enabled, bool):
            raise ValueError("shadow runtime delivery flag must be boolean")
        if self.mode != SHADOW_RUNTIME_MODE:
            raise ValueError("shadow runtime mode must be shadow_only")
        if self.contract_version != SHADOW_RUNTIME_CONTRACT_VERSION:
            raise ValueError("shadow runtime contract is unsupported")
        for name in (
            "incident_rule_version",
            "state_count",
            "active_state_count",
            "candidate_state_count",
            "resolved_state_count",
            "transition_count",
            "transition_record_count",
            "outbox_count",
            "outbox_pending_count",
            "outbox_in_progress_count",
            "outbox_sent_count",
            "outbox_dead_letter_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.updated_at is not None:
            _require_aware_datetime(self.updated_at, context="updated_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "active_state_count": self.active_state_count,
            "candidate_state_count": self.candidate_state_count,
            "contract_version": self.contract_version,
            "delivery_enabled": self.delivery_enabled,
            "incident_rule_version": self.incident_rule_version,
            "mode": self.mode,
            "outbox_count": self.outbox_count,
            "outbox_dead_letter_count": self.outbox_dead_letter_count,
            "outbox_in_progress_count": self.outbox_in_progress_count,
            "outbox_pending_count": self.outbox_pending_count,
            "outbox_sent_count": self.outbox_sent_count,
            "resolved_state_count": self.resolved_state_count,
            "state_count": self.state_count,
            "transition_count": self.transition_count,
            "transition_record_count": self.transition_record_count,
            "updated_at": _format_datetime(self.updated_at),
        }


def build_incident_store_limits(settings: RuntimeSettings) -> IncidentStoreLimits:
    return IncidentStoreLimits(
        max_incident_states=settings.max_incident_states,
        max_transition_records=settings.max_incident_transition_records,
        max_outbox_items=settings.max_outbox_items,
        max_delivery_attempts=settings.outbox_max_attempts,
        retry_backoff_seconds=settings.outbox_retry_backoff_seconds,
        claim_timeout_seconds=settings.outbox_claim_timeout_seconds,
    )


def build_incident_store(settings: RuntimeSettings) -> IncidentStateStore:
    return IncidentStateStore(
        settings.state_dir,
        limits=build_incident_store_limits(settings),
    )


def apply_shadow_incident_cycle(
    *,
    settings: RuntimeSettings,
    observations: Iterable[Observation],
    incident_store: IncidentStateStore | None = None,
    now: datetime | None = None,
) -> ShadowRuntimeSummary:
    recorded_at = datetime.now(timezone.utc) if now is None else now
    _require_aware_datetime(recorded_at, context="recorded_at")
    resolved_observations = tuple(observations)
    if not resolved_observations:
        raise ValueError("shadow incident cycle requires observations")
    store = incident_store or build_incident_store(settings)
    previous_snapshot = store.load()
    evaluation = evaluate_incident_lifecycle(
        [CycleSnapshot.from_observations(resolved_observations)],
        previous_states=previous_snapshot.states,
        now=recorded_at,
    )
    next_snapshot = store.apply_evaluation(evaluation, now=recorded_at)
    return summarize_shadow_incident_snapshot(
        next_snapshot,
        incident_rule_version=evaluation.rule_version,
        transition_count=len(evaluation.transitions),
        delivery_enabled=settings.delivery_automation_enabled,
    )


def summarize_shadow_incident_snapshot(
    snapshot: IncidentStoreSnapshot,
    *,
    incident_rule_version: int,
    transition_count: int = 0,
    delivery_enabled: bool = False,
) -> ShadowRuntimeSummary:
    state_status_counts = Counter(state.status for state in snapshot.states)
    outbox_status_counts = Counter(item.status for item in snapshot.outbox_items)
    return ShadowRuntimeSummary(
        incident_rule_version=incident_rule_version,
        state_count=len(snapshot.states),
        active_state_count=state_status_counts[INCIDENT_STATUS_ACTIVE],
        candidate_state_count=state_status_counts[INCIDENT_STATUS_CANDIDATE],
        resolved_state_count=state_status_counts[INCIDENT_STATUS_RESOLVED],
        transition_count=transition_count,
        transition_record_count=len(snapshot.transition_records),
        outbox_count=len(snapshot.outbox_items),
        outbox_pending_count=outbox_status_counts[OUTBOX_PENDING],
        outbox_in_progress_count=outbox_status_counts[OUTBOX_IN_PROGRESS],
        outbox_sent_count=outbox_status_counts[OUTBOX_SENT],
        outbox_dead_letter_count=outbox_status_counts[OUTBOX_DEAD_LETTER],
        updated_at=snapshot.updated_at,
        delivery_enabled=delivery_enabled,
    )


def _format_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{context} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{context} must be timezone-aware")
