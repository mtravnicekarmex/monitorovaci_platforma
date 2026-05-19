from __future__ import annotations

from datetime import date, datetime, time

from core.db.connect import get_session_ms, get_session_pg
from moduly.apps.dashboard.time_semantics import local_date_range_to_utc, to_prague_naive
from moduly.mereni.manometry.database.models import (
    Manometr_areal_Zarizeni,
    Mereni_manometry_vse,
)
from services.api.services.dashboard_auth import (
    DashboardUserContext,
    require_device_access,
    require_section_access,
)


def _build_datetime_range(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(end_date, time.max)
    return start_dt, end_dt


def _normalize_identifikace(value: object) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _serialize_device_detail(
    *,
    identifikace: str,
    device: Manometr_areal_Zarizeni | None,
    measurement_count: int,
    valid_measurement_count: int,
    first_measurement_at: datetime | None,
    last_measurement_at: datetime | None,
    min_measurement: Mereni_manometry_vse | None,
    max_measurement: Mereni_manometry_vse | None,
) -> dict[str, object]:
    return {
        "identifikace": identifikace,
        "seriove_cislo": device.seriove_cislo if device is not None and device.seriove_cislo is not None else None,
        "objekt": device.objekt if device is not None and device.objekt is not None else None,
        "mistnost": device.mistnost if device is not None and device.mistnost is not None else None,
        "patro": device.patro if device is not None and device.patro is not None else None,
        "vetev": device.vetev if device is not None and device.vetev is not None else None,
        "foto": device.foto if device is not None and device.foto is not None else None,
        "measurement_count": measurement_count,
        "valid_measurement_count": valid_measurement_count,
        "first_measurement_at": first_measurement_at,
        "last_measurement_at": last_measurement_at,
        "min_pressure": float(min_measurement.hodnota) if min_measurement is not None and min_measurement.hodnota is not None else None,
        "min_pressure_at": (
            to_prague_naive(min_measurement.time_utc) or min_measurement.date
            if min_measurement is not None
            else None
        ),
        "max_pressure": float(max_measurement.hodnota) if max_measurement is not None and max_measurement.hodnota is not None else None,
        "max_pressure_at": (
            to_prague_naive(max_measurement.time_utc) or max_measurement.date
            if max_measurement is not None
            else None
        ),
    }


def list_accessible_devices(
    user_context: DashboardUserContext,
    *,
    limit: int = 500,
) -> list[str]:
    require_section_access(user_context, "manometry")

    session_ms = get_session_ms()
    session_pg = get_session_pg()
    try:
        identifiers: set[str] = set()

        device_rows = (
            session_ms.query(Manometr_areal_Zarizeni.identifikace)
            .distinct()
            .order_by(Manometr_areal_Zarizeni.identifikace)
            .all()
        )
        identifiers.update(
            identifikace
            for row in device_rows
            if (identifikace := _normalize_identifikace(row[0])) is not None
        )

        measurement_rows = (
            session_pg.query(Mereni_manometry_vse.identifikace)
            .distinct()
            .order_by(Mereni_manometry_vse.identifikace)
            .all()
        )
        identifiers.update(
            identifikace
            for row in measurement_rows
            if (identifikace := _normalize_identifikace(row[0])) is not None
        )

        if not user_context.is_admin:
            identifiers &= set(user_context.allowed_devices)

        return sorted(identifiers)[:limit]
    finally:
        session_ms.close()
        session_pg.close()


def load_measurement_series(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, object]]:
    require_section_access(user_context, "manometry")
    require_device_access(user_context, identifikace)
    start_utc, end_utc = local_date_range_to_utc(start_date, end_date)

    session = get_session_pg()
    try:
        rows = (
            session.query(
                Mereni_manometry_vse.date,
                Mereni_manometry_vse.identifikace,
                Mereni_manometry_vse.seriove_cislo,
                Mereni_manometry_vse.hodnota,
                Mereni_manometry_vse.platne,
                Mereni_manometry_vse.zdroj,
                Mereni_manometry_vse.source_date,
                Mereni_manometry_vse.time_utc,
                Mereni_manometry_vse.time_basis,
                Mereni_manometry_vse.source_timezone,
                Mereni_manometry_vse.source_utc_offset_minutes,
                Mereni_manometry_vse.time_fold,
                Mereni_manometry_vse.timestamp_position,
            )
            .filter(
                Mereni_manometry_vse.identifikace == identifikace,
                Mereni_manometry_vse.time_utc >= start_utc,
                Mereni_manometry_vse.time_utc < end_utc,
                Mereni_manometry_vse.hodnota.is_not(None),
            )
            .order_by(Mereni_manometry_vse.time_utc.asc())
            .all()
        )
        return [
            {
                "date": row.date,
                "identifikace": str(row.identifikace),
                "seriove_cislo": str(row.seriove_cislo) if row.seriove_cislo is not None else None,
                "hodnota": float(row.hodnota),
                "platne": bool(row.platne) if row.platne is not None else None,
                "zdroj": row.zdroj,
                "source_date": row.source_date,
                "time_utc": row.time_utc,
                "time_basis": row.time_basis,
                "source_timezone": row.source_timezone,
                "source_utc_offset_minutes": row.source_utc_offset_minutes,
                "time_fold": row.time_fold,
                "timestamp_position": row.timestamp_position,
            }
            for row in rows
            if row.identifikace is not None and row.hodnota is not None
        ]
    finally:
        session.close()


def load_device_detail(
    user_context: DashboardUserContext,
    *,
    identifikace: str,
) -> dict[str, object] | None:
    require_section_access(user_context, "manometry")
    require_device_access(user_context, identifikace)

    session_ms = get_session_ms()
    session_pg = get_session_pg()
    try:
        device = (
            session_ms.query(Manometr_areal_Zarizeni)
            .filter(Manometr_areal_Zarizeni.identifikace == identifikace)
            .one_or_none()
        )

        base_query = session_pg.query(Mereni_manometry_vse).filter(Mereni_manometry_vse.identifikace == identifikace)
        stats_base_query = base_query.filter(
            Mereni_manometry_vse.time_utc.is_not(None),
            Mereni_manometry_vse.hodnota.is_not(None),
        )
        valid_query = stats_base_query.filter(Mereni_manometry_vse.platne.is_(True))
        measurement_count = int(stats_base_query.count())
        valid_measurement_count = int(valid_query.count())

        if measurement_count == 0 and device is None:
            return None

        first_measurement = stats_base_query.order_by(Mereni_manometry_vse.time_utc.asc()).first()
        last_measurement = stats_base_query.order_by(Mereni_manometry_vse.time_utc.desc()).first()

        stats_query = valid_query if valid_measurement_count > 0 else stats_base_query
        min_measurement = stats_query.order_by(
            Mereni_manometry_vse.hodnota.asc(),
            Mereni_manometry_vse.time_utc.asc(),
        ).first()
        max_measurement = stats_query.order_by(
            Mereni_manometry_vse.hodnota.desc(),
            Mereni_manometry_vse.time_utc.asc(),
        ).first()

        return _serialize_device_detail(
            identifikace=identifikace,
            device=device,
            measurement_count=measurement_count,
            valid_measurement_count=valid_measurement_count,
            first_measurement_at=(
                to_prague_naive(first_measurement.time_utc) or first_measurement.date
                if first_measurement is not None
                else None
            ),
            last_measurement_at=(
                to_prague_naive(last_measurement.time_utc) or last_measurement.date
                if last_measurement is not None
                else None
            ),
            min_measurement=min_measurement,
            max_measurement=max_measurement,
        )
    finally:
        session_ms.close()
        session_pg.close()
