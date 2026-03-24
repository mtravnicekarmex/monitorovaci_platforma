from __future__ import annotations

from core.db.connect import ENGINE_PG, get_session_pg
from moduly.mereni.vodomery.database.models import Mereni_vodomery, VodomeryAlertDelivery, VodomeryAlertRule


EVENT_TYPE_OPTIONS = ("", "NIGHT_USAGE", "SPIKE", "LONG_LEAK", "ZERO_FLOW", "EXPECTED_ZERO_USAGE")
SEVERITY_OPTIONS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
SEND_ON_OPTIONS = ("ACTIVE", "RESOLVED", "BOTH")


def ensure_vodomery_alerting_tables() -> None:
    VodomeryAlertRule.__table__.create(bind=ENGINE_PG, checkfirst=True)
    VodomeryAlertDelivery.__table__.create(bind=ENGINE_PG, checkfirst=True)


def list_alert_rules() -> list[dict[str, object]]:
    session = get_session_pg()
    try:
        rows = (
            session.query(VodomeryAlertRule)
            .order_by(
                VodomeryAlertRule.enabled.desc(),
                VodomeryAlertRule.rule_name.asc(),
                VodomeryAlertRule.id.asc(),
            )
            .all()
        )
        return [
            {
                "id": row.id,
                "rule_name": row.rule_name,
                "identifikace": row.identifikace,
                "event_type": row.event_type,
                "severity_min": row.severity_min,
                "min_duration_minutes": row.min_duration_minutes,
                "send_on": row.send_on,
                "recipient_email": row.recipient_email,
                "enabled": row.enabled,
                "note": row.note,
                "created_by": row.created_by,
                "updated_by": row.updated_by,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
    finally:
        session.close()


def load_device_options() -> list[str]:
    session = get_session_pg()
    try:
        rows = (
            session.query(Mereni_vodomery.identifikace)
            .distinct()
            .order_by(Mereni_vodomery.identifikace)
            .all()
        )
        return [row[0] for row in rows]
    finally:
        session.close()


def upsert_alert_rule(
    *,
    rule_name: str,
    recipient_email: str,
    severity_min: str,
    min_duration_minutes: int,
    send_on: str,
    identifikace: str | None = None,
    event_type: str | None = None,
    enabled: bool = True,
    note: str | None = None,
    actor: str | None = None,
    rule_id: int | None = None,
) -> int:
    session = get_session_pg()
    try:
        if rule_id is None:
            row = VodomeryAlertRule(
                rule_name=rule_name,
                identifikace=identifikace or None,
                event_type=event_type or None,
                severity_min=severity_min,
                min_duration_minutes=int(min_duration_minutes),
                send_on=send_on,
                recipient_email=recipient_email,
                enabled=enabled,
                note=note or None,
                created_by=actor,
                updated_by=actor,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)

        row = session.get(VodomeryAlertRule, rule_id)
        if row is None:
            raise ValueError("Alert pravidlo neexistuje.")

        row.rule_name = rule_name
        row.identifikace = identifikace or None
        row.event_type = event_type or None
        row.severity_min = severity_min
        row.min_duration_minutes = int(min_duration_minutes)
        row.send_on = send_on
        row.recipient_email = recipient_email
        row.enabled = enabled
        row.note = note or None
        row.updated_by = actor
        session.commit()
        return int(row.id)
    finally:
        session.close()


def delete_alert_rule(rule_id: int) -> None:
    session = get_session_pg()
    try:
        row = session.get(VodomeryAlertRule, rule_id)
        if row is None:
            return
        session.delete(row)
        session.commit()
    finally:
        session.close()
