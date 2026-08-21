from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import re

from .incident_store import (
    OUTBOX_DEAD_LETTER,
    OUTBOX_IN_PROGRESS,
    OUTBOX_PENDING,
    OUTBOX_SENT,
    IncidentStoreSnapshot,
)
from .incidents import (
    INCIDENT_STATUS_ACTIVE,
    INCIDENT_STATUS_CANDIDATE,
    INCIDENT_STATUS_RESOLVED,
    IncidentEvaluation,
    IncidentState,
    IncidentTransition,
)


REPORT_RENDERER_VERSION = 1
SUMMARY_STATUS_HEALTHY = "healthy"
SUMMARY_STATUS_DEGRADED = "degraded"
SUMMARY_STATUS_INCIDENT = "incident"
SUMMARY_STATUS_RECOVERED = "recovered"
SUMMARY_STATUSES = {
    SUMMARY_STATUS_HEALTHY,
    SUMMARY_STATUS_DEGRADED,
    SUMMARY_STATUS_INCIDENT,
    SUMMARY_STATUS_RECOVERED,
}
FACT_SEVERITIES = {"info", "warning", "critical"}
OUTBOX_STATUS_ORDER = (
    OUTBOX_PENDING,
    OUTBOX_IN_PROGRESS,
    OUTBOX_SENT,
    OUTBOX_DEAD_LETTER,
)
DELIVERY_DISABLED_LINE = (
    "Delivery disabled by design. Rendering this report does not send email, "
    "open network connections, mutate state, or authorize a delivery worker."
)
DRAFT_PROMPT_LINE = (
    "DRAFT ONLY - do not execute commands, send messages, mutate state, "
    "contact external systems, or change configuration from this prompt."
)

_STATUS_RANK = {
    INCIDENT_STATUS_ACTIVE: 0,
    INCIDENT_STATUS_CANDIDATE: 1,
    INCIDENT_STATUS_RESOLVED: 2,
}
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b("
    r"authorization|bearer|password|passwd|pwd|secret|token|api[_-]?key|"
    r"client[_-]?secret|access[_-]?token|refresh[_-]?token"
    r")\s*[:=]\s*([^\s,;]+)"
)
_BEARER_VALUE_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_URL_WITH_QUERY_OR_FRAGMENT_RE = re.compile(r"https?://[^\s?#]+[^\s]*[?#][^\s]*")
_WINDOWS_USER_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\[^\s]*")
_PRIVATE_IDENTIFIER_RE = re.compile(r"\bprivate-[A-Za-z0-9_.:-]+\b")


@dataclass(frozen=True)
class ReportFact:
    label: str
    value: str
    severity: str = "info"

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("report fact label is required")
        if not self.value.strip():
            raise ValueError("report fact value is required")
        if self.severity not in FACT_SEVERITIES:
            raise ValueError("report fact severity is invalid")


@dataclass(frozen=True)
class MonitoringReportSnapshot:
    generated_at: datetime
    summary_status: str
    verified_facts: tuple[ReportFact, ...]
    rule_conclusions: tuple[ReportFact, ...]
    historical_qualifications: tuple[ReportFact, ...]
    hypotheses: tuple[ReportFact, ...]
    incident_evaluation: IncidentEvaluation
    store_snapshot: IncidentStoreSnapshot | None = None
    title: str = "Monitoring agent report"

    def __post_init__(self) -> None:
        _require_aware_datetime(self.generated_at, context="generated_at")
        if self.summary_status not in SUMMARY_STATUSES:
            raise ValueError("summary status is invalid")
        if not self.title.strip():
            raise ValueError("report title is required")
        object.__setattr__(self, "verified_facts", tuple(self.verified_facts))
        object.__setattr__(self, "rule_conclusions", tuple(self.rule_conclusions))
        object.__setattr__(
            self,
            "historical_qualifications",
            tuple(self.historical_qualifications),
        )
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))


