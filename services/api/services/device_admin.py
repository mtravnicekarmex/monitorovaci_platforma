from __future__ import annotations

from core.db.connect import get_session_ms
from services.api.services.dashboard_admin import require_admin_access
from services.api.services.dashboard_auth import DashboardUserContext


def create_device_admin(
    user_context: DashboardUserContext,
    *,
    meter_key: str,
    form_values: dict[str, object],
) -> None:
    require_admin_access(user_context)
    (
        config,
        coerce_form_value,
        _primary_key_attr,
        build_create_fields,
        _build_edit_fields,
    ) = _get_device_helpers(meter_key)
    fields = build_create_fields(config)
    payload = {
        field.attr: coerce_form_value(config.model, field.attr, form_values.get(field.attr))
        for field in fields
    }

    session = get_session_ms()
    try:
        session.add(config.model(**payload))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_device_admin(
    user_context: DashboardUserContext,
    *,
    meter_key: str,
    primary_key_value: object,
    form_values: dict[str, object],
) -> None:
    require_admin_access(user_context)
    (
        config,
        coerce_form_value,
        primary_key_resolver,
        _build_create_fields,
        build_edit_fields,
    ) = _get_device_helpers(meter_key)
    primary_key_attr = primary_key_resolver(config.model)
    normalized_primary_key = coerce_form_value(
        config.model,
        primary_key_attr,
        primary_key_value,
    )
    fields = build_edit_fields(config)
    payload = {
        field.attr: coerce_form_value(config.model, field.attr, form_values.get(field.attr))
        for field in fields
    }

    session = get_session_ms()
    try:
        record = session.get(config.model, normalized_primary_key)
        if record is None:
            raise ValueError(
                f"Zaznam s {primary_key_attr}={normalized_primary_key} nebyl nalezen."
            )
        for attr, value in payload.items():
            setattr(record, attr, value)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _get_device_helpers(meter_key: str):
    from moduly.apps.dashboard.device_list_shared import (
        DEVICE_LIST_CONFIGS,
        _coerce_form_value,
        _primary_key_attr,
        build_create_fields,
        build_edit_fields,
    )

    try:
        config = DEVICE_LIST_CONFIGS[meter_key]
    except KeyError as exc:
        raise ValueError(f"Neznamy typ zarizeni: {meter_key}.") from exc
    return (
        config,
        _coerce_form_value,
        _primary_key_attr,
        build_create_fields,
        build_edit_fields,
    )
