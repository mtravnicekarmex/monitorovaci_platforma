from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_MS, ENGINE_PG
from moduly.mereni.elektromery.database.models import (
    Elektromer_areal_Mereni,
    Mereni_elektromery,
)
from moduly.mereni.reset_detection import has_significant_negative_diff
from moduly.mereni.elektromery.database.time_semantics import build_time_columns


logger = logging.getLogger(__name__)

engine = ENGINE_PG
engine_ms = ENGINE_MS

CHUNK_SIZE = 5000
SOFTLINK_INTERVAL_MINUTES = 1440
DEFAULT_DELTA_INTERVAL_MINUTES = 15
MAX_GAP_MULTIPLIER = 2
MIN_NIGHT_DELTA = 0.01


def chunked(items, size: int = CHUNK_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def ensure_destination_table() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))

    inspector = inspect(engine)
    monitoring_tables = inspector.get_table_names(schema="monitoring")
    expected_table = Mereni_elektromery.__tablename__

    case_mismatch = next(
        (
            table_name
            for table_name in monitoring_tables
            if table_name.lower() == expected_table.lower() and table_name != expected_table
        ),
        None,
    )
    if case_mismatch:
        raise RuntimeError(
            f"Case mismatch in monitoring schema: model expects '{expected_table}', "
            f"but database has '{case_mismatch}'. Unify table naming first."
        )

    if expected_table not in monitoring_tables:
        Mereni_elektromery.__table__.create(bind=engine, checkfirst=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_ele_vse_time_utc
                    ON monitoring."Mereni_elektromery_vse" (time_utc)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_ele_vse_ident_time_utc
                    ON monitoring."Mereni_elektromery_vse" (identifikace, time_utc)
                    """
                )
            )
        logger.info('Created missing table monitoring."%s"', expected_table)
        return

    columns = inspector.get_columns(expected_table, schema="monitoring")
    objem_column = next((column for column in columns if column["name"] == "objem"), None)
    if objem_column is not None and not objem_column.get("nullable", True):
        with engine.begin() as conn:
            conn.execute(text('ALTER TABLE monitoring."Mereni_elektromery_vse" ALTER COLUMN objem DROP NOT NULL'))
        logger.info('Relaxed NOT NULL on monitoring."%s".objem for delta-only rows', expected_table)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE monitoring."Mereni_elektromery_vse"
                    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
                    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
                    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
                    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
                    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
                    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_ele_vse_time_utc
                ON monitoring."Mereni_elektromery_vse" (time_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_ele_vse_ident_time_utc
                ON monitoring."Mereni_elektromery_vse" (identifikace, time_utc)
                """
            )
        )


def ensure_elektromery_vse_table() -> None:
    ensure_destination_table()


def get_last_imported_recid(session: Session, source_name: str) -> int | None:
    query = select(func.max(Mereni_elektromery.source_recid)).where(Mereni_elektromery.zdroj == source_name)
    return session.execute(query).scalar()


def fetch_from_ms_softlink() -> list[dict[str, object]]:
    with Session(engine) as pg_session:
        last_recid = get_last_imported_recid(pg_session, "SOFTLINK")

    with Session(engine_ms) as ms_session:
        query = (
            select(
                Elektromer_areal_Mereni.recid,
                Elektromer_areal_Mereni.identifikace,
                Elektromer_areal_Mereni.seriove_cislo,
                Elektromer_areal_Mereni.date,
                Elektromer_areal_Mereni.total,
            )
            .where(
                Elektromer_areal_Mereni.identifikace.is_not(None),
                Elektromer_areal_Mereni.date.is_not(None),
                Elektromer_areal_Mereni.total.is_not(None),
            )
            .order_by(Elektromer_areal_Mereni.recid)
        )
        if last_recid is not None:
            query = query.where(Elektromer_areal_Mereni.recid > last_recid)

        rows = ms_session.execute(query).all()

    return [
        {
            "recid": row.recid,
            "identifikace": row.identifikace,
            "seriove_cislo": row.seriove_cislo,
            "date": row.date,
            "objem": row.total,
            "interval_minutes": SOFTLINK_INTERVAL_MINUTES,
            "platne": True,
        }
        for row in rows
    ]


