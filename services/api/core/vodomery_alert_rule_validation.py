from __future__ import annotations

import re

from moduly.mereni.vodomery.database.alerting import EVENT_TYPE_OPTIONS, SEND_ON_OPTIONS, SEVERITY_OPTIONS


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NON_EMPTY_EVENT_TYPE_OPTIONS = tuple(option for option in EVENT_TYPE_OPTIONS if option)


def _clean_text(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_required_choice(value: object | None, *, field_name: str, allowed_values: tuple[str, ...]) -> str:
    cleaned = _clean_text(value).upper()
    if not cleaned:
        raise ValueError(f"{field_name} je povinne.")
    if cleaned not in allowed_values:
        raise ValueError(f"{field_name} musi byt jedna z hodnot: {', '.join(allowed_values)}.")
    return cleaned


def normalize_alert_rule_name(value: object | None) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        raise ValueError("Nazev pravidla je povinny.")
    if len(cleaned) > 150:
        raise ValueError("Nazev pravidla muze mit nejvyse 150 znaku.")
    return cleaned


def normalize_alert_rule_email(value: object | None) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        raise ValueError("Email prijemce je povinny.")
    if len(cleaned) > 250:
        raise ValueError("Email prijemce muze mit nejvyse 250 znaku.")
    if not _EMAIL_PATTERN.fullmatch(cleaned):
        raise ValueError("Email prijemce nema platny format.")
    return cleaned


def normalize_alert_rule_severity(value: object | None) -> str:
    return _normalize_required_choice(
        value,
        field_name="severity_min",
        allowed_values=SEVERITY_OPTIONS,
    )


def normalize_alert_rule_send_on(value: object | None) -> str:
    return _normalize_required_choice(
        value,
        field_name="send_on",
        allowed_values=SEND_ON_OPTIONS,
    )


def normalize_alert_rule_event_type(value: object | None) -> str | None:
    cleaned = _clean_text(value).upper()
    if not cleaned:
        return None
    if cleaned not in _NON_EMPTY_EVENT_TYPE_OPTIONS:
        raise ValueError(
            f"event_type musi byt jedna z hodnot: {', '.join(_NON_EMPTY_EVENT_TYPE_OPTIONS)}."
        )
    return cleaned


def normalize_alert_rule_identifikace(value: object | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    if len(cleaned) > 250:
        raise ValueError("Identifikace muze mit nejvyse 250 znaku.")
    return cleaned


def normalize_alert_rule_min_duration(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("min_duration_minutes musi byt cele cislo.") from exc
    if normalized < 0:
        raise ValueError("min_duration_minutes musi byt 0 nebo vice.")
    return normalized


def normalize_alert_rule_note(value: object | None) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def normalize_alert_rule_payload(
    *,
    rule_name: object | None,
    recipient_email: object | None,
    severity_min: object | None,
    min_duration_minutes: object,
    send_on: object | None,
    identifikace: object | None = None,
    event_type: object | None = None,
    enabled: object = True,
    note: object | None = None,
) -> dict[str, object]:
    return {
        "rule_name": normalize_alert_rule_name(rule_name),
        "recipient_email": normalize_alert_rule_email(recipient_email),
        "severity_min": normalize_alert_rule_severity(severity_min),
        "min_duration_minutes": normalize_alert_rule_min_duration(min_duration_minutes),
        "send_on": normalize_alert_rule_send_on(send_on),
        "identifikace": normalize_alert_rule_identifikace(identifikace),
        "event_type": normalize_alert_rule_event_type(event_type),
        "enabled": bool(enabled),
        "note": normalize_alert_rule_note(note),
    }
