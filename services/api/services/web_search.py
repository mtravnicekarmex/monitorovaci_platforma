from __future__ import annotations

import json

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from core.db.connect import get_session_pg
from moduly.apps.web_search.database.models import Monitor, Result
from moduly.apps.web_search.service import (
    find_matching_monitor,
    normalize_expressions,
    normalize_monitor_url,
    scan_web_hits,
)
from services.api.services.dashboard_auth import AuthorizationError, DashboardUserContext


class WebSearchOperationError(ValueError):
    """Raised when a web search admin operation is invalid."""


def require_admin_access(user_context: DashboardUserContext) -> None:
    if not user_context.is_admin:
        raise AuthorizationError("Tato operace je dostupna pouze adminovi.")


def _serialize_monitor_record(monitor: Monitor, *, results_count: int = 0) -> dict[str, object]:
    return {
        "id": int(monitor.id),
        "url": str(monitor.url),
        "email": str(monitor.email),
        "expressions": list(normalize_expressions(monitor.get_expressions())),
        "last_run": monitor.last_run,
        "created": monitor.created,
        "results_count": int(results_count),
    }


def _serialize_result_record(result: Result) -> dict[str, object]:
    monitor_url = None
    if getattr(result, "monitor", None) is not None and getattr(result.monitor, "url", None):
        monitor_url = str(result.monitor.url)
    return {
        "id": int(result.id),
        "monitor_id": int(result.monitor_id),
        "monitor_url": monitor_url,
        "url": str(result.url),
        "vyraz": str(result.vyraz),
        "snippet": result.snippet,
        "odkaz": result.odkaz,
        "datum": result.datum,
        "notified": bool(result.notified),
    }


def _normalize_monitor_payload(url: str, email: str, expressions: list[str]) -> tuple[str, str, list[str]]:
    normalized_url = normalize_monitor_url(url)
    if not normalized_url:
        raise WebSearchOperationError("Zadej platnou URL.")

    clean_email = email.strip()
    if not clean_email:
        raise WebSearchOperationError("Vyplň email.")

    normalized_expressions = normalize_expressions(expressions)
    if not normalized_expressions:
        raise WebSearchOperationError("Zadej alespoň jeden platný výraz.")

    return normalized_url, clean_email, normalized_expressions


def list_monitors_admin(user_context: DashboardUserContext) -> list[dict[str, object]]:
    require_admin_access(user_context)

    session = get_session_pg()
    try:
        monitors = session.query(Monitor).order_by(Monitor.created.desc()).all()
        result_counts = {
            int(monitor_id): int(total)
            for monitor_id, total in (
                session.query(Result.monitor_id, func.count(Result.id))
                .group_by(Result.monitor_id)
                .all()
            )
        }
        return [
            _serialize_monitor_record(monitor, results_count=result_counts.get(int(monitor.id), 0))
            for monitor in monitors
        ]
    finally:
        session.close()


def list_results_admin(
    user_context: DashboardUserContext,
    *,
    limit: int = 200,
) -> list[dict[str, object]]:
    require_admin_access(user_context)

    session = get_session_pg()
    try:
        rows = (
            session.query(Result)
            .options(joinedload(Result.monitor))
            .order_by(Result.datum.desc(), Result.id.desc())
            .limit(limit)
            .all()
        )
        return [_serialize_result_record(row) for row in rows]
    finally:
        session.close()


def preview_hits_admin(
    user_context: DashboardUserContext,
    *,
    url: str,
    expressions: list[str],
) -> dict[str, object]:
    require_admin_access(user_context)

    normalized_url = normalize_monitor_url(url)
    if not normalized_url:
        raise WebSearchOperationError("Zadej platnou URL.")

    normalized_expressions = normalize_expressions(expressions)
    if not normalized_expressions:
        raise WebSearchOperationError("Zadej alespoň jeden platný výraz.")

    hits = scan_web_hits(normalized_url, normalized_expressions)
    return {
        "url": normalized_url,
        "total": len(hits),
        "hits": [
            {
                "vyraz": vyraz,
                "snippet": snippet,
                "odkaz": odkaz,
            }
            for vyraz, snippet, odkaz in hits
        ],
    }


def upsert_monitor_admin(
    user_context: DashboardUserContext,
    *,
    url: str,
    email: str,
    expressions: list[str],
) -> dict[str, object]:
    require_admin_access(user_context)
    normalized_url, clean_email, normalized_expressions = _normalize_monitor_payload(url, email, expressions)

    session = get_session_pg()
    try:
        monitors = session.query(Monitor).all()
        existing_monitor = find_matching_monitor(monitors, normalized_url, clean_email)

        if existing_monitor is None:
            monitor = Monitor(
                url=normalized_url,
                vyrazy=json.dumps(normalized_expressions, ensure_ascii=False),
                email=clean_email,
            )
            session.add(monitor)
            session.commit()
            session.refresh(monitor)
            return {
                "monitor": _serialize_monitor_record(monitor),
                "created": True,
                "added_expressions": list(normalized_expressions),
            }

        current_expressions = normalize_expressions(existing_monitor.get_expressions())
        added_expressions = [expression for expression in normalized_expressions if expression not in current_expressions]
        if added_expressions:
            existing_monitor.vyrazy = json.dumps(current_expressions + added_expressions, ensure_ascii=False)
        existing_monitor.url = normalized_url
        existing_monitor.email = clean_email
        session.commit()
        session.refresh(existing_monitor)
        return {
            "monitor": _serialize_monitor_record(existing_monitor),
            "created": False,
            "added_expressions": added_expressions,
        }
    finally:
        session.close()


def update_monitor_admin(
    user_context: DashboardUserContext,
    *,
    monitor_id: int,
    url: str,
    email: str,
    expressions: list[str],
) -> dict[str, object]:
    require_admin_access(user_context)
    normalized_url, clean_email, normalized_expressions = _normalize_monitor_payload(url, email, expressions)

    session = get_session_pg()
    try:
        monitor = session.get(Monitor, monitor_id)
        if monitor is None:
            raise WebSearchOperationError("Monitor neexistuje.")

        duplicate_monitor = find_matching_monitor(
            session.query(Monitor).all(),
            normalized_url,
            clean_email,
            exclude_monitor_id=monitor.id,
        )
        if duplicate_monitor is not None:
            raise WebSearchOperationError("Monitor pro tuto URL a email už existuje.")

        monitor.url = normalized_url
        monitor.email = clean_email
        monitor.vyrazy = json.dumps(normalized_expressions, ensure_ascii=False)
        session.commit()
        session.refresh(monitor)
        results_count = (
            session.query(func.count(Result.id))
            .filter(Result.monitor_id == monitor.id)
            .scalar()
            or 0
        )
        return _serialize_monitor_record(monitor, results_count=int(results_count))
    finally:
        session.close()


def delete_monitor_admin(
    user_context: DashboardUserContext,
    *,
    monitor_id: int,
) -> None:
    require_admin_access(user_context)

    session = get_session_pg()
    try:
        monitor = session.get(Monitor, monitor_id)
        if monitor is None:
            return
        session.delete(monitor)
        session.commit()
    finally:
        session.close()
