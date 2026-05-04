from __future__ import annotations

from sqlalchemy import text

from core.db.connect import ENGINE_PG
from moduly.apps.smartfuelpass.database.models import Base


def ensure_smartfuelpass_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))

    Base.metadata.create_all(bind=ENGINE_PG)
