from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re


ORCHESTRATOR_CONTRACT_VERSION = 1
ORCHESTRATOR_MODE_FILE_ONLY = "file_only"
ORCHESTRATOR_EVENT = "monitoring_orchestrator_snapshot"
REGISTRY_EVENT = "monitoring_orchestrator_registry"
SOURCE_SNAPSHOT_EVENT = "monitoring_orchestrator_source_snapshot"

AGENT_KIND_REMOTE_OBSERVER = "remote_observer"
AGENT_KIND_LOCAL_FACADE_AGENT = "local_facade_agent"
VALID_AGENT_KINDS = {
    AGENT_KIND_REMOTE_OBSERVER,
    AGENT_KIND_LOCAL_FACADE_AGENT,
}
LOCATION_SUPERVISION_CENTER = "supervision_center"
LOCATION_MAIN_WORKSTATION = "main_workstation"
VALID_LOCATIONS = {
    LOCATION_SUPERVISION_CENTER,
    LOCATION_MAIN_WORKSTATION,
}
PAYLOAD_KIND_AGENT_SNAPSHOT_V1 = "agent_snapshot_v1"
PAYLOAD_KIND_LOCAL_AGENT_FACADE_V1 = "local_agent_facade_v1"
PAYLOAD_KIND_REMOTE_AGENT_AUDIT_V8 = "remote_agent_audit_v8"
VALID_PAYLOAD_KINDS = {
    PAYLOAD_KIND_AGENT_SNAPSHOT_V1,
    PAYLOAD_KIND_LOCAL_AGENT_FACADE_V1,
    PAYLOAD_KIND_REMOTE_AGENT_AUDIT_V8,
}

STATUS_OK = "ok"
STATUS_DEGRADED = "degraded"
STATUS_ERROR = "error"
STATUS_UNAVAILABLE = "unavailable"
STATUS_UNKNOWN = "unknown"
VALID_STATUSES = {
    STATUS_OK,
    STATUS_DEGRADED,
    STATUS_ERROR,
    STATUS_UNAVAILABLE,
    STATUS_UNKNOWN,
}
STATUS_ORDER = {
    STATUS_OK: 0,
    STATUS_UNKNOWN: 1,
    STATUS_DEGRADED: 2,
    STATUS_UNAVAILABLE: 3,
    STATUS_ERROR: 4,
}

FRESHNESS_FRESH = "fresh"
FRESHNESS_STALE = "stale"
FRESHNESS_MISSING = "missing"
FRESHNESS_INVALID = "invalid"
VALID_FRESHNESS = {
    FRESHNESS_FRESH,
    FRESHNESS_STALE,
    FRESHNESS_MISSING,
    FRESHNESS_INVALID,
}

SIGNAL_EXTERNAL_DATABASE_DEGRADED = "external_database_endpoint_degraded"
SIGNAL_EXTERNAL_DATABASE_UNAVAILABLE = "external_database_endpoint_unavailable"
SIGNAL_EXTERNAL_SCHEDULER_DEGRADED = "external_scheduler_endpoint_degraded"
SIGNAL_DATABASE_AVAILABILITY_DEGRADED = "database_availability_degraded"
SIGNAL_SCHEDULER_RECENT_FAILURES = "scheduler_recent_failures"
SIGNAL_SCHEDULER_HISTORICAL_ERRORS_NO_RECENT_FAILURES = (
    "scheduler_historical_error_states_no_recent_failures"
)

CORRELATION_DATABASE_PATH_CONFIRMED = "database_path_confirmed"
CORRELATION_SCHEDULER_STATUS_MIXED_EVIDENCE = (
    "scheduler_status_mixed_evidence"
)
CORRELATION_SCHEDULER_HISTORICAL_STATUS_ONLY = (
    "scheduler_historical_error_states_no_recent_failures"
)
CORRELATION_SOURCE_UNAVAILABLE = "source_unavailable"
CORRELATION_SOURCE_STALE = "source_stale"
CORRELATION_SOURCE_INVALID = "source_invalid"

ORCHESTRATOR_SAFETY_BOUNDARY = (
    "File-only/shadow-only orchestrator output; legacy alerts remain authoritative.",
    "The orchestrator consumes supplied sanitized snapshots and does not poll endpoints, read .env, send email, call interpretation providers, mutate state, or control processes.",
    "No alert may be replaced, disabled, rerouted, downgraded, or acknowledged from this output without separate approval.",
)

SAFE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,119}$")
SAFE_GAP_RE = re.compile(r"^[a-z0-9][a-z0-9_.:-]{0,119}$")


class OrchestratorError(ValueError):
    """Raised for fail-closed orchestrator configuration errors."""


