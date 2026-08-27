BEGIN;

ALTER TABLE evidence."OPTICKÉ VANY"
    ADD COLUMN IF NOT EXISTS "budova" character varying,
    ADD COLUMN IF NOT EXISTS "patro" character varying,
    ADD COLUMN IF NOT EXISTS "místnost" character varying;

CREATE INDEX IF NOT EXISTS idx_opticke_vany_rack
    ON evidence."OPTICKÉ VANY" ("rack");

CREATE OR REPLACE FUNCTION evidence.sync_opticke_vany_location_from_rack()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW."rack" IS NULL OR btrim(NEW."rack"::text) = '' THEN
        NEW."budova" := NULL;
        NEW."patro" := NULL;
        NEW."místnost" := NULL;
        RETURN NEW;
    END IF;

    SELECT
        r."budova",
        r."patro",
        r."místnost"
    INTO
        NEW."budova",
        NEW."patro",
        NEW."místnost"
    FROM evidence."RACKY" AS r
    WHERE r."označení" = NEW."rack";

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_opticke_vany_sync_location_from_rack
    ON evidence."OPTICKÉ VANY";

CREATE TRIGGER trg_opticke_vany_sync_location_from_rack
BEFORE INSERT OR UPDATE OF "rack"
ON evidence."OPTICKÉ VANY"
FOR EACH ROW
EXECUTE FUNCTION evidence.sync_opticke_vany_location_from_rack();

CREATE OR REPLACE FUNCTION evidence.propagate_racky_location_to_opticke_vany()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE evidence."OPTICKÉ VANY" AS ov
    SET
        "budova" = NEW."budova",
        "patro" = NEW."patro",
        "místnost" = NEW."místnost"
    WHERE ov."rack" = NEW."označení"
      AND (
          ov."budova" IS DISTINCT FROM NEW."budova"
          OR ov."patro" IS DISTINCT FROM NEW."patro"
          OR ov."místnost" IS DISTINCT FROM NEW."místnost"
      );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_racky_propagate_opticke_vany_location
    ON evidence."RACKY";

CREATE TRIGGER trg_racky_propagate_opticke_vany_location
AFTER UPDATE OF "budova", "patro", "místnost"
ON evidence."RACKY"
FOR EACH ROW
EXECUTE FUNCTION evidence.propagate_racky_location_to_opticke_vany();

UPDATE evidence."OPTICKÉ VANY" AS ov
SET
    "budova" = r."budova",
    "patro" = r."patro",
    "místnost" = r."místnost"
FROM evidence."RACKY" AS r
WHERE r."označení" = ov."rack"
  AND (
      ov."budova" IS DISTINCT FROM r."budova"
      OR ov."patro" IS DISTINCT FROM r."patro"
      OR ov."místnost" IS DISTINCT FROM r."místnost"
  );

COMMIT;
