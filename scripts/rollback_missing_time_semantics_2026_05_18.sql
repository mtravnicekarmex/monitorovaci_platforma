-- Roll back the missing time semantics backfill from
-- scripts/postgres_backfill_missing_time_semantics_2026_05_18.sql.
--
-- This restores only rows captured in
-- monitoring.time_semantics_missing_backfill_audit for the fixed repair batch.

BEGIN;

UPDATE monitoring."Mereni_vodomery_vse" AS measurement
SET
    source_date = audit.old_source_date,
    time_utc = audit.old_time_utc,
    time_basis = audit.old_time_basis,
    source_timezone = audit.old_source_timezone,
    source_utc_offset_minutes = audit.old_source_utc_offset_minutes,
    time_fold = audit.old_time_fold,
    timestamp_position = audit.old_timestamp_position
FROM monitoring.time_semantics_missing_backfill_audit AS audit
WHERE audit.repair_batch = TIMESTAMP '2026-05-18 15:00:00'
  AND audit.measurement_table = 'Mereni_vodomery_vse'
  AND audit.row_id = measurement.id;

UPDATE monitoring."Mereni_plynomery_vse" AS measurement
SET
    source_date = audit.old_source_date,
    time_utc = audit.old_time_utc,
    time_basis = audit.old_time_basis,
    source_timezone = audit.old_source_timezone,
    source_utc_offset_minutes = audit.old_source_utc_offset_minutes,
    time_fold = audit.old_time_fold,
    timestamp_position = audit.old_timestamp_position
FROM monitoring.time_semantics_missing_backfill_audit AS audit
WHERE audit.repair_batch = TIMESTAMP '2026-05-18 15:00:00'
  AND audit.measurement_table = 'Mereni_plynomery_vse'
  AND audit.row_id = measurement.id;

COMMIT;