def compute_slot(dt: datetime, interval_minutes: int) -> int:
    minutes_from_midnight = dt.hour * 60 + dt.minute
    return minutes_from_midnight // interval_minutes


def compute_day_of_week(dt: datetime) -> int:
    return dt.weekday()


def is_night_time(dt: datetime) -> bool:
    return dt.hour >= 23 or dt.hour < 5


def _to_naive_datetime(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=None)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(value: object) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_last_measurements(
    session: Session,
    affected_idents: set[str],
    *,
    only_valid: bool = False,
    source_name: str | None = None,
    require_objem: bool = False,
) -> dict[str, Mereni_elektromery]:
    if not affected_idents:
        return {}

    rows_by_ident: dict[str, Mereni_elektromery] = {}
    for ident_chunk in chunked(list(affected_idents)):
        subquery = (
            select(
                Mereni_elektromery.identifikace,
                func.max(Mereni_elektromery.date).label("max_date"),
            )
            .where(Mereni_elektromery.identifikace.in_(ident_chunk))
        )
        if only_valid:
            subquery = subquery.where(Mereni_elektromery.platne.is_(True))
        if source_name is not None:
            subquery = subquery.where(Mereni_elektromery.zdroj == source_name)
        if require_objem:
            subquery = subquery.where(Mereni_elektromery.objem.is_not(None))

        subquery = subquery.group_by(Mereni_elektromery.identifikace).subquery()
        query = (
            select(Mereni_elektromery)
            .join(
                subquery,
                (Mereni_elektromery.identifikace == subquery.c.identifikace)
                & (Mereni_elektromery.date == subquery.c.max_date),
            )
        )
        if only_valid:
            query = query.where(Mereni_elektromery.platne.is_(True))
        if source_name is not None:
            query = query.where(Mereni_elektromery.zdroj == source_name)
        if require_objem:
            query = query.where(Mereni_elektromery.objem.is_not(None))

        for row in session.execute(query).scalars().all():
            rows_by_ident[row.identifikace] = row

    return rows_by_ident


def filter_valid_rows(session: Session, rows: list[dict[str, object]], source_name: str) -> list[dict[str, object]]:
    if not rows:
        return []

    sanitized: list[dict[str, object]] = []
    dropped_invalid = 0
    dropped_negative = 0

    for row in rows:
        ident = str(row.get("identifikace") or "").strip()
        dt = _to_naive_datetime(row.get("date"))
        interval = int(row.get("interval_minutes") or DEFAULT_DELTA_INTERVAL_MINUTES)
        serial = row.get("seriove_cislo")

        if not ident or dt is None or interval <= 0:
            dropped_invalid += 1
            continue

        prepared = dict(row)
        prepared["identifikace"] = ident
        prepared["date"] = dt
        prepared["seriove_cislo"] = _to_int_or_none(serial)
        prepared["interval_minutes"] = interval
        prepared["platne"] = bool(row.get("platne", True))
        prepared["reset_detected"] = False

        if row.get("delta_source"):
            delta = _to_float(row.get("delta"))
            if delta is None:
                dropped_invalid += 1
                continue
            if delta < 0:
                dropped_negative += 1
                continue
            prepared["objem"] = None
            prepared["delta"] = round(delta, 6)
        else:
            objem = _to_float(row.get("objem"))
            if objem is None:
                dropped_invalid += 1
                continue
            if objem < 0:
                dropped_negative += 1
                continue
            prepared["objem"] = objem

        sanitized.append(prepared)

    if not sanitized:
        logger.warning(
            "%s dropped rows - invalid: %s, negative: %s",
            source_name,
            dropped_invalid,
            dropped_negative,
        )
        return []

    if any(not row.get("delta_source") for row in sanitized):
        affected_idents = {row["identifikace"] for row in sanitized if not row.get("delta_source")}
        last_existing = get_last_measurements(
            session,
            affected_idents,
            only_valid=True,
            source_name=source_name,
            require_objem=True,
        )
        previous_by_ident = {
            ident: {
                "objem": last.objem,
                "date": last.date,
                "seriove_cislo": last.seriove_cislo,
            }
            for ident, last in last_existing.items()
            if last is not None
        }

        for row in sorted((item for item in sanitized if not item.get("delta_source")), key=lambda item: (item["identifikace"], item["date"])):
            ident = row["identifikace"]
            previous = previous_by_ident.get(ident)
            if previous is not None and has_significant_negative_diff(row["objem"], previous["objem"]):
                row["reset_detected"] = True

            if row["platne"]:
                previous_by_ident[ident] = {
                    "objem": row["objem"],
                    "date": row["date"],
                    "seriove_cislo": row.get("seriove_cislo"),
                }

    if dropped_invalid or dropped_negative:
        logger.warning(
            "%s dropped rows - invalid: %s, negative: %s",
            source_name,
            dropped_invalid,
            dropped_negative,
        )

    return sanitized