def build_monitoring_report_snapshot(
    *,
    generated_at: datetime,
    incident_evaluation: IncidentEvaluation,
    store_snapshot: IncidentStoreSnapshot | None = None,
    latest_heartbeat_status: str | None = None,
    observation_count: int | None = None,
    transport_failure_count: int | None = None,
    evidence_gaps: Sequence[str] = (),
    historical_notes: Sequence[str] = (),
    hypotheses: Sequence[str] = (),
    title: str = "Monitoring agent report",
) -> MonitoringReportSnapshot:
    _require_aware_datetime(generated_at, context="generated_at")
    _validate_optional_non_negative_int(
        observation_count,
        context="observation_count",
    )
    _validate_optional_non_negative_int(
        transport_failure_count,
        context="transport_failure_count",
    )
    summary_status = _derive_summary_status(
        incident_evaluation=incident_evaluation,
        latest_heartbeat_status=latest_heartbeat_status,
    )
    verified_facts = _build_verified_facts(
        generated_at=generated_at,
        incident_evaluation=incident_evaluation,
        store_snapshot=store_snapshot,
        latest_heartbeat_status=latest_heartbeat_status,
        observation_count=observation_count,
        transport_failure_count=transport_failure_count,
    )
    rule_conclusions = _build_rule_conclusions(incident_evaluation)
    historical_qualifications = _build_historical_qualifications(
        incident_evaluation=incident_evaluation,
        evidence_gaps=evidence_gaps,
        historical_notes=historical_notes,
    )
    hypothesis_facts = _facts_from_strings(
        hypotheses,
        label="hypothesis",
        default=ReportFact(
            label="none",
            value="No hypotheses generated by this deterministic renderer.",
        ),
    )
    return MonitoringReportSnapshot(
        generated_at=generated_at,
        summary_status=summary_status,
        verified_facts=verified_facts,
        rule_conclusions=rule_conclusions,
        historical_qualifications=historical_qualifications,
        hypotheses=hypothesis_facts,
        incident_evaluation=incident_evaluation,
        store_snapshot=store_snapshot,
        title=title,
    )


def render_monitoring_report(
    snapshot: MonitoringReportSnapshot,
    *,
    max_chars: int = 6_000,
) -> str:
    text = "\n".join(
        [
            f"# {snapshot.title}",
            "",
            f"Generated at: {_format_datetime(snapshot.generated_at)}",
            f"Renderer version: {REPORT_RENDERER_VERSION}",
            f"Summary status: {snapshot.summary_status}",
            "",
            "## Verified facts",
            *_render_facts(snapshot.verified_facts),
            "",
            "## Rule conclusions",
            *_render_facts(snapshot.rule_conclusions),
            "",
            "## Historical qualifications",
            *_render_facts(snapshot.historical_qualifications),
            "",
            "## Hypotheses / not yet verified",
            *_render_facts(snapshot.hypotheses),
            "",
            "## Outbox / delivery state",
            *_render_outbox(snapshot.store_snapshot),
            "",
            "## Safety boundary",
            f"- [critical] no delivery side effects: {DELIVERY_DISABLED_LINE}",
            (
                "- [critical] sanitized inputs only: Report inputs must be "
                "normalized facts; do not pass credentials, raw payloads, "
                "cookies, tokens, or private file contents."
            ),
            "",
        ]
    )
    return _bounded_text(redact_monitoring_text(text), max_chars=max_chars)


