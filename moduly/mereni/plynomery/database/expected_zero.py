from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_PG
from moduly.mereni.plynomery.database.models import PlynomeryExpectedZero


def ensure_expected_zero_table() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        PlynomeryExpectedZero.__table__.create(bind=conn, checkfirst=True)
    _drop_legacy_identifikace_fk(PlynomeryExpectedZero.__tablename__)


def list_expected_zero_devices() -> list[dict[str, object]]:
    ensure_expected_zero_table()
    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        rows = session.execute(
            select(PlynomeryExpectedZero).order_by(PlynomeryExpectedZero.identifikace)
        ).scalars().all()
        return [
            {
                "identifikace": row.identifikace,
                "updated_by": row.updated_by,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]


def get_expected_zero_device_set(session: Session | None = None) -> set[str]:
    ensure_expected_zero_table()
    owns_session = session is None
    db_session = session or Session(ENGINE_PG, autoflush=False, expire_on_commit=False)
    try:
        rows = db_session.execute(select(PlynomeryExpectedZero.identifikace)).all()
        return {row[0] for row in rows}
    finally:
        if owns_session:
            db_session.close()


def replace_expected_zero_devices(
    identifikace_list: Iterable[str],
    updated_by: str | None = None,
) -> None:
    ensure_expected_zero_table()
    desired = {ident.strip() for ident in identifikace_list if ident and ident.strip()}
    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        existing_rows = session.execute(select(PlynomeryExpectedZero)).scalars().all()
        existing_by_ident = {row.identifikace: row for row in existing_rows}
        existing_idents = set(existing_by_ident)

        for ident in existing_idents - desired:
            session.delete(existing_by_ident[ident])

        for ident in desired - existing_idents:
            session.add(PlynomeryExpectedZero(identifikace=ident, updated_by=updated_by))

        for ident in desired & existing_idents:
            existing_by_ident[ident].updated_by = updated_by

        session.commit()


def _drop_legacy_identifikace_fk(table_name: str) -> None:
    inspector = inspect(ENGINE_PG)
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
            with ENGINE_PG.begin() as conn:
                conn.execute(
                    text(
                        f'ALTER TABLE monitoring."{table_name}" '
                        f'DROP CONSTRAINT IF EXISTS "{escaped_name}"'
                    )
                )
