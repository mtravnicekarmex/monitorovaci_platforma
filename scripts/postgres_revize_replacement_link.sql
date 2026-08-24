-- Adds an explicit replacement link for the Revize renewal workflow.
-- Apply once against PostgreSQL before running the dashboard/API code that
-- reads or writes revize.revize.nahrazena_revizi_id.

ALTER TABLE revize.revize
    ADD COLUMN IF NOT EXISTS nahrazena_revizi_id integer NULL;

DO $$
BEGIN
    ALTER TABLE revize.revize
        ADD CONSTRAINT fk_revize_nahrazena_revizi
        FOREIGN KEY (nahrazena_revizi_id)
        REFERENCES revize.revize(id);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$
BEGIN
    ALTER TABLE revize.revize
        ADD CONSTRAINT chk_revize_nahrazena_revizi_not_self
        CHECK (nahrazena_revizi_id IS NULL OR nahrazena_revizi_id <> id);
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_revize_nahrazena_revizi_id
    ON revize.revize(nahrazena_revizi_id);
