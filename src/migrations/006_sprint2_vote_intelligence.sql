-- Sprint 2: Vote Intelligence
-- S2.1: Backfill ~58 agenda items to 'appointments' category
-- S2.3: Add bio columns to officials table
-- Idempotent: safe to run multiple times

-- ── S2.1: Reclassify appointment items ─────────────────────────

-- Items currently categorized as governance or personnel that are actually
-- board/commission appointments, reappointments, or vacancy actions.
UPDATE agenda_items
SET category = 'appointments'
WHERE category IN ('governance', 'personnel')
  AND (
    title ILIKE '%appoint%'
    OR title ILIKE '%reappoint%'
    OR title ILIKE '%commission%member%'
    OR title ILIKE '%board%member%'
    OR title ILIKE '%vacancy%'
    OR title ILIKE '%board%commission%'
  )
  AND category != 'appointments';

-- ── S2.3: Add bio columns to officials ─────────────────────────

ALTER TABLE officials ADD COLUMN IF NOT EXISTS bio_factual JSONB;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS bio_summary TEXT;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS bio_generated_at TIMESTAMPTZ;
ALTER TABLE officials ADD COLUMN IF NOT EXISTS bio_model VARCHAR(50);

-- Add comment for documentation
COMMENT ON COLUMN officials.bio_factual IS 'Layer 1: factual profile data derived from DB queries (JSON)';
COMMENT ON COLUMN officials.bio_summary IS 'Layer 2: AI-synthesized narrative summary (Graduated tier)';
COMMENT ON COLUMN officials.bio_generated_at IS 'Timestamp of last bio generation';
COMMENT ON COLUMN officials.bio_model IS 'Model used for Layer 2 generation (e.g. claude-sonnet-4-5-20250514)';
