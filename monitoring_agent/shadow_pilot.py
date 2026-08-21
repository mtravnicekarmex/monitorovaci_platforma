from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import math

from .incidents import IncidentEvaluation, IncidentTransition
from .reporting import redact_monitoring_text


SHADOW_PILOT_CONTRACT_VERSION = 1
SHADOW_PILOT_MODE = "shadow_only"
SOURCE_MONITORING_AGENT = "monitoring_agent"
SOURCE_LEGACY_ALERT = "legacy_alert"
SOURCE_OPERATOR_REVIEW = "operator_review"
VALID_EVENT_SOURCES = {SOURCE_MONITORING_AGENT, SOURCE_LEGACY_ALERT}
VALID_BLIND_SPOT_SOURCES = {
    SOURCE_MONITORING_AGENT,
    SOURCE_LEGACY_ALERT,
    SOURCE_OPERATOR_REVIEW,
    "both",
}
ACTION_OPENED = "opened"
ACTION_REOPENED = "reopened"
ACTION_ALERTED = "alerted"
ACTION_RECOVERED = "recovered"
ACTION_RESOLVED = "resolved"
OPEN_ACTIONS = {ACTION_OPENED, ACTION_REOPENED, ACTION_ALERTED}
RECOVERY_ACTIONS = {ACTION_RECOVERED, ACTION_RESOLVED}
COMPARABLE_ACTIONS = OPEN_ACTIONS | RECOVERY_ACTIONS
EVENT_FAMILY_DETECTION = "incident_detection"
EVENT_FAMILY_RECOVERY = "recovery"
SHADOW_PILOT_SAFETY_BOUNDARY = (
    "Shadow comparison only; legacy alerts remain authoritative.",
    "The comparison consumes supplied sanitized events and does not poll endpoints, read .env, send email, call interpretation providers, mutate state, or suppress alerts.",
    "No legacy alert may be replaced, disabled, rerouted, or downgraded from this output without separate approval.",
)


@dataclass(frozen=True)
class ShadowPilotEvent:
    source: str
    incident_key: str
    action: str
    occurred_at: datetime
    severity: str = "warning"
    summary: str = ""
    event_reference: str | None = None
    contract_version: int = SHADOW_PILOT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.source not in VALID_EVENT_SOURCES:
            raise ValueError("shadow pilot event source is invalid")
        if not self.incident_key.strip():
            raise ValueError("shadow pilot event incident key is required")
        if self.action not in COMPARABLE_ACTIONS:
            raise ValueError("shadow pilot event action is not comparable")
        _require_aware_datetime(self.occurred_at, context="event occurred_at")
        if not self.severity.strip():
            raise ValueError("shadow pilot event severity is required")
        if self.event_reference is not None and not self.event_reference.strip():
            raise ValueError("shadow pilot event reference must not be empty")
        if self.contract_version != SHADOW_PILOT_CONTRACT_VERSION:
            raise ValueError("shadow pilot event contract is unsupported")

    @property
    def family(self) -> str:
        return _event_family(self.action)

    @classmethod
    def from_incident_transition(
        cls,
        transition: IncidentTransition,
        *,
        source: str = SOURCE_MONITORING_AGENT,
        summary: str = "",
        event_reference: str | None = None,
    ) -> ShadowPilotEvent:
        if transition.action not in COMPARABLE_ACTIONS:
            raise ValueError("incident transition action is not comparable")
        return cls(
            source=source,
            incident_key=transition.incident_key,
            action=transition.action,
            occurred_at=transition.observed_at,
            severity=transition.severity,
            summary=summary or transition.reason,
            event_reference=event_reference,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "contract_version": self.contract_version,
            "event_family": self.family,
            "event_reference": self.event_reference,
            "incident_key": self.incident_key,
            "incident_kind": _incident_kind(self.incident_key),
            "occurred_at": _format_datetime(self.occurred_at),
            "severity": self.severity,
            "source": self.source,
            "summary": _sanitize_optional_text(self.summary),
        }


