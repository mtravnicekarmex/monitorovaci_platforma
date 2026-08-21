from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile

from .incidents import IncidentEvaluation, IncidentState, IncidentTransition


INCIDENT_STORE_CONTRACT_VERSION = 1
OUTBOX_CONTRACT_VERSION = 1
TRANSITION_RECORD_CONTRACT_VERSION = 1
DELIVERY_INTENT_ACTIONS = {"opened", "reopened", "recovered"}
OUTBOX_PENDING = "pending"
OUTBOX_IN_PROGRESS = "in_progress"
OUTBOX_SENT = "sent"
OUTBOX_DEAD_LETTER = "dead_letter"
OUTBOX_STATUSES = {
    OUTBOX_PENDING,
    OUTBOX_IN_PROGRESS,
    OUTBOX_SENT,
    OUTBOX_DEAD_LETTER,
}


class IncidentStoreError(ValueError):
    """Incident state cannot be loaded or updated without ambiguity."""


@dataclass(frozen=True)
class IncidentStoreLimits:
    max_incident_states: int = 200
    max_transition_records: int = 2_000
    max_outbox_items: int = 1_000
    max_delivery_attempts: int = 3
    retry_backoff_seconds: float = 300.0
    claim_timeout_seconds: float = 600.0

    def __post_init__(self) -> None:
        for name in (
            "max_incident_states",
            "max_transition_records",
            "max_outbox_items",
            "max_delivery_attempts",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("retry_backoff_seconds", "claim_timeout_seconds"):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True)
class OutboxItem:
    idempotency_key: str
    incident_key: str
    action: str
    status: str
    report_reference: str
    created_at: datetime
    updated_at: datetime
    next_attempt_at: datetime
    attempt_count: int = 0
    last_attempt_at: datetime | None = None
    last_error_code: str | None = None
    claimed_at: datetime | None = None
    claim_id: str | None = None

    def __post_init__(self) -> None:
        if not self.idempotency_key.strip():
            raise ValueError("outbox idempotency key is required")
        if not self.incident_key.strip():
            raise ValueError("outbox incident key is required")
        if self.action not in DELIVERY_INTENT_ACTIONS:
            raise ValueError("outbox action is not delivery-intent eligible")
        if self.status not in OUTBOX_STATUSES:
            raise ValueError("outbox status is invalid")
        if not self.report_reference.strip():
            raise ValueError("outbox report reference is required")
        if (
            isinstance(self.attempt_count, bool)
            or not isinstance(self.attempt_count, int)
            or self.attempt_count < 0
        ):
            raise ValueError("outbox attempt count must not be negative")
        for name in ("created_at", "updated_at", "next_attempt_at"):
            _require_aware_datetime(getattr(self, name), context=name)
        if self.last_attempt_at is not None:
            _require_aware_datetime(
                self.last_attempt_at,
                context="last_attempt_at",
            )
        if self.claimed_at is not None:
            _require_aware_datetime(self.claimed_at, context="claimed_at")
        if self.status == OUTBOX_IN_PROGRESS and not self.claim_id:
            raise ValueError("in-progress outbox item requires a claim id")
        if self.status != OUTBOX_IN_PROGRESS and (
            self.claim_id is not None or self.claimed_at is not None
        ):
            raise ValueError("non-claimed outbox item must not retain claim fields")

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "attempt_count": self.attempt_count,
            "claim_id": self.claim_id,
            "claimed_at": _format_datetime(self.claimed_at),
            "created_at": _format_datetime(self.created_at),
            "idempotency_key": self.idempotency_key,
            "incident_key": self.incident_key,
            "last_attempt_at": _format_datetime(self.last_attempt_at),
            "last_error_code": self.last_error_code,
            "next_attempt_at": _format_datetime(self.next_attempt_at),
            "outbox_contract_version": OUTBOX_CONTRACT_VERSION,
            "report_reference": self.report_reference,
            "status": self.status,
            "updated_at": _format_datetime(self.updated_at),
        }

    @classmethod
    def from_dict(cls, value: object) -> OutboxItem:
        payload = _require_object(value, context="outbox item")
        _require_exact_keys(
            payload,
            required={
                "action",
                "attempt_count",
                "claim_id",
                "claimed_at",
                "created_at",
                "idempotency_key",
                "incident_key",
                "last_attempt_at",
                "last_error_code",
                "next_attempt_at",
                "outbox_contract_version",
                "report_reference",
                "status",
                "updated_at",
            },
            context="outbox item",
        )
        if payload["outbox_contract_version"] != OUTBOX_CONTRACT_VERSION:
            raise IncidentStoreError("outbox item contract is unsupported")
        return cls(
            idempotency_key=_require_string(
                payload["idempotency_key"],
                context="outbox idempotency_key",
            ),
            incident_key=_require_string(
                payload["incident_key"],
                context="outbox incident_key",
            ),
            action=_require_string(payload["action"], context="outbox action"),
            status=_require_string(payload["status"], context="outbox status"),
            report_reference=_require_string(
                payload["report_reference"],
                context="outbox report_reference",
            ),
            created_at=_parse_datetime(payload["created_at"], context="created_at"),
            updated_at=_parse_datetime(payload["updated_at"], context="updated_at"),
            next_attempt_at=_parse_datetime(
                payload["next_attempt_at"],
                context="next_attempt_at",
            ),
            attempt_count=_require_int(
                payload["attempt_count"],
                context="outbox attempt_count",
            ),
            last_attempt_at=_parse_datetime_or_none(
                payload["last_attempt_at"],
                context="last_attempt_at",
            ),
            last_error_code=_require_string_or_none(
                payload["last_error_code"],
                context="outbox last_error_code",
            ),
            claimed_at=_parse_datetime_or_none(
                payload["claimed_at"],
                context="claimed_at",
            ),
            claim_id=_require_string_or_none(
                payload["claim_id"],
                context="outbox claim_id",
            ),
        )