@dataclass(frozen=True)
class AgentRegistryEntry:
    agent_key: str
    agent_kind: str
    location: str
    source_file: Path
    payload_kind: str
    contract_version_min: int
    contract_version_max: int
    stale_after_seconds: float
    status_mapping_version: int = 1
    enabled: bool = True

    def __post_init__(self) -> None:
        _require_safe_identifier(self.agent_key, context="agent_key")
        if self.agent_kind not in VALID_AGENT_KINDS:
            raise OrchestratorError("agent_kind is unsupported")
        if self.location not in VALID_LOCATIONS:
            raise OrchestratorError("location is unsupported")
        if self.payload_kind not in VALID_PAYLOAD_KINDS:
            raise OrchestratorError("payload_kind is unsupported")
        if self.contract_version_min < 1:
            raise OrchestratorError("contract_version_min must be positive")
        if self.contract_version_max < self.contract_version_min:
            raise OrchestratorError("contract version range is invalid")
        _require_positive_finite(
            self.stale_after_seconds,
            context="stale_after_seconds",
        )
        if self.status_mapping_version != 1:
            raise OrchestratorError("status_mapping_version is unsupported")
        _reject_env_path(self.source_file)

    def contract_supported(self, version: int | None) -> bool:
        return (
            version is not None
            and self.contract_version_min <= version <= self.contract_version_max
        )


@dataclass(frozen=True)
class AgentSnapshot:
    agent_key: str
    agent_kind: str
    location: str
    status: str
    freshness_status: str
    observed_at: datetime
    stale_after_seconds: float
    source_contract_version: int | None = None
    source_checked_at: datetime | None = None
    source_state_updated_at: datetime | None = None
    source_age_seconds: float | None = None
    summary_counts: Mapping[str, int | float] | None = None
    evidence_gaps: Sequence[str] = ()
    signals: Sequence[str] = ()
    source_digest: str | None = None
    orchestrator_contract_version: int = ORCHESTRATOR_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_safe_identifier(self.agent_key, context="agent_key")
        if self.agent_kind not in VALID_AGENT_KINDS:
            raise OrchestratorError("snapshot agent_kind is unsupported")
        if self.location not in VALID_LOCATIONS:
            raise OrchestratorError("snapshot location is unsupported")
        if self.status not in VALID_STATUSES:
            raise OrchestratorError("snapshot status is unsupported")
        if self.freshness_status not in VALID_FRESHNESS:
            raise OrchestratorError("snapshot freshness status is unsupported")
        _require_aware_datetime(self.observed_at, context="observed_at")
        _require_positive_finite(
            self.stale_after_seconds,
            context="stale_after_seconds",
        )
        if self.source_checked_at is not None:
            _require_aware_datetime(
                self.source_checked_at,
                context="source_checked_at",
            )
        if self.source_state_updated_at is not None:
            _require_aware_datetime(
                self.source_state_updated_at,
                context="source_state_updated_at",
            )
        if self.source_age_seconds is not None:
            _require_non_negative_finite(
                self.source_age_seconds,
                context="source_age_seconds",
            )
        for gap in self.evidence_gaps:
            _require_safe_identifier(gap, context="evidence_gap")
        for signal in self.signals:
            _require_safe_identifier(signal, context="signal")

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_key": self.agent_key,
            "agent_kind": self.agent_kind,
            "evidence_gaps": list(self.evidence_gaps),
            "freshness_status": self.freshness_status,
            "location": self.location,
            "observed_at": _format_datetime(self.observed_at),
            "orchestrator_contract_version": self.orchestrator_contract_version,
            "signals": list(self.signals),
            "source_age_seconds": _round_optional(self.source_age_seconds),
            "source_checked_at": _format_optional_datetime(self.source_checked_at),
            "source_contract_version": self.source_contract_version,
            "source_digest": self.source_digest,
            "source_state_updated_at": _format_optional_datetime(
                self.source_state_updated_at,
            ),
            "stale_after_seconds": round(self.stale_after_seconds, 3),
            "status": self.status,
            "summary_counts": _sorted_counts(self.summary_counts or {}),
        }


