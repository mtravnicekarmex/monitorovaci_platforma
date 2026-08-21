from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Protocol

from .incidents import INCIDENT_STATUS_ACTIVE
from .reporting import (
    MonitoringReportSnapshot,
    redact_monitoring_text,
    render_monitoring_report,
    render_programming_agent_prompt,
)


INTERPRETATION_CONTRACT_VERSION = 1
INTERPRETATION_MODE_DISABLED = "disabled"
INTERPRETATION_MODE_DRAFT = "draft"
INTERPRETATION_MODES = {
    INTERPRETATION_MODE_DISABLED,
    INTERPRETATION_MODE_DRAFT,
}
INTERPRETATION_STATUS_DISABLED = "disabled"
INTERPRETATION_STATUS_SKIPPED = "skipped"
INTERPRETATION_STATUS_FALLBACK = "fallback"
INTERPRETATION_STATUS_INTERPRETED = "interpreted"
INTERPRETATION_ERROR_DISABLED = "interpretation_disabled"
INTERPRETATION_ERROR_NO_CONFIRMED_INCIDENT = "no_confirmed_incident"
INTERPRETATION_ERROR_PROVIDER_NOT_CONFIGURED = "provider_not_configured"
INTERPRETATION_ERROR_PROVIDER_FAILED = "provider_failed"
INTERPRETATION_ERROR_PROVIDER_OUTPUT_INVALID = "provider_output_invalid"
DEFAULT_PROVIDER_NAME = "not_configured"
DEFAULT_MODEL_NAME = "not_configured"
DEFAULT_MAX_PROMPT_CHARS = 4_000
DEFAULT_MAX_OUTPUT_CHARS = 3_000
DEFAULT_MAX_HYPOTHESES = 6
DEFAULT_MAX_READ_ONLY_CHECKS = 8
DEFAULT_MAX_EVIDENCE_GAPS = 6
SAFETY_BOUNDARY = (
    "Interpretation is hypotheses and read-only diagnostic planning only.",
    "Deterministic incident rules, report facts, outbox state, and legacy alerts remain authoritative.",
    "No command execution, network contact, state mutation, process control, delivery, remediation, or alert suppression is authorized.",
)

_UNSAFE_OUTPUT_RE = re.compile(
    r"(?i)\b("
    r"run\s+command|execute|powershell|cmd\.exe|restart|stop-scheduledtask|"
    r"start-scheduledtask|stop\s+service|start\s+service|kill\s+process|"
    r"delete|remove-item|write\s+database|mutate|send-due|send\s+email|"
    r"disable\s+alert|replace\s+alert|suppress\s+alert|remediate"
    r")\b"
)


class InterpretationProvider(Protocol):
    def interpret(
        self,
        request: InterpretationRequest,
    ) -> InterpretationProviderOutput:
        """Return one bounded interpretation for the supplied sanitized request."""


@dataclass(frozen=True)
class InterpretationPolicy:
    enabled: bool = False
    mode: str = INTERPRETATION_MODE_DISABLED
    provider_name: str = DEFAULT_PROVIDER_NAME
    model_name: str = DEFAULT_MODEL_NAME
    timeout_seconds: float = 15.0
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS
    max_hypotheses: int = DEFAULT_MAX_HYPOTHESES
    max_read_only_checks: int = DEFAULT_MAX_READ_ONLY_CHECKS
    max_evidence_gaps: int = DEFAULT_MAX_EVIDENCE_GAPS
    max_cost_usd: float = 0.0
    allow_network: bool = False
    allow_state_mutation: bool = False
    allow_process_control: bool = False
    allow_delivery: bool = False
    allow_alert_suppression: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("interpretation enabled flag must be boolean")
        if self.mode not in INTERPRETATION_MODES:
            raise ValueError("interpretation mode is invalid")
        if self.enabled and self.mode != INTERPRETATION_MODE_DRAFT:
            raise ValueError("enabled interpretation must use draft mode")
        for name in ("provider_name", "model_name"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} must not be empty")
        for name in (
            "timeout_seconds",
            "max_cost_usd",
        ):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        for name in (
            "max_prompt_chars",
            "max_output_chars",
            "max_hypotheses",
            "max_read_only_checks",
            "max_evidence_gaps",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in (
            "allow_network",
            "allow_state_mutation",
            "allow_process_control",
            "allow_delivery",
            "allow_alert_suppression",
        ):
            if getattr(self, name) is not False:
                raise ValueError(f"{name} must remain false in item-6 source")


@dataclass(frozen=True)
class InterpretationRequest:
    created_at: datetime
    prompt: str
    confirmed_incident_keys: tuple[str, ...]
    provider_name: str
    model_name: str
    timeout_seconds: float
    max_cost_usd: float
    contract_version: int = INTERPRETATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_aware_datetime(self.created_at, context="created_at")
        if not self.prompt.strip():
            raise ValueError("interpretation prompt is required")
        if not self.confirmed_incident_keys:
            raise ValueError("interpretation request requires a confirmed incident")
        if any(not key.strip() for key in self.confirmed_incident_keys):
            raise ValueError("confirmed incident keys must not be empty")
        if not self.provider_name.strip():
            raise ValueError("provider name is required")
        if not self.model_name.strip():
            raise ValueError("model name is required")
        if self.contract_version != INTERPRETATION_CONTRACT_VERSION:
            raise ValueError("interpretation request contract is unsupported")

    @property
    def prompt_sha256(self) -> str:
        return hashlib.sha256(self.prompt.encode("utf-8")).hexdigest()

    def to_audit_dict(self) -> dict[str, object]:
        return {
            "confirmed_incident_keys": list(self.confirmed_incident_keys),
            "contract_version": self.contract_version,
            "created_at": _format_datetime(self.created_at),
            "max_cost_usd": self.max_cost_usd,
            "model_name": self.model_name,
            "prompt_chars": len(self.prompt),
            "prompt_sha256": self.prompt_sha256,
            "provider_name": self.provider_name,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class InterpretationProviderOutput:
    summary: str
    hypotheses: tuple[str, ...] = ()
    recommended_read_only_checks: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("provider summary is required")
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))
        object.__setattr__(
            self,
            "recommended_read_only_checks",
            tuple(self.recommended_read_only_checks),
        )
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))


