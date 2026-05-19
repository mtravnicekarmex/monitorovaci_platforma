-- Backfill missing canonical UTC time metadata for PostgreSQL water and gas
-- measurements inserted after the original time semantics migration.
--
-- MS SQL source tables are intentionally not touched. This migration only
-- updates PostgreSQL monitoring rows that are missing one or more canonical
-- time metadata columns and records old/new values for rollback.

BEGIN;

CREATE TABLE IF NOT EXISTS monitoring.time_semantics_missing_backfill_audit (
    repair_batch TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    measurement_table VARCHAR(80) NOT NULL,
    row_id INTEGER NOT NULL,
    identifikace VARCHAR(250),
    zdroj VARCHAR(20),
    date TIMESTAMP WITHOUT TIME ZONE,
    old_source_date TIMESTAMP WITHOUT TIME ZONE,
    old_time_utc TIMESTAMP WITH TIME ZONE,
    old_time_basis VARCHAR(40),
    old_source_timezone VARCHAR(64),
    old_source_utc_offset_minutes INTEGER,
    old_time_fold INTEGER,
    old_timestamp_position VARCHAR(20),
    new_source_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    new_time_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    new_time_basis VARCHAR(40) NOT NULL,
    new_source_timezone VARCHAR(64) NOT NULL,
    new_source_utc_offset_minutes INTEGER,
    new_time_fold INTEGER,
    new_timestamp_position VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    PRIMARY KEY (repair_batch, measurement_table, row_id)
);

WITH candidates AS (
    SELECT
        TIMESTAMP '2026-05-18 15:00:00' AS repair_batch,
        'Mereni_vodomery_vse'::varchar(80) AS measurement_table,
        id AS row_id,
        identifikace,
        zdroj,
        date,
        source_date AS old_source_date,
        time_utc AS old_time_utc,
        time_basis AS old_time_basis,
        source_timezone AS old_source_timezone,
        source_utc_offset_minutes AS old_source_utc_offset_minutes,
        time_fold AS old_time_fold,
        timestamp_position AS old_timestamp_position,
        date AS new_source_date,
        date AT TIME ZONE 'Europe/Prague' AS new_time_utc,
        'EUROPE_PRAGUE_CIVIL'::varchar(40) AS new_time_basis,
        'Europe/Prague'::varchar(64) AS new_source_timezone,
        (
            EXTRACT(EPOCH FROM ((date AT TIME ZONE 'UTC') - (date AT TIME ZONE 'Europe/Prague'))) / 60
        )::integer AS new_source_utc_offset_minutes,
        NULL::integer AS new_time_fold,
        'instant'::varchar(20) AS new_timestamp_position
    FROM monitoring."Mereni_vodomery_vse"
    WHERE date IS NOT NULL
      AND (
          source_date IS NULL
          OR time_utc IS NULL
          OR time_basis IS NULL
          OR source_timezone IS NULL
          OR timestamp_position IS NULL
      )
)
INSERT INTO monitoring.time_semantics_missing_backfill_audit (
    repair_batch,
    measurement_table,
    row_id,
    identifikace,
    zdroj,
    date,
    old_source_date,
    old_time_utc,
    old_time_basis,
    old_source_timezone,
    old_source_utc_offset_minutes,
    old_time_fold,
    old_timestamp_position,
    new_source_date,
    new_time_utc,
    new_time_basis,
    new_source_timezone,
    new_source_utc_offset_minutes,
    new_time_fold,
    new_timestamp_position
)
SELECT
    repair_batch,
    measurement_table,
    row_id,
    identifikace,
    zdroj,
    date,
    old_source_date,
    old_time_utc,
    old_time_basis,
    old_source_timezone,
    old_source_utc_offset_minutes,
    old_time_fold,
    old_timestamp_position,
    new_source_date,
    new_time_utc,
    new_time_basis,
    new_source_timezone,
    new_source_utc_offset_minutes,
    new_time_fold,
    new_timestamp_position
FROM candidates
ON CONFLICT (repair_batch, measurement_table, row_id) DO NOTHING;

