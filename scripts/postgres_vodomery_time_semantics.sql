-- Add canonical UTC time metadata for PostgreSQL vodomery measurements and
-- repair historical gap terminal deltas.
--
-- MS SQL source tables are intentionally not touched. This migration only
-- extends and backfills PostgreSQL monitoring data.

BEGIN;

ALTER TABLE monitoring."Mereni_vodomery_vse"
    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20);

UPDATE monitoring."Mereni_vodomery_vse"
SET
    source_date = date,
    time_utc = date AT TIME ZONE 'Europe/Prague',
    time_basis = 'EUROPE_PRAGUE_CIVIL',
    source_timezone = 'Europe/Prague',
    source_utc_offset_minutes = (
        EXTRACT(EPOCH FROM ((date AT TIME ZONE 'UTC') - (date AT TIME ZONE 'Europe/Prague'))) / 60
    )::integer,
    time_fold = NULL,
    timestamp_position = 'instant'
WHERE source_date IS DISTINCT FROM date
   OR time_utc IS DISTINCT FROM (date AT TIME ZONE 'Europe/Prague')
   OR time_basis IS DISTINCT FROM 'EUROPE_PRAGUE_CIVIL'
   OR source_timezone IS DISTINCT FROM 'Europe/Prague'
   OR source_utc_offset_minutes IS DISTINCT FROM (
        EXTRACT(EPOCH FROM ((date AT TIME ZONE 'UTC') - (date AT TIME ZONE 'Europe/Prague'))) / 60
    )::integer
   OR time_fold IS NOT NULL
   OR timestamp_position IS DISTINCT FROM 'instant';

CREATE TABLE IF NOT EXISTS monitoring.vodomery_gap_terminal_delta_repair_audit (
    repair_batch TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    row_id INTEGER NOT NULL,
    identifikace VARCHAR(250) NOT NULL,
    zdroj VARCHAR(20) NOT NULL,
    date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    prev_row_id INTEGER,
    prev_date TIMESTAMP WITHOUT TIME ZONE,
    prev_objem DOUBLE PRECISION,
    current_objem DOUBLE PRECISION NOT NULL,
    old_delta DOUBLE PRECISION,
    new_delta DOUBLE PRECISION NOT NULL,
    old_nocni_odber BOOLEAN NOT NULL,
    new_nocni_odber BOOLEAN NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    PRIMARY KEY (repair_batch, row_id)
);

WITH ordered AS (
    SELECT
        measurement.id,
        measurement.identifikace,
        measurement.zdroj,
        measurement.date,
        measurement.objem,
        measurement.delta,
        measurement.nocni_odber,
        measurement.gap_detected,
        measurement.synthetic,
        lag(measurement.id) OVER (
            PARTITION BY measurement.identifikace, measurement.zdroj
            ORDER BY measurement.date, measurement.id
        ) AS prev_row_id,
        lag(measurement.date) OVER (
            PARTITION BY measurement.identifikace, measurement.zdroj
            ORDER BY measurement.date, measurement.id
        ) AS prev_date,
        lag(measurement.objem) OVER (
            PARTITION BY measurement.identifikace, measurement.zdroj
            ORDER BY measurement.date, measurement.id
        ) AS prev_objem
    FROM monitoring."Mereni_vodomery_vse" AS measurement
    WHERE measurement.platne = TRUE
      AND measurement.reset_detected = FALSE
),
candidates AS (
    SELECT
        TIMESTAMP '2026-05-15 14:10:00' AS repair_batch,
        id AS row_id,
        identifikace,
        zdroj,
        date,
        prev_row_id,
        prev_date,
        prev_objem,
        objem AS current_objem,
        delta AS old_delta,
        GREATEST(ROUND((objem - prev_objem)::numeric, 6), 0)::double precision AS new_delta,
        nocni_odber AS old_nocni_odber,
        (
            GREATEST(ROUND((objem - prev_objem)::numeric, 6), 0)::double precision > 0.01
            AND (EXTRACT(HOUR FROM date)::integer >= 23 OR EXTRACT(HOUR FROM date)::integer < 5)
        ) AS new_nocni_odber
    FROM ordered
    WHERE prev_objem IS NOT NULL
      AND gap_detected = TRUE
      AND synthetic = FALSE
      AND delta IS NULL
      AND objem >= prev_objem - 0.001
)
INSERT INTO monitoring.vodomery_gap_terminal_delta_repair_audit (
    repair_batch,
    row_id,
    identifikace,
    zdroj,
    date,
    prev_row_id,
    prev_date,
    prev_objem,
    current_objem,
    old_delta,
    new_delta,
    old_nocni_odber,
    new_nocni_odber
)
SELECT
    repair_batch,
    row_id,
    identifikace,
    zdroj,
    date,
    prev_row_id,
    prev_date,
    prev_objem,
    current_objem,
    old_delta,
    new_delta,
    old_nocni_odber,
    new_nocni_odber
FROM candidates
ON CONFLICT (repair_batch, row_id) DO NOTHING;

UPDATE monitoring."Mereni_vodomery_vse" AS measurement
SET
    delta = audit.new_delta,
    nocni_odber = audit.new_nocni_odber
FROM monitoring.vodomery_gap_terminal_delta_repair_audit AS audit
WHERE audit.repair_batch = TIMESTAMP '2026-05-15 14:10:00'
  AND audit.row_id = measurement.id
  AND measurement.delta IS DISTINCT FROM audit.new_delta;

CREATE INDEX IF NOT EXISTS ix_vodomery_vse_time_utc
ON monitoring."Mereni_vodomery_vse" (time_utc);

CREATE INDEX IF NOT EXISTS ix_vodomery_vse_ident_time_utc
ON monitoring."Mereni_vodomery_vse" (identifikace, time_utc);

COMMIT;