def render_programming_agent_prompt(
    snapshot: MonitoringReportSnapshot,
    *,
    max_chars: int = 4_000,
) -> str:
    text = "\n".join(
        [
            DRAFT_PROMPT_LINE,
            "",
            "Purpose: provide a sanitized monitoring report to a future "
            "programming agent for read-only analysis planning.",
            "",
            "Scope:",
            "- Analyze only the monitoring evidence included below.",
            "- Propose diagnostics and success criteria; do not perform them.",
            "- Treat delivery, mutation, process control, and credential access "
            "as out of scope unless a human explicitly approves a later step.",
            "",
            "Evidence:",
            f"- generated_at: {_format_datetime(snapshot.generated_at)}",
            f"- summary_status: {snapshot.summary_status}",
            f"- renderer_version: {REPORT_RENDERER_VERSION}",
            *_prompt_fact_lines("verified_fact", snapshot.verified_facts),
            *_prompt_fact_lines("rule_conclusion", snapshot.rule_conclusions),
            *_prompt_fact_lines(
                "historical_qualification",
                snapshot.historical_qualifications,
            ),
            *_prompt_fact_lines("hypothesis", snapshot.hypotheses),
            *_prompt_outbox_lines(snapshot.store_snapshot),
            "",
            "Requested diagnostics:",
            "- Identify which component boundary is most likely involved.",
            "- List the next safe read-only checks and the evidence each check "
            "would confirm or reject.",
            "- Keep verified facts, deterministic rule conclusions, historical "
            "qualifications, and hypotheses separate.",
            "- Call out any evidence gaps before recommending escalation.",
            "",
            "Success criteria:",
            "- No secret, credential, cookie, bearer token, raw private path, or "
            "recipient value is included.",
            "- No command execution, network contact, state mutation, service "
            "restart, delivery attempt, or alert replacement is authorized.",
            "- Output remains a draft diagnostic plan until a human approves a "
            "separate action.",
            "",
        ]
    )
    return _bounded_text(redact_monitoring_text(text), max_chars=max_chars)


def redact_monitoring_text(text: str) -> str:
    redacted = _BEARER_VALUE_RE.sub("Bearer [redacted]", text)
    redacted = _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}=[redacted]",
        redacted,
    )
    redacted = _URL_WITH_QUERY_OR_FRAGMENT_RE.sub(_redact_url, redacted)
    redacted = _WINDOWS_USER_PATH_RE.sub("[redacted-windows-user-path]", redacted)
    redacted = _PRIVATE_IDENTIFIER_RE.sub("[redacted-private-id]", redacted)
    return redacted


def _build_verified_facts(
    *,
    generated_at: datetime,
    incident_evaluation: IncidentEvaluation,
    store_snapshot: IncidentStoreSnapshot | None,
    latest_heartbeat_status: str | None,
    observation_count: int | None,
    transport_failure_count: int | None,
) -> tuple[ReportFact, ...]:
    active_count = _state_count(incident_evaluation.states, INCIDENT_STATUS_ACTIVE)
    candidate_count = _state_count(
        incident_evaluation.states,
        INCIDENT_STATUS_CANDIDATE,
    )
    resolved_count = _state_count(
        incident_evaluation.states,
        INCIDENT_STATUS_RESOLVED,
    )
    facts: list[ReportFact] = [
        ReportFact("generated_at", _format_datetime(generated_at)),
        ReportFact("incident_rule_version", str(incident_evaluation.rule_version)),
        ReportFact(
            "incident_states",
            (
                f"total={len(incident_evaluation.states)}, active={active_count}, "
                f"candidate={candidate_count}, resolved={resolved_count}"
            ),
        ),
        ReportFact("transition_count", str(len(incident_evaluation.transitions))),
    ]
    if latest_heartbeat_status is not None:
        facts.append(ReportFact("latest_heartbeat_status", latest_heartbeat_status))
    if observation_count is not None:
        facts.append(ReportFact("latest_observation_count", str(observation_count)))
    if transport_failure_count is not None:
        severity = "warning" if transport_failure_count else "info"
        facts.append(
            ReportFact(
                "latest_transport_failure_count",
                str(transport_failure_count),
                severity=severity,
            )
        )
    if store_snapshot is not None:
        updated_at = (
            "not persisted"
            if store_snapshot.updated_at is None
            else _format_datetime(store_snapshot.updated_at)
        )
        facts.append(ReportFact("incident_store_updated_at", updated_at))
        facts.append(
            ReportFact(
                "incident_store_records",
                (
                    f"states={len(store_snapshot.states)}, "
                    f"transitions={len(store_snapshot.transition_records)}, "
                    f"outbox={len(store_snapshot.outbox_items)}"
                ),
            )
        )
    return tuple(facts)


