-- Apply scripts/postgres_revize_map_terms_view.sql first, then run this
-- metadata update when the map layer already exists.

WITH current_layer AS (
    SELECT
        layer_id,
        COALESCE(NULLIF(property_columns, '')::jsonb, '[]'::jsonb) AS property_columns_json,
        COALESCE(NULLIF(popup_columns, '')::jsonb, '[]'::jsonb) AS popup_columns_json,
        COALESCE(NULLIF(property_labels, '')::jsonb, '{}'::jsonb) AS property_labels_json
    FROM dashboard."Map_Layers"
    WHERE layer_id = 'revize_terminy_zarizeni'
)
UPDATE dashboard."Map_Layers" AS target
SET
    property_columns = (
        SELECT jsonb_agg(value ORDER BY ordinal)::text
        FROM (
            SELECT item.value, item.ordinal
            FROM current_layer AS layer,
                jsonb_array_elements_text(layer.property_columns_json) WITH ORDINALITY AS item(value, ordinal)
            UNION ALL
            SELECT 'servisni_smlouva', 100000
            WHERE NOT EXISTS (
                SELECT 1
                FROM current_layer AS layer,
                    jsonb_array_elements_text(layer.property_columns_json) AS item(value)
                WHERE item.value = 'servisni_smlouva'
            )
            UNION ALL
            SELECT 'revize_soubor', 100001
            WHERE NOT EXISTS (
                SELECT 1
                FROM current_layer AS layer,
                    jsonb_array_elements_text(layer.property_columns_json) AS item(value)
                WHERE item.value = 'revize_soubor'
            )
        ) AS merged
    ),
    popup_columns = (
        SELECT jsonb_agg(value ORDER BY ordinal)::text
        FROM (
            SELECT item.value, item.ordinal
            FROM current_layer AS layer,
                jsonb_array_elements_text(layer.popup_columns_json) WITH ORDINALITY AS item(value, ordinal)
            UNION ALL
            SELECT 'servisni_smlouva', 100000
            WHERE NOT EXISTS (
                SELECT 1
                FROM current_layer AS layer,
                    jsonb_array_elements_text(layer.popup_columns_json) AS item(value)
                WHERE item.value = 'servisni_smlouva'
            )
            UNION ALL
            SELECT 'revize_soubor', 100001
            WHERE NOT EXISTS (
                SELECT 1
                FROM current_layer AS layer,
                    jsonb_array_elements_text(layer.popup_columns_json) AS item(value)
                WHERE item.value = 'revize_soubor'
            )
        ) AS merged
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