@dataclass(frozen=True)
class ShadowPilotBlindSpot:
    source: str
    category: str
    observed_at: datetime
    summary: str
    severity: str = "warning"
    contract_version: int = SHADOW_PILOT_CONTRACT_VERSION

    def __post_init__(self) -> None:
        if self.source not in VALID_BLIND_SPOT_SOURCES:
            raise ValueError("shadow pilot blind-spot source is invalid")
        if not self.category.strip():
            raise ValueError("shadow pilot blind-spot category is required")
        _require_aware_datetime(self.observed_at, context="blind spot observed_at")
        if not self.summary.strip():
            raise ValueError("shadow pilot blind-spot summary is required")
        if not self.severity.strip():
            raise ValueError("shadow pilot blind-spot severity is required")
        if self.contract_version != SHADOW_PILOT_CONTRACT_VERSION:
            raise ValueError("shadow pilot blind-spot contract is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "contract_version": self.contract_version,
            "observed_at": _format_datetime(self.observed_at),
            "severity": self.severity,
            "source": self.source,
            "summary": _sanitize_optional_text(self.summary),
        }


@dataclass(frozen=True)
class ShadowPilotMatch:
    event_family: str
    incident_key: str
    agent_event: ShadowPilotEvent
    legacy_event: ShadowPilotEvent
    agent_minus_legacy_seconds: float

    def __post_init__(self) -> None:
        if self.event_family not in {EVENT_FAMILY_DETECTION, EVENT_FAMILY_RECOVERY}:
            raise ValueError("shadow pilot match family is invalid")
        if not self.incident_key.strip():
            raise ValueError("shadow pilot match incident key is required")
        if self.agent_event.source != SOURCE_MONITORING_AGENT:
            raise ValueError("shadow pilot match agent event has invalid source")
        if self.legacy_event.source != SOURCE_LEGACY_ALERT:
            raise ValueError("shadow pilot match legacy event has invalid source")
        if self.agent_event.incident_key != self.incident_key:
            raise ValueError("shadow pilot match agent incident key mismatch")
        if self.legacy_event.incident_key != self.incident_key:
            raise ValueError("shadow pilot match legacy incident key mismatch")
        if self.agent_event.family != self.event_family:
            raise ValueError("shadow pilot match agent family mismatch")
        if self.legacy_event.family != self.event_family:
            raise ValueError("shadow pilot match legacy family mismatch")

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_event": self.agent_event.to_dict(),
            "agent_minus_legacy_seconds": round(
                self.agent_minus_legacy_seconds,
                3,
            ),
            "event_family": self.event_family,
            "incident_key": self.incident_key,
            "legacy_event": self.legacy_event.to_dict(),
        }


@dataclass(frozen=True)
class ShadowPilotDuplicate:
    source: str
    event_family: str
    incident_key: str
    primary_event: ShadowPilotEvent
    duplicate_event: ShadowPilotEvent
    delta_seconds: float

    def __post_init__(self) -> None:
        if self.source not in VALID_EVENT_SOURCES:
            raise ValueError("shadow pilot duplicate source is invalid")
        if self.event_family not in {EVENT_FAMILY_DETECTION, EVENT_FAMILY_RECOVERY}:
            raise ValueError("shadow pilot duplicate family is invalid")
        if not self.incident_key.strip():
            raise ValueError("shadow pilot duplicate incident key is required")
        if self.primary_event.source != self.source:
            raise ValueError("shadow pilot duplicate primary source mismatch")
        if self.duplicate_event.source != self.source:
            raise ValueError("shadow pilot duplicate event source mismatch")
        if self.primary_event.incident_key != self.incident_key:
            raise ValueError("shadow pilot duplicate primary incident mismatch")
        if self.duplicate_event.incident_key != self.incident_key:
            raise ValueError("shadow pilot duplicate event incident mismatch")
        if self.primary_event.family != self.event_family:
            raise ValueError("shadow pilot duplicate primary family mismatch")
        if self.duplicate_event.family != self.event_family:
            raise ValueError("shadow pilot duplicate event family mismatch")
        if self.delta_seconds < 0:
            raise ValueError("shadow pilot duplicate delta must not be negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "delta_seconds": round(self.delta_seconds, 3),
            "duplicate_event": self.duplicate_event.to_dict(),
            "event_family": self.event_family,
            "incident_key": self.incident_key,
            "primary_event": self.primary_event.to_dict(),
            "source": self.source,
        }


