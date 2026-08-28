BEGIN;

ALTER TABLE evidence."MAR CPU a převodníky"
    ADD COLUMN IF NOT EXISTS "budova" character varying,
    ADD COLUMN IF NOT EXISTS "patro" character varying,
    ADD COLUMN IF NOT EXISTS "místnost" character varying;

CREATE INDEX IF NOT EXISTS idx_mar_cpu_prevodniky_pripojeno_v_racku
    ON evidence."MAR CPU a převodníky" ("připojeno_v_racku");

CREATE OR REPLACE FUNCTION evidence.sync_mar_cpu_prevodniky_location_from_rack()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW."připojeno_v_racku" IS NULL OR btrim(NEW."připojeno_v_racku"::text) = '' THEN
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
    WHERE r."označení" = NEW."připojeno_v_racku";

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_mar_cpu_prevodniky_sync_location_from_rack
    ON evidence."MAR CPU a převodníky";

CREATE TRIGGER trg_mar_cpu_prevodniky_sync_location_from_rack
BEFORE INSERT OR UPDATE OF "připojeno_v_racku"
ON evidence."MAR CPU a převodníky"
FOR EACH ROW
EXECUTE FUNCTION evidence.sync_mar_cpu_prevodniky_location_from_rack();

CREATE OR REPLACE FUNCTION evidence.propagate_racky_location_to_mar_cpu_prevodniky()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE evidence."MAR CPU a převodníky" AS mar
    SET
        "budova" = NEW."budova",
        "patro" = NEW."patro",
        "místnost" = NEW."místnost"
    WHERE mar."připojeno_v_racku" = NEW."označení"
      AND (
          mar."budova" IS DISTINCT FROM NEW."budova"
          OR mar."patro" IS DISTINCT FROM NEW."patro"
          OR mar."místnost" IS DISTINCT FROM NEW."místnost"
      );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_racky_propagate_mar_cpu_prevodniky_location
    ON evidence."RACKY";

CREATE TRIGGER trg_racky_propagate_mar_cpu_prevodniky_location
AFTER UPDATE OF "budova", "patro", "místnost"
ON evidence."RACKY"
FOR EACH ROW
EXECUTE FUNCTION evidence.propagate_racky_location_to_mar_cpu_prevodniky();

UPDATE evidence."MAR CPU a převodníky" AS mar
SET
    "budova" = r."budova",
    "patro" = r."patro",
    "místnost" = r."místnost"
FROM evidence."RACKY" AS r
WHERE r."označení" = mar."připojeno_v_racku"
  AND (
      mar."budova" IS DISTINCT FROM r."budova"
      OR mar."patro" IS DISTINCT FROM r."patro"
      OR mar."místnost" IS DISTINCT FROM r."místnost"
  );

COMMIT;