WITH candidates AS (
    SELECT
        TIMESTAMP '2026-05-18 15:00:00' AS repair_batch,
        'Mereni_plynomery_vse'::varchar(80) AS measurement_table,
        id AS row_id,
        identifikace,
        zdroj,
        date,
        source_date AS old_source_date,
        time_utc AS old_time_utc,
        time_basis AS old_time_basis,
        source_timezone AS old_source_timezone,
        source_utc_offset_minutes AS old_source_utc_offset_minutes,
        time_fold AS old_time_fold,
        timestamp_position AS old_timestamp_position,
        date AS new_source_date,
        date AT TIME ZONE 'Europe/Prague' AS new_time_utc,
        'EUROPE_PRAGUE_CIVIL'::varchar(40) AS new_time_basis,
        'Europe/Prague'::varchar(64) AS new_source_timezone,
        (
            EXTRACT(EPOCH FROM ((date AT TIME ZONE 'UTC') - (date AT TIME ZONE 'Europe/Prague'))) / 60
        )::integer AS new_source_utc_offset_minutes,
        NULL::integer AS new_time_fold,
        'instant'::varchar(20) AS new_timestamp_position
    FROM monitoring."Mereni_plynomery_vse"
    WHERE date IS NOT NULL
      AND (
          source_date IS NULL
          OR time_utc IS NULL
          OR time_basis IS NULL
          OR source_timezone IS NULL
          OR timestamp_position IS NULL
      )
)
INSERT INTO monitoring.time_semantics_missing_backfill_audit (
    repair_batch,
    measurement_table,
    row_id,
    identifikace,
    zdroj,
    date,
    old_source_date,
    old_time_utc,
    old_time_basis,
    old_source_timezone,
    old_source_utc_offset_minutes,
    old_time_fold,
    old_timestamp_position,
    new_source_date,
    new_time_utc,
    new_time_basis,
    new_source_timezone,
    new_source_utc_offset_minutes,
    new_time_fold,
    new_timestamp_position
)
SELECT
    repair_batch,
    measurement_table,
    row_id,
    identifikace,
    zdroj,
    date,
    old_source_date,
    old_time_utc,
    old_time_basis,
    old_source_timezone,
    old_source_utc_offset_minutes,
    old_time_fold,
    old_timestamp_position,
    new_source_date,
    new_time_utc,
    new_time_basis,
    new_source_timezone,
    new_source_utc_offset_minutes,
    new_time_fold,
    new_timestamp_position
FROM candidates
ON CONFLICT (repair_batch, measurement_table, row_id) DO NOTHING;

UPDATE monitoring."Mereni_vodomery_vse" AS measurement
SET
    source_date = audit.new_source_date,
    time_utc = audit.new_time_utc,
    time_basis = audit.new_time_basis,
    source_timezone = audit.new_source_timezone,
    source_utc_offset_minutes = audit.new_source_utc_offset_minutes,
    time_fold = audit.new_time_fold,
    timestamp_position = audit.new_timestamp_position
FROM monitoring.time_semantics_missing_backfill_audit AS audit
WHERE audit.repair_batch = TIMESTAMP '2026-05-18 15:00:00'
  AND audit.measurement_table = 'Mereni_vodomery_vse'
  AND audit.row_id = measurement.id;

UPDATE monitoring."Mereni_plynomery_vse" AS measurement
SET
    source_date = audit.new_source_date,
    time_utc = audit.new_time_utc,
    time_basis = audit.new_time_basis,
    source_timezone = audit.new_source_timezone,
    source_utc_offset_minutes = audit.new_source_utc_offset_minutes,
    time_fold = audit.new_time_fold,
    timestamp_position = audit.new_timestamp_position
FROM monitoring.time_semantics_missing_backfill_audit AS audit
WHERE audit.repair_batch = TIMESTAMP '2026-05-18 15:00:00'
  AND audit.measurement_table = 'Mereni_plynomery_vse'
  AND audit.row_id = measurement.id;

COMMIT;
