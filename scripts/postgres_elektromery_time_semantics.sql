-- Add canonical UTC time metadata for PostgreSQL elektromery measurements.
--
-- MS SQL source tables are intentionally not touched. This migration only
-- extends and backfills PostgreSQL tables.

BEGIN;

ALTER TABLE monitoring."Mereni_elektromery_vse"
    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20);

ALTER TABLE dbo."Mereni_elektromery_BINARY"
    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20);

ALTER TABLE dbo."Mereni_elektromery_OTE"
    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20);

ALTER TABLE dbo.elektromery_binary_source_configs
    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40) NOT NULL DEFAULT 'FIXED_OFFSET',
    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64) NOT NULL DEFAULT '+01:00',
    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20) NOT NULL DEFAULT 'start',
    ADD COLUMN IF NOT EXISTS time_fold INTEGER;

UPDATE dbo.elektromery_binary_source_configs
SET
    time_basis = 'FIXED_OFFSET',
    source_timezone = '+01:00',
    source_utc_offset_minutes = 60,
    timestamp_position = 'start',
    time_fold = NULL,
    updated_at = now()
WHERE time_basis IS DISTINCT FROM 'FIXED_OFFSET'
   OR source_timezone IS DISTINCT FROM '+01:00'
   OR source_utc_offset_minutes IS DISTINCT FROM 60
   OR timestamp_position IS DISTINCT FROM 'start'
   OR time_fold IS NOT NULL;

UPDATE dbo."Mereni_elektromery_BINARY"
SET
    source_date = date,
    time_utc = (date - INTERVAL '60 minutes') AT TIME ZONE 'UTC',
    time_basis = 'FIXED_OFFSET',
    source_timezone = '+01:00',
    source_utc_offset_minutes = 60,
    time_fold = NULL,
    timestamp_position = 'start'
WHERE source_date IS DISTINCT FROM date
   OR time_utc IS DISTINCT FROM ((date - INTERVAL '60 minutes') AT TIME ZONE 'UTC')
   OR time_basis IS DISTINCT FROM 'FIXED_OFFSET'
   OR source_timezone IS DISTINCT FROM '+01:00'
   OR source_utc_offset_minutes IS DISTINCT FROM 60
   OR time_fold IS NOT NULL
   OR timestamp_position IS DISTINCT FROM 'start';

UPDATE dbo."Mereni_elektromery_OTE"
SET
    source_date = date,
    time_utc = date AT TIME ZONE 'Europe/Prague',
    time_basis = 'EUROPE_PRAGUE_CIVIL',
    source_timezone = 'Europe/Prague',
    source_utc_offset_minutes = (
        EXTRACT(EPOCH FROM ((date AT TIME ZONE 'UTC') - (date AT TIME ZONE 'Europe/Prague'))) / 60
    )::integer,
    time_fold = NULL,
    timestamp_position = 'start'
WHERE source_date IS DISTINCT FROM date
   OR time_utc IS DISTINCT FROM (date AT TIME ZONE 'Europe/Prague')
   OR time_basis IS DISTINCT FROM 'EUROPE_PRAGUE_CIVIL'
   OR source_timezone IS DISTINCT FROM 'Europe/Prague'
   OR source_utc_offset_minutes IS DISTINCT FROM (
        EXTRACT(EPOCH FROM ((date AT TIME ZONE 'UTC') - (date AT TIME ZONE 'Europe/Prague'))) / 60
    )::integer
   OR time_fold IS NOT NULL
   OR timestamp_position IS DISTINCT FROM 'start';

UPDATE monitoring."Mereni_elektromery_vse"
SET
    source_date = date,
    time_utc = (date - INTERVAL '60 minutes') AT TIME ZONE 'UTC',
    time_basis = 'FIXED_OFFSET',
    source_timezone = '+01:00',
    source_utc_offset_minutes = 60,
    time_fold = NULL,
    timestamp_position = 'start'
WHERE zdroj LIKE 'BINARY_%'
  AND (
    source_date IS DISTINCT FROM date
    OR time_utc IS DISTINCT FROM ((date - INTERVAL '60 minutes') AT TIME ZONE 'UTC')
    OR time_basis IS DISTINCT FROM 'FIXED_OFFSET'
    OR source_timezone IS DISTINCT FROM '+01:00'
    OR source_utc_offset_minutes IS DISTINCT FROM 60
    OR time_fold IS NOT NULL
    OR timestamp_position IS DISTINCT FROM 'start'
  );

UPDATE monitoring."Mereni_elektromery_vse"
SET
    source_date = date,
    time_utc = date AT TIME ZONE 'Europe/Prague',
    time_basis = 'EUROPE_PRAGUE_CIVIL',
    source_timezone = 'Europe/Prague',
    source_utc_offset_minutes = (
        EXTRACT(EPOCH FROM ((date AT TIME ZONE 'UTC') - (date AT TIME ZONE 'Europe/Prague'))) / 60
    )::integer,
    time_fold = NULL,
    timestamp_position = CASE WHEN zdroj = 'SOFTLINK' THEN 'instant' ELSE 'start' END
WHERE zdroj IN ('OTE', 'SOFTLINK')
  AND (
    source_date IS DISTINCT FROM date
    OR time_utc IS DISTINCT FROM (date AT TIME ZONE 'Europe/Prague')
    OR time_basis IS DISTINCT FROM 'EUROPE_PRAGUE_CIVIL'
    OR source_timezone IS DISTINCT FROM 'Europe/Prague'
    OR source_utc_offset_minutes IS DISTINCT FROM (
        EXTRACT(EPOCH FROM ((date AT TIME ZONE 'UTC') - (date AT TIME ZONE 'Europe/Prague'))) / 60
    )::integer
    OR time_fold IS NOT NULL
    OR timestamp_position IS DISTINCT FROM CASE WHEN zdroj = 'SOFTLINK' THEN 'instant' ELSE 'start' END
  );

CREATE INDEX IF NOT EXISTS ix_ele_vse_time_utc
ON monitoring."Mereni_elektromery_vse" (time_utc);

CREATE INDEX IF NOT EXISTS ix_ele_vse_ident_time_utc
ON monitoring."Mereni_elektromery_vse" (identifikace, time_utc);

CREATE INDEX IF NOT EXISTS ix_ele_binary_time_utc
ON dbo."Mereni_elektromery_BINARY" (time_utc);

CREATE INDEX IF NOT EXISTS ix_ele_ote_time_utc
ON dbo."Mereni_elektromery_OTE" (time_utc);

COMMIT;