@dataclass(frozen=True)
class CorrelationFinding:
    kind: str
    status: str
    agent_keys: tuple[str, ...]
    evidence_gaps: tuple[str, ...] = ()
    summary: str = ""

    def __post_init__(self) -> None:
        _require_safe_identifier(self.kind, context="correlation kind")
        if self.status not in VALID_STATUSES:
            raise OrchestratorError("correlation status is unsupported")
        if not self.agent_keys:
            raise OrchestratorError("correlation agent_keys are required")
        for agent_key in self.agent_keys:
            _require_safe_identifier(agent_key, context="correlation agent_key")
        for gap in self.evidence_gaps:
            _require_safe_identifier(gap, context="correlation evidence_gap")

    def to_dict(self) -> dict[str, object]:
        return {
            "agent_keys": list(self.agent_keys),
            "evidence_gaps": list(self.evidence_gaps),
            "kind": self.kind,
            "status": self.status,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class OrchestratorSnapshot:
    generated_at: datetime
    agents: tuple[AgentSnapshot, ...]
    correlations: tuple[CorrelationFinding, ...]
    mode: str = ORCHESTRATOR_MODE_FILE_ONLY
    contract_version: int = ORCHESTRATOR_CONTRACT_VERSION
    safety_boundary: tuple[str, ...] = ORCHESTRATOR_SAFETY_BOUNDARY

    def __post_init__(self) -> None:
        _require_aware_datetime(self.generated_at, context="generated_at")
        if self.mode != ORCHESTRATOR_MODE_FILE_ONLY:
            raise OrchestratorError("orchestrator mode is unsupported")
        if self.contract_version != ORCHESTRATOR_CONTRACT_VERSION:
            raise OrchestratorError("orchestrator contract is unsupported")
        _validate_unique_agent_keys(self.agents)

    @property
    def status(self) -> str:
        if not self.agents:
            return STATUS_UNKNOWN
        return max(
            (agent.status for agent in self.agents),
            key=lambda status: STATUS_ORDER.get(status, STATUS_ORDER[STATUS_ERROR]),
        )

    @property
    def metrics(self) -> dict[str, object]:
        status_counts = Counter(agent.status for agent in self.agents)
        freshness_counts = Counter(agent.freshness_status for agent in self.agents)
        return {
            "agent_count": len(self.agents),
            "correlation_count": len(self.correlations),
            "freshness_counts": {
                key: freshness_counts.get(key, 0)
                for key in sorted(VALID_FRESHNESS)
            },
            "status_counts": {
                key: status_counts.get(key, 0)
                for key in sorted(VALID_STATUSES)
            },
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "agents": [agent.to_dict() for agent in self.agents],
            "contract_version": self.contract_version,
            "correlations": [
                correlation.to_dict() for correlation in self.correlations
            ],
            "event": ORCHESTRATOR_EVENT,
            "generated_at": _format_datetime(self.generated_at),
            "metrics": self.metrics,
            "mode": self.mode,
            "safety_boundary": list(self.safety_boundary),
            "status": self.status,
        }


def load_registry_file(path: Path) -> tuple[AgentRegistryEntry, ...]:
    resolved = path.resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return registry_entries_from_payload(payload, base_dir=resolved.parent)


def registry_entries_from_payload(
    payload: object,
    *,
    base_dir: Path,
) -> tuple[AgentRegistryEntry, ...]:
    registry = _require_mapping(payload, context="registry")
    contract_version = _coerce_int(registry.get("contract_version"))
    if contract_version != ORCHESTRATOR_CONTRACT_VERSION:
        raise OrchestratorError("registry contract is unsupported")
    event = str(registry.get("event", REGISTRY_EVENT)).strip()
    if event != REGISTRY_EVENT:
        raise OrchestratorError("registry event is unsupported")
    mode = str(registry.get("mode", ORCHESTRATOR_MODE_FILE_ONLY)).strip()
    if mode != ORCHESTRATOR_MODE_FILE_ONLY:
        raise OrchestratorError("registry mode is unsupported")
    agents_raw = registry.get("agents")
    if not isinstance(agents_raw, list):
        raise OrchestratorError("registry agents must be a list")
    entries = tuple(
        _registry_entry_from_mapping(_require_mapping(item, context="agent"), base_dir)
        for item in agents_raw
        if bool(_require_mapping(item, context="agent").get("enabled", True))
    )
    _validate_unique_registry_keys(entries)
    if not entries:
        raise OrchestratorError("registry must enable at least one agent")
    return entries


def build_orchestrator_snapshot(
    registry_entries: Sequence[AgentRegistryEntry],
    *,
    generated_at: datetime | None = None,
) -> OrchestratorSnapshot:
    now = generated_at or datetime.now(timezone.utc)
    _require_aware_datetime(now, context="generated_at")
    _validate_unique_registry_keys(registry_entries)
    agents = tuple(
        _load_agent_snapshot(entry, observed_at=now)
        for entry in registry_entries
        if entry.enabled
    )
    return OrchestratorSnapshot(
        generated_at=now,
        agents=agents,
        correlations=correlate_agent_snapshots(agents),
    )


def correlate_agent_snapshots(
    agents: Sequence[AgentSnapshot],
) -> tuple[CorrelationFinding, ...]:
    by_key = {agent.agent_key: agent for agent in agents}
    findings: list[CorrelationFinding] = []

    for agent in agents:
        if agent.freshness_status == FRESHNESS_MISSING:
            findings.append(
                CorrelationFinding(
                    kind=CORRELATION_SOURCE_UNAVAILABLE,
                    status=STATUS_DEGRADED,
                    agent_keys=(agent.agent_key,),
                    evidence_gaps=tuple(agent.evidence_gaps),
                    summary="Source snapshot is missing or unavailable.",
                )
            )
        elif agent.freshness_status == FRESHNESS_INVALID:
            findings.append(
                CorrelationFinding(
                    kind=CORRELATION_SOURCE_INVALID,
                    status=STATUS_DEGRADED,
                    agent_keys=(agent.agent_key,),
                    evidence_gaps=tuple(agent.evidence_gaps),
                    summary="Source snapshot is invalid or contract-incompatible.",
                )
            )
        elif agent.freshness_status == FRESHNESS_STALE:
            findings.append(
                CorrelationFinding(
                    kind=CORRELATION_SOURCE_STALE,
                    status=STATUS_DEGRADED,
                    agent_keys=(agent.agent_key,),
                    evidence_gaps=tuple(agent.evidence_gaps),
                    summary="Source snapshot is stale.",
                )
            )

    remote = _first_agent_with_kind(agents, AGENT_KIND_REMOTE_OBSERVER)
    db_local = by_key.get("database_availability")
    scheduler_local = by_key.get("scheduler_metrics")

    if remote is not None and db_local is not None:
        remote_db_degraded = _has_any_signal(
            remote,
            {
                SIGNAL_EXTERNAL_DATABASE_DEGRADED,
                SIGNAL_EXTERNAL_DATABASE_UNAVAILABLE,
            },
        )
        local_db_degraded = (
            db_local.status in {STATUS_DEGRADED, STATUS_ERROR, STATUS_UNAVAILABLE}
            or _has_signal(db_local, SIGNAL_DATABASE_AVAILABILITY_DEGRADED)
        )
        if remote_db_degraded and local_db_degraded:
            findings.append(
                CorrelationFinding(
                    kind=CORRELATION_DATABASE_PATH_CONFIRMED,
                    status=STATUS_DEGRADED,
                    agent_keys=(remote.agent_key, db_local.agent_key),
                    summary=(
                        "External database-path degradation is confirmed by "
                        "the local DB-availability aggregate."
                    ),
                )
            )

    if remote is not None and scheduler_local is not None:
        if _has_signal(remote, SIGNAL_EXTERNAL_SCHEDULER_DEGRADED) and _has_signal(
            scheduler_local,
            SIGNAL_SCHEDULER_HISTORICAL_ERRORS_NO_RECENT_FAILURES,
        ):
            findings.append(
                CorrelationFinding(
                    kind=CORRELATION_SCHEDULER_STATUS_MIXED_EVIDENCE,
                    status=STATUS_DEGRADED,
                    agent_keys=(remote.agent_key, scheduler_local.agent_key),
                    summary=(
                        "Scheduler endpoint evidence is degraded while local "
                        "scheduler metrics show historical errors but no "
                        "recent failures."
                    ),
                )
            )

    if scheduler_local is not None and _only_scheduler_historical_degraded(
        agents,
        scheduler_local,
    ):
        findings.append(
            CorrelationFinding(
                kind=CORRELATION_SCHEDULER_HISTORICAL_STATUS_ONLY,
                status=STATUS_DEGRADED,
                agent_keys=(scheduler_local.agent_key,),
                summary=(
                    "Global degradation is limited to historical scheduler "
                    "last-error states with zero recent failures."
                ),
            )
        )

    return tuple(findings)


def render_orchestrator_snapshot(snapshot: OrchestratorSnapshot) -> str:
    lines = [
        "# Monitoring orchestrator snapshot",
        "",
        f"Generated at: {_format_datetime(snapshot.generated_at)}",
        f"Contract version: {snapshot.contract_version}",
        f"Mode: {snapshot.mode}",
        f"Status: {snapshot.status}",
        "",
        "## Agent rollup",
    ]
    for agent in snapshot.agents:
        lines.append(
            "- "
            f"{agent.agent_key}: status={agent.status}, "
            f"freshness={agent.freshness_status}, "
            f"gaps={len(agent.evidence_gaps)}"
        )
    lines.extend(
        [
            "",
            "## Correlations",
        ]
    )
    if snapshot.correlations:
        for finding in snapshot.correlations:
            agent_keys = ",".join(finding.agent_keys)
            lines.append(
                "- "
                f"{finding.kind}: status={finding.status}, "
                f"agents={agent_keys}"
            )
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Safety boundary",
        ]
    )
    lines.extend(f"- {item}" for item in snapshot.safety_boundary)
    return "\n".join(lines) + "\n"


