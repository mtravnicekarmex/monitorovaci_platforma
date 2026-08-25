ALTER TABLE dashboard."Map_Layers"
    ADD COLUMN IF NOT EXISTS property_labels TEXT NOT NULL DEFAULT '{}';
