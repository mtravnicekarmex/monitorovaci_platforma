from __future__ import annotations

from sqlalchemy import text

from core.db.connect import ENGINE_PG
from moduly.mereni.vodomery.database.models import (
    VodomeryModelValidationMetric,
    VodomeryModelValidationRun,
)


def ensure_vodomery_model_validation_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        VodomeryModelValidationRun.__table__.create(bind=conn, checkfirst=True)
        VodomeryModelValidationMetric.__table__.create(bind=conn, checkfirst=True)
