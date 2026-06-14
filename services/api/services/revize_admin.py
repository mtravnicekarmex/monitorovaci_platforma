from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.exc import IntegrityError

from core.db.connect import get_session_pg
from moduly.evidence.revize.database.models import Revize, Revize_zarizeni
from services.api.services.dashboard_admin import require_admin_access
from services.api.services.dashboard_auth import DashboardUserContext


def create_revize_admin(
    user_context: DashboardUserContext,
    *,
    payload: dict[str, object],
    linked_device_ids: Iterable[int] | None = None,
) -> int:
    require_admin_access(user_context)
    normalized_payload = _normalize_payload(payload)
    session = get_session_pg()
    try:
        normalized_device_ids = _validate_linked_devices(
            session,
            budova=normalized_payload.get("budova"),
            typ_zarizeni=normalized_payload.get("typ_zarizeni"),
            linked_device_ids=linked_device_ids,
        )
        _raise_if_duplicate_revize(session, normalized_payload)
        record = Revize(**normalized_payload)
        session.add(record)
        session.flush()
        _write_revize_device_links(
            session,
            revize_id=int(record.id),
            typ_zarizeni=normalized_payload.get("typ_zarizeni"),
            normalized_device_ids=normalized_device_ids,
        )
        session.commit()
        return int(record.id)
    except IntegrityError as exc:
        session.rollback()
        if _is_revize_unique_constraint_error(exc):
            raise ValueError(_format_revize_duplicate_message(normalized_payload)) from exc
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_revize_admin(
    user_context: DashboardUserContext,
    *,
    revize_id: int,
    payload: dict[str, object],
    linked_device_ids: Iterable[int] | None = None,
) -> int:
    require_admin_access(user_context)
    normalized_payload = _normalize_payload(payload)
    session = get_session_pg()
    try:
        record = session.get(Revize, int(revize_id))
        if record is None:
            raise ValueError(f"Revize s ID {revize_id} nebyla nalezena.")

        normalized_device_ids = _validate_linked_devices(
            session,
            budova=normalized_payload.get("budova"),
            typ_zarizeni=normalized_payload.get("typ_zarizeni"),
            linked_device_ids=linked_device_ids,
        )
        _raise_if_duplicate_revize(
            session,
            normalized_payload,
            exclude_revize_id=int(revize_id),
        )
        for field, value in normalized_payload.items():
            setattr(record, field, value)
        _write_revize_device_links(
            session,
            revize_id=int(revize_id),
            typ_zarizeni=normalized_payload.get("typ_zarizeni"),
            normalized_device_ids=normalized_device_ids,
        )
        session.commit()
        return int(revize_id)
    except IntegrityError as exc:
        session.rollback()
        if _is_revize_unique_constraint_error(exc):
            raise ValueError(_format_revize_duplicate_message(normalized_payload)) from exc
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _normalize_payload(payload: dict[str, object]) -> dict[str, object]:
    from moduly.apps.dashboard.revize_shared import normalize_revize_payload

    return normalize_revize_payload(
        budova=payload.get("budova"),
        datum=payload.get("datum"),
        delka_platnosti=payload.get("delka_platnosti"),
        typ_zarizeni=payload.get("typ_zarizeni"),
        nazev_revize=payload.get("nazev_revize"),
        dodavatel=payload.get("dodavatel"),
        servisni_smlouva=payload.get("servisni_smlouva"),
        soubor=payload.get("soubor"),
        poznamka=payload.get("poznamka"),
    )


def _validate_linked_devices(
    session,
    *,
    budova: object,
    typ_zarizeni: object,
    linked_device_ids: Iterable[int] | None,
) -> list[int]:
    from moduly.apps.dashboard.revize_shared import validate_revize_linked_devices

    return validate_revize_linked_devices(
        session,
        budova=budova,
        typ_zarizeni=typ_zarizeni,
        linked_device_ids=linked_device_ids,
    )


def _format_date_for_message(value: object) -> str:
    if hasattr(value, "date") and callable(value.date):
        value = value.date()
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y")
    return str(value or "-")


def _format_revize_duplicate_message(payload: dict[str, object]) -> str:
    building = payload.get("budova") or "-"
    revision_date = _format_date_for_message(payload.get("datum"))
    file_value = payload.get("soubor") or "bez souboru"
    return f"Revize pro budovu {building}, datum {revision_date} a soubor {file_value} uz existuje."


def _find_duplicate_revize_id(
    session,
    payload: dict[str, object],
    *,
    exclude_revize_id: int | None = None,
) -> int | None:
    statement = session.query(Revize.id).filter(
        Revize.budova == payload.get("budova"),
        Revize.datum == payload.get("datum"),
    )
    if exclude_revize_id is not None:
        statement = statement.filter(Revize.id != int(exclude_revize_id))

    soubor = payload.get("soubor")
    if soubor is None:
        statement = statement.filter(Revize.soubor.is_(None))
    else:
        statement = statement.filter(Revize.soubor == soubor)

    result = statement.first()
    if result is None:
        return None
    return int(result[0])


def _raise_if_duplicate_revize(
    session,
    payload: dict[str, object],
    *,
    exclude_revize_id: int | None = None,
) -> None:
    if _find_duplicate_revize_id(
        session,
        payload,
        exclude_revize_id=exclude_revize_id,
    ) is not None:
        raise ValueError(_format_revize_duplicate_message(payload))


def _is_revize_unique_constraint_error(exc: IntegrityError) -> bool:
    return "uq_revize_budova_datum_soubor" in str(exc.orig or exc)


def _write_revize_device_links(
    session,
    *,
    revize_id: int,
    typ_zarizeni: object,
    normalized_device_ids: Iterable[int],
) -> None:
    normalized_type = str(typ_zarizeni or "").strip() or None
    session.query(Revize_zarizeni).filter(
        Revize_zarizeni.revize_id == int(revize_id)
    ).delete(synchronize_session=False)
    if not normalized_device_ids:
        return

    session.add_all(
        Revize_zarizeni(
            revize_id=int(revize_id),
            typ_zarizeni=normalized_type,
            zarizeni_id=device_id,
        )
        for device_id in normalized_device_ids
    )