def _build_rule_conclusions(
    incident_evaluation: IncidentEvaluation,
) -> tuple[ReportFact, ...]:
    facts: list[ReportFact] = []
    for state in sorted(incident_evaluation.states, key=_state_sort_key):
        facts.append(
            ReportFact(
                label=f"{state.status} {state.incident_key}",
                value=_state_summary(state),
                severity=state.severity,
            )
        )
    for transition in incident_evaluation.transitions:
        if transition.reason == "historical_evidence_only":
            continue
        facts.append(
            ReportFact(
                label=f"{transition.action} {transition.incident_key}",
                value=_transition_summary(transition),
                severity=transition.severity,
            )
        )
    if not facts:
        return (
            ReportFact(
                label="no incident transition",
                value="No active incident, candidate, or recovery transition in the supplied evaluation.",
            ),
        )
    return tuple(facts)


def _build_historical_qualifications(
    *,
    incident_evaluation: IncidentEvaluation,
    evidence_gaps: Sequence[str],
    historical_notes: Sequence[str],
) -> tuple[ReportFact, ...]:
    facts: list[ReportFact] = [
        *list(
            _facts_from_strings(
                historical_notes,
                label="historical note",
                severity="info",
            )
        ),
        *list(
            _facts_from_strings(
                evidence_gaps,
                label="evidence gap",
                severity="warning",
            )
        ),
    ]
    for transition in incident_evaluation.transitions:
        if transition.reason != "historical_evidence_only":
            continue
        facts.append(
            ReportFact(
                label=f"historical-only {transition.incident_key}",
                value=(
                    f"action={transition.action}, status={transition.status}, "
                    "no incident state or outbox intent is created from retained history only"
                ),
                severity="warning",
            )
        )
    if not facts:
        return (
            ReportFact(
                label="none",
                value="No historical qualifiers or evidence gaps supplied.",
            ),
        )
    return tuple(facts)


def _render_facts(facts: Iterable[ReportFact]) -> list[str]:
    return [
        f"- [{fact.severity}] {fact.label}: {fact.value}"
        for fact in facts
    ]


def _render_outbox(snapshot: IncidentStoreSnapshot | None) -> list[str]:
    if snapshot is None:
        return [
            "- [info] delivery_enabled: false",
            "- [info] outbox_snapshot: not supplied; no delivery attempted",
        ]
    counts = _outbox_counts(snapshot)
    lines = [
        "- [info] delivery_enabled: false",
        "- [info] outbox_counts: "
        + ", ".join(f"{status}={counts[status]}" for status in OUTBOX_STATUS_ORDER),
    ]
    for item in sorted(
        snapshot.outbox_items,
        key=lambda candidate: (
            candidate.status,
            candidate.created_at,
            candidate.incident_key,
            candidate.action,
        ),
    ):
        severity = "critical" if item.status == OUTBOX_DEAD_LETTER else "info"
        lines.append(
            (
                f"- [{severity}] {item.status} {item.action} "
                f"{item.incident_key}: report_reference={item.report_reference}, "
                f"attempt_count={item.attempt_count}"
            )
        )
    return lines


def _prompt_fact_lines(prefix: str, facts: Iterable[ReportFact]) -> list[str]:
    return [
        f"- {prefix}: severity={fact.severity}; {fact.label}={fact.value}"
        for fact in facts
    ]


def _prompt_outbox_lines(snapshot: IncidentStoreSnapshot | None) -> list[str]:
    if snapshot is None:
        return ["- outbox: delivery_enabled=false; snapshot=not_supplied"]
    counts = _outbox_counts(snapshot)
    return [
        "- outbox: delivery_enabled=false; "
        + ", ".join(f"{status}={counts[status]}" for status in OUTBOX_STATUS_ORDER)
    ]


