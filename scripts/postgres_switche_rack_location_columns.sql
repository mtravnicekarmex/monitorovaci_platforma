BEGIN;

ALTER TABLE evidence."SWITCHE"
    ADD COLUMN IF NOT EXISTS "budova" character varying,
    ADD COLUMN IF NOT EXISTS "patro" character varying,
    ADD COLUMN IF NOT EXISTS "místnost" character varying;

CREATE INDEX IF NOT EXISTS idx_switche_rack
    ON evidence."SWITCHE" ("rack");

CREATE OR REPLACE FUNCTION evidence.sync_switche_location_from_rack()
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

DROP TRIGGER IF EXISTS trg_switche_sync_location_from_rack
    ON evidence."SWITCHE";

CREATE TRIGGER trg_switche_sync_location_from_rack
BEFORE INSERT OR UPDATE OF "rack"
ON evidence."SWITCHE"
FOR EACH ROW
EXECUTE FUNCTION evidence.sync_switche_location_from_rack();

CREATE OR REPLACE FUNCTION evidence.propagate_racky_location_to_switche()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE evidence."SWITCHE" AS sw
    SET
        "budova" = NEW."budova",
        "patro" = NEW."patro",
        "místnost" = NEW."místnost"
    WHERE sw."rack" = NEW."označení"
      AND (
          sw."budova" IS DISTINCT FROM NEW."budova"
          OR sw."patro" IS DISTINCT FROM NEW."patro"
          OR sw."místnost" IS DISTINCT FROM NEW."místnost"
      );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_racky_propagate_switche_location
    ON evidence."RACKY";

CREATE TRIGGER trg_racky_propagate_switche_location
AFTER UPDATE OF "budova", "patro", "místnost"
ON evidence."RACKY"
FOR EACH ROW
EXECUTE FUNCTION evidence.propagate_racky_location_to_switche();

UPDATE evidence."SWITCHE" AS sw
SET
    "budova" = r."budova",
    "patro" = r."patro",
    "místnost" = r."místnost"
FROM evidence."RACKY" AS r
WHERE r."označení" = sw."rack"
  AND (
      sw."budova" IS DISTINCT FROM r."budova"
      OR sw."patro" IS DISTINCT FROM r."patro"
      OR sw."místnost" IS DISTINCT FROM r."místnost"
  );

COMMIT;
