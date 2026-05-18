from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter

from sqlalchemy import func, inspect, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_MS, ENGINE_PG
from moduly.mereni.manometry.database.models import (
    Manometr_areal_Zarizeni,
    Mereni_manometry,
    Mereni_manometry_vse,
)
from moduly.mereni.time_semantics import build_time_columns


logger = logging.getLogger(__name__)

engine = ENGINE_PG
engine_ms = ENGINE_MS

CHUNK_SIZE = 5000
SOURCE_NAME = "AREAL"
TIME_SEMANTICS_SOURCE_NAME = "MANOMETRY"


def chunked(items, size: int = CHUNK_SIZE):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def ensure_destination_table() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))

    inspector = inspect(engine)
    monitoring_tables = inspector.get_table_names(schema="monitoring")
    expected_table = Mereni_manometry_vse.__tablename__

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
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE monitoring."Mereni_manometry_vse" (
                        id BIGSERIAL PRIMARY KEY,
                        source_recid BIGINT,
                        identifikace VARCHAR(250) NOT NULL,
                        seriove_cislo VARCHAR(250),
                        date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
                        source_date TIMESTAMP WITHOUT TIME ZONE,
                        time_utc TIMESTAMP WITH TIME ZONE,
                        time_basis VARCHAR(40),
                        source_timezone VARCHAR(64),
                        source_utc_offset_minutes INTEGER,
                        time_fold INTEGER,
                        timestamp_position VARCHAR(20),
                        hodnota DOUBLE PRECISION NOT NULL,
                        platne BOOLEAN NOT NULL DEFAULT TRUE,
                        zdroj VARCHAR(20) NOT NULL,
                        created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
                        CONSTRAINT uq_manometry_ident_date_zdroj UNIQUE (identifikace, date, zdroj),
                        CONSTRAINT uq_manometry_source_recid_zdroj UNIQUE (source_recid, zdroj)
                    )
                    """
                )
            )
        logger.info('Created missing table monitoring."%s"', expected_table)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE monitoring."Mereni_manometry_vse"
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
                CREATE TABLE IF NOT EXISTS monitoring.manometry_import_state (
                    zdroj VARCHAR(20) PRIMARY KEY,
                    last_source_recid BIGINT NOT NULL,
                    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_Mereni_manometry_vse_source_recid
                ON monitoring."Mereni_manometry_vse" (source_recid)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_manometry_ident_date_desc
                ON monitoring."Mereni_manometry_vse" (identifikace, date)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_manometry_date_desc
                ON monitoring."Mereni_manometry_vse" (date)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_manometry_vse_time_utc
                ON monitoring."Mereni_manometry_vse" (time_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_manometry_vse_ident_time_utc
                ON monitoring."Mereni_manometry_vse" (identifikace, time_utc)
                """
            )
        )


def get_last_imported_recid(session: Session, source_name: str) -> int | None:
    state_value = session.execute(
        text(
            """
            SELECT last_source_recid
            FROM monitoring.manometry_import_state
            WHERE zdroj = :source_name
            """
        ),
        {"source_name": source_name},
    ).scalar()
    if state_value is not None:
        return int(state_value)

    query = select(func.max(Mereni_manometry_vse.source_recid)).where(Mereni_manometry_vse.zdroj == source_name)
    return session.execute(query).scalar()


def update_import_state(session: Session, source_name: str, ms_rows: list[dict[str, object]]) -> None:
    source_recids = [int(row["recid"]) for row in ms_rows if row.get("recid") is not None]
    if not source_recids:
        return

    session.execute(
        text(
            """
            INSERT INTO monitoring.manometry_import_state (zdroj, last_source_recid, updated_at)
            VALUES (:source_name, :last_source_recid, now())
            ON CONFLICT (zdroj) DO UPDATE
            SET last_source_recid = GREATEST(
                    monitoring.manometry_import_state.last_source_recid,
                    EXCLUDED.last_source_recid
                ),
                updated_at = now()
            """
        ),
        {
            "source_name": source_name,
            "last_source_recid": max(source_recids),
        },
    )


