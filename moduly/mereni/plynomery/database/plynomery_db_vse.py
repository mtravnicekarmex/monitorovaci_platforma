from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_MS, ENGINE_PG
from moduly.mereni.plynomery.database.models import (
    Mereni_plynomery,
    Plynomer_areal_Mereni,
    Plynomer_areal_Zarizeni,
)


logger = logging.getLogger(__name__)

engine = ENGINE_PG
engine_ms = ENGINE_MS

CHUNK_SIZE = 5000
DEFAULT_INTERVAL_MINUTES = 15
MAX_GAP_MULTIPLIER = 2
MIN_NIGHT_DELTA = 0.01


def chunked(items, size: int = CHUNK_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _drop_legacy_identifikace_fk(table_name: str) -> None:
    inspector = inspect(engine)
    for foreign_key in inspector.get_foreign_keys(table_name, schema="monitoring"):
        name = foreign_key.get("name")
        constrained_columns = tuple(foreign_key.get("constrained_columns") or ())
        referred_schema = foreign_key.get("referred_schema")
        referred_table = foreign_key.get("referred_table")
        if (
            name
            and constrained_columns == ("identifikace",)
            and referred_schema == "evidence"
            and referred_table == "plynoměry"
        ):
            escaped_name = str(name).replace('"', '""')
            with engine.begin() as conn:
                conn.execute(
                    text(
                        f'ALTER TABLE monitoring."{table_name}" '
                        f'DROP CONSTRAINT IF EXISTS "{escaped_name}"'
                    )
                )
            logger.info(
                'Dropped legacy foreign key "%s" from monitoring."%s"',
                name,
                table_name,
            )


def ensure_destination_table() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))

    inspector = inspect(engine)
    monitoring_tables = inspector.get_table_names(schema="monitoring")
    expected_table = Mereni_plynomery.__tablename__

    case_mismatch = next(
        (table_name for table_name in monitoring_tables if table_name.lower() == expected_table.lower() and table_name != expected_table),
        None,
    )
    if case_mismatch:
        raise RuntimeError(
            f"Case mismatch in monitoring schema: model expects '{expected_table}', "
            f"but database has '{case_mismatch}'. Unify table naming first."
        )

    if expected_table not in monitoring_tables:
        Mereni_plynomery.__table__.create(bind=engine, checkfirst=True)
        logger.info('Created missing table monitoring."%s"', expected_table)

    _drop_legacy_identifikace_fk(expected_table)


def get_last_imported_recid(session: Session, source_name: str) -> int | None:
    query = select(func.max(Mereni_plynomery.source_recid)).where(Mereni_plynomery.zdroj == source_name)
    return session.execute(query).scalar()