@dataclass(frozen=True)
class ShadowPilotComparison:
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    match_window_seconds: float
    duplicate_window_seconds: float
    raw_agent_event_count: int
    raw_legacy_event_count: int
    excluded_agent_event_count: int
    excluded_legacy_event_count: int
    deduplicated_agent_event_count: int
    deduplicated_legacy_event_count: int
    agent_blind_spot_event_count: int
    legacy_blind_spot_event_count: int
    matches: tuple[ShadowPilotMatch, ...]
    agent_only_events: tuple[ShadowPilotEvent, ...]
    legacy_only_events: tuple[ShadowPilotEvent, ...]
    duplicates: tuple[ShadowPilotDuplicate, ...]
    blind_spots: tuple[ShadowPilotBlindSpot, ...] = ()
    mode: str = SHADOW_PILOT_MODE
    contract_version: int = SHADOW_PILOT_CONTRACT_VERSION
    safety_boundary: tuple[str, ...] = SHADOW_PILOT_SAFETY_BOUNDARY

    def __post_init__(self) -> None:
        _require_aware_datetime(self.generated_at, context="generated_at")
        _require_valid_period(self.period_start, self.period_end)
        _require_positive_finite(
            self.match_window_seconds,
            context="match_window_seconds",
        )
        _require_positive_finite(
            self.duplicate_window_seconds,
            context="duplicate_window_seconds",
        )
        for name in (
            "raw_agent_event_count",
            "raw_legacy_event_count",
            "excluded_agent_event_count",
            "excluded_legacy_event_count",
            "deduplicated_agent_event_count",
            "deduplicated_legacy_event_count",
            "agent_blind_spot_event_count",
            "legacy_blind_spot_event_count",
        ):
            _require_non_negative_int(getattr(self, name), context=name)
        object.__setattr__(self, "matches", tuple(self.matches))
        object.__setattr__(self, "agent_only_events", tuple(self.agent_only_events))
        object.__setattr__(self, "legacy_only_events", tuple(self.legacy_only_events))
        object.__setattr__(self, "duplicates", tuple(self.duplicates))
        object.__setattr__(self, "blind_spots", tuple(self.blind_spots))
        object.__setattr__(self, "safety_boundary", tuple(self.safety_boundary))
        if self.mode != SHADOW_PILOT_MODE:
            raise ValueError("shadow pilot comparison mode must be shadow_only")
        if self.contract_version != SHADOW_PILOT_CONTRACT_VERSION:
            raise ValueError("shadow pilot comparison contract is unsupported")

    @property
    def included_agent_event_count(self) -> int:
        return self.raw_agent_event_count - self.excluded_agent_event_count

    @property
    def included_legacy_event_count(self) -> int:
        return self.raw_legacy_event_count - self.excluded_legacy_event_count

    @property
    def metrics(self) -> dict[str, object]:
        detection_matches = _filter_matches(self.matches, EVENT_FAMILY_DETECTION)
        recovery_matches = _filter_matches(self.matches, EVENT_FAMILY_RECOVERY)
        agent_only_detection = _filter_events(
            self.agent_only_events,
            EVENT_FAMILY_DETECTION,
        )
        legacy_only_detection = _filter_events(
            self.legacy_only_events,
            EVENT_FAMILY_DETECTION,
        )
        agent_only_recovery = _filter_events(
            self.agent_only_events,
            EVENT_FAMILY_RECOVERY,
        )
        legacy_only_recovery = _filter_events(
            self.legacy_only_events,
            EVENT_FAMILY_RECOVERY,
        )
        agent_duplicate_count = _count_duplicates(
            self.duplicates,
            source=SOURCE_MONITORING_AGENT,
        )
        legacy_duplicate_count = _count_duplicates(
            self.duplicates,
            source=SOURCE_LEGACY_ALERT,
        )
        return {
            "agent_blind_spot_event_count": self.agent_blind_spot_event_count,
            "agent_duplicate_event_count": agent_duplicate_count,
            "agent_duplicate_rate": _ratio(
                agent_duplicate_count,
                self.included_agent_event_count,
            ),
            "agent_event_count": {
                "deduplicated": self.deduplicated_agent_event_count,
                "excluded_outside_period": self.excluded_agent_event_count,
                "included": self.included_agent_event_count,
                "raw": self.raw_agent_event_count,
            },
            "agent_only_detection_count": len(agent_only_detection),
            "agent_only_recovery_count": len(agent_only_recovery),
            "confirmation_delay_seconds": _delay_summary(detection_matches),
            "false_negative_count": len(legacy_only_detection),
            "false_positive_count": len(agent_only_detection),
            "legacy_blind_spot_event_count": self.legacy_blind_spot_event_count,
            "legacy_duplicate_event_count": legacy_duplicate_count,
            "legacy_duplicate_rate": _ratio(
                legacy_duplicate_count,
                self.included_legacy_event_count,
            ),
            "legacy_event_count": {
                "deduplicated": self.deduplicated_legacy_event_count,
                "excluded_outside_period": self.excluded_legacy_event_count,
                "included": self.included_legacy_event_count,
                "raw": self.raw_legacy_event_count,
            },
            "legacy_only_detection_count": len(legacy_only_detection),
            "legacy_only_recovery_count": len(legacy_only_recovery),
            "matched_detection_count": len(detection_matches),
            "matched_recovery_count": len(recovery_matches),
            "operator_blind_spot_count": len(self.blind_spots),
            "recovery_delay_seconds": _delay_summary(recovery_matches),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "configuration": {
                "duplicate_window_seconds": round(
                    self.duplicate_window_seconds,
                    3,
                ),
                "match_window_seconds": round(self.match_window_seconds, 3),
                "period_boundary": "start_inclusive_end_exclusive",
            },
            "contract_version": self.contract_version,
            "event": "monitoring_shadow_pilot_comparison",
            "generated_at": _format_datetime(self.generated_at),
            "metrics": self.metrics,
            "mode": self.mode,
            "period": {
                "end": _format_datetime(self.period_end),
                "start": _format_datetime(self.period_start),
            },
            "safety_boundary": list(self.safety_boundary),
            "shadow_outputs": {
                "agent_only_events": [
                    event.to_dict() for event in self.agent_only_events
                ],
                "blind_spots": [item.to_dict() for item in self.blind_spots],
                "duplicates": [item.to_dict() for item in self.duplicates],
                "legacy_only_events": [
                    event.to_dict() for event in self.legacy_only_events
                ],
                "matches": [match.to_dict() for match in self.matches],
            },
        }


