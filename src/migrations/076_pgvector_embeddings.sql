-- Migration 076: Activate Layer 3 — pgvector embeddings on content tables
--
-- Instead of a separate chunks table, we add embedding columns directly to
-- the four content tables. Each content unit (agenda item, meeting summary,
-- vote explainer, official bio) is already a compact semantic unit (200-500
-- tokens) that doesn't need chunking. Direct columns mean similarity queries
-- are single-table scans with no JOIN overhead.
--
-- Also adds:
-- - proceeding_type classification column on agenda_items
-- - search_queries analytics table for zero-result tracking

-- ── Enable pgvector extension ──────────────────────────────────
-- NOTE: Must also be toggled on in Supabase Dashboard > Database > Extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- Supabase installs extensions in the 'extensions' schema.
-- Add it to search_path so 'vector' type resolves without schema prefix.
SET search_path TO public, extensions;

-- ── Embedding columns on content tables ────────────────────────
-- Each gets: the vector itself, model provenance, generation timestamp.
-- HNSW indexes chosen over ivfflat: buildable on empty tables, better recall.

-- agenda_items (primary search corpus — ~15K items)
ALTER TABLE agenda_items
  ADD COLUMN IF NOT EXISTS embedding vector(1536),
  ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(50),
  ADD COLUMN IF NOT EXISTS embedding_generated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_agenda_items_embedding
  ON agenda_items USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- meetings (summary embeddings — ~240 meetings)
ALTER TABLE meetings
  ADD COLUMN IF NOT EXISTS embedding vector(1536),
  ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(50),
  ADD COLUMN IF NOT EXISTS embedding_generated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_meetings_embedding
  ON meetings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- officials (bio embeddings — ~50 officials)
ALTER TABLE officials
  ADD COLUMN IF NOT EXISTS embedding vector(1536),
  ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(50),
  ADD COLUMN IF NOT EXISTS embedding_generated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_officials_embedding
  ON officials USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- motions (vote explainer embeddings — ~8K motions)
ALTER TABLE motions
  ADD COLUMN IF NOT EXISTS embedding vector(1536),
  ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(50),
  ADD COLUMN IF NOT EXISTS embedding_generated_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_motions_embedding
  ON motions USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ── Proceeding type classification ─────────────────────────────
-- VARCHAR with CHECK (not ENUM) so values can be extended without migration.
ALTER TABLE agenda_items
  ADD COLUMN IF NOT EXISTS proceeding_type VARCHAR(30);

-- Validate values at DB level
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_proceeding_type'
  ) THEN
    ALTER TABLE agenda_items ADD CONSTRAINT chk_proceeding_type
      CHECK (proceeding_type IS NULL OR proceeding_type IN (
        'resolution', 'ordinance', 'contract', 'appropriation',
        'appointment', 'hearing', 'proclamation', 'report',
        'censure', 'appeal', 'consent', 'other'
      ));
  END IF;
END $$;

-- Partial index for non-null values (fast filtering by type)
CREATE INDEX IF NOT EXISTS idx_agenda_items_proceeding_type
  ON agenda_items (proceeding_type)
  WHERE proceeding_type IS NOT NULL;

-- ── Search query analytics ─────────────────────────────────────
-- No PII: client_hash is SHA-256 of IP, not raw IP.
CREATE TABLE IF NOT EXISTS search_queries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
  query_text TEXT NOT NULL,
  result_count INTEGER NOT NULL DEFAULT 0,
  result_type_filter TEXT,
  search_mode VARCHAR(20) NOT NULL DEFAULT 'keyword',
  client_hash VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for zero-result analytics (operator dashboard)
CREATE INDEX IF NOT EXISTS idx_search_queries_zero_results
  ON search_queries (city_fips, created_at DESC)
  WHERE result_count = 0;

-- Index for general analytics queries
CREATE INDEX IF NOT EXISTS idx_search_queries_created
  ON search_queries (city_fips, created_at DESC);

-- RLS: anon can INSERT (logging), only service_role can SELECT (analytics)
ALTER TABLE search_queries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS search_queries_anon_insert ON search_queries;
CREATE POLICY search_queries_anon_insert ON search_queries
  FOR INSERT TO anon WITH CHECK (true);

DROP POLICY IF EXISTS search_queries_service_read ON search_queries;
CREATE POLICY search_queries_service_read ON search_queries
  FOR ALL TO service_role USING (true);