def fetch_from_ms_areal() -> list[dict[str, object]]:
    with Session(engine) as pg_session:
        last_recid = get_last_imported_recid(pg_session, "AREAL")

    with Session(engine_ms) as ms_session:
        query = (
            select(
                Plynomer_areal_Mereni.recid,
                Plynomer_areal_Mereni.identifikace,
                Plynomer_areal_Mereni.seriove_cislo,
                Plynomer_areal_Mereni.date,
                Plynomer_areal_Mereni.objem,
                Plynomer_areal_Mereni.platne,
            )
            .where(
                Plynomer_areal_Mereni.identifikace.is_not(None),
                Plynomer_areal_Mereni.date.is_not(None),
                Plynomer_areal_Mereni.objem.is_not(None),
            )
            .order_by(Plynomer_areal_Mereni.recid)
        )
        if last_recid is not None:
            query = query.where(Plynomer_areal_Mereni.recid > last_recid)

        rows = ms_session.execute(query).all()

    return [
        {
            "recid": row.recid,
            "identifikace": row.identifikace,
            "seriove_cislo": row.seriove_cislo,
            "date": row.date,
            "objem": row.objem,
            "platne": True if row.platne is None else bool(row.platne),
            "interval_minutes": DEFAULT_INTERVAL_MINUTES,
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


def get_last_measurements(session: Session, affected_idents: set[str], *, only_valid: bool = False) -> dict[str, Mereni_plynomery]:
    if not affected_idents:
        return {}

    rows_by_ident: dict[str, Mereni_plynomery] = {}
    for ident_chunk in chunked(list(affected_idents)):
        subquery = (
            select(
                Mereni_plynomery.identifikace,
                func.max(Mereni_plynomery.date).label("max_date"),
            )
            .where(Mereni_plynomery.identifikace.in_(ident_chunk))
        )
        if only_valid:
            subquery = subquery.where(Mereni_plynomery.platne.is_(True))
        subquery = subquery.group_by(Mereni_plynomery.identifikace).subquery()

        query = (
            select(Mereni_plynomery)
            .join(
                subquery,
                (Mereni_plynomery.identifikace == subquery.c.identifikace)
                & (Mereni_plynomery.date == subquery.c.max_date),
            )
        )
        if only_valid:
            query = query.where(Mereni_plynomery.platne.is_(True))

        for row in session.execute(query).scalars().all():
            rows_by_ident[row.identifikace] = row

    return rows_by_ident


def resolve_gap(
    ident: str,
    prev: dict[str, object],
    current_dt: datetime,
    current_objem: float,
    interval: int,
    source_name: str,
) -> tuple[list[dict[str, object]], float | None]:
    prev_dt = prev["date"]
    prev_objem = prev["objem"]

    total_minutes = int((current_dt - prev_dt).total_seconds() // 60)
    num_slots = total_minutes // interval
    if num_slots <= 1:
        return [], None

    total_delta = current_objem - prev_objem
    if total_delta <= 0:
        return [], None

    mean_delta = round(total_delta / num_slots, 6)
    rows: list[dict[str, object]] = []

    for index in range(1, num_slots):
        slot_time = prev_dt + timedelta(minutes=index * interval)
        rows.append(
            {
                "source_recid": None,
                "identifikace": ident,
                "seriove_cislo": prev.get("seriove_cislo"),
                "date": slot_time,
                "objem": round(prev_objem + mean_delta * index, 6),
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


def filter_valid_rows(session: Session, rows: list[dict[str, object]], source_name: str) -> list[dict[str, object]]:
    if not rows:
        return []

    sanitized = []
    dropped_invalid = 0

    for row in rows:
        ident = str(row.get("identifikace") or "").strip()
        dt = row.get("date")
        objem = row.get("objem")

        if not ident or dt is None or objem is None:
            dropped_invalid += 1
            continue

        row["identifikace"] = ident
        row["platne"] = bool(row.get("platne", True))
        row["reset_detected"] = False
        sanitized.append(row)

    if not sanitized:
        logger.warning("%s dropped rows - invalid: %s", source_name, dropped_invalid)
        return []

    valid_idents = set()
    ident_list = list({row["identifikace"] for row in sanitized})
    with Session(engine_ms) as ms_session:
        for ident_chunk in chunked(ident_list):
            valid_idents.update(
                ms_session.execute(
                    select(Plynomer_areal_Zarizeni.identifikace).where(Plynomer_areal_Zarizeni.identifikace.in_(ident_chunk))
                )
                .scalars()
                .all()
            )

    filtered = [row for row in sanitized if row["identifikace"] in valid_idents]
    dropped_fk = len(sanitized) - len(filtered)

    if filtered:
        affected_idents = {row["identifikace"] for row in filtered}
        last_existing = get_last_measurements(session, affected_idents, only_valid=True)
        previous_by_ident = {
            ident: {
                "objem": last.objem,
                "date": last.date,
                "seriove_cislo": last.seriove_cislo,
            }
            for ident, last in last_existing.items()
            if last is not None
        }

        for row in sorted(filtered, key=lambda item: (item["identifikace"], item["date"])):
            ident = row["identifikace"]
            previous = previous_by_ident.get(ident)
            serial_changed = (
                previous is not None
                and previous.get("seriove_cislo") is not None
                and row.get("seriove_cislo") is not None
                and row["seriove_cislo"] != previous["seriove_cislo"]
            )
            volume_reset = previous is not None and row["objem"] < previous["objem"]
            if serial_changed or volume_reset:
                row["reset_detected"] = True

            if row["platne"]:
                previous_by_ident[ident] = {
                    "objem": row["objem"],
                    "date": row["date"],
                    "seriove_cislo": row.get("seriove_cislo"),
                }

    if dropped_invalid or dropped_fk:
        logger.warning(
            "%s dropped rows - invalid: %s, missing_ms_zarizeni_identifikace: %s",
            source_name,
            dropped_invalid,
            dropped_fk,
        )

    return filtered


def prepare_rows(session: Session, new_rows: list[dict[str, object]], source_name: str) -> list[dict[str, object]]:
    if not new_rows:
        return []

    affected_idents = {row["identifikace"] for row in new_rows}
    last_existing = get_last_measurements(session, affected_idents, only_valid=True)
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
        prev = previous_map.get(ident)

        delta = None
        gap_detected = False
        is_valid_row = bool(row.get("platne", True))
        reset_detected = bool(row.get("reset_detected", False))

        if is_valid_row and not reset_detected and prev and prev.get("date") is not None:
            expected_interval = timedelta(minutes=interval)
            actual_diff = dt - prev["date"]

            if actual_diff > expected_interval * MAX_GAP_MULTIPLIER and objem >= prev["objem"]:
                synthetic_rows, gap_delta = resolve_gap(
                    ident,
                    prev,
                    dt,
                    objem,
                    interval,
                    source_name,
                )
                rows_to_insert.extend(synthetic_rows)
                if synthetic_rows:
                    gap_detected = True
                    delta = gap_delta
            elif objem >= prev["objem"]:
                delta = objem - prev["objem"]

        if delta is not None:
            delta = round(delta, 6)

        if reset_detected:
            delta = None

        nocni_odber = (
            is_valid_row
            and not reset_detected
            and delta is not None
            and delta > MIN_NIGHT_DELTA
            and is_night_time(dt)
        )

        rows_to_insert.append(
            {
                "source_recid": row["recid"],
                "identifikace": ident,
                "seriove_cislo": row.get("seriove_cislo"),
                "date": dt,
                "objem": objem,
                "delta": delta,
                "interval_minutes": interval,
                "day_of_week": compute_day_of_week(dt),
                "slot": compute_slot(dt, interval),
                "nocni_odber": nocni_odber,
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


def import_measurements(session: Session, source_name: str, ms_rows: list[dict[str, object]]) -> dict[str, object]:
    if not ms_rows:
        return {"rows": []}

    new_rows = filter_valid_rows(session, ms_rows, source_name)
    if not new_rows:
        return {"rows": []}

    rows_to_insert = prepare_rows(session, new_rows, source_name)
    if not rows_to_insert:
        return {"rows": []}

    for batch in chunked(rows_to_insert):
        statement = insert(Mereni_plynomery).on_conflict_do_nothing(index_elements=["identifikace", "date", "zdroj"])
        session.execute(statement, batch)

    logger.info("%s prepared for insert: %s", source_name, len(rows_to_insert))
    return {"rows": rows_to_insert}


def plynomery_db_import() -> None:
    ensure_destination_table()

    with Session(engine) as session:
        with session.begin():
            rows_areal = fetch_from_ms_areal()
            inserted_areal = import_measurements(session, "AREAL", rows_areal)
            logger.info("AREAL inserted: %s", len(inserted_areal["rows"]))