def _registry_entry_from_mapping(
    item: Mapping[str, object],
    base_dir: Path,
) -> AgentRegistryEntry:
    source_file = _resolve_source_file(item, base_dir=base_dir)
    return AgentRegistryEntry(
        agent_key=_require_text(item.get("agent_key"), context="agent_key"),
        agent_kind=_require_text(item.get("agent_kind"), context="agent_kind"),
        location=_require_text(item.get("location"), context="location"),
        source_file=source_file,
        payload_kind=_require_text(item.get("payload_kind"), context="payload_kind"),
        contract_version_min=_require_positive_int(
            item.get("contract_version_min"),
            context="contract_version_min",
        ),
        contract_version_max=_require_positive_int(
            item.get("contract_version_max"),
            context="contract_version_max",
        ),
        stale_after_seconds=_require_positive_float(
            item.get("stale_after_seconds"),
            context="stale_after_seconds",
        ),
        status_mapping_version=_require_positive_int(
            item.get("status_mapping_version", 1),
            context="status_mapping_version",
        ),
        enabled=bool(item.get("enabled", True)),
    )


def _resolve_source_file(item: Mapping[str, object], *, base_dir: Path) -> Path:
    if "source_file" in item:
        source = item["source_file"]
    else:
        source_mapping = _require_mapping(item.get("source"), context="source")
        source_type = str(source_mapping.get("type", "file")).strip()
        if source_type != "file":
            raise OrchestratorError("only file sources are supported")
        source = source_mapping.get("path")
    source_text = _require_text(source, context="source_file")
    source_path = Path(source_text)
    if not source_path.is_absolute():
        source_path = base_dir / source_path
    resolved = source_path.resolve()
    _reject_env_path(resolved)
    return resolved