def events_from_incident_evaluation(
    evaluation: IncidentEvaluation,
    *,
    source: str = SOURCE_MONITORING_AGENT,
) -> tuple[ShadowPilotEvent, ...]:
    if source not in VALID_EVENT_SOURCES:
        raise ValueError("shadow pilot event source is invalid")
    return tuple(
        ShadowPilotEvent.from_incident_transition(transition, source=source)
        for transition in evaluation.transitions
        if transition.action in COMPARABLE_ACTIONS
    )


def events_from_incident_transition_records(
    records: Iterable[Mapping[str, object]],
    *,
    source: str = SOURCE_MONITORING_AGENT,
) -> tuple[ShadowPilotEvent, ...]:
    if source not in VALID_EVENT_SOURCES:
        raise ValueError("shadow pilot event source is invalid")
    events: list[ShadowPilotEvent] = []
    for record in records:
        payload = _require_mapping(record, context="incident transition record")
        transition = _incident_transition_from_mapping(
            payload.get("transition"),
        )
        if transition.action not in COMPARABLE_ACTIONS:
            continue
        report_reference = _require_optional_string(
            payload.get("report_reference"),
            context="transition report_reference",
        )
        events.append(
            ShadowPilotEvent.from_incident_transition(
                transition,
                source=source,
                event_reference=report_reference,
            )
        )
    return tuple(events)


def events_from_shadow_pilot_payload(
    payload: object,
    *,
    default_source: str,
) -> tuple[ShadowPilotEvent, ...]:
    if default_source not in VALID_EVENT_SOURCES:
        raise ValueError("shadow pilot event source is invalid")
    raw_events = _extract_payload_array(
        payload,
        item_key="events",
        context="shadow pilot events payload",
    )
    events = tuple(
        _event_from_mapping(item, default_source=default_source)
        for item in raw_events
    )
    for event in events:
        if event.source != default_source:
            raise ValueError("shadow pilot event source does not match input stream")
    return events


def blind_spots_from_shadow_pilot_payload(
    payload: object,
) -> tuple[ShadowPilotBlindSpot, ...]:
    raw_items = _extract_payload_array(
        payload,
        item_key="blind_spots",
        context="shadow pilot blind-spots payload",
    )
    return tuple(_blind_spot_from_mapping(item) for item in raw_items)


def shadow_pilot_events_payload(
    events: Iterable[ShadowPilotEvent],
    *,
    source: str,
) -> dict[str, object]:
    if source not in VALID_EVENT_SOURCES:
        raise ValueError("shadow pilot event source is invalid")
    resolved_events = tuple(events)
    for event in resolved_events:
        if event.source != source:
            raise ValueError("shadow pilot event source mismatch")
    return {
        "contract_version": SHADOW_PILOT_CONTRACT_VERSION,
        "event": "monitoring_shadow_pilot_events",
        "event_count": len(resolved_events),
        "events": [event.to_dict() for event in _ordered_events(resolved_events)],
        "safety_boundary": list(SHADOW_PILOT_SAFETY_BOUNDARY),
        "source": source,
    }


