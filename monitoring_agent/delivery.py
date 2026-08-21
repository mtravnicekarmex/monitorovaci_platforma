from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr
import hashlib
import os
import re
import smtplib
import ssl
import threading
import time
from typing import Protocol

from .incident_store import IncidentStateStore, OutboxItem
from .reporting import redact_monitoring_text


DELIVERY_ADAPTER_VERSION = 1
DELIVERY_MODE_TEST = "test"
DELIVERY_MODE_DISABLED = "disabled"
DELIVERY_STATUS_DISABLED = "disabled"
DELIVERY_STATUS_CONFIGURATION_ERROR = "configuration_error"
DELIVERY_STATUS_NO_DUE_ITEMS = "no_due_items"
DELIVERY_STATUS_SENT = "sent"
DELIVERY_STATUS_FAILED = "failed"
DELIVERY_ERROR_DELIVERY_DISABLED = "delivery_disabled"
DELIVERY_ERROR_INVALID_POLICY = "invalid_delivery_policy"
DELIVERY_ERROR_RECIPIENT_NOT_ALLOWLISTED = "recipient_not_allowlisted"
DELIVERY_ERROR_REPORT_MISSING = "report_missing"
DELIVERY_ERROR_REPORT_FILE_REJECTED = "report_file_rejected"
DELIVERY_ERROR_TRANSPORT_FAILED = "delivery_transport_failed"
DELIVERY_ERROR_UNSUPPORTED_MODE = "unsupported_delivery_mode"
DELIVERY_ERROR_CONFIRMATION_REQUIRED = "confirmation_required"
DEFAULT_TEST_SUBJECT_PREFIX = "[monitoring-agent-test]"
DEFAULT_MAX_SUBJECT_CHARS = 160
DEFAULT_MAX_BODY_CHARS = 12_000
OUTLOOK_EMAIL_ENV_KEY = "O_EMAIL"
OUTLOOK_APP_ENV_KEY = "O_APP"
LEGACY_EMAIL_ENV_KEY = "EMAIL"
LEGACY_APP_ENV_KEY = "APP"
OUTLOOK_SMTP_HOST = "smtp.office365.com"
OUTLOOK_SMTP_PORT = 587
OUTLOOK_SMTP_TIMEOUT_SECONDS = 30.0
OUTLOOK_SMTP_MAX_ATTEMPTS = 3
OUTLOOK_SMTP_RETRY_DELAY_SECONDS = 5.0
OUTLOOK_SMTP_TRANSIENT_CODES = {421, 432, 451, 452}
_SMTP_LOCK = threading.Lock()


class DeliveryTransport(Protocol):
    def send(self, envelope: DeliveryEnvelope) -> None:
        """Send one in-memory delivery envelope or raise an exception."""


@dataclass(frozen=True)
class TestDeliveryPolicy:
    enabled: bool = False
    mode: str = DELIVERY_MODE_DISABLED
    test_recipient: str | None = None
    allowed_recipient_hashes: tuple[str, ...] = ()
    subject_prefix: str = DEFAULT_TEST_SUBJECT_PREFIX
    max_subject_chars: int = DEFAULT_MAX_SUBJECT_CHARS
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS

    def __post_init__(self) -> None:
        if self.mode not in {DELIVERY_MODE_DISABLED, DELIVERY_MODE_TEST}:
            raise ValueError("delivery mode is invalid")
        if not isinstance(self.enabled, bool):
            raise ValueError("delivery enabled flag must be boolean")
        if not self.subject_prefix.strip():
            raise ValueError("delivery subject prefix is required")
        for name in ("max_subject_chars", "max_body_chars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        object.__setattr__(
            self,
            "allowed_recipient_hashes",
            tuple(str(value).strip().lower() for value in self.allowed_recipient_hashes),
        )


@dataclass(frozen=True)
class DeliveryEnvelope:
    recipient: str
    subject: str
    body_text: str
    idempotency_key: str
    incident_key: str
    action: str
    report_reference: str
    recipient_hash: str

    def __post_init__(self) -> None:
        if not self.recipient.strip():
            raise ValueError("delivery recipient is required")
        if not self.subject.strip():
            raise ValueError("delivery subject is required")
        if not self.body_text.strip():
            raise ValueError("delivery body is required")
        for name in (
            "idempotency_key",
            "incident_key",
            "action",
            "report_reference",
            "recipient_hash",
        ):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")


