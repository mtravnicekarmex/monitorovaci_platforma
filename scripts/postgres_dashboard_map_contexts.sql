CREATE SCHEMA IF NOT EXISTS dashboard;

ALTER TABLE dashboard."Map_Layers"
    ADD COLUMN IF NOT EXISTS map_context VARCHAR(50) NOT NULL DEFAULT 'evidence';

ALTER TABLE dashboard."Map_Layers"
    ADD COLUMN IF NOT EXISTS document_columns TEXT NOT NULL DEFAULT '{}';

UPDATE dashboard."Map_Layers"
SET map_context = 'evidence'
WHERE map_context IS NULL
   OR btrim(map_context) = ''
   OR map_context NOT IN ('evidence', 'revize', 'pronajem', 'shared');

ALTER TABLE dashboard."Map_Layers"
    DROP CONSTRAINT IF EXISTS map_layers_map_context_check;

ALTER TABLE dashboard."Map_Layers"
    ADD CONSTRAINT map_layers_map_context_check
    CHECK (map_context IN ('evidence', 'revize', 'pronajem', 'shared'));

INSERT INTO dashboard."Map_Layers" (
    layer_id,
    title,
    layer_kind,
    map_context,
    source_schema,
    source_table,
    geometry_column,
    identifier_column,
    source_srid,
    target_srid,
    property_columns,
    property_aliases,
    property_labels,
    filter_columns,
    map_label_columns,
    popup_columns,
    document_columns,
    style,
    device_section_key,
    restrict_to_allowed_devices,
    map_enabled,
    default_visible,
    show_photo,
    is_active,
    draw_order
)
VALUES (
    'revize_terminy_zarizeni',
    'Terminy revizi a cejchu',
    'context',
    'revize',
    'revize',
    'v_mapa_terminy_zarizeni',
    'geom',
    'map_id',
    3857,
    4326,
    '["map_id","typ_zarizeni","typ_terminu","zarizeni_id","budova","patro","mistnost_id","mistnost","identifikace","seriove_cislo","mbus","revize_id","termin_nazev","datum_provedeni","datum_platnosti","delka_platnosti","dnu_do_konce","stav_terminu","stav_terminu_poradi","posledni_mereni_datum","posledni_stav","poznamka"]',
    '{}',
    '{"typ_zarizeni":"Typ zarizeni","typ_terminu":"Typ terminu","zarizeni_id":"ID zarizeni","budova":"Budova","patro":"Patro","mistnost_id":"Mistnost ID","mistnost":"Mistnost","identifikace":"Identifikace","seriove_cislo":"Seriove cislo","mbus":"MBUS","revize_id":"Revize ID","termin_nazev":"Nazev terminu","datum_provedeni":"Datum provedeni","datum_platnosti":"Datum platnosti","delka_platnosti":"Delka platnosti","servisni_smlouva":"Servisni smlouva","revize_soubor":"Soubor revize","dnu_do_konce":"Dnu do konce","stav_terminu":"Stav terminu","stav_terminu_poradi":"Poradi stavu","posledni_mereni_datum":"Posledni mereni","posledni_stav":"Posledni stav","poznamka":"Poznamka"}',
    '["stav_terminu","typ_zarizeni","typ_terminu","budova","patro","mistnost"]',
    '[]',
    '["typ_zarizeni","identifikace","stav_terminu","datum_platnosti","dnu_do_konce","typ_terminu","termin_nazev","budova","patro","mistnost","seriove_cislo","mbus","poznamka"]',
    '{"revize_soubor": "Zobrazit revizi", "servisni_smlouva": "Zobrazit servisni smlouvu"}',
    '{"color":"#4b5563","fillColor":"#9ca3af","weight":2,"fillOpacity":0.35,"radius":7,"conditionalStyle":{"rules":[{"name":"Bez revize","property":"stav_terminu","operator":"equals","value":"Bez revize","style":{"color":"#7c2d12","fillColor":"#9a3412","weight":3,"radius":7}},{"name":"Bez data platnosti","property":"stav_terminu","operator":"equals","value":"Bez data platnosti","style":{"color":"#6b7280","fillColor":"#9ca3af","weight":2,"radius":7}},{"name":"Po platnosti","property":"stav_terminu","operator":"equals","value":"Po platnosti","style":{"color":"#b91c1c","fillColor":"#ef4444","weight":4,"radius":8}},{"name":"Do 30 dnu","property":"stav_terminu","operator":"equals","value":"Do 30 dnů","style":{"color":"#c2410c","fillColor":"#f97316","weight":3,"radius":8}},{"name":"Platne","property":"stav_terminu","operator":"equals","value":"Platné","style":{"color":"#15803d","fillColor":"#22c55e","weight":2,"radius":7}}],"fallback":{"color":"#4b5563","fillColor":"#9ca3af","weight":2,"fillOpacity":0.35,"radius":7}}}',
    NULL,
    FALSE,
    TRUE,
    TRUE,
    FALSE,
    TRUE,
    200
)
ON CONFLICT (layer_id) DO UPDATE
SET
    map_context = EXCLUDED.map_context,
    updated_at = now()
WHERE dashboard."Map_Layers".map_context IS DISTINCT FROM EXCLUDED.map_context;

DO $$
DECLARE
    field_name text;
    current_values jsonb;
    updated_values jsonb;
BEGIN
    FOR field_name IN SELECT unnest(ARRAY['filter_columns', 'property_columns'])
    LOOP
        EXECUTE format(
            'SELECT COALESCE(NULLIF(%I, ''''), ''[]'')::jsonb FROM dashboard."Map_Layers" WHERE layer_id = %L',
            field_name,
            'revize_terminy_zarizeni'
        )
        INTO current_values;

        IF current_values IS NULL OR jsonb_typeof(current_values) <> 'array' THEN
            current_values := '[]'::jsonb;
        END IF;

        updated_values := current_values;
        IF NOT updated_values ? 'budova' THEN
            updated_values := updated_values || '["budova"]'::jsonb;
        END IF;
        IF NOT updated_values ? 'patro' THEN
            updated_values := updated_values || '["patro"]'::jsonb;
        END IF;

        IF updated_values IS DISTINCT FROM current_values THEN
            EXECUTE format(
                'UPDATE dashboard."Map_Layers" SET %I = $1::text, updated_at = now() WHERE layer_id = $2',
                field_name
            )
            USING updated_values, 'revize_terminy_zarizeni';
        END IF;
    END LOOP;
END
$$;
