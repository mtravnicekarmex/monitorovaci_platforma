from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.time_utils import utc_now_naive
from core.db.connect import get_session_pg
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    PlynomeryAnomalyEvent,
    PlynomeryAnomalyScore,
)
from moduly.mereni.plynomery.plynomery_prediction import get_runtime_model_version
from services.api.services.dashboard_auth import (
    DashboardUserContext,
    require_device_access,
    require_section_access,
)


MIN_VISIBLE_EVENT_DURATION_MINUTES = 120


def _build_datetime_range(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)
    return start_dt, end_dt


def _get_active_model_version(*, session=None) -> int:
    return get_runtime_model_version(session=session, default=1)


def list_accessible_devices(
    user_context: DashboardUserContext,
    *,
    limit: int = 500,
) -> list[str]:
    require_section_access(user_context, "plynomery")

    session = get_session_pg()
    try:
        query = session.query(Mereni_plynomery.identifikace).distinct()
        if not user_context.is_admin:
            query = query.filter(Mereni_plynomery.identifikace.in_(user_context.allowed_devices))

        rows = query.order_by(Mereni_plynomery.identifikace).limit(limit).all()
        return [str(row[0]) for row in rows if row[0]]
    finally:
        session.close()


def load_recent_anomalies(
    user_context: DashboardUserContext,
    *,
    identifikace: str | None,
    start_date: date,
    end_date: date,
    limit: int = 50,
) -> list[dict[str, object]]:
    require_section_access(user_context, "plynomery")
    start_dt, end_dt = _build_datetime_range(start_date, end_date)
    if identifikace:
        require_device_access(user_context, identifikace)

    session = get_session_pg()
    try:
        active_model_version = _get_active_model_version(session=session)
        query = (
            session.query(
                PlynomeryAnomalyScore.date,
                PlynomeryAnomalyScore.identifikace,
                PlynomeryAnomalyScore.actual_value,
                PlynomeryAnomalyScore.expected_mean,
                PlynomeryAnomalyScore.z_score,
                PlynomeryAnomalyScore.severity,
                PlynomeryAnomalyScore.is_anomaly,
            )
            .filter(PlynomeryAnomalyScore.model_version == active_model_version)
            .filter(PlynomeryAnomalyScore.is_anomaly.is_(True))
            .filter(PlynomeryAnomalyScore.date >= start_dt, PlynomeryAnomalyScore.date <= end_dt)
        )
        if not user_context.is_admin:
            query = query.filter(PlynomeryAnomalyScore.identifikace.in_(user_context.allowed_devices))
        if identifikace:
            query = query.filter(PlynomeryAnomalyScore.identifikace == identifikace)

        rows = query.order_by(PlynomeryAnomalyScore.date.desc()).limit(limit).all()
        return [
            {
                "date": row.date,
                "identifikace": str(row.identifikace),
                "actual_value": float(row.actual_value),
                "expected_mean": float(row.expected_mean),
                "z_score": float(row.z_score),
                "severity": str(row.severity) if row.severity is not None else None,
                "is_anomaly": bool(row.is_anomaly),
            }
            for row in rows
        ]
    finally:
        session.close()


def load_all_open_events(
    user_context: DashboardUserContext,
    *,
    limit: int = 500,
) -> list[dict[str, object]]:
    require_section_access(user_context, "plynomery")

    session = get_session_pg()
    try:
        active_model_version = _get_active_model_version(session=session)
        query = session.query(
            PlynomeryAnomalyEvent.identifikace,
            PlynomeryAnomalyEvent.event_type,
            PlynomeryAnomalyEvent.start_time,
            PlynomeryAnomalyEvent.end_time,
            PlynomeryAnomalyEvent.duration_minutes,
            PlynomeryAnomalyEvent.max_z_score,
            PlynomeryAnomalyEvent.avg_z_score,
            PlynomeryAnomalyEvent.severity,
        ).filter(
            PlynomeryAnomalyEvent.model_version == active_model_version,
            PlynomeryAnomalyEvent.end_time.is_(None),
            PlynomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES,
        )
        if not user_context.is_admin:
            query = query.filter(PlynomeryAnomalyEvent.identifikace.in_(user_context.allowed_devices))

        rows = query.order_by(
            PlynomeryAnomalyEvent.severity.asc(),
            PlynomeryAnomalyEvent.duration_minutes.desc(),
            PlynomeryAnomalyEvent.start_time.desc(),
        ).limit(limit).all()
        return [
            {
                "identifikace": str(row.identifikace),
                "event_type": str(row.event_type),
                "start_time": row.start_time,
                "end_time": row.end_time,
                "duration_minutes": int(row.duration_minutes),
                "max_z_score": float(row.max_z_score),
                "avg_z_score": float(row.avg_z_score),
                "severity": str(row.severity),
            }
            for row in rows
        ]
    finally:
        session.close()


def load_recent_resolved_events(
    user_context: DashboardUserContext,
    *,
    days: int = 7,
    limit: int = 500,
) -> list[dict[str, object]]:
    require_section_access(user_context, "plynomery")
    resolved_since = utc_now_naive() - timedelta(days=days)

    session = get_session_pg()
    try:
        active_model_version = _get_active_model_version(session=session)
        query = session.query(
            PlynomeryAnomalyEvent.identifikace,
            PlynomeryAnomalyEvent.event_type,
            PlynomeryAnomalyEvent.start_time,
            PlynomeryAnomalyEvent.end_time,
            PlynomeryAnomalyEvent.duration_minutes,
            PlynomeryAnomalyEvent.max_z_score,
            PlynomeryAnomalyEvent.avg_z_score,
            PlynomeryAnomalyEvent.severity,
        ).filter(
            PlynomeryAnomalyEvent.model_version == active_model_version,
            PlynomeryAnomalyEvent.resolved.is_(True),
            PlynomeryAnomalyEvent.end_time.is_not(None),
            PlynomeryAnomalyEvent.end_time >= resolved_since,
            PlynomeryAnomalyEvent.duration_minutes > MIN_VISIBLE_EVENT_DURATION_MINUTES,
        )
        if not user_context.is_admin:
            query = query.filter(PlynomeryAnomalyEvent.identifikace.in_(user_context.allowed_devices))

        rows = query.order_by(
            PlynomeryAnomalyEvent.end_time.desc(),
            PlynomeryAnomalyEvent.duration_minutes.desc(),
        ).limit(limit).all()
        return [
            {
                "identifikace": str(row.identifikace),
                "event_type": str(row.event_type),
                "start_time": row.start_time,
                "end_time": row.end_time,
                "duration_minutes": int(row.duration_minutes),
                "max_z_score": float(row.max_z_score),
                "avg_z_score": float(row.avg_z_score),
                "severity": str(row.severity),
            }
            for row in rows
        ]
    finally:
        session.close()