@dataclass(frozen=True)
class DeliveryAttemptResult:
    status: str
    idempotency_key: str | None = None
    incident_key: str | None = None
    action: str | None = None
    report_reference: str | None = None
    recipient_hash: str | None = None
    attempt_count: int | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "attempt_count": self.attempt_count,
            "delivery_adapter_version": DELIVERY_ADAPTER_VERSION,
            "error_code": self.error_code,
            "idempotency_key": self.idempotency_key,
            "incident_key": self.incident_key,
            "recipient_hash": self.recipient_hash,
            "report_reference": self.report_reference,
            "status": self.status,
        }


class OutlookEmailTransport:
    def __init__(
        self,
        *,
        sender_alias: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._sender_alias = sender_alias
        self._env = env

    def send(self, envelope: DeliveryEnvelope) -> None:
        kwargs = {
            "email_receiver": envelope.recipient,
            "subject": envelope.subject,
            "body": envelope.body_text,
            "sender_alias": self._sender_alias,
            "is_html": False,
        }
        if self._env is not None:
            kwargs["env"] = self._env
        send_email_outlook(
            **kwargs,
        )


def send_email_outlook(
    *,
    email_receiver: str,
    subject: str,
    body: str,
    sender_alias: str | None = None,
    is_html: bool = False,
    env: Mapping[str, str] | None = None,
    smtp_factory=None,
    sleep_func=None,
) -> None:
    resolved_env = os.environ if env is None else env
    email_sender, email_password = _read_outlook_credentials(resolved_env)
    message = EmailMessage()
    message["From"] = sender_alias or email_sender
    message["To"] = normalize_delivery_recipient(email_receiver)
    message["Subject"] = subject

    if is_html:
        message.set_content(_html_to_plain_text(body))
        message.add_alternative(body, subtype="html")
    else:
        message.set_content(body)

    context = ssl.create_default_context()
    smtp_factory = smtplib.SMTP if smtp_factory is None else smtp_factory
    sleep_func = time.sleep if sleep_func is None else sleep_func

    with _SMTP_LOCK:
        for attempt in range(1, OUTLOOK_SMTP_MAX_ATTEMPTS + 1):
            try:
                _send_outlook_message_once(
                    email_sender=email_sender,
                    email_password=email_password,
                    message=message,
                    context=context,
                    smtp_factory=smtp_factory,
                )
                return
            except Exception as exc:
                if (
                    attempt >= OUTLOOK_SMTP_MAX_ATTEMPTS
                    or not _is_transient_smtp_error(exc)
                ):
                    raise
                sleep_func(OUTLOOK_SMTP_RETRY_DELAY_SECONDS * attempt)


def validate_outlook_email_environment(
    env: Mapping[str, str] | None = None,
) -> str | None:
    resolved_env = os.environ if env is None else env
    primary_sender = _read_optional_env_value(resolved_env, OUTLOOK_EMAIL_ENV_KEY)
    primary_password = _read_optional_env_value(resolved_env, OUTLOOK_APP_ENV_KEY)
    if primary_sender or primary_password:
        if not primary_sender:
            return "email_env_missing"
        if not primary_password:
            return "app_env_missing"
        return None

    fallback_sender = _read_optional_env_value(resolved_env, LEGACY_EMAIL_ENV_KEY)
    fallback_password = _read_optional_env_value(resolved_env, LEGACY_APP_ENV_KEY)
    if fallback_sender or fallback_password:
        if not fallback_sender:
            return "email_env_missing"
        if not fallback_password:
            return "app_env_missing"
        return None

    return "email_env_missing"


def hash_delivery_recipient(recipient: str) -> str:
    normalized = normalize_delivery_recipient(recipient)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_delivery_recipient(recipient: str) -> str:
    _, parsed_address = parseaddr(str(recipient or ""))
    candidate = parsed_address.strip() if parsed_address else str(recipient or "").strip()
    if "@" not in candidate:
        raise ValueError("delivery recipient must be an email address")
    local, domain = candidate.rsplit("@", 1)
    if not local.strip() or not domain.strip():
        raise ValueError("delivery recipient must be an email address")
    return f"{local.strip()}@{domain.strip().lower()}"


def build_test_delivery_envelope(
    *,
    outbox_item: OutboxItem,
    report_text: str,
    policy: TestDeliveryPolicy,
) -> DeliveryEnvelope:
    recipient = _require_test_recipient(policy)
    recipient_hash = hash_delivery_recipient(recipient)
    subject = _bounded_text(
        (
            f"{policy.subject_prefix.strip()} {outbox_item.action} "
            f"{outbox_item.incident_key}"
        ),
        max_chars=policy.max_subject_chars,
    )
    sanitized_report = redact_monitoring_text(report_text)
    body = _bounded_text(
        "\n".join(
            [
                "Monitoring agent controlled TEST delivery.",
                "Legacy scheduler alerts remain authoritative.",
                "This message does not authorize remediation or alert replacement.",
                "",
                f"incident_key: {outbox_item.incident_key}",
                f"action: {outbox_item.action}",
                f"report_reference: {outbox_item.report_reference}",
                f"idempotency_key: {outbox_item.idempotency_key}",
                "",
                sanitized_report,
                "",
            ]
        ),
        max_chars=policy.max_body_chars,
    )
    return DeliveryEnvelope(
        recipient=normalize_delivery_recipient(recipient),
        subject=subject,
        body_text=body,
        idempotency_key=outbox_item.idempotency_key,
        incident_key=outbox_item.incident_key,
        action=outbox_item.action,
        report_reference=outbox_item.report_reference,
        recipient_hash=recipient_hash,
    )


def deliver_due_test_delivery_intents(
    *,
    store: IncidentStateStore,
    reports_by_reference: Mapping[str, str],
    policy: TestDeliveryPolicy,
    transport: DeliveryTransport,
    claim_id: str,
    now: datetime,
    limit: int = 10,
    idempotency_key: str | None = None,
    report_reference: str | None = None,
) -> tuple[DeliveryAttemptResult, ...]:
    _require_aware_datetime(now, context="now")
    if not claim_id.strip():
        raise ValueError("claim id is required")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("delivery limit must be a positive integer")
    configuration_error = _delivery_configuration_error(policy)
    if configuration_error is not None:
        return (
            DeliveryAttemptResult(
                status=(
                    DELIVERY_STATUS_DISABLED
                    if configuration_error == DELIVERY_ERROR_DELIVERY_DISABLED
                    else DELIVERY_STATUS_CONFIGURATION_ERROR
                ),
                error_code=configuration_error,
            ),
        )

    claimed = store.claim_due_delivery_intents(
        claim_id=claim_id.strip(),
        now=now,
        limit=limit,
        idempotency_key=idempotency_key,
        report_reference=report_reference,
    )
    if not claimed:
        return (DeliveryAttemptResult(status=DELIVERY_STATUS_NO_DUE_ITEMS),)

    results: list[DeliveryAttemptResult] = []
    for item in claimed:
        report_text = reports_by_reference.get(item.report_reference)
        if report_text is None:
            snapshot = store.record_delivery_result(
                idempotency_key=item.idempotency_key,
                claim_id=claim_id.strip(),
                succeeded=False,
                error_code=DELIVERY_ERROR_REPORT_MISSING,
                now=now,
            )
            updated_item = snapshot.outbox_by_key()[item.idempotency_key]
            results.append(
                _result_from_item(
                    updated_item,
                    status=DELIVERY_STATUS_FAILED,
                    recipient_hash=hash_delivery_recipient(
                        _require_test_recipient(policy)
                    ),
                    error_code=DELIVERY_ERROR_REPORT_MISSING,
                )
            )
            continue

        envelope = build_test_delivery_envelope(
            outbox_item=item,
            report_text=report_text,
            policy=policy,
        )
        try:
            transport.send(envelope)
        except Exception:
            snapshot = store.record_delivery_result(
                idempotency_key=item.idempotency_key,
                claim_id=claim_id.strip(),
                succeeded=False,
                error_code=DELIVERY_ERROR_TRANSPORT_FAILED,
                now=now,
            )
            updated_item = snapshot.outbox_by_key()[item.idempotency_key]
            results.append(
                _result_from_item(
                    updated_item,
                    status=DELIVERY_STATUS_FAILED,
                    recipient_hash=envelope.recipient_hash,
                    error_code=DELIVERY_ERROR_TRANSPORT_FAILED,
                )
            )
            continue

        snapshot = store.record_delivery_result(
            idempotency_key=item.idempotency_key,
            claim_id=claim_id.strip(),
            succeeded=True,
            now=now,
        )
        updated_item = snapshot.outbox_by_key()[item.idempotency_key]
        results.append(
            _result_from_item(
                updated_item,
                status=DELIVERY_STATUS_SENT,
                recipient_hash=envelope.recipient_hash,
            )
        )
    return tuple(results)


def _delivery_configuration_error(policy: TestDeliveryPolicy) -> str | None:
    if not policy.enabled:
        return DELIVERY_ERROR_DELIVERY_DISABLED
    if policy.mode != DELIVERY_MODE_TEST:
        return DELIVERY_ERROR_UNSUPPORTED_MODE
    try:
        recipient = _require_test_recipient(policy)
        recipient_hash = hash_delivery_recipient(recipient)
    except ValueError:
        return DELIVERY_ERROR_INVALID_POLICY
    allowed_hashes = tuple(policy.allowed_recipient_hashes)
    if not allowed_hashes or any(not _is_sha256_hex(value) for value in allowed_hashes):
        return DELIVERY_ERROR_INVALID_POLICY
    if recipient_hash not in allowed_hashes:
        return DELIVERY_ERROR_RECIPIENT_NOT_ALLOWLISTED
    return None


def validate_test_delivery_policy(policy: TestDeliveryPolicy) -> str | None:
    return _delivery_configuration_error(policy)


def _require_test_recipient(policy: TestDeliveryPolicy) -> str:
    if policy.test_recipient is None or not str(policy.test_recipient).strip():
        raise ValueError("test delivery recipient is required")
    return normalize_delivery_recipient(policy.test_recipient)


def _result_from_item(
    item: OutboxItem,
    *,
    status: str,
    recipient_hash: str | None = None,
    error_code: str | None = None,
) -> DeliveryAttemptResult:
    return DeliveryAttemptResult(
        status=status,
        idempotency_key=item.idempotency_key,
        incident_key=item.incident_key,
        action=item.action,
        report_reference=item.report_reference,
        recipient_hash=recipient_hash,
        attempt_count=item.attempt_count,
        error_code=error_code,
    )


def _is_sha256_hex(value: str) -> bool:
    return (
        len(value) == 64
        and all(character in "0123456789abcdef" for character in value.lower())
    )


def _is_transient_smtp_error(exc: BaseException) -> bool:
    if not isinstance(exc, smtplib.SMTPResponseException):
        return False
    return int(exc.smtp_code) in OUTLOOK_SMTP_TRANSIENT_CODES


def _send_outlook_message_once(
    *,
    email_sender: str,
    email_password: str,
    message: EmailMessage,
    context: ssl.SSLContext,
    smtp_factory,
) -> None:
    with smtp_factory(
        OUTLOOK_SMTP_HOST,
        OUTLOOK_SMTP_PORT,
        timeout=OUTLOOK_SMTP_TIMEOUT_SECONDS,
    ) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(email_sender, email_password)
        smtp.send_message(message)


def _html_to_plain_text(body: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.replace("&nbsp;", " ").strip()


def _read_outlook_credentials(env: Mapping[str, str]) -> tuple[str, str]:
    primary_sender = _read_optional_env_value(env, OUTLOOK_EMAIL_ENV_KEY)
    primary_password = _read_optional_env_value(env, OUTLOOK_APP_ENV_KEY)
    if primary_sender or primary_password:
        return (
            _require_value(primary_sender, context="email sender"),
            _require_value(primary_password, context="email password"),
        )

    fallback_sender = _read_optional_env_value(env, LEGACY_EMAIL_ENV_KEY)
    fallback_password = _read_optional_env_value(env, LEGACY_APP_ENV_KEY)
    if fallback_sender or fallback_password:
        return (
            _require_value(fallback_sender, context="email sender"),
            _require_value(fallback_password, context="email password"),
        )

    raise ValueError("email sender is not configured")


def _read_optional_env_value(env: Mapping[str, str], key: str) -> str:
    return str(env.get(key, "")).strip()


def _require_value(
    value: str,
    *,
    context: str,
) -> str:
    if not value:
        raise ValueError(f"{context} is not configured")
    return value


def _bounded_text(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    marker = "\n[truncated: monitoring delivery content exceeded configured character limit]\n"
    if max_chars <= len(marker):
        return marker[:max_chars]
    return text[: max_chars - len(marker)].rstrip() + marker


def _require_aware_datetime(value: datetime, *, context: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{context} must include a timezone")
    value.astimezone(timezone.utc)


__all__ = [
    "DELIVERY_ADAPTER_VERSION",
    "DELIVERY_MODE_DISABLED",
    "DELIVERY_MODE_TEST",
    "DELIVERY_STATUS_CONFIGURATION_ERROR",
    "DELIVERY_STATUS_DISABLED",
    "DELIVERY_STATUS_FAILED",
    "DELIVERY_STATUS_NO_DUE_ITEMS",
    "DELIVERY_STATUS_SENT",
    "DELIVERY_ERROR_CONFIRMATION_REQUIRED",
    "DELIVERY_ERROR_REPORT_FILE_REJECTED",
    "DeliveryAttemptResult",
    "DeliveryEnvelope",
    "DeliveryTransport",
    "OutlookEmailTransport",
    "TestDeliveryPolicy",
    "build_test_delivery_envelope",
    "deliver_due_test_delivery_intents",
    "hash_delivery_recipient",
    "normalize_delivery_recipient",
    "send_email_outlook",
    "validate_test_delivery_policy",
    "validate_outlook_email_environment",
]