def build_shadow_pilot_comparison(
    *,
    period_start: datetime,
    period_end: datetime,
    agent_events: Iterable[ShadowPilotEvent],
    legacy_events: Iterable[ShadowPilotEvent],
    blind_spots: Iterable[ShadowPilotBlindSpot] = (),
    match_window_seconds: float = 300.0,
    duplicate_window_seconds: float = 300.0,
    generated_at: datetime | None = None,
) -> ShadowPilotComparison:
    _require_valid_period(period_start, period_end)
    _require_positive_finite(match_window_seconds, context="match_window_seconds")
    _require_positive_finite(
        duplicate_window_seconds,
        context="duplicate_window_seconds",
    )
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)
    _require_aware_datetime(generated_at, context="generated_at")

    raw_agent_events = tuple(agent_events)
    raw_legacy_events = tuple(legacy_events)
    for event in raw_agent_events:
        if event.source != SOURCE_MONITORING_AGENT:
            raise ValueError("agent_events contains a non-agent event")
    for event in raw_legacy_events:
        if event.source != SOURCE_LEGACY_ALERT:
            raise ValueError("legacy_events contains a non-legacy event")

    included_agent_events = _events_inside_period(
        raw_agent_events,
        period_start=period_start,
        period_end=period_end,
    )
    included_legacy_events = _events_inside_period(
        raw_legacy_events,
        period_start=period_start,
        period_end=period_end,
    )
    deduped_agent_events, agent_duplicates = _deduplicate_events(
        included_agent_events,
        duplicate_window_seconds=duplicate_window_seconds,
    )
    deduped_legacy_events, legacy_duplicates = _deduplicate_events(
        included_legacy_events,
        duplicate_window_seconds=duplicate_window_seconds,
    )
    detection = _match_family(
        deduped_agent_events,
        deduped_legacy_events,
        event_family=EVENT_FAMILY_DETECTION,
        match_window_seconds=match_window_seconds,
    )
    recovery = _match_family(
        deduped_agent_events,
        deduped_legacy_events,
        event_family=EVENT_FAMILY_RECOVERY,
        match_window_seconds=match_window_seconds,
    )
    included_blind_spots = tuple(
        item
        for item in blind_spots
        if _inside_period(
            item.observed_at,
            period_start=period_start,
            period_end=period_end,
        )
    )

    return ShadowPilotComparison(
        generated_at=generated_at,
        period_start=period_start,
        period_end=period_end,
        match_window_seconds=match_window_seconds,
        duplicate_window_seconds=duplicate_window_seconds,
        raw_agent_event_count=len(raw_agent_events),
        raw_legacy_event_count=len(raw_legacy_events),
        excluded_agent_event_count=len(raw_agent_events) - len(included_agent_events),
        excluded_legacy_event_count=len(raw_legacy_events)
        - len(included_legacy_events),
        deduplicated_agent_event_count=len(deduped_agent_events),
        deduplicated_legacy_event_count=len(deduped_legacy_events),
        agent_blind_spot_event_count=_count_blind_spot_events(
            included_agent_events,
        ),
        legacy_blind_spot_event_count=_count_blind_spot_events(
            included_legacy_events,
        ),
        matches=detection.matches + recovery.matches,
        agent_only_events=detection.unmatched_agent_events
        + recovery.unmatched_agent_events,
        legacy_only_events=detection.unmatched_legacy_events
        + recovery.unmatched_legacy_events,
        duplicates=agent_duplicates + legacy_duplicates,
        blind_spots=included_blind_spots,
    )


