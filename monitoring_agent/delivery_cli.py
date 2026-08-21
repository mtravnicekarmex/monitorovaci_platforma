from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Sequence

from .delivery import (
    DELIVERY_ADAPTER_VERSION,
    DELIVERY_ERROR_CONFIRMATION_REQUIRED,
    DELIVERY_ERROR_REPORT_FILE_REJECTED,
    DELIVERY_MODE_TEST,
    DELIVERY_STATUS_CONFIGURATION_ERROR,
    DeliveryAttemptResult,
    OutlookEmailTransport,
    TestDeliveryPolicy,
    deliver_due_test_delivery_intents,
    hash_delivery_recipient,
    validate_outlook_email_environment,
    validate_test_delivery_policy,
)
from .incident_store import (
    OUTBOX_DEAD_LETTER,
    OUTBOX_PENDING,
    OUTBOX_SENT,
    IncidentStateStore,
)
from .client import CURRENT_ENDPOINT_KEYS
from .incidents import (
    CycleSnapshot,
    EndpointObservationFact,
    evaluate_incident_lifecycle,
)


CONFIRM_SEND_TEST_DELIVERY = "SEND_TEST_DELIVERY"
CONFIRM_SKIP_PENDING_OUTBOX = "SKIP_PENDING_OUTBOX"
CONFIRM_PREPARE_SYNTHETIC_STATE = "PREPARE_SYNTHETIC_DELIVERY_TEST_STATE"
DEFAULT_RECIPIENT_ENV = "DELIVERY_TEST_RECIPIENT"
DEFAULT_SMTP_SENDER_ALIAS_ENV = "DELIVERY_TEST_SENDER_ALIAS"
OUTBOX_REVIEW_TERMINAL_STATUSES = {OUTBOX_DEAD_LETTER, OUTBOX_SENT}


