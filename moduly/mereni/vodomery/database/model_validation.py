from __future__ import annotations

from sqlalchemy import text

from core.db.connect import ENGINE_PG
from moduly.mereni.vodomery.database.models import (
    VodomeryModelSelectionCandidate,
    VodomeryModelSelectionRun,
    VodomeryModelValidationMetric,
    VodomeryModelValidationRun,
)


def ensure_vodomery_model_validation_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        VodomeryModelValidationRun.__table__.create(bind=conn, checkfirst=True)
        VodomeryModelValidationMetric.__table__.create(bind=conn, checkfirst=True)
        VodomeryModelSelectionRun.__table__.create(bind=conn, checkfirst=True)
        VodomeryModelSelectionCandidate.__table__.create(bind=conn, checkfirst=True)


def get_active_vodomery_model_version(*, session=None, default: int = 1) -> int:
    ensure_vodomery_model_validation_tables()
    owns_connection = session is None
    db_session = session
    if db_session is None:
        db_session = ENGINE_PG.connect()

    try:
        selected_model_version = db_session.execute(
            text(
                """
                SELECT selected_model_version
                FROM monitoring.vodomery_model_selection_runs
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            )
        ).scalar_one_or_none()
        if selected_model_version is None:
            return default
        return int(selected_model_version)
    finally:
        if owns_connection:
            db_session.close()
