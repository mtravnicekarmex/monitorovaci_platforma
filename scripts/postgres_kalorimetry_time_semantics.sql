BEGIN;

CREATE SCHEMA IF NOT EXISTS monitoring;

CREATE TABLE IF NOT EXISTS monitoring."Mereni_kalorimetry_vse" (
    id BIGSERIAL PRIMARY KEY,
    source_recid BIGINT,
    identifikace VARCHAR(250) NOT NULL,
    seriove_cislo BIGINT,
    date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    source_date TIMESTAMP WITHOUT TIME ZONE,
    time_utc TIMESTAMP WITH TIME ZONE,
    time_basis VARCHAR(40),
    source_timezone VARCHAR(64),
    source_utc_offset_minutes INTEGER,
    time_fold INTEGER,
    timestamp_position VARCHAR(20),
    spotreba_energie DOUBLE PRECISION NOT NULL,
    objem DOUBLE PRECISION,
    delta DOUBLE PRECISION,
    interval_minutes INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    nocni_odber BOOLEAN NOT NULL DEFAULT FALSE,
    platne BOOLEAN NOT NULL DEFAULT TRUE,
    gap_detected BOOLEAN NOT NULL DEFAULT FALSE,
    synthetic BOOLEAN NOT NULL DEFAULT FALSE,
    zdroj VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    reset_detected BOOLEAN NOT NULL DEFAULT FALSE
);

ALTER TABLE monitoring."Mereni_kalorimetry_vse"
    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20);

CREATE UNIQUE INDEX IF NOT EXISTS uq_kalorimetry_ident_date_zdroj
    ON monitoring."Mereni_kalorimetry_vse" (identifikace, date, zdroj);

CREATE UNIQUE INDEX IF NOT EXISTS uq_kalorimetry_source_recid_zdroj
    ON monitoring."Mereni_kalorimetry_vse" (source_recid, zdroj);

CREATE INDEX IF NOT EXISTS ix_kalorimetry_ident_interval_slot
    ON monitoring."Mereni_kalorimetry_vse" (identifikace, interval_minutes, day_of_week, slot);

CREATE INDEX IF NOT EXISTS ix_kalorimetry_ident_date_desc
    ON monitoring."Mereni_kalorimetry_vse" (identifikace, date);

CREATE INDEX IF NOT EXISTS ix_kalorimetry_date_desc
    ON monitoring."Mereni_kalorimetry_vse" (date);

CREATE INDEX IF NOT EXISTS ix_kalorimetry_vse_time_utc
    ON monitoring."Mereni_kalorimetry_vse" (time_utc);

CREATE INDEX IF NOT EXISTS ix_kalorimetry_vse_ident_time_utc
    ON monitoring."Mereni_kalorimetry_vse" (identifikace, time_utc);

CREATE TABLE IF NOT EXISTS monitoring.kalorimetry_import_state (
    zdroj VARCHAR(20) PRIMARY KEY,
    last_source_recid BIGINT NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

COMMIT;