@dataclass(frozen=True)
class InterpretationResult:
    generated_at: datetime
    status: str
    deterministic_summary_status: str
    confirmed_incident_keys: tuple[str, ...]
    provider_name: str
    model_name: str
    timeout_seconds: float
    max_cost_usd: float
    summary: str
    hypotheses: tuple[str, ...]
    recommended_read_only_checks: tuple[str, ...]
    evidence_gaps: tuple[str, ...]
    prompt_sha256: str | None = None
    prompt_chars: int | None = None
    fallback_report: str | None = None
    error_code: str | None = None
    safety_boundary: tuple[str, ...] = SAFETY_BOUNDARY
    contract_version: int = INTERPRETATION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        _require_aware_datetime(self.generated_at, context="generated_at")
        if self.status not in {
            INTERPRETATION_STATUS_DISABLED,
            INTERPRETATION_STATUS_SKIPPED,
            INTERPRETATION_STATUS_FALLBACK,
            INTERPRETATION_STATUS_INTERPRETED,
        }:
            raise ValueError("interpretation status is invalid")
        if not self.summary.strip():
            raise ValueError("interpretation summary is required")
        object.__setattr__(
            self,
            "confirmed_incident_keys",
            tuple(self.confirmed_incident_keys),
        )
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))
        object.__setattr__(
            self,
            "recommended_read_only_checks",
            tuple(self.recommended_read_only_checks),
        )
        object.__setattr__(self, "evidence_gaps", tuple(self.evidence_gaps))
        object.__setattr__(self, "safety_boundary", tuple(self.safety_boundary))

    def to_dict(self) -> dict[str, object]:
        return {
            "confirmed_incident_keys": list(self.confirmed_incident_keys),
            "contract_version": self.contract_version,
            "deterministic_summary_status": self.deterministic_summary_status,
            "error_code": self.error_code,
            "evidence_gaps": list(self.evidence_gaps),
            "fallback_report": self.fallback_report,
            "generated_at": _format_datetime(self.generated_at),
            "hypotheses": list(self.hypotheses),
            "max_cost_usd": self.max_cost_usd,
            "model_name": self.model_name,
            "prompt_chars": self.prompt_chars,
            "prompt_sha256": self.prompt_sha256,
            "provider_name": self.provider_name,
            "recommended_read_only_checks": list(self.recommended_read_only_checks),
            "safety_boundary": list(self.safety_boundary),
            "status": self.status,
            "summary": self.summary,
            "timeout_seconds": self.timeout_seconds,
        }


def build_interpretation_prompt(
    snapshot: MonitoringReportSnapshot,
    *,
    policy: InterpretationPolicy,
    now: datetime | None = None,
) -> str:
    generated_at = _utc_now() if now is None else now
    _require_aware_datetime(generated_at, context="generated_at")
    confirmed_keys = _confirmed_incident_keys(snapshot)
    if not confirmed_keys:
        raise ValueError("interpretation prompt requires a confirmed incident")
    header = "\n".join(
        [
            "INTERPRETATION REQUEST - DRAFT ONLY",
            f"Interpretation contract version: {INTERPRETATION_CONTRACT_VERSION}",
            f"Generated at: {_format_datetime(generated_at)}",
            f"Provider: {policy.provider_name}",
            f"Model: {policy.model_name}",
            f"Timeout seconds: {policy.timeout_seconds}",
            f"Cost ceiling USD: {policy.max_cost_usd}",
            "Confirmed incident keys: " + ", ".join(confirmed_keys),
            "",
            "Allowed output:",
            "- bounded hypotheses;",
            "- recommended read-only checks;",
            "- explicit evidence gaps.",
            "",
            "Forbidden output:",
            "- commands, network actions, state writes, service restarts, delivery attempts, remediation, or alert suppression;",
            "- claims that interpretation overrides deterministic incident rules or legacy alerts.",
            "",
        ]
    )
    base_prompt = render_programming_agent_prompt(
        snapshot,
        max_chars=policy.max_prompt_chars,
    )
    return _bounded_text(
        redact_monitoring_text(f"{header}{base_prompt}"),
        max_chars=policy.max_prompt_chars,
    )