def resolve_gap(
    ident: str,
    previous: dict[str, object],
    current_dt: datetime,
    current_objem: float,
    interval: int,
    source_name: str,
) -> tuple[list[dict[str, object]], float | None]:
    previous_dt = previous["date"]
    previous_objem = previous["objem"]
    total_minutes = int((current_dt - previous_dt).total_seconds() // 60)
    slot_count = total_minutes // interval
    if slot_count <= 1:
        return [], None

    total_delta = current_objem - previous_objem
    if total_delta <= 0:
        return [], None

    mean_delta = round(total_delta / slot_count, 6)
    rows: list[dict[str, object]] = []
    for index in range(1, slot_count):
        slot_time = previous_dt + timedelta(minutes=index * interval)
        rows.append(
            {
                "source_recid": None,
                "identifikace": ident,
                "seriove_cislo": previous.get("seriove_cislo"),
                "date": slot_time,
                **build_time_columns(slot_time, source_name),
                "objem": round(previous_objem + mean_delta * index, 6),
                "delta": mean_delta,
                "interval_minutes": interval,
                "day_of_week": compute_day_of_week(slot_time),
                "slot": compute_slot(slot_time, interval),
                "nocni_odber": mean_delta > MIN_NIGHT_DELTA and is_night_time(slot_time),
                "platne": True,
                "gap_detected": False,
                "synthetic": True,
                "zdroj": source_name,
                "reset_detected": False,
            }
        )
    return rows, mean_delta


def prepare_state_rows(session: Session, new_rows: list[dict[str, object]], source_name: str) -> list[dict[str, object]]:
    if not new_rows:
        return []

    affected_idents = {row["identifikace"] for row in new_rows}
    last_existing = get_last_measurements(
        session,
        affected_idents,
        only_valid=True,
        source_name=source_name,
        require_objem=True,
    )
    previous_map: dict[str, dict[str, object] | None] = {}
    for ident in affected_idents:
        last = last_existing.get(ident)
        previous_map[ident] = None
        if last is not None:
            previous_map[ident] = {
                "objem": last.objem,
                "date": last.date,
                "seriove_cislo": last.seriove_cislo,
            }

    rows_to_insert: list[dict[str, object]] = []
    for row in sorted(new_rows, key=lambda item: (item["identifikace"], item["date"])):
        ident = row["identifikace"]
        dt = row["date"]
        interval = int(row["interval_minutes"])
        objem = float(row["objem"])
        previous = previous_map.get(ident)
        is_valid_row = bool(row.get("platne", True))
        reset_detected = bool(row.get("reset_detected", False))
        delta = None
        gap_detected = False

        if is_valid_row and not reset_detected and previous and previous.get("date") is not None:
            expected_interval = timedelta(minutes=interval)
            actual_diff = dt - previous["date"]
            if actual_diff > expected_interval * MAX_GAP_MULTIPLIER and objem >= previous["objem"]:
                synthetic_rows, gap_delta = resolve_gap(ident, previous, dt, objem, interval, source_name)
                if synthetic_rows:
                    rows_to_insert.extend(synthetic_rows)
                    gap_detected = True
                    delta = gap_delta

            if delta is None and objem >= previous["objem"]:
                delta = round(objem - previous["objem"], 6)

        if reset_detected:
            delta = None

        rows_to_insert.append(
            {
                "source_recid": row["recid"],
                "identifikace": ident,
                "seriove_cislo": row.get("seriove_cislo"),
                "date": dt,
                **build_time_columns(dt, source_name, row),
                "objem": objem,
                "delta": delta,
                "interval_minutes": interval,
                "day_of_week": compute_day_of_week(dt),
                "slot": compute_slot(dt, interval),
                "nocni_odber": (
                    is_valid_row
                    and not reset_detected
                    and delta is not None
                    and delta > MIN_NIGHT_DELTA
                    and is_night_time(dt)
                ),
                "platne": is_valid_row,
                "gap_detected": gap_detected,
                "synthetic": False,
                "zdroj": source_name,
                "reset_detected": reset_detected,
            }
        )

        if is_valid_row:
            previous_map[ident] = {
                "objem": objem,
                "date": dt,
                "seriove_cislo": row.get("seriove_cislo"),
            }

    return rows_to_insert


def prepare_delta_rows(session: Session, new_rows: list[dict[str, object]], source_name: str) -> list[dict[str, object]]:
    if not new_rows:
        return []

    affected_idents = {row["identifikace"] for row in new_rows}
    last_existing = get_last_measurements(
        session,
        affected_idents,
        only_valid=True,
        source_name=source_name,
    )
    previous_dates = {
        ident: last.date
        for ident, last in last_existing.items()
        if last is not None and last.date is not None
    }

    rows_to_insert: list[dict[str, object]] = []
    for row in sorted(new_rows, key=lambda item: (item["identifikace"], item["date"])):
        ident = row["identifikace"]
        dt = row["date"]
        interval = int(row["interval_minutes"])
        delta = round(float(row["delta"]), 6)
        previous_dt = previous_dates.get(ident)
        gap_detected = False
        if previous_dt is not None and dt - previous_dt > timedelta(minutes=interval * MAX_GAP_MULTIPLIER):
            gap_detected = True

        rows_to_insert.append(
            {
                "source_recid": row["recid"],
                "identifikace": ident,
                "seriove_cislo": row.get("seriove_cislo"),
                "date": dt,
                **build_time_columns(dt, source_name, row),
                "objem": None,
                "delta": delta,
                "interval_minutes": interval,
                "day_of_week": compute_day_of_week(dt),
                "slot": compute_slot(dt, interval),
                "nocni_odber": delta > MIN_NIGHT_DELTA and is_night_time(dt),
                "platne": bool(row.get("platne", True)),
                "gap_detected": gap_detected,
                "synthetic": False,
                "zdroj": source_name,
                "reset_detected": False,
            }
        )
        previous_dates[ident] = dt

    return rows_to_insert


def import_measurements(session: Session, source_name: str, source_rows: list[dict[str, object]]) -> dict[str, object]:
    if not source_rows:
        return {"rows": []}

    new_rows = filter_valid_rows(session, source_rows, source_name)
    if not new_rows:
        return {"rows": []}

    if all(row.get("delta_source") for row in new_rows):
        rows_to_insert = prepare_delta_rows(session, new_rows, source_name)
    else:
        rows_to_insert = prepare_state_rows(session, new_rows, source_name)

    if not rows_to_insert:
        return {"rows": []}

    inserted_rows = 0
    for batch in chunked(rows_to_insert):
        stmt = insert(Mereni_elektromery).on_conflict_do_nothing(
            index_elements=["identifikace", "date", "zdroj"]
        )
        session.execute(stmt, batch)
        inserted_rows += len(batch)

    logger.info("%s prepared for insert into monitoring.Mereni_elektromery_vse: %s", source_name, inserted_rows)
    return {"rows": rows_to_insert}


def elektromery_db_import() -> dict[str, object]:
    ensure_destination_table()

    with Session(engine) as session:
        with session.begin():
            rows_softlink = fetch_from_ms_softlink()
            inserted_softlink = import_measurements(session, "SOFTLINK", rows_softlink)
            logger.info("SOFTLINK inserted into elektromery_vse: %s", len(inserted_softlink["rows"]))

        return {
            "inserted_softlink": len(inserted_softlink["rows"]),
        }
