-- Migration 025: Add publication_tier to conflict_flags
-- Stores the scanner's tier assignment (1=public-ready, 2=operator review, 3=low confidence)
-- so the frontend can filter by tier instead of deriving from confidence scores.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'conflict_flags' AND column_name = 'publication_tier'
    ) THEN
        ALTER TABLE conflict_flags ADD COLUMN publication_tier SMALLINT;
    END IF;
END $$;

-- Index for tier-based queries (most common: "show me Tier 1 and 2 flags")
CREATE INDEX IF NOT EXISTS idx_flags_publication_tier
    ON conflict_flags(publication_tier)
    WHERE is_current = TRUE;

COMMENT ON COLUMN conflict_flags.publication_tier IS
    'Scanner-assigned tier: 1=public-ready, 2=operator review, 3=low confidence/internal';
