-- Roll back the historical vodomery gap terminal delta repair.
--
-- This restores only the values changed by:
--   scripts/postgres_vodomery_time_semantics.sql
--   monitoring.vodomery_gap_terminal_delta_repair_audit.repair_batch = '2026-05-15 14:10:00'

BEGIN;

UPDATE monitoring."Mereni_vodomery_vse" AS measurement
SET
    delta = audit.old_delta,
    nocni_odber = audit.old_nocni_odber
FROM monitoring.vodomery_gap_terminal_delta_repair_audit AS audit
WHERE audit.repair_batch = TIMESTAMP '2026-05-15 14:10:00'
  AND audit.row_id = measurement.id;

COMMIT;
