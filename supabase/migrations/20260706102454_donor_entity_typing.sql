-- Migration 123: Donor entity typing (S28.2)
-- Adds entity_type and entity_slug columns to donors table.
-- entity_type: person | union | corporation | committee | other_org
-- entity_slug: URL-safe slug for entity profile pages (S28.3-S28.6)

-- Column: entity_type
ALTER TABLE donors ADD COLUMN IF NOT EXISTS entity_type VARCHAR(20);
COMMENT ON COLUMN donors.entity_type IS 'person | union | corporation | committee | other_org — S28.2 entity typing';

-- Column: entity_slug (for profile page URLs)
ALTER TABLE donors ADD COLUMN IF NOT EXISTS entity_slug VARCHAR(400);
COMMENT ON COLUMN donors.entity_slug IS 'URL-safe slug for entity profile pages (S28.3-S28.6)';

-- Index: entity_type for filtering
CREATE INDEX IF NOT EXISTS idx_donors_entity_type ON donors(entity_type);

-- Index: entity_slug for profile lookups
CREATE INDEX IF NOT EXISTS idx_donors_entity_slug ON donors(entity_slug);
