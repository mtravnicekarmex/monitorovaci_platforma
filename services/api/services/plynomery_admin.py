from __future__ import annotations

from moduly.mereni.plynomery.database.alerting import (
    delete_alert_rule,
    list_alert_rules,
    upsert_alert_rule,
)
from moduly.mereni.plynomery.database.expected_zero import (
    list_expected_zero_devices,
    replace_expected_zero_devices,
)
from moduly.mereni.plynomery.database.outlier_reviews import (
    list_outlier_reviews,
)
from moduly.mereni.plynomery.database.outlier_review_apply import apply_outlier_review_update
from services.api.core.plynomery_alert_rule_validation import normalize_alert_rule_payload
from services.api.services.dashboard_admin import require_admin_access
from services.api.services.dashboard_auth import DashboardUserContext


class PlynomeryAdminOperationError(ValueError):
    """Raised when a plynomery admin operation is invalid."""


def _prepare_alert_rule_payload(
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
) -> dict[str, object]:
    try:
        return normalize_alert_rule_payload(
            rule_name=rule_name,
            recipient_email=recipient_email,
            severity_min=severity_min,
            min_duration_minutes=min_duration_minutes,
            send_on=send_on,
            identifikace=identifikace,
            event_type=event_type,
            enabled=enabled,
            note=note,
        )
    except ValueError as exc:
        raise PlynomeryAdminOperationError(str(exc)) from exc


def list_alert_rules_admin(user_context: DashboardUserContext) -> list[dict[str, object]]:
    require_admin_access(user_context)
    return list_alert_rules()


def list_expected_zero_devices_admin(user_context: DashboardUserContext) -> list[dict[str, object]]:
    require_admin_access(user_context)
    return list_expected_zero_devices()


def replace_expected_zero_devices_admin(
    user_context: DashboardUserContext,
    *,
    identifikace_list: list[str],
) -> list[dict[str, object]]:
    require_admin_access(user_context)
    replace_expected_zero_devices(identifikace_list, updated_by=user_context.username)
    return list_expected_zero_devices()


def list_outlier_reviews_admin(
    user_context: DashboardUserContext,
    *,
    review_status: str | None = None,
    identifikace: str | None = None,
    source_filter: str = "VSE",
    limit: int = 200,
) -> list[dict[str, object]]:
    require_admin_access(user_context)
    try:
        return list_outlier_reviews(
            review_status=review_status,
            identifikace=identifikace,
            source_filter=source_filter,
            limit=limit,
        )
    except ValueError as exc:
        raise PlynomeryAdminOperationError(str(exc)) from exc


def update_outlier_review_admin(
    user_context: DashboardUserContext,
    *,
    review_id: int,
    review_status: str,
    review_note: str | None = None,
) -> dict[str, object]:
    require_admin_access(user_context)
    try:
        return apply_outlier_review_update(
            review_id,
            review_status=review_status,
            review_note=review_note,
            actor=user_context.username,
        )
    except ValueError as exc:
        raise PlynomeryAdminOperationError(str(exc)) from exc


def create_alert_rule_admin(
    user_context: DashboardUserContext,
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
) -> dict[str, object]:
    require_admin_access(user_context)
    payload = _prepare_alert_rule_payload(
        rule_name=rule_name,
        recipient_email=recipient_email,
        severity_min=severity_min,
        min_duration_minutes=min_duration_minutes,
        send_on=send_on,
        identifikace=identifikace,
        event_type=event_type,
        enabled=enabled,
        note=note,
    )

    rule_id = upsert_alert_rule(
        **payload,
        actor=user_context.username,
    )
    return next(row for row in list_alert_rules() if int(row["id"]) == int(rule_id))


def update_alert_rule_admin(
    user_context: DashboardUserContext,
    *,
    rule_id: int,
    rule_name: str,
    recipient_email: str,
    severity_min: str,
    min_duration_minutes: int,
    send_on: str,
    identifikace: str | None = None,
    event_type: str | None = None,
    enabled: bool = True,
    note: str | None = None,
) -> dict[str, object]:
    require_admin_access(user_context)
    payload = _prepare_alert_rule_payload(
        rule_name=rule_name,
        recipient_email=recipient_email,
        severity_min=severity_min,
        min_duration_minutes=min_duration_minutes,
        send_on=send_on,
        identifikace=identifikace,
        event_type=event_type,
        enabled=enabled,
        note=note,
    )

    updated_rule_id = upsert_alert_rule(
        rule_id=rule_id,
        **payload,
        actor=user_context.username,
    )
    return next(row for row in list_alert_rules() if int(row["id"]) == int(updated_rule_id))


def delete_alert_rule_admin(
    user_context: DashboardUserContext,
    *,
    rule_id: int,
) -> None:
    require_admin_access(user_context)
    delete_alert_rule(rule_id)