def _facts_from_strings(
    values: Sequence[str],
    *,
    label: str,
    severity: str = "info",
    default: ReportFact | None = None,
) -> tuple[ReportFact, ...]:
    facts = tuple(
        ReportFact(label=label, value=value.strip(), severity=severity)
        for value in values
        if value.strip()
    )
    if not facts and default is not None:
        return (default,)
    return facts


def _derive_summary_status(
    *,
    incident_evaluation: IncidentEvaluation,
    latest_heartbeat_status: str | None,
) -> str:
    states = incident_evaluation.states
    if any(state.status == INCIDENT_STATUS_ACTIVE for state in states):
        return SUMMARY_STATUS_INCIDENT
    if any(state.status == INCIDENT_STATUS_CANDIDATE for state in states):
        return SUMMARY_STATUS_DEGRADED
    if latest_heartbeat_status is not None and latest_heartbeat_status != "healthy":
        return SUMMARY_STATUS_DEGRADED
    if any(
        transition.action == "recovered"
        for transition in incident_evaluation.transitions
    ):
        return SUMMARY_STATUS_RECOVERED
    return SUMMARY_STATUS_HEALTHY


def _outbox_counts(snapshot: IncidentStoreSnapshot) -> dict[str, int]:
    counts = {status: 0 for status in OUTBOX_STATUS_ORDER}
    for item in snapshot.outbox_items:
        counts[item.status] = counts.get(item.status, 0) + 1
    return counts


def _state_count(states: Sequence[IncidentState], status: str) -> int:
    return sum(1 for state in states if state.status == status)


def _state_sort_key(state: IncidentState) -> tuple[int, str, str]:
    return (
        _STATUS_RANK.get(state.status, 99),
        state.kind,
        state.subject,
    )


def _state_summary(state: IncidentState) -> str:
    cycle_label = (
        "none"
        if state.last_cycle_sequence is None
        else str(state.last_cycle_sequence)
    )
    return (
        f"severity={state.severity}, reason={state.last_reason}, "
        f"failure_count={state.failure_count}, recovery_count={state.recovery_count}, "
        f"occurrence_count={state.occurrence_count}, last_cycle={cycle_label}, "
        f"last_observed_at={_format_datetime(state.last_observed_at)}"
    )


def _transition_summary(transition: IncidentTransition) -> str:
    cycle_label = (
        "none"
        if transition.cycle_sequence is None
        else str(transition.cycle_sequence)
    )
    return (
        f"status={transition.status}, reason={transition.reason}, "
        f"failure_count={transition.failure_count}, "
        f"recovery_count={transition.recovery_count}, "
        f"occurrence_count={transition.occurrence_count}, cycle={cycle_label}, "
        f"observed_at={_format_datetime(transition.observed_at)}"
    )


def _redact_url(match: re.Match[str]) -> str:
    value = match.group(0)
    query_index = value.find("?")
    fragment_index = value.find("#")
    cut_positions = [
        index for index in (query_index, fragment_index) if index != -1
    ]
    cut_at = min(cut_positions)
    return f"{value[:cut_at]}[redacted-query]"


def _bounded_text(text: str, *, max_chars: int) -> str:
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("max_chars must be a positive integer")
    if len(text) <= max_chars:
        return text
    marker = "\n[truncated: monitoring report exceeded configured character limit]\n"
    if max_chars <= len(marker):
        return marker[:max_chars]
    return text[: max_chars - len(marker)].rstrip() + marker


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _validate_optional_non_negative_int(value: int | None, *, context: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{context} must be a non-negative integer or None")


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{context} must include a timezone")


__all__ = [
    "DRAFT_PROMPT_LINE",
    "REPORT_RENDERER_VERSION",
    "SUMMARY_STATUS_DEGRADED",
    "SUMMARY_STATUS_HEALTHY",
    "SUMMARY_STATUS_INCIDENT",
    "SUMMARY_STATUS_RECOVERED",
    "MonitoringReportSnapshot",
    "ReportFact",
    "build_monitoring_report_snapshot",
    "redact_monitoring_text",
    "render_monitoring_report",
    "render_programming_agent_prompt",
]