def render_shadow_pilot_comparison(
    comparison: ShadowPilotComparison,
    *,
    max_chars: int = 6_000,
) -> str:
    if (
        isinstance(max_chars, bool)
        or not isinstance(max_chars, int)
        or max_chars < 200
    ):
        raise ValueError("max_chars must be an integer of at least 200")
    metrics = comparison.metrics
    confirmation = metrics["confirmation_delay_seconds"]
    recovery = metrics["recovery_delay_seconds"]
    text = "\n".join(
        [
            "# Monitoring shadow pilot comparison",
            "",
            f"Generated at: {_format_datetime(comparison.generated_at)}",
            f"Contract version: {comparison.contract_version}",
            f"Mode: {comparison.mode}",
            (
                "Period: "
                f"{_format_datetime(comparison.period_start)} <= event < "
                f"{_format_datetime(comparison.period_end)}"
            ),
            (
                "Windows: "
                f"match={comparison.match_window_seconds:.3f}s, "
                f"duplicate={comparison.duplicate_window_seconds:.3f}s"
            ),
            "",
            "## Detection comparison",
            f"- matched detections: {metrics['matched_detection_count']}",
            f"- agent-only detections / false positives: {metrics['false_positive_count']}",
            f"- legacy-only detections / false negatives: {metrics['false_negative_count']}",
            f"- confirmation delay agent-minus-legacy seconds: {_render_delay_summary(confirmation)}",
            "",
            "## Recovery comparison",
            f"- matched recoveries: {metrics['matched_recovery_count']}",
            f"- agent-only recoveries: {metrics['agent_only_recovery_count']}",
            f"- legacy-only recoveries: {metrics['legacy_only_recovery_count']}",
            f"- recovery delay agent-minus-legacy seconds: {_render_delay_summary(recovery)}",
            "",
            "## Duplicates and blind spots",
            (
                "- duplicate events: "
                f"agent={metrics['agent_duplicate_event_count']} "
                f"legacy={metrics['legacy_duplicate_event_count']}"
            ),
            (
                "- duplicate rates: "
                f"agent={metrics['agent_duplicate_rate']:.6f} "
                f"legacy={metrics['legacy_duplicate_rate']:.6f}"
            ),
            (
                "- blind spots: "
                f"agent_events={metrics['agent_blind_spot_event_count']} "
                f"legacy_events={metrics['legacy_blind_spot_event_count']} "
                f"operator_review={metrics['operator_blind_spot_count']}"
            ),
            "",
            "## Safety boundary",
            *[f"- {line}" for line in comparison.safety_boundary],
            "",
        ]
    )
    sanitized = redact_monitoring_text(text)
    if len(sanitized) <= max_chars:
        return sanitized
    return sanitized[: max_chars - 20].rstrip() + "\n...[truncated]\n"


@dataclass(frozen=True)
class _FamilyMatchResult:
    matches: tuple[ShadowPilotMatch, ...]
    unmatched_agent_events: tuple[ShadowPilotEvent, ...]
    unmatched_legacy_events: tuple[ShadowPilotEvent, ...]


def _match_family(
    agent_events: Sequence[ShadowPilotEvent],
    legacy_events: Sequence[ShadowPilotEvent],
    *,
    event_family: str,
    match_window_seconds: float,
) -> _FamilyMatchResult:
    agents = [
        event for event in _ordered_events(agent_events) if event.family == event_family
    ]
    legacy = [
        event for event in _ordered_events(legacy_events) if event.family == event_family
    ]
    unmatched_legacy_indexes = set(range(len(legacy)))
    matches: list[ShadowPilotMatch] = []
    unmatched_agents: list[ShadowPilotEvent] = []

    for agent in agents:
        candidates: list[tuple[float, int, ShadowPilotEvent]] = []
        for index in sorted(unmatched_legacy_indexes):
            candidate = legacy[index]
            if candidate.incident_key != agent.incident_key:
                continue
            delta_seconds = (agent.occurred_at - candidate.occurred_at).total_seconds()
            if abs(delta_seconds) <= match_window_seconds:
                candidates.append((abs(delta_seconds), index, candidate))
        if not candidates:
            unmatched_agents.append(agent)
            continue
        _, matched_index, matched_legacy = min(
            candidates,
            key=lambda item: (item[0], item[2].occurred_at, item[1]),
        )
        unmatched_legacy_indexes.remove(matched_index)
        matches.append(
            ShadowPilotMatch(
                event_family=event_family,
                incident_key=agent.incident_key,
                agent_event=agent,
                legacy_event=matched_legacy,
                agent_minus_legacy_seconds=(
                    agent.occurred_at - matched_legacy.occurred_at
                ).total_seconds(),
            )
        )

    unmatched_legacy = tuple(legacy[index] for index in sorted(unmatched_legacy_indexes))
    return _FamilyMatchResult(
        matches=tuple(matches),
        unmatched_agent_events=tuple(unmatched_agents),
        unmatched_legacy_events=unmatched_legacy,
    )