def fetch_from_ms_areal() -> list[dict[str, object]]:
    t0 = perf_counter()
    with Session(engine) as pg_session:
        last_recid = get_last_imported_recid(pg_session, SOURCE_NAME)
    logger.info("%s last_recid: %s", SOURCE_NAME, last_recid)

    with Session(engine_ms) as ms_session:
        query = (
            select(
                Mereni_manometry.recid,
                Mereni_manometry.identifikace,
                Mereni_manometry.seriove_cislo,
                Mereni_manometry.date,
                Mereni_manometry.hodnota,
                Mereni_manometry.platne,
            )
            .where(
                Mereni_manometry.identifikace.is_not(None),
                Mereni_manometry.date.is_not(None),
                Mereni_manometry.hodnota.is_not(None),
            )
            .order_by(Mereni_manometry.recid)
        )
        if last_recid is not None:
            query = query.where(Mereni_manometry.recid > last_recid)

        rows = ms_session.execute(query).all()
        logger.info("%s rows fetched: %s in %.1fs", SOURCE_NAME, len(rows), perf_counter() - t0)

    return [
        {
            "recid": row.recid,
            "identifikace": row.identifikace,
            "seriove_cislo": row.seriove_cislo,
            "date": row.date,
            "hodnota": row.hodnota,
            "platne": True if row.platne is None else bool(row.platne),
        }
        for row in rows
    ]


def filter_valid_rows(rows: list[dict[str, object]], source_name: str) -> list[dict[str, object]]:
    if not rows:
        return []

    sanitized: list[dict[str, object]] = []
    dropped_invalid = 0

    for row in rows:
        ident = str(row.get("identifikace") or "").strip()
        dt = row.get("date")
        hodnota = row.get("hodnota")

        if not ident or dt is None or hodnota is None:
            dropped_invalid += 1
            continue

        try:
            row["hodnota"] = float(hodnota)
        except (TypeError, ValueError):
            dropped_invalid += 1
            continue

        row["identifikace"] = ident
        row["seriove_cislo"] = None if row.get("seriove_cislo") is None else str(row["seriove_cislo"])
        row["platne"] = True if row.get("platne") is None else bool(row["platne"])
        sanitized.append(row)

    if not sanitized:
        logger.warning("%s dropped rows - invalid: %s", source_name, dropped_invalid)
        return []

    valid_idents: set[str] = set()
    ident_list = list({row["identifikace"] for row in sanitized})
    with Session(engine_ms) as ms_session:
        for ident_chunk in chunked(ident_list):
            valid_idents.update(
                ms_session.execute(
                    select(Manometr_areal_Zarizeni.identifikace).where(
                        Manometr_areal_Zarizeni.identifikace.in_(ident_chunk)
                    )
                )
                .scalars()
                .all()
            )

    filtered = [row for row in sanitized if row["identifikace"] in valid_idents]
    dropped_fk = len(sanitized) - len(filtered)
    if dropped_invalid or dropped_fk:
        logger.warning(
            "%s dropped rows - invalid: %s, missing_ms_zarizeni_identifikace: %s",
            source_name,
            dropped_invalid,
            dropped_fk,
        )

    return filtered


def prepare_rows(new_rows: list[dict[str, object]], source_name: str) -> list[dict[str, object]]:
    rows_to_insert: list[dict[str, object]] = []

    for row in sorted(new_rows, key=lambda item: (item["identifikace"], item["date"], item["recid"])):
        dt = row["date"]
        if not isinstance(dt, datetime):
            continue

        rows_to_insert.append(
            {
                "source_recid": row["recid"],
                "identifikace": row["identifikace"],
                "seriove_cislo": row.get("seriove_cislo"),
                "date": dt,
                **build_time_columns(dt, TIME_SEMANTICS_SOURCE_NAME, row),
                "hodnota": float(row["hodnota"]),
                "platne": bool(row.get("platne", True)),
                "zdroj": source_name,
            }
        )

    return rows_to_insert


def import_measurements(session: Session, source_name: str, ms_rows: list[dict[str, object]]) -> dict[str, object]:
    if not ms_rows:
        return {"rows": []}

    new_rows = filter_valid_rows(ms_rows, source_name)
    if not new_rows:
        update_import_state(session, source_name, ms_rows)
        return {"rows": []}

    rows_to_insert = prepare_rows(new_rows, source_name)
    if not rows_to_insert:
        update_import_state(session, source_name, ms_rows)
        return {"rows": []}

    for batch in chunked(rows_to_insert):
        statement = insert(Mereni_manometry_vse).on_conflict_do_nothing()
        session.execute(statement, batch)

    update_import_state(session, source_name, ms_rows)
    logger.info("%s prepared for insert: %s", source_name, len(rows_to_insert))
    return {"rows": rows_to_insert}


def manometry_db_import() -> dict[str, int]:
    ensure_destination_table()

    with Session(engine) as session:
        with session.begin():
            rows_areal = fetch_from_ms_areal()
            inserted_areal = import_measurements(session, SOURCE_NAME, rows_areal)
            logger.info("%s inserted: %s", SOURCE_NAME, len(inserted_areal["rows"]))

    return {"inserted_areal": len(inserted_areal["rows"])}
