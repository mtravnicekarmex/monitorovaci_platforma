from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.db.connect import get_session_pg
from moduly.apps.smartfuelpass.database.db_init import ensure_smartfuelpass_tables
from moduly.apps.smartfuelpass.database.models import SmartFuelPassRelace
from moduly.apps.smartfuelpass.service import (
    _prepare_charge_sessions_dataframe,
    fetch_charge_sessions_dataframe,
)


def build_charge_sessions_sync_rows(dataframe: pd.DataFrame) -> tuple[list[dict[str, Any]], dict[str, int]]:
    prepared, invalid_row_count = _prepare_charge_sessions_dataframe(dataframe)
    completed = prepared[prepared["is_completed"]].copy()

    rows: list[dict[str, Any]] = []
    skipped_missing_id_count = 0
    for row in completed.itertuples(index=False):
        id_relace = str(row.id_relace or "").strip()
        if not id_relace:
            skipped_missing_id_count += 1
            continue

        rows.append(
            {
                "id_relace": id_relace,
                "kwh": None if pd.isna(row.kwh) else round(float(row.kwh), 3),
                "tarif": None if str(row.tariff_label).strip() in {"", "-"} else str(row.tariff_label).strip(),
                "battery_status": None if pd.isna(row.battery_status) else int(row.battery_status),
                "suma": round(float(row.amount_czk), 2),
                "started_at": row.started_at.to_pydatetime() if hasattr(row.started_at, "to_pydatetime") else row.started_at,
                "ended_at": row.ended_at.to_pydatetime() if hasattr(row.ended_at, "to_pydatetime") else row.ended_at,
                "lokace": str(row.location_name).strip() or "-",
                "rychlost_nabijeni": (
                    None if pd.isna(row.rychlost_nabijeni) else round(float(row.rychlost_nabijeni), 3)
                ),
            }
        )

    return rows, {
        "raw_row_count": int(len(dataframe)),
        "prepared_row_count": int(len(prepared)),
        "completed_row_count": int(len(completed)),
        "invalid_row_count": int(invalid_row_count),
        "skipped_missing_id_count": int(skipped_missing_id_count),
    }


def upsert_charge_sessions_sync_rows(
    db_session: Session,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0

    stmt = insert(SmartFuelPassRelace).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["id_relace"])
    result = db_session.execute(stmt)
    db_session.commit()
    return int(result.rowcount or 0)


def sync_charge_sessions_to_db(
    *,
    cookie_path: str | None = None,
    headless: bool = True,
    timeout_seconds: int | None = None,
    db_session: Session | None = None,
) -> dict[str, int]:
    ensure_smartfuelpass_tables()

    owns_session = db_session is None
    session = db_session or get_session_pg()
    try:
        dataframe = fetch_charge_sessions_dataframe(
            cookie_path=cookie_path,
            headless=headless,
            timeout_seconds=timeout_seconds,
        )
        rows, stats = build_charge_sessions_sync_rows(dataframe)
        upserted_count = upsert_charge_sessions_sync_rows(session, rows)
        stats["upserted_count"] = int(upserted_count)
        return stats
    finally:
        if owns_session:
            session.close()
