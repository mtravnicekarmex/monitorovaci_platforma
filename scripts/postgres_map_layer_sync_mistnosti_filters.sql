ALTER TABLE dashboard."Map_Layers"
    ADD COLUMN IF NOT EXISTS sync_mistnosti_filters BOOLEAN NOT NULL DEFAULT FALSE;

UPDATE dashboard."Map_Layers"
SET sync_mistnosti_filters = TRUE
WHERE layer_kind = 'device'
   OR lower(layer_id) IN ('vodovodni_potrubi', 'vodovodni_uzly', 'vzt');