def _deduplicate_events(
    events: Sequence[ShadowPilotEvent],
    *,
    duplicate_window_seconds: float,
) -> tuple[tuple[ShadowPilotEvent, ...], tuple[ShadowPilotDuplicate, ...]]:
    retained: list[ShadowPilotEvent] = []
    duplicates: list[ShadowPilotDuplicate] = []
    last_retained_by_key: dict[tuple[str, str, str], ShadowPilotEvent] = {}
    for event in _ordered_events(events):
        key = (event.source, event.incident_key, event.family)
        previous = last_retained_by_key.get(key)
        if previous is not None:
            delta_seconds = (event.occurred_at - previous.occurred_at).total_seconds()
            if 0 <= delta_seconds <= duplicate_window_seconds:
                duplicates.append(
                    ShadowPilotDuplicate(
                        source=event.source,
                        event_family=event.family,
                        incident_key=event.incident_key,
                        primary_event=previous,
                        duplicate_event=event,
                        delta_seconds=delta_seconds,
                    )
                )
                continue
        retained.append(event)
        last_retained_by_key[key] = event
    return tuple(retained), tuple(duplicates)


def _events_inside_period(
    events: Sequence[ShadowPilotEvent],
    *,
    period_start: datetime,
    period_end: datetime,
) -> tuple[ShadowPilotEvent, ...]:
    return tuple(
        event
        for event in events
        if _inside_period(
            event.occurred_at,
            period_start=period_start,
            period_end=period_end,
        )
    )


def _inside_period(
    value: datetime,
    *,
    period_start: datetime,
    period_end: datetime,
) -> bool:
    return period_start <= value < period_end


def _ordered_events(events: Iterable[ShadowPilotEvent]) -> tuple[ShadowPilotEvent, ...]:
    return tuple(
        sorted(
            events,
            key=lambda event: (
                event.occurred_at,
                event.incident_key,
                event.action,
                event.source,
                event.event_reference or "",
            ),
        )
    )


def _event_family(action: str) -> str:
    if action in OPEN_ACTIONS:
        return EVENT_FAMILY_DETECTION
    if action in RECOVERY_ACTIONS:
        return EVENT_FAMILY_RECOVERY
    raise ValueError("shadow pilot event action is not comparable")


def _filter_matches(
    matches: Sequence[ShadowPilotMatch],
    event_family: str,
) -> tuple[ShadowPilotMatch, ...]:
    return tuple(match for match in matches if match.event_family == event_family)


def _filter_events(
    events: Sequence[ShadowPilotEvent],
    event_family: str,
) -> tuple[ShadowPilotEvent, ...]:
    return tuple(event for event in events if event.family == event_family)


def _count_duplicates(
    duplicates: Sequence[ShadowPilotDuplicate],
    *,
    source: str,
) -> int:
    return sum(1 for duplicate in duplicates if duplicate.source == source)


def _delay_summary(matches: Sequence[ShadowPilotMatch]) -> dict[str, object]:
    values = [match.agent_minus_legacy_seconds for match in matches]
    if not values:
        return {
            "agent_earlier_count": 0,
            "agent_later_count": 0,
            "average": None,
            "count": 0,
            "maximum": None,
            "minimum": None,
            "same_time_count": 0,
        }
    return {
        "agent_earlier_count": sum(1 for value in values if value < 0),
        "agent_later_count": sum(1 for value in values if value > 0),
        "average": round(sum(values) / len(values), 3),
        "count": len(values),
        "maximum": round(max(values), 3),
        "minimum": round(min(values), 3),
        "same_time_count": sum(1 for value in values if value == 0),
    }