class DeliveryCliError(ValueError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        _load_env_file(
            getattr(args, "env_file", None),
            allowed_keys=_env_file_keys_for_command(args),
        )
        if args.command == "hash-recipient":
            payload = _hash_recipient(args)
            _print_json(payload)
            return 0
        if args.command == "dry-run":
            payload = _dry_run(args)
            _print_json(payload)
            return 0 if payload["status"] != DELIVERY_STATUS_CONFIGURATION_ERROR else 2
        if args.command == "review-outbox":
            payload = _review_outbox(args)
            _print_json(payload)
            return 0
        if args.command == "skip-outbox":
            payload = _skip_outbox(args)
            _print_json(payload)
            return (
                0
                if payload["status"] != DELIVERY_STATUS_CONFIGURATION_ERROR
                else 2
            )
        if args.command == "prepare-synthetic":
            payload = _prepare_synthetic(args)
            _print_json(payload)
            return 0 if payload["status"] == "prepared" else 2
        if args.command == "send-due":
            payload = _send_due(args)
            _print_json(payload)
            return _send_exit_code(payload)
        parser.error("unsupported command")
        return 2
    except DeliveryCliError as exc:
        _print_json(
            {
                "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
                "event": "monitoring_test_delivery_cli_error",
                "error_code": exc.error_code,
                "status": DELIVERY_STATUS_CONFIGURATION_ERROR,
            }
        )
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Controlled monitoring-agent test delivery helper."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    hash_parser = subparsers.add_parser(
        "hash-recipient",
        help="Print only the SHA-256 hash of the recipient stored in an env var.",
    )
    hash_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    hash_parser.add_argument("--recipient-env", default=DEFAULT_RECIPIENT_ENV)

    dry_run_parser = subparsers.add_parser(
        "dry-run",
        help="Validate policy and due outbox count without claiming or sending.",
    )
    _add_common_policy_args(dry_run_parser)
    _add_common_outbox_args(dry_run_parser)
    dry_run_parser.add_argument("--now", default=None)

    review_parser = subparsers.add_parser(
        "review-outbox",
        help="Print a sanitized read-only summary of delivery outbox state.",
    )
    review_parser.add_argument("--state-dir", type=Path, required=True)
    review_parser.add_argument("--now", default=None)
    review_parser.add_argument("--limit", type=int, default=20)
    review_parser.add_argument("--incident-key", default=None)
    review_parser.add_argument("--report-reference", default=None)
    review_parser.add_argument("--include-terminal", action="store_true")

    skip_parser = subparsers.add_parser(
        "skip-outbox",
        help="Mark pending outbox items as operator-skipped without sending.",
    )
    skip_parser.add_argument("--state-dir", type=Path, required=True)
    skip_parser.add_argument("--confirm", required=True)
    skip_parser.add_argument("--now", default=None)
    skip_parser.add_argument("--limit", type=int, required=True)
    skip_parser.add_argument("--created-before", default=None)
    skip_parser.add_argument("--idempotency-key", default=None)
    skip_parser.add_argument("--incident-key", default=None)
    skip_parser.add_argument("--report-reference", default=None)

    prepare_parser = subparsers.add_parser(
        "prepare-synthetic",
        help="Create one synthetic outbox item and sanitized report file for a local controlled test.",
    )
    prepare_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    prepare_parser.add_argument("--state-dir", type=Path, required=True)
    prepare_parser.add_argument("--report-file", type=Path, required=True)
    prepare_parser.add_argument(
        "--report-reference",
        default="controlled-test-report:v1:synthetic-endpoint-system-database",
    )
    prepare_parser.add_argument("--confirm", required=True)
    prepare_parser.add_argument("--allow-existing-state", action="store_true")
    prepare_parser.add_argument("--now", default=None)

    send_parser = subparsers.add_parser(
        "send-due",
        help="Send one explicitly confirmed test delivery from the outbox.",
    )
    _add_common_policy_args(send_parser)
    _add_common_outbox_args(send_parser)
    send_parser.add_argument("--report-file", type=Path, required=True)
    send_parser.add_argument("--claim-id", required=True)
    send_parser.add_argument("--confirm", required=True)
    send_parser.add_argument("--now", default=None)
    send_parser.add_argument(
        "--smtp-sender-alias-env",
        default=DEFAULT_SMTP_SENDER_ALIAS_ENV,
    )
    return parser


def _add_common_policy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--recipient-env", default=DEFAULT_RECIPIENT_ENV)


def _add_common_outbox_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--report-reference", required=True)
    parser.add_argument("--idempotency-key", default=None)
    parser.add_argument("--limit", type=int, default=1)


def _hash_recipient(args: argparse.Namespace) -> dict[str, object]:
    recipient = _read_required_env(args.recipient_env, error_code="recipient_env_missing")
    return {
        "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
        "event": "monitoring_test_delivery_recipient_hash",
        "recipient_hash": hash_delivery_recipient(recipient),
    }


def _env_file_keys_for_command(args: argparse.Namespace) -> set[str]:
    keys: set[str] = set()
    recipient_env = str(getattr(args, "recipient_env", "") or "").strip()
    if recipient_env:
        keys.add(recipient_env)
    sender_alias_env = str(getattr(args, "smtp_sender_alias_env", "") or "").strip()
    if sender_alias_env:
        keys.add(sender_alias_env)
    if getattr(args, "command", None) == "send-due":
        keys.update({"O_EMAIL", "O_APP", "EMAIL", "APP"})
    return keys


def _load_env_file(path: Path | None, *, allowed_keys: set[str]) -> None:
    if path is None:
        return
    if not allowed_keys:
        return
    resolved = path.resolve()
    if not resolved.exists():
        return
    if not resolved.is_file():
        raise DeliveryCliError("env_file_not_file")
    for raw_line in resolved.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key not in allowed_keys or key in os.environ:
            continue
        os.environ[key] = _normalize_env_file_value(value)


def _normalize_env_file_value(value: str) -> str:
    normalized = value.strip()
    if (
        len(normalized) >= 2
        and normalized[0] == normalized[-1]
        and normalized[0] in {"'", '"'}
    ):
        return normalized[1:-1]
    return normalized


