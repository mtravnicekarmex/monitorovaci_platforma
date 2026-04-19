from __future__ import annotations

import logging
from email.utils import parseaddr
from typing import Iterable

from decouple import config

logger = logging.getLogger(__name__)

_RESERVED_EMAIL_DOMAINS = (
    "example.com",
    "example.net",
    "example.org",
    "invalid",
    "localhost",
    "test",
)
_RESERVED_EMAIL_SUFFIXES = (
    ".example.com",
    ".example.net",
    ".example.org",
    ".invalid",
    ".localhost",
    ".test",
)


def _normalize_values(values: Iterable[str]) -> tuple[str, ...]:
    normalized_values: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized_values:
            normalized_values.append(text)
    return tuple(normalized_values)


def _extract_email_domain(value: str) -> str | None:
    _, parsed_address = parseaddr(value)
    candidate = parsed_address.strip() if parsed_address else str(value).strip()
    if "@" not in candidate:
        return None
    domain = candidate.rsplit("@", 1)[-1].strip().lower().rstrip(".")
    return domain or None


def is_placeholder_email_address(value: str) -> bool:
    domain = _extract_email_domain(value)
    if domain is None:
        return False
    return domain in _RESERVED_EMAIL_DOMAINS or any(
        domain.endswith(suffix)
        for suffix in _RESERVED_EMAIL_SUFFIXES
    )


def filter_placeholder_recipients(
    recipients: Iterable[str],
    *,
    context_label: str,
) -> tuple[str, ...]:
    normalized_recipients = _normalize_values(recipients)
    if not normalized_recipients:
        return ()

    valid_recipients = tuple(
        recipient
        for recipient in normalized_recipients
        if not is_placeholder_email_address(recipient)
    )
    skipped_recipients = tuple(
        recipient
        for recipient in normalized_recipients
        if recipient not in valid_recipients
    )

    if skipped_recipients:
        logger.warning(
            "Ignoruji placeholder email prijemce pro %s: %s",
            context_label,
            ", ".join(skipped_recipients),
        )
    if not valid_recipients and skipped_recipients:
        logger.warning(
            "Preskakuji doruceni pro %s, protoze jsou nastaveni jen placeholder prijemci.",
            context_label,
        )

    return valid_recipients


def load_report_recipients(
    env_key: str,
    *,
    default: str = "",
    fallback_env_keys: tuple[str, ...] = (),
    error_cls: type[Exception] = ValueError,
) -> tuple[str, ...]:
    raw_recipients = ""
    for candidate_key in (env_key, *fallback_env_keys):
        candidate_value = str(config(candidate_key, default="") or "").strip()
        if candidate_value:
            raw_recipients = candidate_value
            break

    if not raw_recipients:
        raw_recipients = str(default or "").strip()

    recipients = _normalize_values(raw_recipients.split(","))
    if not recipients:
        raise error_cls(f"Neni nastavena promenna {env_key}.")

    return filter_placeholder_recipients(recipients, context_label=env_key)


def sanitize_sender_alias(
    sender_alias: str | None,
    *,
    context_label: str,
) -> str | None:
    normalized_sender_alias = str(sender_alias or "").strip()
    if not normalized_sender_alias:
        return None

    if is_placeholder_email_address(normalized_sender_alias):
        logger.warning(
            "Ignoruji placeholder sender alias pro %s: %s",
            context_label,
            normalized_sender_alias,
        )
        return None

    return normalized_sender_alias
