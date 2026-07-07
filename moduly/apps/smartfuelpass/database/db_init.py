from __future__ import annotations

from sqlalchemy import text

from core.db.connect import ENGINE_PG
from moduly.apps.smartfuelpass.database.models import Base


def ensure_smartfuelpass_tables() -> None:
    with ENGINE_PG.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))

    Base.metadata.create_all(bind=ENGINE_PG)

    with ENGINE_PG.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE monitoring.smartfuelpass_relace
                    ADD COLUMN IF NOT EXISTS connector_id VARCHAR(128),
                    ADD COLUMN IF NOT EXISTS source_started_at TIMESTAMP WITHOUT TIME ZONE,
                    ADD COLUMN IF NOT EXISTS source_ended_at TIMESTAMP WITHOUT TIME ZONE,
                    ADD COLUMN IF NOT EXISTS started_at_utc TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS ended_at_utc TIMESTAMP WITH TIME ZONE,
                    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
                    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
                    ADD COLUMN IF NOT EXISTS started_utc_offset_minutes INTEGER,
                    ADD COLUMN IF NOT EXISTS ended_utc_offset_minutes INTEGER,
                    ADD COLUMN IF NOT EXISTS started_time_fold INTEGER,
                    ADD COLUMN IF NOT EXISTS ended_time_fold INTEGER,
                    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20)
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE monitoring.smartfuelpass_relace
                SET
                    source_started_at = started_at,
                    source_ended_at = ended_at,
                    started_at_utc = started_at AT TIME ZONE 'Europe/Prague',
                    ended_at_utc = ended_at AT TIME ZONE 'Europe/Prague',
                    time_basis = 'EUROPE_PRAGUE_CIVIL',
                    source_timezone = 'Europe/Prague',
                    started_utc_offset_minutes = (
                        EXTRACT(EPOCH FROM ((started_at AT TIME ZONE 'UTC') - (started_at AT TIME ZONE 'Europe/Prague'))) / 60
                    )::integer,
                    ended_utc_offset_minutes = (
                        EXTRACT(EPOCH FROM ((ended_at AT TIME ZONE 'UTC') - (ended_at AT TIME ZONE 'Europe/Prague'))) / 60
                    )::integer,
                    started_time_fold = NULL,
                    ended_time_fold = NULL,
                    timestamp_position = 'interval'
                WHERE source_started_at IS DISTINCT FROM started_at
                   OR source_ended_at IS DISTINCT FROM ended_at
                   OR started_at_utc IS DISTINCT FROM (started_at AT TIME ZONE 'Europe/Prague')
                   OR ended_at_utc IS DISTINCT FROM (ended_at AT TIME ZONE 'Europe/Prague')
                   OR time_basis IS DISTINCT FROM 'EUROPE_PRAGUE_CIVIL'
                   OR source_timezone IS DISTINCT FROM 'Europe/Prague'
                   OR started_utc_offset_minutes IS DISTINCT FROM (
                        EXTRACT(EPOCH FROM ((started_at AT TIME ZONE 'UTC') - (started_at AT TIME ZONE 'Europe/Prague'))) / 60
                   )::integer
                   OR ended_utc_offset_minutes IS DISTINCT FROM (
                        EXTRACT(EPOCH FROM ((ended_at AT TIME ZONE 'UTC') - (ended_at AT TIME ZONE 'Europe/Prague'))) / 60
                   )::integer
                   OR started_time_fold IS NOT NULL
                   OR ended_time_fold IS NOT NULL
                   OR timestamp_position IS DISTINCT FROM 'interval'
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_smartfuelpass_relace_started_at_utc
                ON monitoring.smartfuelpass_relace (started_at_utc)
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_smartfuelpass_relace_ended_at_utc
                ON monitoring.smartfuelpass_relace (ended_at_utc)
                """
            )
        )