def _dry_run(args: argparse.Namespace) -> dict[str, object]:
    now = _parse_now(args.now)
    policy = _policy_from_env(args)
    policy_error = validate_test_delivery_policy(policy)
    if policy_error is not None:
        return {
            "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
            "event": "monitoring_test_delivery_dry_run",
            "error_code": policy_error,
            "status": DELIVERY_STATUS_CONFIGURATION_ERROR,
        }
    snapshot = IncidentStateStore(args.state_dir).load()
    due_items = [
        item
        for item in snapshot.outbox_items
        if item.status == OUTBOX_PENDING
        and item.next_attempt_at <= now
        and item.report_reference == args.report_reference
        and (
            args.idempotency_key is None
            or item.idempotency_key == args.idempotency_key
        )
    ]
    return {
        "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
        "event": "monitoring_test_delivery_dry_run",
        "due_count": len(due_items),
        "mode": DELIVERY_MODE_TEST,
        "recipient_hash": hash_delivery_recipient(
            _read_required_env(args.recipient_env, error_code="recipient_env_missing")
        ),
        "status": "dry_run_ok",
    }


def _review_outbox(args: argparse.Namespace) -> dict[str, object]:
    if args.limit < 1:
        raise DeliveryCliError("review_limit_must_be_positive")
    now = _parse_now(args.now)
    snapshot = IncidentStateStore(args.state_dir).load()
    outbox_items = list(snapshot.outbox_items)
    status_counts = _count_by(outbox_items, key_name="status")
    action_counts = _count_by(outbox_items, key_name="action")
    due_pending_items = [
        item
        for item in outbox_items
        if item.status == OUTBOX_PENDING and item.next_attempt_at <= now
    ]
    review_items = [
        item
        for item in outbox_items
        if (
            args.include_terminal
            or item.status not in OUTBOX_REVIEW_TERMINAL_STATUSES
        )
        and (
            args.incident_key is None
            or item.incident_key == str(args.incident_key)
        )
        and (
            args.report_reference is None
            or item.report_reference == str(args.report_reference)
        )
    ]
    review_items.sort(
        key=lambda item: (
            item.next_attempt_at,
            item.created_at,
            item.incident_key,
            item.idempotency_key,
        )
    )
    limited_items = review_items[: args.limit]
    return {
        "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
        "due_pending_count": len(due_pending_items),
        "event": "monitoring_delivery_outbox_review",
        "generated_at": now.isoformat(),
        "item_count": len(outbox_items),
        "items": [_review_item_to_dict(item, now=now) for item in limited_items],
        "review_item_count": len(review_items),
        "state_updated_at": (
            snapshot.updated_at.isoformat() if snapshot.updated_at is not None else None
        ),
        "status": "reviewed",
        "status_counts": status_counts,
        "action_counts": action_counts,
        "truncated_item_count": max(0, len(review_items) - len(limited_items)),
    }


def _skip_outbox(args: argparse.Namespace) -> dict[str, object]:
    if args.confirm != CONFIRM_SKIP_PENDING_OUTBOX:
        return {
            "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
            "event": "monitoring_delivery_outbox_skip",
            "error_code": "confirmation_required",
            "status": DELIVERY_STATUS_CONFIGURATION_ERROR,
        }
    if args.limit < 1:
        raise DeliveryCliError("skip_limit_must_be_positive")
    created_before = _parse_optional_datetime(
        args.created_before,
        error_code="invalid_created_before",
    )
    if (
        args.idempotency_key is None
        and args.incident_key is None
        and args.report_reference is None
        and created_before is None
    ):
        raise DeliveryCliError("skip_filter_required")
    now = _parse_now(args.now)
    skipped = IncidentStateStore(args.state_dir).skip_pending_delivery_intents(
        now=now,
        limit=args.limit,
        idempotency_key=args.idempotency_key,
        incident_key=args.incident_key,
        report_reference=args.report_reference,
        created_before=created_before,
        reason_code="operator_skipped",
    )
    return {
        "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
        "created_before": (
            created_before.isoformat() if created_before is not None else None
        ),
        "event": "monitoring_delivery_outbox_skip",
        "generated_at": now.isoformat(),
        "idempotency_key": args.idempotency_key,
        "incident_key": args.incident_key,
        "items": [_review_item_to_dict(item, now=now) for item in skipped],
        "reason_code": "operator_skipped",
        "report_reference": args.report_reference,
        "requested_limit": args.limit,
        "skipped_count": len(skipped),
        "status": "skipped" if skipped else "no_matching_pending_items",
        "terminal_status": OUTBOX_DEAD_LETTER,
    }


