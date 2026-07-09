from __future__ import annotations

from sqlalchemy import text

from core.db.connect import ENGINE_PG
from moduly.mereni.vodomery.database.models import (
    VodomeryModelSelectionCandidate,
    VodomeryModelSelectionDeviceCandidate,
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
        VodomeryModelSelectionDeviceCandidate.__table__.create(bind=conn, checkfirst=True)
        conn.execute(
            text(
                """
                ALTER TABLE monitoring.vodomery_model_selection_candidates
                    ADD COLUMN IF NOT EXISTS model_key varchar(80),
                    ADD COLUMN IF NOT EXISTS training_window_months integer,
                    ADD COLUMN IF NOT EXISTS validation_window_months integer,
                    ADD COLUMN IF NOT EXISTS selection_enabled boolean NOT NULL DEFAULT true,
                    ADD COLUMN IF NOT EXISTS rolling_backtest_fold_count integer NOT NULL DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS rolling_validation_total_count integer,
                    ADD COLUMN IF NOT EXISTS rolling_matched_validation_count integer,
                    ADD COLUMN IF NOT EXISTS rolling_coverage double precision,
                    ADD COLUMN IF NOT EXISTS rolling_mae double precision,
                    ADD COLUMN IF NOT EXISTS rolling_rmse double precision,
                    ADD COLUMN IF NOT EXISTS rolling_bias double precision,
                    ADD COLUMN IF NOT EXISTS rolling_wape double precision
                """
            )
        )


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