def interpret_confirmed_incidents(
    snapshot: MonitoringReportSnapshot,
    *,
    policy: InterpretationPolicy | None = None,
    provider: InterpretationProvider | None = None,
    now: datetime | None = None,
) -> InterpretationResult:
    resolved_policy = policy or InterpretationPolicy()
    generated_at = _utc_now() if now is None else now
    _require_aware_datetime(generated_at, context="generated_at")
    confirmed_keys = _confirmed_incident_keys(snapshot)

    if not resolved_policy.enabled:
        return _fallback_result(
            snapshot=snapshot,
            policy=resolved_policy,
            generated_at=generated_at,
            confirmed_keys=confirmed_keys,
            status=INTERPRETATION_STATUS_DISABLED,
            error_code=INTERPRETATION_ERROR_DISABLED,
        )
    if resolved_policy.mode != INTERPRETATION_MODE_DRAFT:
        return _fallback_result(
            snapshot=snapshot,
            policy=resolved_policy,
            generated_at=generated_at,
            confirmed_keys=confirmed_keys,
            status=INTERPRETATION_STATUS_DISABLED,
            error_code=INTERPRETATION_ERROR_DISABLED,
        )
    if not confirmed_keys:
        return _fallback_result(
            snapshot=snapshot,
            policy=resolved_policy,
            generated_at=generated_at,
            confirmed_keys=confirmed_keys,
            status=INTERPRETATION_STATUS_SKIPPED,
            error_code=INTERPRETATION_ERROR_NO_CONFIRMED_INCIDENT,
        )

    request = InterpretationRequest(
        created_at=generated_at,
        prompt=build_interpretation_prompt(
            snapshot,
            policy=resolved_policy,
            now=generated_at,
        ),
        confirmed_incident_keys=confirmed_keys,
        provider_name=resolved_policy.provider_name,
        model_name=resolved_policy.model_name,
        timeout_seconds=resolved_policy.timeout_seconds,
        max_cost_usd=resolved_policy.max_cost_usd,
    )
    if provider is None:
        return _fallback_result(
            snapshot=snapshot,
            policy=resolved_policy,
            generated_at=generated_at,
            confirmed_keys=confirmed_keys,
            status=INTERPRETATION_STATUS_FALLBACK,
            error_code=INTERPRETATION_ERROR_PROVIDER_NOT_CONFIGURED,
            request=request,
        )

    try:
        provider_output = provider.interpret(request)
        sanitized_output = _sanitize_provider_output(
            provider_output,
            policy=resolved_policy,
        )
    except Exception:
        return _fallback_result(
            snapshot=snapshot,
            policy=resolved_policy,
            generated_at=generated_at,
            confirmed_keys=confirmed_keys,
            status=INTERPRETATION_STATUS_FALLBACK,
            error_code=INTERPRETATION_ERROR_PROVIDER_FAILED,
            request=request,
        )

    if sanitized_output is None:
        return _fallback_result(
            snapshot=snapshot,
            policy=resolved_policy,
            generated_at=generated_at,
            confirmed_keys=confirmed_keys,
            status=INTERPRETATION_STATUS_FALLBACK,
            error_code=INTERPRETATION_ERROR_PROVIDER_OUTPUT_INVALID,
            request=request,
        )

    return InterpretationResult(
        generated_at=generated_at,
        status=INTERPRETATION_STATUS_INTERPRETED,
        deterministic_summary_status=snapshot.summary_status,
        confirmed_incident_keys=confirmed_keys,
        provider_name=resolved_policy.provider_name,
        model_name=resolved_policy.model_name,
        timeout_seconds=resolved_policy.timeout_seconds,
        max_cost_usd=resolved_policy.max_cost_usd,
        prompt_sha256=request.prompt_sha256,
        prompt_chars=len(request.prompt),
        summary=sanitized_output.summary,
        hypotheses=sanitized_output.hypotheses,
        recommended_read_only_checks=sanitized_output.recommended_read_only_checks,
        evidence_gaps=sanitized_output.evidence_gaps,
        fallback_report=None,
        error_code=None,
    )