def _prepare_synthetic(args: argparse.Namespace) -> dict[str, object]:
    if args.confirm != CONFIRM_PREPARE_SYNTHETIC_STATE:
        return {
            "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
            "event": "monitoring_test_delivery_prepare_synthetic",
            "error_code": "confirmation_required",
            "status": DELIVERY_STATUS_CONFIGURATION_ERROR,
        }
    report_file = args.report_file.resolve()
    if report_file.name.lower().startswith(".env"):
        raise DeliveryCliError(DELIVERY_ERROR_REPORT_FILE_REJECTED)
    store = IncidentStateStore(args.state_dir)
    if store.state_path.exists() and not args.allow_existing_state:
        raise DeliveryCliError("synthetic_state_already_exists")
    now = _parse_now(args.now)
    evaluation = evaluate_incident_lifecycle(
        [
            _synthetic_cycle(1, observed_at=now),
            _synthetic_cycle(2, observed_at=now),
        ]
    )
    snapshot = store.apply_evaluation(
        evaluation,
        report_references={"endpoint:system_database": args.report_reference},
        now=now,
    )
    matching_items = [
        item
        for item in snapshot.outbox_items
        if item.report_reference == args.report_reference
    ]
    if not matching_items:
        raise DeliveryCliError("synthetic_outbox_missing")
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(_synthetic_report_text(now), encoding="utf-8")
    item = matching_items[0]
    return {
        "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
        "event": "monitoring_test_delivery_prepare_synthetic",
        "idempotency_key": item.idempotency_key,
        "incident_key": item.incident_key,
        "report_reference": item.report_reference,
        "status": "prepared",
    }


def _send_due(args: argparse.Namespace) -> dict[str, object]:
    if args.confirm != CONFIRM_SEND_TEST_DELIVERY:
        return {
            "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
            "event": "monitoring_test_delivery_send",
            "error_code": DELIVERY_ERROR_CONFIRMATION_REQUIRED,
            "status": DELIVERY_STATUS_CONFIGURATION_ERROR,
        }
    if args.limit != 1:
        raise DeliveryCliError("send_limit_must_be_one")
    now = _parse_now(args.now)
    policy = _policy_from_env(args)
    policy_error = validate_test_delivery_policy(policy)
    if policy_error is not None:
        return {
            "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
            "event": "monitoring_test_delivery_send",
            "error_code": policy_error,
            "status": DELIVERY_STATUS_CONFIGURATION_ERROR,
        }
    report_text = _read_report_text(args.report_file)
    email_env_error = validate_outlook_email_environment()
    if email_env_error is not None:
        return {
            "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
            "event": "monitoring_test_delivery_send",
            "error_code": email_env_error,
            "status": DELIVERY_STATUS_CONFIGURATION_ERROR,
        }
    transport = OutlookEmailTransport(
        sender_alias=_read_optional_env(args.smtp_sender_alias_env),
    )
    results = deliver_due_test_delivery_intents(
        store=IncidentStateStore(args.state_dir),
        reports_by_reference={args.report_reference: report_text},
        policy=policy,
        transport=transport,
        claim_id=args.claim_id,
        now=now,
        limit=1,
        idempotency_key=args.idempotency_key,
        report_reference=args.report_reference,
    )
    return {
        "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
        "event": "monitoring_test_delivery_send",
        "results": [item.to_dict() for item in results],
        "status": _aggregate_status(results),
    }