@dataclass(frozen=True)
class IncidentStoreSnapshot:
    states: tuple[IncidentState, ...]
    transition_records: tuple[dict[str, object], ...]
    outbox_items: tuple[OutboxItem, ...]
    updated_at: datetime | None = None

    def state_by_key(self) -> dict[str, IncidentState]:
        return {state.incident_key: state for state in self.states}

    def outbox_by_key(self) -> dict[str, OutboxItem]:
        return {item.idempotency_key: item for item in self.outbox_items}

    def to_dict(self) -> dict[str, object]:
        return {
            "delivery_enabled": False,
            "incident_store_contract_version": INCIDENT_STORE_CONTRACT_VERSION,
            "outbox": [item.to_dict() for item in self.outbox_items],
            "states": [state.to_dict() for state in self.states],
            "transition_records": list(self.transition_records),
            "updated_at": _format_datetime(self.updated_at),
        }


class IncidentStateStore:
    def __init__(
        self,
        state_dir: Path,
        *,
        limits: IncidentStoreLimits | None = None,
    ) -> None:
        self._state_dir = state_dir.resolve()
        self._state_path = self._state_dir / "incident_state.json"
        self._limits = limits or IncidentStoreLimits()

    @property
    def state_path(self) -> Path:
        return self._state_path

    @property
    def limits(self) -> IncidentStoreLimits:
        return self._limits

    def load(self) -> IncidentStoreSnapshot:
        if not self._state_path.exists():
            return IncidentStoreSnapshot(
                states=(),
                transition_records=(),
                outbox_items=(),
            )
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise IncidentStoreError("incident state file cannot be read") from exc
        try:
            return _parse_snapshot(payload)
        except IncidentStoreError:
            raise
        except ValueError as exc:
            raise IncidentStoreError("incident state file has invalid schema") from exc

    def apply_evaluation(
        self,
        evaluation: IncidentEvaluation,
        *,
        report_references: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> IncidentStoreSnapshot:
        recorded_at = _utc_now() if now is None else now
        _require_aware_datetime(recorded_at, context="recorded_at")
        snapshot = self.load()
        report_references = report_references or {}
        states = tuple(
            _retain_incident_states(
                evaluation.states,
                max_states=self._limits.max_incident_states,
            )
        )
        transition_records = _append_transition_records(
            snapshot.transition_records,
            evaluation.transitions,
            rule_version=evaluation.rule_version,
            report_references=report_references,
            recorded_at=recorded_at,
            max_records=self._limits.max_transition_records,
        )
        outbox_items = list(snapshot.outbox_items)
        known_idempotency_keys = {
            item.idempotency_key for item in snapshot.outbox_items
        }
        for transition in evaluation.transitions:
            if transition.action not in DELIVERY_INTENT_ACTIONS:
                continue
            report_reference = _report_reference(
                transition,
                report_references=report_references,
            )
            idempotency_key = _idempotency_key(
                transition=transition,
                rule_version=evaluation.rule_version,
                report_reference=report_reference,
            )
            if idempotency_key in known_idempotency_keys:
                continue
            known_idempotency_keys.add(idempotency_key)
            outbox_items.append(
                OutboxItem(
                    idempotency_key=idempotency_key,
                    incident_key=transition.incident_key,
                    action=transition.action,
                    status=OUTBOX_PENDING,
                    report_reference=report_reference,
                    created_at=recorded_at,
                    updated_at=recorded_at,
                    next_attempt_at=recorded_at,
                )
            )
        retained_outbox = _retain_outbox_items(
            outbox_items,
            max_items=self._limits.max_outbox_items,
        )
        next_snapshot = IncidentStoreSnapshot(
            states=states,
            transition_records=tuple(transition_records),
            outbox_items=tuple(retained_outbox),
            updated_at=recorded_at,
        )
        self._write_snapshot(next_snapshot)
        return next_snapshot

    def recover_abandoned_claims(
        self,
        *,
        now: datetime | None = None,
    ) -> IncidentStoreSnapshot:
        recovered_at = _utc_now() if now is None else now
        _require_aware_datetime(recovered_at, context="recovered_at")
        snapshot = self.load()
        items = [
            _recover_abandoned_claim(
                item,
                now=recovered_at,
                claim_timeout_seconds=self._limits.claim_timeout_seconds,
            )
            for item in snapshot.outbox_items
        ]
        next_snapshot = replace(
            snapshot,
            outbox_items=tuple(items),
            updated_at=recovered_at,
        )
        self._write_snapshot(next_snapshot)
        return next_snapshot

    def claim_due_delivery_intents(
        self,
        *,
        claim_id: str,
        now: datetime | None = None,
        limit: int = 10,
        idempotency_key: str | None = None,
        report_reference: str | None = None,
    ) -> tuple[OutboxItem, ...]:
        if not claim_id.strip():
            raise ValueError("claim id is required")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("claim limit must be a positive integer")
        normalized_idempotency_key = _normalize_optional_filter(
            idempotency_key,
            context="idempotency key filter",
        )
        normalized_report_reference = _normalize_optional_filter(
            report_reference,
            context="report reference filter",
        )
        claimed_at = _utc_now() if now is None else now
        _require_aware_datetime(claimed_at, context="claimed_at")
        snapshot = self.recover_abandoned_claims(now=claimed_at)
        selected: list[OutboxItem] = []
        updated_items: list[OutboxItem] = []
        for item in sorted(
            snapshot.outbox_items,
            key=lambda candidate: (candidate.next_attempt_at, candidate.created_at),
        ):
            if (
                len(selected) < limit
                and item.status == OUTBOX_PENDING
                and item.next_attempt_at <= claimed_at
                and (
                    normalized_idempotency_key is None
                    or item.idempotency_key == normalized_idempotency_key
                )
                and (
                    normalized_report_reference is None
                    or item.report_reference == normalized_report_reference
                )
            ):
                claimed = replace(
                    item,
                    status=OUTBOX_IN_PROGRESS,
                    updated_at=claimed_at,
                    claimed_at=claimed_at,
                    claim_id=claim_id.strip(),
                )
                selected.append(claimed)
                updated_items.append(claimed)
            else:
                updated_items.append(item)
        if selected:
            self._write_snapshot(
                replace(
                    snapshot,
                    outbox_items=tuple(updated_items),
                    updated_at=claimed_at,
                )
            )
        return tuple(selected)

    def record_delivery_result(
        self,
        *,
        idempotency_key: str,
        claim_id: str,
        succeeded: bool,
        error_code: str | None = None,
        now: datetime | None = None,
    ) -> IncidentStoreSnapshot:
        if not idempotency_key.strip():
            raise ValueError("idempotency key is required")
        if not claim_id.strip():
            raise ValueError("claim id is required")
        recorded_at = _utc_now() if now is None else now
        _require_aware_datetime(recorded_at, context="recorded_at")
        snapshot = self.load()
        updated_items: list[OutboxItem] = []
        matched = False
        for item in snapshot.outbox_items:
            if item.idempotency_key != idempotency_key:
                updated_items.append(item)
                continue
            matched = True
            if item.status != OUTBOX_IN_PROGRESS or item.claim_id != claim_id:
                raise IncidentStoreError("outbox item is not held by this claim")
            attempt_count = item.attempt_count + 1
            if succeeded:
                updated_items.append(
                    replace(
                        item,
                        status=OUTBOX_SENT,
                        attempt_count=attempt_count,
                        updated_at=recorded_at,
                        last_attempt_at=recorded_at,
                        last_error_code=None,
                        next_attempt_at=recorded_at,
                        claimed_at=None,
                        claim_id=None,
                    )
                )
                continue
            normalized_error = _normalize_error_code(error_code)
            if attempt_count >= self._limits.max_delivery_attempts:
                status = OUTBOX_DEAD_LETTER
                next_attempt_at = recorded_at
            else:
                status = OUTBOX_PENDING
                next_attempt_at = recorded_at + timedelta(
                    seconds=self._limits.retry_backoff_seconds
                    * (2 ** (attempt_count - 1))
                )
            updated_items.append(
                replace(
                    item,
                    status=status,
                    attempt_count=attempt_count,
                    updated_at=recorded_at,
                    last_attempt_at=recorded_at,
                    last_error_code=normalized_error,
                    next_attempt_at=next_attempt_at,
                    claimed_at=None,
                    claim_id=None,
                )
            )
        if not matched:
            raise IncidentStoreError("outbox item was not found")
        retained_outbox = _retain_outbox_items(
            updated_items,
            max_items=self._limits.max_outbox_items,
        )
        next_snapshot = replace(
            snapshot,
            outbox_items=tuple(retained_outbox),
            updated_at=recorded_at,
        )
        self._write_snapshot(next_snapshot)
        return next_snapshot

    def skip_pending_delivery_intents(
        self,
        *,
        now: datetime | None = None,
        limit: int = 10,
        idempotency_key: str | None = None,
        incident_key: str | None = None,
        report_reference: str | None = None,
        created_before: datetime | None = None,
        reason_code: str = "operator_skipped",
    ) -> tuple[OutboxItem, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("skip limit must be a positive integer")
        normalized_idempotency_key = _normalize_optional_filter(
            idempotency_key,
            context="idempotency key filter",
        )
        normalized_incident_key = _normalize_optional_filter(
            incident_key,
            context="incident key filter",
        )
        normalized_report_reference = _normalize_optional_filter(
            report_reference,
            context="report reference filter",
        )
        if created_before is not None:
            _require_aware_datetime(created_before, context="created_before")
            created_before = created_before.astimezone(timezone.utc)
        if (
            normalized_idempotency_key is None
            and normalized_incident_key is None
            and normalized_report_reference is None
            and created_before is None
        ):
            raise ValueError("skip requires at least one exact filter or cutoff")
        skipped_at = _utc_now() if now is None else now
        _require_aware_datetime(skipped_at, context="skipped_at")
        normalized_reason = _normalize_error_code(reason_code)
        snapshot = self.load()
        selected: list[OutboxItem] = []
        updated_items: list[OutboxItem] = []
        for item in sorted(
            snapshot.outbox_items,
            key=lambda candidate: (candidate.created_at, candidate.idempotency_key),
        ):
            if (
                len(selected) < limit
                and item.status == OUTBOX_PENDING
                and (
                    normalized_idempotency_key is None
                    or item.idempotency_key == normalized_idempotency_key
                )
                and (
                    normalized_incident_key is None
                    or item.incident_key == normalized_incident_key
                )
                and (
                    normalized_report_reference is None
                    or item.report_reference == normalized_report_reference
                )
                and (
                    created_before is None
                    or item.created_at < created_before
                )
            ):
                skipped = replace(
                    item,
                    status=OUTBOX_DEAD_LETTER,
                    updated_at=skipped_at,
                    next_attempt_at=skipped_at,
                    last_error_code=normalized_reason,
                    claimed_at=None,
                    claim_id=None,
                )
                selected.append(skipped)
                updated_items.append(skipped)
            else:
                updated_items.append(item)
        if selected:
            retained_outbox = _retain_outbox_items(
                updated_items,
                max_items=self._limits.max_outbox_items,
            )
            self._write_snapshot(
                replace(
                    snapshot,
                    outbox_items=tuple(retained_outbox),
                    updated_at=skipped_at,
                )
            )
        return tuple(selected)

    def _write_snapshot(self, snapshot: IncidentStoreSnapshot) -> None:
        _validate_snapshot_limits(snapshot, limits=self._limits)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        content = (
            json.dumps(
                snapshot.to_dict(),
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix="incident-state-",
            suffix=".tmp",
            dir=self._state_dir,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(
                file_descriptor,
                "w",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.replace(self._state_path)
        finally:
            temporary_path.unlink(missing_ok=True)


def _parse_snapshot(payload: object) -> IncidentStoreSnapshot:
    value = _require_object(payload, context="incident state")
    _require_exact_keys(
        value,
        required={
            "delivery_enabled",
            "incident_store_contract_version",
            "outbox",
            "states",
            "transition_records",
            "updated_at",
        },
        context="incident state",
    )
    if value["incident_store_contract_version"] != INCIDENT_STORE_CONTRACT_VERSION:
        raise IncidentStoreError("incident state contract is unsupported")
    if value["delivery_enabled"] is not False:
        raise IncidentStoreError("incident delivery must not be enabled here")
    states = value["states"]
    transition_records = value["transition_records"]
    outbox = value["outbox"]
    if not isinstance(states, list):
        raise IncidentStoreError("incident states must be an array")
    if not isinstance(transition_records, list):
        raise IncidentStoreError("incident transition records must be an array")
    if not isinstance(outbox, list):
        raise IncidentStoreError("incident outbox must be an array")
    return IncidentStoreSnapshot(
        states=tuple(_incident_state_from_dict(item) for item in states),
        transition_records=tuple(
            _parse_transition_record(item) for item in transition_records
        ),
        outbox_items=tuple(OutboxItem.from_dict(item) for item in outbox),
        updated_at=_parse_datetime_or_none(value["updated_at"], context="updated_at"),
    )


def _incident_state_from_dict(value: object) -> IncidentState:
    payload = _require_object(value, context="incident state record")
    _require_exact_keys(
        payload,
        required={
            "failure_count",
            "incident_key",
            "kind",
            "last_cycle_sequence",
            "last_observed_at",
            "last_reason",
            "occurrence_count",
            "opened_at",
            "opened_cycle_sequence",
            "recovered_at",
            "recovered_cycle_sequence",
            "recovery_count",
            "severity",
            "status",
            "subject",
        },
        context="incident state record",
    )
    return IncidentState(
        incident_key=_require_string(
            payload["incident_key"],
            context="incident incident_key",
        ),
        kind=_require_string(payload["kind"], context="incident kind"),
        subject=_require_string(payload["subject"], context="incident subject"),
        status=_require_string(payload["status"], context="incident status"),
        severity=_require_string(payload["severity"], context="incident severity"),
        opened_at=_parse_datetime_or_none(payload["opened_at"], context="opened_at"),
        last_observed_at=_parse_datetime(
            payload["last_observed_at"],
            context="last_observed_at",
        ),
        recovered_at=_parse_datetime_or_none(
            payload["recovered_at"],
            context="recovered_at",
        ),
        opened_cycle_sequence=_require_int_or_none(
            payload["opened_cycle_sequence"],
            context="opened_cycle_sequence",
        ),
        recovered_cycle_sequence=_require_int_or_none(
            payload["recovered_cycle_sequence"],
            context="recovered_cycle_sequence",
        ),
        last_cycle_sequence=_require_int_or_none(
            payload["last_cycle_sequence"],
            context="last_cycle_sequence",
        ),
        failure_count=_require_int(
            payload["failure_count"],
            context="failure_count",
        ),
        recovery_count=_require_int(
            payload["recovery_count"],
            context="recovery_count",
        ),
        occurrence_count=_require_int(
            payload["occurrence_count"],
            context="occurrence_count",
        ),
        last_reason=_require_string(
            payload["last_reason"],
            context="last_reason",
        ),
    )


def _parse_transition_record(value: object) -> dict[str, object]:
    payload = _require_object(value, context="incident transition record")
    _require_exact_keys(
        payload,
        required={
            "recorded_at",
            "report_reference",
            "rule_version",
            "transition",
            "transition_record_contract_version",
        },
        context="incident transition record",
    )
    if (
        payload["transition_record_contract_version"]
        != TRANSITION_RECORD_CONTRACT_VERSION
    ):
        raise IncidentStoreError("transition record contract is unsupported")
    _parse_datetime(payload["recorded_at"], context="transition recorded_at")
    _require_int(payload["rule_version"], context="transition rule_version")
    _require_string(
        payload["report_reference"],
        context="transition report_reference",
    )
    _incident_transition_from_dict(payload["transition"])
    return dict(payload)


def _incident_transition_from_dict(value: object) -> IncidentTransition:
    payload = _require_object(value, context="incident transition")
    _require_exact_keys(
        payload,
        required={
            "action",
            "cycle_sequence",
            "failure_count",
            "incident_key",
            "kind",
            "observed_at",
            "occurrence_count",
            "reason",
            "recovery_count",
            "severity",
            "status",
            "subject",
        },
        context="incident transition",
    )
    return IncidentTransition(
        incident_key=_require_string(
            payload["incident_key"],
            context="transition incident_key",
        ),
        action=_require_string(payload["action"], context="transition action"),
        kind=_require_string(payload["kind"], context="transition kind"),
        subject=_require_string(payload["subject"], context="transition subject"),
        severity=_require_string(payload["severity"], context="transition severity"),
        status=_require_string(payload["status"], context="transition status"),
        reason=_require_string(payload["reason"], context="transition reason"),
        observed_at=_parse_datetime(payload["observed_at"], context="observed_at"),
        cycle_sequence=_require_int_or_none(
            payload["cycle_sequence"],
            context="cycle_sequence",
        ),
        failure_count=_require_int(
            payload["failure_count"],
            context="failure_count",
        ),
        recovery_count=_require_int(
            payload["recovery_count"],
            context="recovery_count",
        ),
        occurrence_count=_require_int(
            payload["occurrence_count"],
            context="occurrence_count",
        ),
    )


def _transition_record(
    *,
    transition: IncidentTransition,
    rule_version: int,
    report_reference: str,
    recorded_at: datetime,
) -> dict[str, object]:
    return {
        "recorded_at": _format_datetime(recorded_at),
        "report_reference": report_reference,
        "rule_version": rule_version,
        "transition": transition.to_dict(),
        "transition_record_contract_version": TRANSITION_RECORD_CONTRACT_VERSION,
    }


def _append_transition_records(
    existing_records: tuple[dict[str, object], ...],
    transitions: tuple[IncidentTransition, ...],
    *,
    rule_version: int,
    report_references: Mapping[str, str],
    recorded_at: datetime,
    max_records: int,
) -> tuple[dict[str, object], ...]:
    records = list(existing_records)
    for transition in transitions:
        if not _should_record_transition(records, transition):
            continue
        records.append(
            _transition_record(
                transition=transition,
                rule_version=rule_version,
                report_reference=_report_reference(
                    transition,
                    report_references=report_references,
                ),
                recorded_at=recorded_at,
            )
        )
    return tuple(records[-max_records:])


def _should_record_transition(
    records: list[dict[str, object]],
    transition: IncidentTransition,
) -> bool:
    if transition.action != "updated":
        return True
    previous = _last_transition_for_incident(records, transition.incident_key)
    if previous is None:
        return True
    if previous.action != "updated":
        return True
    return (
        previous.reason != transition.reason
        or previous.status != transition.status
        or previous.severity != transition.severity
    )


def _last_transition_for_incident(
    records: list[dict[str, object]],
    incident_key: str,
) -> IncidentTransition | None:
    for record in reversed(records):
        transition_payload = record.get("transition")
        if not isinstance(transition_payload, dict):
            continue
        if transition_payload.get("incident_key") != incident_key:
            continue
        return _incident_transition_from_dict(transition_payload)
    return None


def _idempotency_key(
    *,
    transition: IncidentTransition,
    rule_version: int,
    report_reference: str,
) -> str:
    material = json.dumps(
        {
            "action": transition.action,
            "cycle_sequence": transition.cycle_sequence,
            "incident_key": transition.incident_key,
            "observed_at": _format_datetime(transition.observed_at),
            "report_reference": report_reference,
            "rule_version": rule_version,
            "status": transition.status,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _report_reference(
    transition: IncidentTransition,
    *,
    report_references: Mapping[str, str],
) -> str:
    explicit = report_references.get(transition.incident_key)
    if explicit is not None:
        if not explicit.strip():
            raise ValueError("report reference must not be empty")
        return explicit.strip()
    return (
        f"incident-report:v1:{transition.incident_key}:"
        f"{transition.action}:{_format_datetime(transition.observed_at)}"
    )


def _retain_incident_states(
    states: tuple[IncidentState, ...],
    *,
    max_states: int,
) -> tuple[IncidentState, ...]:
    if len(states) <= max_states:
        return tuple(sorted(states, key=lambda item: item.incident_key))
    mandatory = [
        state
        for state in states
        if state.status in {"active", "candidate"}
    ]
    if len(mandatory) > max_states:
        raise IncidentStoreError("active incident states exceed retention bound")
    retained = sorted(
        states,
        key=lambda item: (
            0 if item.status in {"active", "candidate"} else 1,
            -item.last_observed_at.timestamp(),
            item.incident_key,
        ),
    )[:max_states]
    return tuple(sorted(retained, key=lambda item: item.incident_key))


def _retain_outbox_items(
    items: list[OutboxItem],
    *,
    max_items: int,
) -> tuple[OutboxItem, ...]:
    mandatory = [
        item
        for item in items
        if item.status in {OUTBOX_PENDING, OUTBOX_IN_PROGRESS}
    ]
    if len(mandatory) > max_items:
        raise IncidentStoreError("pending outbox items exceed retention bound")
    retained = sorted(
        items,
        key=lambda item: (
            0 if item.status in {OUTBOX_PENDING, OUTBOX_IN_PROGRESS} else 1,
            -item.updated_at.timestamp(),
            item.idempotency_key,
        ),
    )[:max_items]
    return tuple(sorted(retained, key=lambda item: item.idempotency_key))


def _validate_snapshot_limits(
    snapshot: IncidentStoreSnapshot,
    *,
    limits: IncidentStoreLimits,
) -> None:
    if len(snapshot.states) > limits.max_incident_states:
        raise IncidentStoreError("incident states exceed retention bound")
    if len(snapshot.transition_records) > limits.max_transition_records:
        raise IncidentStoreError("incident transitions exceed retention bound")
    if len(snapshot.outbox_items) > limits.max_outbox_items:
        raise IncidentStoreError("incident outbox exceeds retention bound")
    if len(snapshot.outbox_by_key()) != len(snapshot.outbox_items):
        raise IncidentStoreError("incident outbox idempotency key is duplicated")


def _recover_abandoned_claim(
    item: OutboxItem,
    *,
    now: datetime,
    claim_timeout_seconds: float,
) -> OutboxItem:
    if item.status != OUTBOX_IN_PROGRESS or item.claimed_at is None:
        return item
    if (now - item.claimed_at).total_seconds() <= claim_timeout_seconds:
        return item
    return replace(
        item,
        status=OUTBOX_PENDING,
        updated_at=now,
        next_attempt_at=now,
        claimed_at=None,
        claim_id=None,
    )


def _normalize_error_code(value: str | None) -> str:
    if value is None or not value.strip():
        return "delivery_failed"
    stripped = value.strip()
    if len(stripped) > 80:
        stripped = stripped[:80]
    if any(character.isspace() for character in stripped):
        return "delivery_failed"
    return stripped


def _require_object(value: object, *, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise IncidentStoreError(f"{context} must be an object")
    return dict(value)


def _require_exact_keys(
    value: Mapping[str, object],
    *,
    required: set[str],
    context: str,
) -> None:
    actual = set(value)
    if actual != required:
        raise IncidentStoreError(
            f"{context} schema mismatch: "
            f"missing={sorted(required - actual)!r}, "
            f"unexpected={sorted(actual - required)!r}"
        )


def _require_string(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IncidentStoreError(f"{context} must be a non-empty string")
    return value


def _require_string_or_none(value: object, *, context: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, context=context)


def _normalize_optional_filter(value: str | None, *, context: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{context} must not be empty")
    return normalized


def _require_int(value: object, *, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IncidentStoreError(f"{context} must be a non-negative integer")
    return value


def _require_int_or_none(value: object, *, context: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, context=context)


def _parse_datetime(value: object, *, context: str) -> datetime:
    raw_value = _require_string(value, context=context)
    try:
        resolved = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IncidentStoreError(f"{context} must be an ISO datetime") from exc
    _require_aware_datetime(resolved, context=context)
    return resolved.astimezone(timezone.utc)


def _parse_datetime_or_none(value: object, *, context: str) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime(value, context=context)


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{context} must include a timezone")


def _format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "IncidentStateStore",
    "IncidentStoreError",
    "IncidentStoreLimits",
    "IncidentStoreSnapshot",
    "OutboxItem",
]