def _load_agent_snapshot(
    entry: AgentRegistryEntry,
    *,
    observed_at: datetime,
) -> AgentSnapshot:
    try:
        payload = json.loads(entry.source_file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _unavailable_snapshot(
            entry,
            observed_at=observed_at,
            freshness_status=FRESHNESS_MISSING,
            evidence_gaps=("source_unavailable",),
        )
    except OSError:
        return _unavailable_snapshot(
            entry,
            observed_at=observed_at,
            freshness_status=FRESHNESS_MISSING,
            evidence_gaps=("source_unavailable",),
        )
    except json.JSONDecodeError:
        return _unavailable_snapshot(
            entry,
            observed_at=observed_at,
            freshness_status=FRESHNESS_INVALID,
            evidence_gaps=("source_invalid_json",),
        )

    try:
        if entry.payload_kind == PAYLOAD_KIND_AGENT_SNAPSHOT_V1:
            return _snapshot_from_generic_payload(
                entry,
                payload,
                observed_at=observed_at,
            )
        if entry.payload_kind == PAYLOAD_KIND_LOCAL_AGENT_FACADE_V1:
            return _snapshot_from_local_facade_payload(
                entry,
                payload,
                observed_at=observed_at,
            )
        if entry.payload_kind == PAYLOAD_KIND_REMOTE_AGENT_AUDIT_V8:
            return _snapshot_from_remote_audit_payload(
                entry,
                payload,
                observed_at=observed_at,
            )
    except OrchestratorError as exc:
        return _unavailable_snapshot(
            entry,
            observed_at=observed_at,
            freshness_status=FRESHNESS_INVALID,
            evidence_gaps=(str(exc),),
        )
    raise OrchestratorError("unsupported payload kind")


def _snapshot_from_generic_payload(
    entry: AgentRegistryEntry,
    payload: object,
    *,
    observed_at: datetime,
) -> AgentSnapshot:
    source = _require_mapping(payload, context="source snapshot")
    event = str(source.get("event", SOURCE_SNAPSHOT_EVENT)).strip()
    if event != SOURCE_SNAPSHOT_EVENT:
        raise OrchestratorError("source_event_unsupported")
    payload_agent_key = source.get("agent_key")
    if payload_agent_key is not None and str(payload_agent_key).strip() != entry.agent_key:
        raise OrchestratorError("source_agent_key_mismatch")
    source_contract_version = _coerce_int(source.get("contract_version"))
    _require_supported_source_contract(entry, source_contract_version)
    status = _normalize_status(source.get("status"))
    evidence_gaps = _bounded_identifier_tuple(source.get("evidence_gaps", ()))
    summary_counts = _summary_counts_from_mapping(source.get("summary_counts", {}))
    signals = _bounded_identifier_tuple(source.get("signals", ()))
    source_checked_at = _parse_datetime_or_none(source.get("checked_at"))
    source_state_updated_at = _parse_datetime_or_none(source.get("state_updated_at"))
    source_age_seconds = _coerce_optional_non_negative_float(
        source.get("state_age_seconds", source.get("source_age_seconds")),
    )
    stale_after_seconds = entry.stale_after_seconds
    freshness_status, status, evidence_gaps = _apply_freshness(
        status=status,
        evidence_gaps=evidence_gaps,
        source_age_seconds=source_age_seconds,
        stale_after_seconds=stale_after_seconds,
    )
    digest = _source_digest(
        {
            "agent_key": entry.agent_key,
            "contract_version": source_contract_version,
            "evidence_gaps": evidence_gaps,
            "signals": signals,
            "status": status,
            "summary_counts": summary_counts,
        }
    )
    return AgentSnapshot(
        agent_key=entry.agent_key,
        agent_kind=entry.agent_kind,
        location=entry.location,
        status=status,
        freshness_status=freshness_status,
        observed_at=observed_at,
        stale_after_seconds=stale_after_seconds,
        source_contract_version=source_contract_version,
        source_checked_at=source_checked_at,
        source_state_updated_at=source_state_updated_at,
        source_age_seconds=source_age_seconds,
        summary_counts=summary_counts,
        evidence_gaps=evidence_gaps,
        signals=signals,
        source_digest=digest,
    )


def _snapshot_from_local_facade_payload(
    entry: AgentRegistryEntry,
    payload: object,
    *,
    observed_at: datetime,
) -> AgentSnapshot:
    source = _require_mapping(payload, context="local facade source")
    payload_agent_key = _require_text(source.get("agent_key"), context="agent_key")
    if payload_agent_key != entry.agent_key:
        raise OrchestratorError("source_agent_key_mismatch")
    source_contract_version = _coerce_int(source.get("contract_version"))
    _require_supported_source_contract(entry, source_contract_version)
    status = _normalize_status(source.get("status"))
    evidence_gaps = _bounded_identifier_tuple(source.get("evidence_gaps", ()))
    stale_after_seconds = entry.stale_after_seconds
    source_age_seconds = _coerce_optional_non_negative_float(
        source.get("state_age_seconds"),
    )
    summary_counts = _local_facade_summary_counts(source)
    signals = _local_facade_signals(entry.agent_key, status, summary_counts)
    freshness_status, status, evidence_gaps = _apply_freshness(
        status=status,
        evidence_gaps=evidence_gaps,
        source_age_seconds=source_age_seconds,
        stale_after_seconds=stale_after_seconds,
    )
    digest = _source_digest(
        {
            "agent_key": entry.agent_key,
            "contract_version": source_contract_version,
            "evidence_gaps": evidence_gaps,
            "signals": signals,
            "status": status,
            "summary_counts": summary_counts,
        }
    )
    return AgentSnapshot(
        agent_key=entry.agent_key,
        agent_kind=entry.agent_kind,
        location=entry.location,
        status=status,
        freshness_status=freshness_status,
        observed_at=observed_at,
        stale_after_seconds=stale_after_seconds,
        source_contract_version=source_contract_version,
        source_checked_at=_parse_datetime_or_none(source.get("checked_at")),
        source_state_updated_at=_parse_datetime_or_none(source.get("state_updated_at")),
        source_age_seconds=source_age_seconds,
        summary_counts=summary_counts,
        evidence_gaps=evidence_gaps,
        signals=signals,
        source_digest=digest,
    )


def _snapshot_from_remote_audit_payload(
    entry: AgentRegistryEntry,
    payload: object,
    *,
    observed_at: datetime,
) -> AgentSnapshot:
    source = _require_mapping(payload, context="remote audit source")
    if source.get("event") != "agent_state_audit":
        raise OrchestratorError("source_event_unsupported")
    source_contract_version = _coerce_int(source.get("audit_contract_version"))
    _require_supported_source_contract(entry, source_contract_version)
    latest_heartbeat = _require_mapping(
        source.get("latest_heartbeat"),
        context="latest_heartbeat",
    )
    raw_status = str(latest_heartbeat.get("status", "")).strip().lower()
    status = _normalize_remote_status(raw_status)
    evidence_gaps = _bounded_identifier_tuple(source.get("evidence_gaps", ()))
    summary_counts = _remote_audit_summary_counts(source, latest_heartbeat)
    signals = tuple(
        dict.fromkeys(
            (
                *_bounded_identifier_tuple(source.get("signals", ())),
                *_remote_audit_signals(status, summary_counts),
            )
        )
    )
    source_checked_at = _parse_datetime_or_none(
        source.get(
            "captured_at",
            source.get("checked_at", source.get("generated_at")),
        ),
    )
    if source_checked_at is None:
        evidence_gaps = tuple(
            dict.fromkeys((*evidence_gaps, "source_timestamp_missing"))
        )
    digest = _source_digest(
        {
            "contract_version": source_contract_version,
            "evidence_gaps": evidence_gaps,
            "signals": signals,
            "status": status,
            "summary_counts": summary_counts,
        }
    )
    return AgentSnapshot(
        agent_key=entry.agent_key,
        agent_kind=entry.agent_kind,
        location=entry.location,
        status=status,
        freshness_status=FRESHNESS_FRESH,
        observed_at=observed_at,
        stale_after_seconds=entry.stale_after_seconds,
        source_contract_version=source_contract_version,
        source_checked_at=source_checked_at,
        source_state_updated_at=source_checked_at,
        source_age_seconds=None,
        summary_counts=summary_counts,
        evidence_gaps=evidence_gaps,
        signals=signals,
        source_digest=digest,
    )


def _unavailable_snapshot(
    entry: AgentRegistryEntry,
    *,
    observed_at: datetime,
    freshness_status: str,
    evidence_gaps: Sequence[str],
) -> AgentSnapshot:
    return AgentSnapshot(
        agent_key=entry.agent_key,
        agent_kind=entry.agent_kind,
        location=entry.location,
        status=STATUS_UNAVAILABLE,
        freshness_status=freshness_status,
        observed_at=observed_at,
        stale_after_seconds=entry.stale_after_seconds,
        evidence_gaps=_bounded_identifier_tuple(evidence_gaps),
        summary_counts={},
        signals=(),
        source_digest=None,
    )


def _require_supported_source_contract(
    entry: AgentRegistryEntry,
    source_contract_version: int | None,
) -> None:
    if not entry.contract_supported(source_contract_version):
        raise OrchestratorError("source_contract_mismatch")


def _apply_freshness(
    *,
    status: str,
    evidence_gaps: Sequence[str],
    source_age_seconds: float | None,
    stale_after_seconds: float,
) -> tuple[str, str, tuple[str, ...]]:
    gaps = tuple(evidence_gaps)
    if source_age_seconds is None:
        return FRESHNESS_FRESH, status, gaps
    if source_age_seconds > stale_after_seconds:
        status = STATUS_DEGRADED if status == STATUS_OK else status
        gaps = tuple(dict.fromkeys((*gaps, "source_stale")))
        return FRESHNESS_STALE, status, gaps
    return FRESHNESS_FRESH, status, gaps


def _local_facade_summary_counts(
    source: Mapping[str, object],
) -> dict[str, int | float]:
    allowed = (
        "service_count",
        "unavailable_service_count",
        "stale_service_count",
        "pending_event_count",
        "delivered_event_count_24h",
        "recent_transition_count",
        "job_count",
        "success_count_24h",
        "failure_count_24h",
        "error_job_count",
        "degraded_job_count",
    )
    return {
        key: value
        for key in allowed
        if (value := _coerce_optional_count(source.get(key))) is not None
    }


def _local_facade_signals(
    agent_key: str,
    status: str,
    summary_counts: Mapping[str, int | float],
) -> tuple[str, ...]:
    signals: list[str] = []
    if agent_key == "database_availability":
        unavailable = int(summary_counts.get("unavailable_service_count", 0))
        if status in {STATUS_DEGRADED, STATUS_ERROR, STATUS_UNAVAILABLE} or unavailable:
            signals.append(SIGNAL_DATABASE_AVAILABILITY_DEGRADED)
    if agent_key == "scheduler_metrics":
        failure_count = int(summary_counts.get("failure_count_24h", 0))
        error_job_count = int(summary_counts.get("error_job_count", 0))
        if failure_count > 0:
            signals.append(SIGNAL_SCHEDULER_RECENT_FAILURES)
        if failure_count == 0 and error_job_count > 0:
            signals.append(SIGNAL_SCHEDULER_HISTORICAL_ERRORS_NO_RECENT_FAILURES)
    return tuple(signals)


def _remote_audit_summary_counts(
    source: Mapping[str, object],
    latest_heartbeat: Mapping[str, object],
) -> dict[str, int | float]:
    configuration = source.get("configuration")
    shadow_incidents = source.get("shadow_incidents")
    counts: dict[str, int | float] = {}
    if isinstance(configuration, Mapping):
        endpoint_count = _coerce_optional_count(configuration.get("endpoint_count"))
        if endpoint_count is not None:
            counts["endpoint_count"] = endpoint_count
    for key, source_key in (
        ("latest_observation_count", "observation_count"),
        ("latest_transport_failure_count", "transport_failure_count"),
    ):
        value = _coerce_optional_count(latest_heartbeat.get(source_key))
        if value is not None:
            counts[key] = value
    if isinstance(shadow_incidents, Mapping):
        for key in (
            "active_state_count",
            "candidate_state_count",
            "outbox_pending_count",
            "outbox_sent_count",
            "transition_record_count",
        ):
            value = _coerce_optional_count(shadow_incidents.get(key))
            if value is not None:
                counts[f"shadow_{key}"] = value
    return counts


def _remote_audit_signals(
    status: str,
    summary_counts: Mapping[str, int | float],
) -> tuple[str, ...]:
    signals: list[str] = []
    if status in {STATUS_DEGRADED, STATUS_ERROR, STATUS_UNAVAILABLE}:
        signals.append("external_health_degraded")
    if int(summary_counts.get("latest_transport_failure_count", 0)) > 0:
        signals.append("external_transport_failures")
    return tuple(signals)


def _only_scheduler_historical_degraded(
    agents: Sequence[AgentSnapshot],
    scheduler_local: AgentSnapshot,
) -> bool:
    if not _has_signal(
        scheduler_local,
        SIGNAL_SCHEDULER_HISTORICAL_ERRORS_NO_RECENT_FAILURES,
    ):
        return False
    if _has_signal(scheduler_local, SIGNAL_SCHEDULER_RECENT_FAILURES):
        return False
    for agent in agents:
        if agent.agent_key == scheduler_local.agent_key:
            if agent.status != STATUS_DEGRADED:
                return False
            continue
        if agent.status != STATUS_OK or agent.freshness_status != FRESHNESS_FRESH:
            return False
    return True


def _first_agent_with_kind(
    agents: Sequence[AgentSnapshot],
    agent_kind: str,
) -> AgentSnapshot | None:
    return next((agent for agent in agents if agent.agent_kind == agent_kind), None)


def _has_signal(agent: AgentSnapshot, signal: str) -> bool:
    return signal in set(agent.signals)


def _has_any_signal(agent: AgentSnapshot, signals: set[str]) -> bool:
    return bool(signals & set(agent.signals))


def _validate_unique_registry_keys(entries: Sequence[AgentRegistryEntry]) -> None:
    keys = [entry.agent_key for entry in entries]
    if len(set(keys)) != len(keys):
        raise OrchestratorError("duplicate_agent_key")


def _validate_unique_agent_keys(agents: Sequence[AgentSnapshot]) -> None:
    keys = [agent.agent_key for agent in agents]
    if len(set(keys)) != len(keys):
        raise OrchestratorError("duplicate_agent_key")


def _require_mapping(value: object, *, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise OrchestratorError(f"{context}_invalid")
    return value


def _require_text(value: object, *, context: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise OrchestratorError(f"{context}_required")
    return text


def _require_positive_int(value: object, *, context: str) -> int:
    number = _coerce_int(value)
    if number is None or number < 1:
        raise OrchestratorError(f"{context}_invalid")
    return number


def _require_positive_float(value: object, *, context: str) -> float:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise OrchestratorError(f"{context}_invalid") from exc
    _require_positive_finite(number, context=context)
    return number


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _coerce_optional_count(value: object) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return value if math.isfinite(value) and value >= 0 else None
    return None


def _coerce_optional_non_negative_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _coerce_optional_positive_float(value: object) -> float | None:
    number = _coerce_optional_non_negative_float(value)
    if number is None or number <= 0:
        return None
    return number


def _summary_counts_from_mapping(value: object) -> dict[str, int | float]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int | float] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not SAFE_KEY_RE.fullmatch(key):
            continue
        count = _coerce_optional_count(raw_value)
        if count is not None:
            counts[key] = count
    return _sorted_counts(counts)


def _bounded_identifier_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        items = (value,)
    elif isinstance(value, Sequence):
        items = value
    else:
        return ()
    output: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if SAFE_GAP_RE.fullmatch(text):
            output.append(text)
    return tuple(dict.fromkeys(output))


def _normalize_status(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in VALID_STATUSES:
        return text
    if text == "healthy":
        return STATUS_OK
    if text in {"failed", "failure"}:
        return STATUS_ERROR
    return STATUS_UNKNOWN


def _normalize_remote_status(value: str) -> str:
    if value == "healthy":
        return STATUS_OK
    return _normalize_status(value)


def _parse_datetime_or_none(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _format_optional_datetime(value: datetime | None) -> str | None:
    return _format_datetime(value) if value is not None else None


def _round_optional(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _sorted_counts(counts: Mapping[str, int | float]) -> dict[str, int | float]:
    return {key: counts[key] for key in sorted(counts)}


def _source_digest(payload: Mapping[str, object]) -> str:
    content = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise OrchestratorError(f"{context}_must_be_timezone_aware")


def _require_positive_finite(value: float, *, context: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise OrchestratorError(f"{context}_must_be_positive")


def _require_non_negative_finite(value: float, *, context: str) -> None:
    if not math.isfinite(value) or value < 0:
        raise OrchestratorError(f"{context}_must_be_non_negative")


def _require_safe_identifier(value: str, *, context: str) -> None:
    if not SAFE_KEY_RE.fullmatch(value):
        raise OrchestratorError(f"{context}_invalid")


def _reject_env_path(path: Path) -> None:
    if any(part.lower() == ".env" for part in path.parts):
        raise OrchestratorError("env_source_forbidden")
    if path.name.lower().startswith(".env"):
        raise OrchestratorError("env_source_forbidden")
