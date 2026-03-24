from __future__ import annotations

from collections import defaultdict
import datetime
from html import escape
from uuid import uuid4
from zoneinfo import ZoneInfo

from decouple import config
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.email import send_email_outlook
from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.mereni.vodomery.database.models import (
    VodomeryAlertDelivery,
    VodomeryAlertRule,
    VodomeryAnomalyEvent,
)


SEVERITY_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}

LOCAL_TIMEZONE = ZoneInfo("Europe/Prague")


def process_vodomery_alerts(
    *,
    active_event_ids: list[int] | None = None,
    resolved_event_ids: list[int] | None = None,
) -> dict[str, int]:
    active_ids = _normalize_ids(active_event_ids)
    resolved_ids = _normalize_ids(resolved_event_ids)
    all_ids = sorted(set(active_ids + resolved_ids))

    if not all_ids:
        return {
            "matched": 0,
            "emails_sent": 0,
            "deliveries_sent": 0,
            "deliveries_failed": 0,
        }

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        rules = (
            session.execute(
                select(VodomeryAlertRule)
                .where(VodomeryAlertRule.enabled.is_(True))
                .order_by(VodomeryAlertRule.recipient_email.asc(), VodomeryAlertRule.rule_name.asc())
            )
            .scalars()
            .all()
        )
        if not rules:
            return {
                "matched": 0,
                "emails_sent": 0,
                "deliveries_sent": 0,
                "deliveries_failed": 0,
            }

        active_events = _load_events(session, active_ids, active_only=True)
        resolved_events = _load_events(session, resolved_ids, active_only=False)
        existing_deliveries = _load_existing_deliveries(session, all_ids)
        reserved_delivery_keys = {
            key for key, row in existing_deliveries.items() if row.status in {"SENT", "PENDING", "SKIPPED"}
        }

        grouped_candidates: dict[str, list[dict[str, object]]] = defaultdict(list)

        for event in active_events:
            for rule in rules:
                candidate = _build_candidate(rule=rule, event=event, alert_state="ACTIVE_THRESHOLD")
                if candidate is None:
                    continue
                delivery_key = candidate["delivery_key"]
                if delivery_key in reserved_delivery_keys:
                    continue
                candidate["existing_delivery"] = existing_deliveries.get(delivery_key)
                grouped_candidates[str(candidate["recipient_email"])].append(candidate)
                reserved_delivery_keys.add(delivery_key)

        for event in resolved_events:
            for rule in rules:
                candidate = _build_candidate(rule=rule, event=event, alert_state="RESOLVED")
                if candidate is None:
                    continue
                delivery_key = candidate["delivery_key"]
                if delivery_key in reserved_delivery_keys:
                    continue
                candidate["existing_delivery"] = existing_deliveries.get(delivery_key)
                grouped_candidates[str(candidate["recipient_email"])].append(candidate)
                reserved_delivery_keys.add(delivery_key)

        if not grouped_candidates:
            return {
                "matched": 0,
                "emails_sent": 0,
                "deliveries_sent": 0,
                "deliveries_failed": 0,
            }

        matched = sum(len(items) for items in grouped_candidates.values())
        emails_sent = 0
        deliveries_sent = 0
        deliveries_failed = 0
        failed_recipients: list[str] = []

        for recipient_email, items in grouped_candidates.items():
            summary_group_key = uuid4().hex
            subject = _build_subject(items)
            body = _build_html_body(items)

            try:
                send_email_outlook(
                    email_receiver=recipient_email,
                    subject=subject,
                    body=body,
                    sender_alias=config("O_EMAIL_ALARM", default=None),
                    is_html=True,
                )
                sent_at = utc_now_naive()
                for item in items:
                    delivery = item.get("existing_delivery")
                    if isinstance(delivery, VodomeryAlertDelivery):
                        delivery.identifikace = str(item["identifikace"])
                        delivery.event_type = str(item["event_type"])
                        delivery.severity = str(item["severity"])
                        delivery.duration_minutes = int(item["duration_minutes"])
                        delivery.summary_group_key = summary_group_key
                        delivery.status = "SENT"
                        delivery.error_message = None
                        delivery.sent_at = sent_at
                    else:
                        session.add(
                            VodomeryAlertDelivery(
                                event_id=int(item["event_id"]),
                                rule_id=int(item["rule_id"]),
                                identifikace=str(item["identifikace"]),
                                event_type=str(item["event_type"]),
                                severity=str(item["severity"]),
                                duration_minutes=int(item["duration_minutes"]),
                                recipient_email=recipient_email,
                                alert_state=str(item["alert_state"]),
                                summary_group_key=summary_group_key,
                                status="SENT",
                                created_at=sent_at,
                                sent_at=sent_at,
                            )
                        )
                session.commit()
                emails_sent += 1
                deliveries_sent += len(items)
            except Exception as exc:
                error_message = str(exc)
                failed_recipients.append(recipient_email)
                for item in items:
                    delivery = item.get("existing_delivery")
                    if isinstance(delivery, VodomeryAlertDelivery):
                        delivery.identifikace = str(item["identifikace"])
                        delivery.event_type = str(item["event_type"])
                        delivery.severity = str(item["severity"])
                        delivery.duration_minutes = int(item["duration_minutes"])
                        delivery.summary_group_key = summary_group_key
                        delivery.status = "FAILED"
                        delivery.error_message = error_message
                        delivery.sent_at = None
                    else:
                        session.add(
                            VodomeryAlertDelivery(
                                event_id=int(item["event_id"]),
                                rule_id=int(item["rule_id"]),
                                identifikace=str(item["identifikace"]),
                                event_type=str(item["event_type"]),
                                severity=str(item["severity"]),
                                duration_minutes=int(item["duration_minutes"]),
                                recipient_email=recipient_email,
                                alert_state=str(item["alert_state"]),
                                summary_group_key=summary_group_key,
                                status="FAILED",
                                error_message=error_message,
                                created_at=utc_now_naive(),
                            )
                        )
                session.commit()
                deliveries_failed += len(items)

        if failed_recipients:
            raise RuntimeError(
                "Odeslani alert emailu selhalo pro: "
                + ", ".join(sorted(set(failed_recipients)))
            )

        return {
            "matched": matched,
            "emails_sent": emails_sent,
            "deliveries_sent": deliveries_sent,
            "deliveries_failed": deliveries_failed,
        }


