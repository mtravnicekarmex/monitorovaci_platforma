from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from core.db.connect import ENGINE_PG
from moduly.mereni.vodomery.database.models import VodomeryExpectedZero


def ensure_expected_zero_table() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        VodomeryExpectedZero.__table__.create(bind=conn, checkfirst=True)


def list_expected_zero_devices() -> list[dict[str, object]]:
    ensure_expected_zero_table()
    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        rows = session.execute(
            select(VodomeryExpectedZero).order_by(VodomeryExpectedZero.identifikace)
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
        rows = db_session.execute(select(VodomeryExpectedZero.identifikace)).all()
        return {row[0] for row in rows}
    finally:
        if owns_session:
            db_session.close()


def replace_expected_zero_devices(identifikace_list: Iterable[str], updated_by: str | None = None) -> None:
    ensure_expected_zero_table()
    desired = {ident.strip() for ident in identifikace_list if ident and ident.strip()}
    with Session(ENGINE_PG, autoflush=False, expire_on_commit=False) as session:
        existing_rows = session.execute(select(VodomeryExpectedZero)).scalars().all()
        existing_by_ident = {row.identifikace: row for row in existing_rows}
        existing_idents = set(existing_by_ident)

        for ident in existing_idents - desired:
            session.delete(existing_by_ident[ident])

        for ident in desired - existing_idents:
            session.add(VodomeryExpectedZero(identifikace=ident, updated_by=updated_by))

        for ident in desired & existing_idents:
            existing_by_ident[ident].updated_by = updated_by

        session.commit()
