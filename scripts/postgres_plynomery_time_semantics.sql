-- Add canonical UTC time metadata for PostgreSQL plynomery measurements and
-- repair historical gap terminal deltas when present.
--
-- MS SQL source tables are intentionally not touched. This migration only
-- extends and backfills PostgreSQL monitoring data.

BEGIN;

ALTER TABLE monitoring."Mereni_plynomery_vse"
    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20);

UPDATE monitoring."Mereni_plynomery_vse"
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

CREATE TABLE IF NOT EXISTS monitoring.plynomery_gap_terminal_delta_repair_audit (
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

WITH terminal AS (
    SELECT
        measurement.id,
        measurement.identifikace,
        measurement.zdroj,
        measurement.date,
        measurement.objem,
        measurement.delta,
        measurement.nocni_odber
    FROM monitoring."Mereni_plynomery_vse" AS measurement
    WHERE measurement.platne = TRUE
      AND measurement.reset_detected = FALSE
      AND measurement.gap_detected = TRUE
      AND measurement.synthetic = FALSE
),
bounded AS (
    SELECT
        terminal.id,
        terminal.identifikace,
        terminal.zdroj,
        terminal.date,
        terminal.objem,
        terminal.delta,
        terminal.nocni_odber,
        previous_real.id AS prev_row_id,
        previous_real.date AS prev_date,
        previous_real.objem AS prev_objem,
        COALESCE(synthetic_totals.synthetic_delta, 0) AS synthetic_delta
    FROM terminal
    JOIN LATERAL (
        SELECT id, date, objem
        FROM monitoring."Mereni_plynomery_vse" AS previous_real
        WHERE previous_real.identifikace = terminal.identifikace
          AND previous_real.zdroj = terminal.zdroj
          AND previous_real.platne = TRUE
          AND previous_real.reset_detected = FALSE
          AND previous_real.synthetic = FALSE
          AND previous_real.date < terminal.date
        ORDER BY previous_real.date DESC, previous_real.id DESC
        LIMIT 1
    ) AS previous_real ON TRUE
    LEFT JOIN LATERAL (
        SELECT sum(synthetic.delta) AS synthetic_delta
        FROM monitoring."Mereni_plynomery_vse" AS synthetic
        WHERE synthetic.identifikace = terminal.identifikace
          AND synthetic.zdroj = terminal.zdroj
          AND synthetic.platne = TRUE
          AND synthetic.reset_detected = FALSE
          AND synthetic.synthetic = TRUE
          AND synthetic.date > previous_real.date
          AND synthetic.date < terminal.date
    ) AS synthetic_totals ON TRUE
),
calculated AS (
    SELECT
        *,
        GREATEST(ROUND((objem - prev_objem - synthetic_delta)::numeric, 6), 0)::double precision AS calculated_delta
    FROM bounded
    WHERE prev_objem IS NOT NULL
      AND objem >= prev_objem - 0.001
),
candidates AS (
    SELECT
        TIMESTAMP '2026-05-15 15:25:00' AS repair_batch,
        id AS row_id,
        identifikace,
        zdroj,
        date,
        prev_row_id,
        prev_date,
        prev_objem,
        objem AS current_objem,
        delta AS old_delta,
        calculated_delta AS new_delta,
        nocni_odber AS old_nocni_odber,
        (
            calculated_delta > 0.01
            AND (EXTRACT(HOUR FROM date)::integer >= 23 OR EXTRACT(HOUR FROM date)::integer < 5)
        ) AS new_nocni_odber
    FROM calculated
    WHERE delta IS NULL
       OR abs(delta - calculated_delta) > 0.001
)
INSERT INTO monitoring.plynomery_gap_terminal_delta_repair_audit (
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

UPDATE monitoring."Mereni_plynomery_vse" AS measurement
SET
    delta = audit.new_delta,
    nocni_odber = audit.new_nocni_odber
FROM monitoring.plynomery_gap_terminal_delta_repair_audit AS audit
WHERE audit.repair_batch = TIMESTAMP '2026-05-15 15:25:00'
  AND audit.row_id = measurement.id
  AND measurement.delta IS DISTINCT FROM audit.new_delta;

CREATE INDEX IF NOT EXISTS ix_plynomery_vse_time_utc
ON monitoring."Mereni_plynomery_vse" (time_utc);

CREATE INDEX IF NOT EXISTS ix_plynomery_vse_ident_time_utc
ON monitoring."Mereni_plynomery_vse" (identifikace, time_utc);

COMMIT;