def _normalize_ids(values: list[int] | None) -> list[int]:
    if not values:
        return []
    normalized = []
    seen = set()
    for value in values:
        if value is None:
            continue
        int_value = int(value)
        if int_value in seen:
            continue
        seen.add(int_value)
        normalized.append(int_value)
    return normalized


def _load_events(session: Session, event_ids: list[int], *, active_only: bool) -> list[VodomeryAnomalyEvent]:
    if not event_ids:
        return []

    query = select(VodomeryAnomalyEvent).where(VodomeryAnomalyEvent.id.in_(event_ids))
    if active_only:
        query = query.where(VodomeryAnomalyEvent.is_active.is_(True))
    else:
        query = query.where(VodomeryAnomalyEvent.resolved.is_(True))

    return session.execute(query).scalars().all()


def _load_existing_deliveries(
    session: Session,
    event_ids: list[int],
) -> dict[tuple[int, int | None, str, str], VodomeryAlertDelivery]:
    rows = session.execute(
        select(VodomeryAlertDelivery).where(VodomeryAlertDelivery.event_id.in_(event_ids))
    ).scalars().all()
    return {
        (
            int(row.event_id),
            int(row.rule_id) if row.rule_id is not None else None,
            str(row.alert_state),
            str(row.recipient_email),
        ): row
        for row in rows
    }


def _build_candidate(
    *,
    rule: VodomeryAlertRule,
    event: VodomeryAnomalyEvent,
    alert_state: str,
) -> dict[str, object] | None:
    if not _rule_matches_event(rule=rule, event=event, alert_state=alert_state):
        return None

    return {
        "event_id": int(event.id),
        "rule_id": int(rule.id),
        "rule_name": rule.rule_name,
        "recipient_email": rule.recipient_email,
        "identifikace": event.identifikace,
        "event_type": event.event_type,
        "severity": event.severity,
        "duration_minutes": int(event.duration_minutes or 0),
        "start_time": event.start_time,
        "end_time": event.end_time,
        "alert_state": alert_state,
        "delivery_key": (int(event.id), int(rule.id), alert_state, rule.recipient_email),
    }


def _rule_matches_event(*, rule: VodomeryAlertRule, event: VodomeryAnomalyEvent, alert_state: str) -> bool:
    if not rule.enabled:
        return False
    if rule.identifikace and rule.identifikace != event.identifikace:
        return False
    if rule.event_type and rule.event_type != event.event_type:
        return False
    if not _severity_matches(event.severity, rule.severity_min):
        return False
    if int(event.duration_minutes or 0) <= int(rule.min_duration_minutes or 0):
        return False

    if alert_state == "ACTIVE_THRESHOLD":
        return bool(event.is_active) and rule.send_on in {"ACTIVE", "BOTH"}
    if alert_state == "RESOLVED":
        return bool(event.resolved) and rule.send_on in {"RESOLVED", "BOTH"}
    return False


def _severity_matches(event_severity: str | None, required_severity: str | None) -> bool:
    if not event_severity or not required_severity:
        return False
    return SEVERITY_RANK.get(str(event_severity), 0) >= SEVERITY_RANK.get(str(required_severity), 0)


def _build_subject(items: list[dict[str, object]]) -> str:
    return f"[Vodomery] Souhrn alertu ({len(items)})"


def _build_html_body(items: list[dict[str, object]]) -> str:
    now_label = _format_datetime(_to_local_time(utc_now_naive()))
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f"<td>{escape(str(item['rule_name']))}</td>"
            f"<td>{escape(str(item['identifikace']))}</td>"
            f"<td>{escape(str(item['event_type']))}</td>"
            f"<td>{escape(str(item['severity']))}</td>"
            f"<td>{escape(_format_datetime(item['start_time']))}</td>"
            f"<td>{escape(_format_datetime(item['end_time']))}</td>"
            f"<td>{escape(str(item['duration_minutes']))}</td>"
            f"<td>{escape(_format_alert_state(str(item['alert_state'])))}</td>"
            "</tr>"
        )

    return (
        "<html><body>"
        f"<p>Souhrn alertu vodomeru vygenerovany {escape(now_label)}.</p>"
        "<table border='1' cellspacing='0' cellpadding='6'>"
        "<thead><tr>"
        "<th>Pravidlo</th>"
        "<th>Vodomer</th>"
        "<th>Event</th>"
        "<th>Zavaznost</th>"
        "<th>Zacatek</th>"
        "<th>Konec</th>"
        "<th>Trvani [min]</th>"
        "<th>Stav alertu</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</body></html>"
    )


def _format_datetime(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime.datetime):
        return _to_local_time(value).strftime("%d.%m.%Y %H:%M")
    return str(value)


def _to_local_time(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC).astimezone(LOCAL_TIMEZONE)
    return value.astimezone(LOCAL_TIMEZONE)


def _format_alert_state(value: str) -> str:
    if value == "ACTIVE_THRESHOLD":
        return "Aktivni event nad limitem"
    if value == "RESOLVED":
        return "Vyreseny event"
    return value
