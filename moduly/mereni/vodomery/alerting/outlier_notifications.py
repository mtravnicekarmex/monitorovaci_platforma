from __future__ import annotations

from collections import defaultdict
import datetime
from html import escape
import logging
from uuid import uuid4
from zoneinfo import ZoneInfo

from decouple import config
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.channels.email import send_email_outlook
from app.time_utils import utc_now_naive
from core.db.connect import ENGINE_PG
from moduly.mereni.vodomery.database.models import (
    VodomeryAlertRule,
    VodomeryOutlierEmailDelivery,
    VodomeryOutlierReview,
)


logger = logging.getLogger(__name__)
LOCAL_TIMEZONE = ZoneInfo("Europe/Prague")
OUTLIER_EVENT_TYPE = "OUTLIER_REVIEW"
SEVERITY_RANK = {
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}


def ensure_vodomery_outlier_email_delivery_table() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        VodomeryOutlierEmailDelivery.__table__.create(bind=conn, checkfirst=True)
        _migrate_outlier_email_delivery_table(conn)


def process_new_outlier_review_notifications(review_ids: list[int] | None = None) -> dict[str, int]:
    ensure_vodomery_outlier_email_delivery_table()

    normalized_review_ids = _normalize_ids(review_ids)
    if not normalized_review_ids:
        return {
            "matched": 0,
            "emails_sent": 0,
            "deliveries_sent": 0,
            "deliveries_failed": 0,
        }

    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        reviews = (
            session.execute(
                select(VodomeryOutlierReview)
                .where(VodomeryOutlierReview.id.in_(normalized_review_ids))
                .order_by(VodomeryOutlierReview.date.asc(), VodomeryOutlierReview.id.asc())
            )
            .scalars()
            .all()
        )
        if not reviews:
            return {
                "matched": 0,
                "emails_sent": 0,
                "deliveries_sent": 0,
                "deliveries_failed": 0,
            }

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
            logger.info("No enabled vodomery alert rules configured for outlier notifications.")
            return {
                "matched": 0,
                "emails_sent": 0,
                "deliveries_sent": 0,
                "deliveries_failed": 0,
            }

        existing_deliveries = _load_existing_deliveries(session, normalized_review_ids)
        reserved_delivery_keys = {
            key for key, row in existing_deliveries.items() if row.status in {"SENT", "PENDING", "SKIPPED"}
        }
        grouped_candidates: dict[str, list[dict[str, object]]] = defaultdict(list)

        for review in reviews:
            for rule in rules:
                candidate = _build_candidate(rule=rule, review=review)
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

        for recipient_email, items in grouped_candidates.items():
            summary_group_key = uuid4().hex
            try:
                send_email_outlook(
                    email_receiver=recipient_email,
                    subject=_build_subject(items),
                    body=_build_html_body(items),
                    sender_alias=config("O_EMAIL_ALARM", default=None),
                    is_html=True,
                )
                sent_at = utc_now_naive()
                for item in items:
                    delivery = item.get("existing_delivery")
                    if isinstance(delivery, VodomeryOutlierEmailDelivery):
                        delivery.rule_id = int(item["rule_id"])
                        delivery.identifikace = str(item["identifikace"])
                        delivery.review_date = item["review_date"]
                        delivery.zdroj = str(item["zdroj"])
                        delivery.severity = str(item["severity"])
                        delivery.detection_kind = str(item["detection_kind"])
                        delivery.summary_group_key = summary_group_key
                        delivery.status = "SENT"
                        delivery.error_message = None
                        delivery.sent_at = sent_at
                    else:
                        session.add(
                            VodomeryOutlierEmailDelivery(
                                review_id=int(item["review_id"]),
                                rule_id=int(item["rule_id"]),
                                identifikace=str(item["identifikace"]),
                                review_date=item["review_date"],
                                zdroj=str(item["zdroj"]),
                                severity=str(item["severity"]),
                                detection_kind=str(item["detection_kind"]),
                                recipient_email=recipient_email,
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
                logger.exception(
                    "Failed to send new outlier review notification email to %s",
                    recipient_email,
                )
                for item in items:
                    delivery = item.get("existing_delivery")
                    if isinstance(delivery, VodomeryOutlierEmailDelivery):
                        delivery.rule_id = int(item["rule_id"])
                        delivery.identifikace = str(item["identifikace"])
                        delivery.review_date = item["review_date"]
                        delivery.zdroj = str(item["zdroj"])
                        delivery.severity = str(item["severity"])
                        delivery.detection_kind = str(item["detection_kind"])
                        delivery.summary_group_key = summary_group_key
                        delivery.status = "FAILED"
                        delivery.error_message = error_message
                        delivery.sent_at = None
                    else:
                        session.add(
                            VodomeryOutlierEmailDelivery(
                                review_id=int(item["review_id"]),
                                rule_id=int(item["rule_id"]),
                                identifikace=str(item["identifikace"]),
                                review_date=item["review_date"],
                                zdroj=str(item["zdroj"]),
                                severity=str(item["severity"]),
                                detection_kind=str(item["detection_kind"]),
                                recipient_email=recipient_email,
                                summary_group_key=summary_group_key,
                                status="FAILED",
                                error_message=error_message,
                                created_at=utc_now_naive(),
                            )
                        )
                session.commit()
                deliveries_failed += len(items)

        return {
            "matched": matched,
            "emails_sent": emails_sent,
            "deliveries_sent": deliveries_sent,
            "deliveries_failed": deliveries_failed,
        }


def _migrate_outlier_email_delivery_table(conn) -> None:
    inspector = inspect(conn)
    if "vodomery_outlier_email_deliveries" not in inspector.get_table_names(schema="monitoring"):
        return

    columns = {column["name"] for column in inspector.get_columns("vodomery_outlier_email_deliveries", schema="monitoring")}
    if "rule_id" not in columns:
        conn.execute(text("ALTER TABLE monitoring.vodomery_outlier_email_deliveries ADD COLUMN rule_id INTEGER"))
    if "severity" not in columns:
        conn.execute(
            text(
                "ALTER TABLE monitoring.vodomery_outlier_email_deliveries "
                "ADD COLUMN severity VARCHAR(20) NOT NULL DEFAULT 'HIGH'"
            )
        )

    conn.execute(
        text(
            "ALTER TABLE monitoring.vodomery_outlier_email_deliveries "
            "DROP CONSTRAINT IF EXISTS uq_outlier_email_delivery_review_recipient"
        )
    )
    conn.execute(
        text(
            "ALTER TABLE monitoring.vodomery_outlier_email_deliveries "
            "DROP CONSTRAINT IF EXISTS uq_outlier_email_delivery_review_rule_recipient"
        )
    )
    conn.execute(
        text(
            "ALTER TABLE monitoring.vodomery_outlier_email_deliveries "
            "ADD CONSTRAINT uq_outlier_email_delivery_review_rule_recipient "
            "UNIQUE (review_id, rule_id, recipient_email)"
        )
    )


def _normalize_ids(values: list[int] | None) -> list[int]:
    if not values:
        return []

    normalized: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value is None:
            continue
        int_value = int(value)
        if int_value in seen:
            continue
        normalized.append(int_value)
        seen.add(int_value)
    return normalized


def _load_existing_deliveries(
    session: Session,
    review_ids: list[int],
) -> dict[tuple[int, int | None, str], VodomeryOutlierEmailDelivery]:
    rows = session.execute(
        select(VodomeryOutlierEmailDelivery).where(VodomeryOutlierEmailDelivery.review_id.in_(review_ids))
    ).scalars().all()
    return {
        (
            int(row.review_id),
            int(row.rule_id) if row.rule_id is not None else None,
            str(row.recipient_email),
        ): row
        for row in rows
    }


def _build_candidate(
    *,
    rule: VodomeryAlertRule,
    review: VodomeryOutlierReview,
) -> dict[str, object] | None:
    severity = _compute_outlier_severity(review)
    duration_minutes = max(int(review.interval_minutes or 0), 1)

    if not _rule_matches_review(
        rule=rule,
        review=review,
        severity=severity,
        duration_minutes=duration_minutes,
    ):
        return None

    return {
        "review_id": int(review.id),
        "rule_id": int(rule.id),
        "rule_name": rule.rule_name,
        "recipient_email": rule.recipient_email,
        "identifikace": review.identifikace,
        "review_date": review.date,
        "zdroj": review.zdroj,
        "severity": severity,
        "duration_minutes": duration_minutes,
        "detection_kind": review.detection_kind,
        "candidate_delta": float(review.candidate_delta),
        "threshold_delta": None if review.threshold_delta is None else float(review.threshold_delta),
        "current_objem": float(review.current_objem),
        "baseline_objem": None if review.baseline_objem is None else float(review.baseline_objem),
        "delivery_key": (int(review.id), int(rule.id), rule.recipient_email),
    }


def _rule_matches_review(
    *,
    rule: VodomeryAlertRule,
    review: VodomeryOutlierReview,
    severity: str,
    duration_minutes: int,
) -> bool:
    if not rule.enabled:
        return False
    if rule.identifikace and rule.identifikace != review.identifikace:
        return False
    if rule.event_type and rule.event_type != OUTLIER_EVENT_TYPE:
        return False
    if not _severity_matches(severity, rule.severity_min):
        return False
    if duration_minutes <= int(rule.min_duration_minutes or 0):
        return False
    return rule.send_on in {"ACTIVE", "BOTH"}


def _severity_matches(event_severity: str | None, required_severity: str | None) -> bool:
    if not event_severity or not required_severity:
        return False
    return SEVERITY_RANK.get(str(event_severity), 0) >= SEVERITY_RANK.get(str(required_severity), 0)


def _compute_outlier_severity(review: VodomeryOutlierReview) -> str:
    candidate_delta = max(float(review.candidate_delta or 0.0), 0.0)
    threshold_delta = max(float(review.threshold_delta or 0.0), 0.0)

    if threshold_delta > 0:
        ratio = candidate_delta / max(threshold_delta, 0.0001)
        if ratio >= 4.0:
            return "CRITICAL"
        if ratio >= 2.5:
            return "HIGH"
        if ratio >= 1.5:
            return "MEDIUM"
        return "LOW"

    if candidate_delta >= 100.0:
        return "CRITICAL"
    if candidate_delta >= 50.0:
        return "HIGH"
    if candidate_delta >= 20.0:
        return "MEDIUM"
    return "LOW"


def _build_subject(items: list[dict[str, object]]) -> str:
    return f"[Vodomery] Nove outliery k review ({len(items)})"


def _build_html_body(items: list[dict[str, object]]) -> str:
    generated_at = _format_datetime(_to_local_time(utc_now_naive()))
    rows: list[str] = []
    for item in items:
        rows.append(
            "<tr>"
            f"<td>{escape(str(item['rule_name']))}</td>"
            f"<td>{escape(str(item['identifikace']))}</td>"
            f"<td>{escape(str(item['zdroj']))}</td>"
            f"<td>{escape(_format_datetime(item['review_date']))}</td>"
            f"<td>{escape(str(item['severity']))}</td>"
            f"<td>{escape(str(item['detection_kind']))}</td>"
            f"<td>{escape(_format_number(item['candidate_delta']))}</td>"
            f"<td>{escape(_format_number(item['threshold_delta']))}</td>"
            "</tr>"
        )

    return (
        "<html><body>"
        f"<p>Byly nalezeny nove outliery vodomeru k manualnimu review. Generovano {escape(generated_at)}.</p>"
        "<p>Zkontrolujte prosim dashboard stranku Vodomery Outlier Review.</p>"
        "<table border='1' cellspacing='0' cellpadding='6'>"
        "<thead><tr>"
        "<th>Pravidlo</th>"
        "<th>Vodomer</th>"
        "<th>Zdroj</th>"
        "<th>Cas mereni</th>"
        "<th>Zavaznost</th>"
        "<th>Typ detekce</th>"
        "<th>Kandidat delta</th>"
        "<th>Limit delta</th>"
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


def _format_number(value: object) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def _to_local_time(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC).astimezone(LOCAL_TIMEZONE)
    return value.astimezone(LOCAL_TIMEZONE)
