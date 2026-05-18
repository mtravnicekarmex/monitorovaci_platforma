-- Roll back SmartFuelPass UTC interval metadata columns.
--
-- Original source columns started_at and ended_at are not changed by the
-- forward migration, so rollback only removes derived metadata.

BEGIN;

DROP INDEX IF EXISTS monitoring.ix_smartfuelpass_relace_started_at_utc;
DROP INDEX IF EXISTS monitoring.ix_smartfuelpass_relace_ended_at_utc;

ALTER TABLE monitoring.smartfuelpass_relace
    DROP COLUMN IF EXISTS source_started_at,
    DROP COLUMN IF EXISTS source_ended_at,
    DROP COLUMN IF EXISTS started_at_utc,
    DROP COLUMN IF EXISTS ended_at_utc,
    DROP COLUMN IF EXISTS time_basis,
    DROP COLUMN IF EXISTS source_timezone,
    DROP COLUMN IF EXISTS started_utc_offset_minutes,
    DROP COLUMN IF EXISTS ended_utc_offset_minutes,
    DROP COLUMN IF EXISTS started_time_fold,
    DROP COLUMN IF EXISTS ended_time_fold,
    DROP COLUMN IF EXISTS timestamp_position;

COMMIT;
