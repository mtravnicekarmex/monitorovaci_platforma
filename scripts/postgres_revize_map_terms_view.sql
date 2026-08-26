CREATE OR REPLACE VIEW revize.v_mapa_terminy_zarizeni AS
WITH sjednocene AS (
    SELECT
        'DVEŘE:' || v.fid::text AS map_id,
        'DVEŘE'::text AS typ_zarizeni,
        'Revize'::text AS typ_terminu,
        v.fid::bigint AS zarizeni_id,
        v.geom::geometry AS geom,
        v.budova::text AS budova,
        v.patro::text AS patro,
        v.mistnost_id::text AS mistnost_id,
        NULL::text AS mistnost,
        NULL::text AS identifikace,
        NULL::text AS seriove_cislo,
        NULL::text AS mbus,
        v.revize_id::integer AS revize_id,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize') AS termin_nazev,
        v.revize_datum::date AS datum_provedeni,
        v.revize_datum_platnosti::date AS datum_platnosti,
        v.revize_delka_platnosti::numeric(4, 2) AS delka_platnosti,
        NULL::text AS foto,
        NULL::timestamp AS posledni_mereni_datum,
        NULL::double precision AS posledni_stav,
        v.revize_poznamka::text AS poznamka
    FROM evidence."v_DVEŘE" v

    UNION ALL
    SELECT
        'HASÍCÍ PŘÍSTROJE:' || v.fid::text,
        'HASÍCÍ PŘÍSTROJE',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        v.foto::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_HASÍCÍ PŘÍSTROJE" v

    UNION ALL
    SELECT
        'HYDRANTY:' || v.fid::text,
        'HYDRANTY',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        v.foto::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_HYDRANTY" v

    UNION ALL
    SELECT
        'KLIMATIZACE:' || v.fid::text,
        'KLIMATIZACE',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        NULL::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_KLIMATIZACE" v

    UNION ALL
    SELECT
        'PLYNOVÁ ZAŘÍZENÍ:' || v.fid::text,
        'PLYNOVÁ ZAŘÍZENÍ',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        v.foto::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_PLYNOVÁ ZAŘÍZENÍ" v

    UNION ALL
    SELECT
        'RYCHLOBĚŽNÉ ROLETY:' || v.fid::text,
        'RYCHLOBĚŽNÉ ROLETY',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        v.foto::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_RYCHLOBĚŽNÉ ROLETY" v

    UNION ALL
    SELECT
        'SEKČNÍ VRATA:' || v.fid::text,
        'SEKČNÍ VRATA',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        v.foto::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_SEKČNÍ VRATA" v

    UNION ALL
    SELECT
        'SPALINOVÉ CESTY:' || v.fid::text,
        'SPALINOVÉ CESTY',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        NULL::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_SPALINOVÉ CESTY" v

    UNION ALL
    SELECT
        'TLAKOVÉ NÁDOBY:' || v.fid::text,
        'TLAKOVÉ NÁDOBY',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        v.foto::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_TLAKOVÉ NÁDOBY" v

    UNION ALL
    SELECT
        'VZT:' || v.fid::text,
        'VZT',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        NULL::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_VZT" v

    UNION ALL
    SELECT
        'VÝTAHY:' || v.fid::text,
        'VÝTAHY',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        NULL::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_VÝTAHY" v

    UNION ALL
    SELECT
        'ZDVIHACÍ PLOŠINY:' || v.fid::text,
        'ZDVIHACÍ PLOŠINY',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        NULL::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_ZDVIHACÍ PLOŠINY" v

    UNION ALL
    SELECT
        'ZÁVORY:' || v.fid::text,
        'ZÁVORY',
        'Revize',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        NULL::text,
        v.revize_id::integer,
        COALESCE(NULLIF(v.revize_nazev::text, ''), 'Revize'),
        v.revize_datum::date,
        v.revize_datum_platnosti::date,
        v.revize_delka_platnosti::numeric(4, 2),
        NULL::text,
        NULL::timestamp,
        NULL::double precision,
        v.revize_poznamka::text
    FROM evidence."v_ZÁVORY" v

    UNION ALL
    SELECT
        'VODOMĚRY:' || v.fid::text,
        'VODOMĚRY',
        'Metrologické ověření',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        NULL::text,
        v.identifikace::text,
        v.seriove_cislo::text,
        v."MBUS"::text,
        NULL::integer,
        'Platnost cejchu',
        NULL::date,
        v.platnost_cejchu::date,
        NULL::numeric(4, 2),
        v.foto::text,
        v.posledni_mereni_datum::timestamp,
        v.posledni_stav::double precision,
        v.poznamka_vodomery::text
    FROM evidence."v_VODOMĚRY" v

    UNION ALL
    SELECT
        'PLYNOMĚRY:' || v.fid::text,
        'PLYNOMĚRY',
        'Metrologické ověření',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        v.mistnost_id::text,
        v.mistnost::text,
        v.identifikace::text,
        v.seriove_cislo::text,
        v."MBUS"::text,
        NULL::integer,
        'Platnost cejchu',
        NULL::date,
        v.platnost_cejchu::date,
        NULL::numeric(4, 2),
        v.foto::text,
        v.posledni_mereni_datum::timestamp,
        v.posledni_stav::double precision,
        v.poznamka_plynomery::text
    FROM evidence."v_PLYNOMĚRY" v

    UNION ALL
    SELECT
        'KALORIMETRY:' || v.fid::text,
        'KALORIMETRY',
        'Metrologické ověření',
        v.fid::bigint,
        v.geom::geometry,
        v.budova::text,
        v.patro::text,
        NULL::text,
        v.mistnost::text,
        v.identifikace::text,
        v.seriove_cislo::text,
        v."MBUS"::text,
        NULL::integer,
        'Platnost cejchu',
        NULL::date,
        v.platnost_cejchu::date,
        NULL::numeric(4, 2),
        v.foto::text,
        v.posledni_mereni_datum::timestamp,
        v.posledni_stav::double precision,
        v.poznamka_kalorimetry::text
    FROM evidence."v_KALORIMETRY" v
)
SELECT
    map_id,
    typ_zarizeni,
    typ_terminu,
    zarizeni_id,
    ST_CurveToLine(geom)::geometry AS geom,
    budova,
    patro,
    mistnost_id,
    mistnost,
    identifikace,
    seriove_cislo,
    mbus,
    revize_id,
    termin_nazev,
    datum_provedeni,
    datum_platnosti,
    delka_platnosti,
    CASE
        WHEN datum_platnosti IS NULL THEN NULL
        ELSE (datum_platnosti - CURRENT_DATE)::integer
    END AS dnu_do_konce,
    CASE
        WHEN typ_terminu = 'Revize' AND revize_id IS NULL THEN 'Bez revize'
        WHEN datum_platnosti IS NULL THEN 'Bez data platnosti'
        WHEN datum_platnosti < CURRENT_DATE THEN 'Po platnosti'
        WHEN datum_platnosti <= CURRENT_DATE + 30 THEN 'Do 30 dnů'
        ELSE 'Platné'
    END AS stav_terminu,
    CASE
        WHEN typ_terminu = 'Revize' AND revize_id IS NULL THEN 0
        WHEN datum_platnosti IS NULL THEN 1
        WHEN datum_platnosti < CURRENT_DATE THEN 2
        WHEN datum_platnosti <= CURRENT_DATE + 30 THEN 3
        ELSE 4
    END AS stav_terminu_poradi,
    foto,
    posledni_mereni_datum,
    posledni_stav,
    poznamka
FROM sjednocene
WHERE geom IS NOT NULL;
