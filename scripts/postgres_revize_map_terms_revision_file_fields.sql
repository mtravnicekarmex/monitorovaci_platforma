-- Apply scripts/postgres_revize_map_terms_view.sql first.
-- This updates the existing revize map layer so revision/service-contract
-- file paths stay server-side and are exposed in popup only as PDF document links.

ALTER TABLE dashboard."Map_Layers"
    ADD COLUMN IF NOT EXISTS document_columns TEXT NOT NULL DEFAULT '{}';

WITH current_layer AS (
    SELECT
        layer_id,
        COALESCE(NULLIF(property_columns, '')::jsonb, '[]'::jsonb) AS property_columns_json,
        COALESCE(NULLIF(popup_columns, '')::jsonb, '[]'::jsonb) AS popup_columns_json,
        COALESCE(NULLIF(property_labels, '')::jsonb, '{}'::jsonb) AS property_labels_json,
        COALESCE(NULLIF(document_columns, '')::jsonb, '{}'::jsonb) AS document_columns_json
    FROM dashboard."Map_Layers"
    WHERE layer_id = 'revize_terminy_zarizeni'
)
UPDATE dashboard."Map_Layers" AS target
SET
    property_columns = (
        SELECT COALESCE(jsonb_agg(value ORDER BY ordinal), '[]'::jsonb)::text
        FROM (
            SELECT item.value, item.ordinal
            FROM current_layer AS layer,
                jsonb_array_elements_text(layer.property_columns_json) WITH ORDINALITY AS item(value, ordinal)
            WHERE item.value NOT IN ('servisni_smlouva', 'revize_soubor')
        ) AS filtered
    ),
    popup_columns = (
        SELECT COALESCE(jsonb_agg(value ORDER BY ordinal), '[]'::jsonb)::text
        FROM (
            SELECT item.value, item.ordinal
            FROM current_layer AS layer,
                jsonb_array_elements_text(layer.popup_columns_json) WITH ORDINALITY AS item(value, ordinal)
            WHERE item.value NOT IN ('servisni_smlouva', 'revize_soubor')
        ) AS filtered
    ),
    document_columns = (
        SELECT (
            layer.document_columns_json
            || '{"revize_soubor": "Zobrazit revizi", "servisni_smlouva": "Zobrazit servisni smlouvu"}'::jsonb
        )::text
        FROM current_layer AS layer
    ),
    property_labels = (
        SELECT (
            layer.property_labels_json
            || '{"servisni_smlouva": "Servisni smlouva", "revize_soubor": "Soubor revize"}'::jsonb
        )::text
        FROM current_layer AS layer
    ),
    updated_at = now()
FROM current_layer
WHERE target.layer_id = current_layer.layer_id;
