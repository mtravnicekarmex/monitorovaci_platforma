ALTER TABLE dashboard."Map_Layers"
    ADD COLUMN IF NOT EXISTS map_labels_default_visible BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE dashboard."Map_Layers"
SET map_labels_default_visible = TRUE
WHERE map_labels_default_visible IS NULL;