def _render_delay_summary(value: object) -> str:
    if not isinstance(value, dict) or value.get("count") == 0:
        return "none"
    return (
        f"count={value['count']}, avg={value['average']}, "
        f"min={value['minimum']}, max={value['maximum']}, "
        f"agent_earlier={value['agent_earlier_count']}, "
        f"agent_later={value['agent_later_count']}"
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _count_blind_spot_events(events: Sequence[ShadowPilotEvent]) -> int:
    return sum(
        1
        for event in events
        if event.family == EVENT_FAMILY_DETECTION
        and _incident_kind(event.incident_key) == "supervision_center_blind_spot"
    )


def _incident_kind(incident_key: str) -> str:
    return incident_key.split(":", 1)[0]


def _sanitize_optional_text(value: str) -> str:
    if not value:
        return ""
    return redact_monitoring_text(value)


def _incident_transition_from_mapping(value: object) -> IncidentTransition:
    payload = _require_mapping(value, context="incident transition")
    return IncidentTransition(
        incident_key=_require_string(
            payload.get("incident_key"),
            context="transition incident_key",
        ),
        action=_require_string(payload.get("action"), context="transition action"),
        kind=_require_string(payload.get("kind"), context="transition kind"),
        subject=_require_string(payload.get("subject"), context="transition subject"),
        severity=_require_string(
            payload.get("severity"),
            context="transition severity",
        ),
        status=_require_string(payload.get("status"), context="transition status"),
        reason=_require_string(payload.get("reason"), context="transition reason"),
        observed_at=_parse_datetime(
            payload.get("observed_at"),
            context="transition observed_at",
        ),
        cycle_sequence=_require_optional_int(
            payload.get("cycle_sequence"),
            context="transition cycle_sequence",
        ),
        failure_count=_require_int(
            payload.get("failure_count"),
            context="transition failure_count",
        ),
        recovery_count=_require_int(
            payload.get("recovery_count"),
            context="transition recovery_count",
        ),
        occurrence_count=_require_int(
            payload.get("occurrence_count"),
            context="transition occurrence_count",
        ),
    )


def _event_from_mapping(
    value: object,
    *,
    default_source: str,
) -> ShadowPilotEvent:
    payload = _require_mapping(value, context="shadow pilot event")
    source = _require_optional_string(
        payload.get("source"),
        context="shadow pilot event source",
    )
    return ShadowPilotEvent(
        source=source or default_source,
        incident_key=_require_string(
            payload.get("incident_key"),
            context="shadow pilot event incident_key",
        ),
        action=_require_string(payload.get("action"), context="shadow pilot action"),
        occurred_at=_parse_datetime(
            payload.get("occurred_at"),
            context="shadow pilot occurred_at",
        ),
        severity=_require_string(
            payload.get("severity", "warning"),
            context="shadow pilot severity",
        ),
        summary=_require_string(
            payload.get("summary", ""),
            context="shadow pilot summary",
        ),
        event_reference=_require_optional_string(
            payload.get("event_reference"),
            context="shadow pilot event_reference",
        ),
        contract_version=_require_int(
            payload.get("contract_version", SHADOW_PILOT_CONTRACT_VERSION),
            context="shadow pilot contract_version",
        ),
    )


def _blind_spot_from_mapping(value: object) -> ShadowPilotBlindSpot:
    payload = _require_mapping(value, context="shadow pilot blind spot")
    return ShadowPilotBlindSpot(
        source=_require_string(payload.get("source"), context="blind spot source"),
        category=_require_string(
            payload.get("category"),
            context="blind spot category",
        ),
        observed_at=_parse_datetime(
            payload.get("observed_at"),
            context="blind spot observed_at",
        ),
        summary=_require_string(payload.get("summary"), context="blind spot summary"),
        severity=_require_string(
            payload.get("severity", "warning"),
            context="blind spot severity",
        ),
        contract_version=_require_int(
            payload.get("contract_version", SHADOW_PILOT_CONTRACT_VERSION),
            context="blind spot contract_version",
        ),
    )


def _extract_payload_array(
    payload: object,
    *,
    item_key: str,
    context: str,
) -> list[object]:
    if isinstance(payload, list):
        return payload
    value = _require_mapping(payload, context=context)
    items = value.get(item_key)
    if not isinstance(items, list):
        raise ValueError(f"{context} must contain an array field named {item_key}")
    return items


def _format_datetime(value: datetime) -> str:
    return value.isoformat()


def _parse_datetime(value: object, *, context: str) -> datetime:
    text = _require_string(value, context=context)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{context} must be ISO-8601 datetime") from exc
    _require_aware_datetime(parsed, context=context)
    return parsed


def _require_mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    return value


def _require_string(value: object, *, context: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string")
    return value


def _require_optional_string(value: object, *, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{context} must be a string or null")
    if not value.strip():
        return None
    return value


def _require_int(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer")
    return value


def _require_optional_int(value: object, *, context: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, context=context)


def _require_valid_period(period_start: datetime, period_end: datetime) -> None:
    _require_aware_datetime(period_start, context="period_start")
    _require_aware_datetime(period_end, context="period_end")
    if period_start >= period_end:
        raise ValueError("shadow pilot period_start must be before period_end")


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{context} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{context} must be timezone-aware")


def _require_positive_finite(value: float, *, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be a positive finite number")
    if not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError(f"{context} must be a positive finite number")


def _require_non_negative_int(value: int, *, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{context} must be a non-negative integer")