def _fallback_result(
    *,
    snapshot: MonitoringReportSnapshot,
    policy: InterpretationPolicy,
    generated_at: datetime,
    confirmed_keys: tuple[str, ...],
    status: str,
    error_code: str,
    request: InterpretationRequest | None = None,
) -> InterpretationResult:
    return InterpretationResult(
        generated_at=generated_at,
        status=status,
        deterministic_summary_status=snapshot.summary_status,
        confirmed_incident_keys=confirmed_keys,
        provider_name=policy.provider_name,
        model_name=policy.model_name,
        timeout_seconds=policy.timeout_seconds,
        max_cost_usd=policy.max_cost_usd,
        prompt_sha256=None if request is None else request.prompt_sha256,
        prompt_chars=None if request is None else len(request.prompt),
        summary=(
            "Agentic interpretation was not produced; the deterministic monitoring "
            "report remains the authoritative fallback."
        ),
        hypotheses=(),
        recommended_read_only_checks=(),
        evidence_gaps=(error_code,),
        fallback_report=render_monitoring_report(
            snapshot,
            max_chars=policy.max_output_chars,
        ),
        error_code=error_code,
    )


def _sanitize_provider_output(
    output: InterpretationProviderOutput,
    *,
    policy: InterpretationPolicy,
) -> InterpretationProviderOutput | None:
    try:
        summary = _sanitize_output_text(
            output.summary,
            max_chars=policy.max_output_chars,
        )
        hypotheses = _sanitize_output_items(
            output.hypotheses,
            max_items=policy.max_hypotheses,
            max_chars=policy.max_output_chars,
            require_item=False,
        )
        checks = _sanitize_output_items(
            output.recommended_read_only_checks,
            max_items=policy.max_read_only_checks,
            max_chars=policy.max_output_chars,
            require_item=True,
        )
        evidence_gaps = _sanitize_output_items(
            output.evidence_gaps,
            max_items=policy.max_evidence_gaps,
            max_chars=policy.max_output_chars,
            require_item=False,
        )
    except ValueError:
        return None
    return InterpretationProviderOutput(
        summary=summary,
        hypotheses=hypotheses,
        recommended_read_only_checks=checks,
        evidence_gaps=evidence_gaps,
    )


def _sanitize_output_items(
    values: Sequence[str],
    *,
    max_items: int,
    max_chars: int,
    require_item: bool,
) -> tuple[str, ...]:
    if isinstance(values, str):
        raise ValueError("provider output items must be a sequence of strings")
    sanitized = tuple(
        _sanitize_output_text(value, max_chars=max_chars)
        for value in values[:max_items]
        if str(value).strip()
    )
    if require_item and not sanitized:
        raise ValueError("provider output requires at least one read-only check")
    return sanitized


def _sanitize_output_text(value: str, *, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("provider output text must be non-empty")
    sanitized = _bounded_text(
        redact_monitoring_text(value.strip()),
        max_chars=max_chars,
    )
    if _UNSAFE_OUTPUT_RE.search(sanitized):
        raise ValueError("provider output contains unsafe action text")
    return sanitized


def _confirmed_incident_keys(
    snapshot: MonitoringReportSnapshot,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            state.incident_key
            for state in snapshot.incident_evaluation.states
            if state.status == INCIDENT_STATUS_ACTIVE
        )
    )


def _bounded_text(text: str, *, max_chars: int) -> str:
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("max_chars must be a positive integer")
    if len(text) <= max_chars:
        return text
    marker = "\n[truncated: monitoring interpretation exceeded configured character limit]\n"
    if max_chars <= len(marker):
        return marker[:max_chars]
    return text[: max_chars - len(marker)].rstrip() + marker


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{context} must include a timezone")


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "INTERPRETATION_CONTRACT_VERSION",
    "INTERPRETATION_ERROR_DISABLED",
    "INTERPRETATION_ERROR_NO_CONFIRMED_INCIDENT",
    "INTERPRETATION_ERROR_PROVIDER_FAILED",
    "INTERPRETATION_ERROR_PROVIDER_NOT_CONFIGURED",
    "INTERPRETATION_ERROR_PROVIDER_OUTPUT_INVALID",
    "INTERPRETATION_MODE_DISABLED",
    "INTERPRETATION_MODE_DRAFT",
    "INTERPRETATION_STATUS_DISABLED",
    "INTERPRETATION_STATUS_FALLBACK",
    "INTERPRETATION_STATUS_INTERPRETED",
    "INTERPRETATION_STATUS_SKIPPED",
    "InterpretationPolicy",
    "InterpretationProvider",
    "InterpretationProviderOutput",
    "InterpretationRequest",
    "InterpretationResult",
    "build_interpretation_prompt",
    "interpret_confirmed_incidents",
]
