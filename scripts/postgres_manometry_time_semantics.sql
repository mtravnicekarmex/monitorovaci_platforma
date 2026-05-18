BEGIN;

CREATE SCHEMA IF NOT EXISTS monitoring;

CREATE TABLE IF NOT EXISTS monitoring."Mereni_manometry_vse" (
    id BIGSERIAL PRIMARY KEY,
    source_recid BIGINT,
    identifikace VARCHAR(250) NOT NULL,
    seriove_cislo VARCHAR(250),
    date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    source_date TIMESTAMP WITHOUT TIME ZONE,
    time_utc TIMESTAMP WITH TIME ZONE,
    time_basis VARCHAR(40),
    source_timezone VARCHAR(64),
    source_utc_offset_minutes INTEGER,
    time_fold INTEGER,
    timestamp_position VARCHAR(20),
    hodnota DOUBLE PRECISION NOT NULL,
    platne BOOLEAN NOT NULL DEFAULT TRUE,
    zdroj VARCHAR(20) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

ALTER TABLE monitoring."Mereni_manometry_vse"
    ADD COLUMN IF NOT EXISTS source_date TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_utc TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS time_basis VARCHAR(40),
    ADD COLUMN IF NOT EXISTS source_timezone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS source_utc_offset_minutes INTEGER,
    ADD COLUMN IF NOT EXISTS time_fold INTEGER,
    ADD COLUMN IF NOT EXISTS timestamp_position VARCHAR(20);

CREATE UNIQUE INDEX IF NOT EXISTS uq_manometry_ident_date_zdroj
    ON monitoring."Mereni_manometry_vse" (identifikace, date, zdroj);

CREATE UNIQUE INDEX IF NOT EXISTS uq_manometry_source_recid_zdroj
    ON monitoring."Mereni_manometry_vse" (source_recid, zdroj);

CREATE INDEX IF NOT EXISTS ix_Mereni_manometry_vse_source_recid
    ON monitoring."Mereni_manometry_vse" (source_recid);

CREATE INDEX IF NOT EXISTS ix_manometry_ident_date_desc
    ON monitoring."Mereni_manometry_vse" (identifikace, date);

CREATE INDEX IF NOT EXISTS ix_manometry_date_desc
    ON monitoring."Mereni_manometry_vse" (date);

CREATE INDEX IF NOT EXISTS ix_manometry_vse_time_utc
    ON monitoring."Mereni_manometry_vse" (time_utc);

CREATE INDEX IF NOT EXISTS ix_manometry_vse_ident_time_utc
    ON monitoring."Mereni_manometry_vse" (identifikace, time_utc);

CREATE TABLE IF NOT EXISTS monitoring.manometry_import_state (
    zdroj VARCHAR(20) PRIMARY KEY,
    last_source_recid BIGINT NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
);

COMMIT;