def _policy_from_env(args: argparse.Namespace) -> TestDeliveryPolicy:
    recipient = _read_required_env(args.recipient_env, error_code="recipient_env_missing")
    return TestDeliveryPolicy(
        enabled=True,
        mode=DELIVERY_MODE_TEST,
        test_recipient=recipient,
        allowed_recipient_hashes=(hash_delivery_recipient(recipient),),
    )


def _read_report_text(path: Path) -> str:
    resolved = path.resolve()
    if resolved.name.lower().startswith(".env"):
        raise DeliveryCliError(DELIVERY_ERROR_REPORT_FILE_REJECTED)
    if not resolved.is_file():
        raise DeliveryCliError("report_file_missing")
    return resolved.read_text(encoding="utf-8")


def _read_required_env(name: str, *, error_code: str) -> str:
    value = os.environ.get(str(name or "").strip())
    if value is None or not value.strip():
        raise DeliveryCliError(error_code)
    return value.strip()


def _read_optional_env(name: str) -> str | None:
    value = os.environ.get(str(name or "").strip())
    if value is None or not value.strip():
        return None
    return value.strip()


def _parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        resolved = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeliveryCliError("invalid_now") from exc
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise DeliveryCliError("invalid_now")
    return resolved.astimezone(timezone.utc)


def _parse_optional_datetime(value: str | None, *, error_code: str) -> datetime | None:
    if value is None:
        return None
    try:
        resolved = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DeliveryCliError(error_code) from exc
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise DeliveryCliError(error_code)
    return resolved.astimezone(timezone.utc)


def _synthetic_cycle(sequence: int, *, observed_at: datetime) -> CycleSnapshot:
    return CycleSnapshot(
        cycle_sequence=sequence,
        observed_at=observed_at,
        endpoint_observations=tuple(
            EndpointObservationFact(
                endpoint_key=endpoint_key,
                transport_status="success",
                http_status=200,
                payload_status=(
                    "degraded" if endpoint_key == "system_database" else "ok"
                ),
            )
            for endpoint_key in CURRENT_ENDPOINT_KEYS
        ),
    )


def _synthetic_report_text(now: datetime) -> str:
    return "\n".join(
        [
            "# Monitoring agent controlled synthetic delivery test",
            "",
            f"Generated at: {now.astimezone(timezone.utc).isoformat()}",
            "Scope: local synthetic outbox delivery test only.",
            "Legacy scheduler alerts remain authoritative.",
            "No production recipient, alert replacement, process control, or remediation is authorized.",
            "",
        ]
    )


def _aggregate_status(results: Sequence[DeliveryAttemptResult]) -> str:
    statuses = {item.status for item in results}
    if len(statuses) == 1:
        return next(iter(statuses))
    return "mixed"


def _count_by(items: Sequence[object], *, key_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(getattr(item, key_name, "") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _review_item_to_dict(item, *, now: datetime) -> dict[str, object]:
    return {
        "action": item.action,
        "attempt_count": item.attempt_count,
        "due": item.status == OUTBOX_PENDING and item.next_attempt_at <= now,
        "created_at": item.created_at.isoformat(),
        "idempotency_key": item.idempotency_key,
        "incident_key": item.incident_key,
        "last_attempt_at": (
            item.last_attempt_at.isoformat()
            if item.last_attempt_at is not None
            else None
        ),
        "last_error_code": item.last_error_code,
        "next_attempt_at": item.next_attempt_at.isoformat(),
        "report_reference": item.report_reference,
        "status": item.status,
        "updated_at": item.updated_at.isoformat(),
    }


def _send_exit_code(payload: MappingLike) -> int:
    status = payload.get("status")
    if status in {"sent", "no_due_items"}:
        return 0
    return 2 if status == DELIVERY_STATUS_CONFIGURATION_ERROR else 1


def _print_json(payload: MappingLike) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


MappingLike = dict[str, object]


if __name__ == "__main__":
    raise SystemExit(main())
