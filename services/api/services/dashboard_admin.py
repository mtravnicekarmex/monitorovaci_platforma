from __future__ import annotations

from core.db.connect import get_session_ms, get_session_pg
from moduly.apps.dashboard.database.users import (
    count_active_admin_users,
    delete_user,
    get_user,
    list_users,
    upsert_user,
)
from moduly.mereni.kalorimetry.database.models import Kalorimetr_areal_Mereni
from moduly.mereni.plynomery.database.models import Plynomer_areal_Mereni
from moduly.mereni.vodomery.database.models import Mereni_vodomery
from services.api.services.dashboard_auth import AuthorizationError, DashboardUserContext

_MISSING = object()


class AdminOperationError(ValueError):
    """Raised when an admin write operation is invalid."""


def require_admin_access(user_context: DashboardUserContext) -> None:
    if not user_context.is_admin:
        raise AuthorizationError("Tato operace je dostupna pouze adminovi.")


def _serialize_user_record(user_row: dict[str, object]) -> dict[str, object]:
    return {
        "username": str(user_row["uzivatel"]),
        "email": user_row["email"],
        "available_sections": list(user_row["dostupne_sekce"]),
        "available_pages": list(user_row["dostupne_stranky"]),
        "device_ids": list(user_row["seznam_zarizeni"]),
        "is_active": bool(user_row["is_active"]),
        "is_admin": bool(user_row["is_admin"]),
        "created_at": user_row["created_at"],
        "updated_at": user_row["updated_at"],
        "last_login_at": user_row["last_login_at"],
    }


def _ensure_active_admin_remains(
    *,
    username: str,
    current_is_admin: bool,
    current_is_active: bool,
    resolved_is_admin: bool,
    resolved_is_active: bool,
) -> None:
    if not current_is_admin or not current_is_active:
        return
    if resolved_is_admin and resolved_is_active:
        return
    if count_active_admin_users(exclude_username=username) > 0:
        return
    raise AdminOperationError("Nelze odebrat posledniho aktivniho admina.")


def list_admin_users(user_context: DashboardUserContext) -> list[dict[str, object]]:
    require_admin_access(user_context)
    return [_serialize_user_record(row) for row in list_users()]


def list_all_device_options(user_context: DashboardUserContext) -> list[str]:
    require_admin_access(user_context)
    identifiers: set[str] = set()

    session_pg = get_session_pg()
    try:
        vodomery_rows = (
            session_pg.query(Mereni_vodomery.identifikace)
            .distinct()
            .order_by(Mereni_vodomery.identifikace)
            .all()
        )
        identifiers.update(str(row[0]) for row in vodomery_rows if row[0])
    finally:
        session_pg.close()

    session_ms = get_session_ms()
    try:
        plynomery_rows = (
            session_ms.query(Plynomer_areal_Mereni.identifikace)
            .distinct()
            .order_by(Plynomer_areal_Mereni.identifikace)
            .all()
        )
        identifiers.update(str(row[0]) for row in plynomery_rows if row[0])

        kalorimetry_rows = (
            session_ms.query(Kalorimetr_areal_Mereni.identifikace)
            .distinct()
            .order_by(Kalorimetr_areal_Mereni.identifikace)
            .all()
        )
        identifiers.update(str(row[0]) for row in kalorimetry_rows if row[0])
    finally:
        session_ms.close()

    return sorted(identifiers)


def create_admin_user(
    user_context: DashboardUserContext,
    *,
    username: str,
    password: str,
    email: str | None,
    available_sections: list[str],
    available_pages: list[str],
    device_ids: list[str],
    is_active: bool,
    is_admin: bool,
) -> dict[str, object]:
    require_admin_access(user_context)
    cleaned_username = username.strip()
    if not cleaned_username:
        raise AdminOperationError("Uzivatel je povinny.")
    if get_user(cleaned_username) is not None:
        raise AdminOperationError("Uzivatel jiz existuje.")

    upsert_user(
        username=cleaned_username,
        password=password,
        email=email,
        dostupne_sekce=available_sections,
        dostupne_stranky=available_pages,
        seznam_zarizeni=device_ids,
        is_admin=is_admin,
        is_active=is_active,
    )
    created_user = get_user(cleaned_username)
    if created_user is None:
        raise AdminOperationError("Uzivatele se nepodarilo nacist po ulozeni.")
    return next(row for row in list_admin_users(user_context) if row["username"] == cleaned_username)


def update_admin_user(
    user_context: DashboardUserContext,
    *,
    username: str,
    password: str | None | object = _MISSING,
    email: str | None | object = _MISSING,
    available_sections: list[str] | None | object = _MISSING,
    available_pages: list[str] | None | object = _MISSING,
    device_ids: list[str] | None | object = _MISSING,
    is_active: bool | None | object = _MISSING,
    is_admin: bool | None | object = _MISSING,
) -> dict[str, object]:
    require_admin_access(user_context)
    cleaned_username = username.strip()
    if not cleaned_username:
        raise AdminOperationError("Uzivatel je povinny.")
    existing_user = get_user(cleaned_username)
    if existing_user is None:
        raise AdminOperationError("Uzivatel neexistuje.")

    current_record = _serialize_user_record(next(row for row in list_users() if row["uzivatel"] == cleaned_username))

    resolved_password = None if password is _MISSING else password
    resolved_email = current_record["email"] if email is _MISSING else email
    resolved_sections = (
        list(current_record["available_sections"])
        if available_sections is _MISSING or available_sections is None
        else list(available_sections)
    )
    resolved_pages = (
        list(current_record["available_pages"])
        if available_pages is _MISSING or available_pages is None
        else list(available_pages)
    )
    resolved_device_ids = (
        list(current_record["device_ids"])
        if device_ids is _MISSING or device_ids is None
        else list(device_ids)
    )
    resolved_is_active = bool(current_record["is_active"]) if is_active is _MISSING or is_active is None else bool(is_active)
    resolved_is_admin = bool(current_record["is_admin"]) if is_admin is _MISSING or is_admin is None else bool(is_admin)

    if cleaned_username == user_context.username and not resolved_is_active:
        raise AdminOperationError("Nelze deaktivovat prave prihlaseneho uzivatele.")
    _ensure_active_admin_remains(
        username=cleaned_username,
        current_is_admin=bool(current_record["is_admin"]),
        current_is_active=bool(current_record["is_active"]),
        resolved_is_admin=resolved_is_admin,
        resolved_is_active=resolved_is_active,
    )

    upsert_user(
        username=cleaned_username,
        password=resolved_password,
        email=resolved_email,
        dostupne_sekce=resolved_sections,
        dostupne_stranky=resolved_pages,
        seznam_zarizeni=resolved_device_ids,
        is_admin=resolved_is_admin,
        is_active=resolved_is_active,
    )
    return next(row for row in list_admin_users(user_context) if row["username"] == cleaned_username)


def delete_admin_user(
    user_context: DashboardUserContext,
    *,
    username: str,
) -> None:
    require_admin_access(user_context)
    cleaned_username = username.strip()
    if not cleaned_username:
        raise AdminOperationError("Uzivatel je povinny.")
    if cleaned_username == user_context.username:
        raise AdminOperationError("Nemuzes smazat prave prihlaseneho uzivatele.")
    existing_user = get_user(cleaned_username)
    if existing_user is None:
        return
    _ensure_active_admin_remains(
        username=cleaned_username,
        current_is_admin=bool(existing_user.is_admin),
        current_is_active=bool(existing_user.is_active),
        resolved_is_admin=False,
        resolved_is_active=False,
    )
    delete_user(cleaned_username)
