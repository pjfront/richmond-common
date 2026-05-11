-- Migration 111: Move vector(1536) embeddings off content tables into sidecar tables.
--
-- Phase 2.10 of the 2026-05-09 re-architecture plan. The embedding columns were
-- adding ~6 KB per row to every `SELECT *` against agenda_items/meetings/
-- officials/motions, even when the caller didn't need them. Moving them to
-- *_embeddings sidecars (with FK + ON DELETE CASCADE) keeps Layer 3 in Layer 3
-- and stops bleeding it into Layer 2 list queries.
--
-- Safe to run on a DB with or without existing embedding rows. Embedding
-- generation has been failing repo-wide since OPENAI_API_KEY went unset
-- (see SessionStart health report), so in practice the base columns are
-- almost entirely NULL — the COPY step is a no-op. We do it anyway for
-- defense in depth.
--
-- Side effects:
--   - HNSW indexes move from base tables to sidecars (same parameters)
--   - search_hybrid() and find_similar_items() RPCs rewritten to JOIN sidecars

SET search_path TO public, extensions;

-- ── Sidecar tables ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agenda_items_embeddings (
  id UUID PRIMARY KEY REFERENCES agenda_items(id) ON DELETE CASCADE,
  embedding vector(1536) NOT NULL,
  embedding_model VARCHAR(50) NOT NULL,
  embedding_generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS meetings_embeddings (
  id UUID PRIMARY KEY REFERENCES meetings(id) ON DELETE CASCADE,
  embedding vector(1536) NOT NULL,
  embedding_model VARCHAR(50) NOT NULL,
  embedding_generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS officials_embeddings (
  id UUID PRIMARY KEY REFERENCES officials(id) ON DELETE CASCADE,
  embedding vector(1536) NOT NULL,
  embedding_model VARCHAR(50) NOT NULL,
  embedding_generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS motions_embeddings (
  id UUID PRIMARY KEY REFERENCES motions(id) ON DELETE CASCADE,
  embedding vector(1536) NOT NULL,
  embedding_model VARCHAR(50) NOT NULL,
  embedding_generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Copy any existing data (defensive — base columns may not even exist yet) ──

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'agenda_items' AND column_name = 'embedding'
  ) THEN
    INSERT INTO agenda_items_embeddings (id, embedding, embedding_model, embedding_generated_at)
    SELECT id, embedding, embedding_model, COALESCE(embedding_generated_at, NOW())
    FROM agenda_items
    WHERE embedding IS NOT NULL
    ON CONFLICT (id) DO NOTHING;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'meetings' AND column_name = 'embedding'
  ) THEN
    INSERT INTO meetings_embeddings (id, embedding, embedding_model, embedding_generated_at)
    SELECT id, embedding, embedding_model, COALESCE(embedding_generated_at, NOW())
    FROM meetings
    WHERE embedding IS NOT NULL
    ON CONFLICT (id) DO NOTHING;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'officials' AND column_name = 'embedding'
  ) THEN
    INSERT INTO officials_embeddings (id, embedding, embedding_model, embedding_generated_at)
    SELECT id, embedding, embedding_model, COALESCE(embedding_generated_at, NOW())
    FROM officials
    WHERE embedding IS NOT NULL
    ON CONFLICT (id) DO NOTHING;
  END IF;

  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'motions' AND column_name = 'embedding'
  ) THEN
    INSERT INTO motions_embeddings (id, embedding, embedding_model, embedding_generated_at)
    SELECT id, embedding, embedding_model, COALESCE(embedding_generated_at, NOW())
    FROM motions
    WHERE embedding IS NOT NULL
    ON CONFLICT (id) DO NOTHING;
  END IF;
END $$;

-- ── HNSW indexes on the sidecars ──────────────────────────────

CREATE INDEX IF NOT EXISTS idx_agenda_items_embeddings_hnsw
  ON agenda_items_embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_meetings_embeddings_hnsw
  ON meetings_embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_officials_embeddings_hnsw
  ON officials_embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_motions_embeddings_hnsw
  ON motions_embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ── Drop old HNSW indexes on base tables, then the columns themselves ──

DROP INDEX IF EXISTS idx_agenda_items_embedding;
DROP INDEX IF EXISTS idx_meetings_embedding;
DROP INDEX IF EXISTS idx_officials_embedding;
DROP INDEX IF EXISTS idx_motions_embedding;

ALTER TABLE agenda_items
  DROP COLUMN IF EXISTS embedding,
  DROP COLUMN IF EXISTS embedding_model,
  DROP COLUMN IF EXISTS embedding_generated_at;

ALTER TABLE meetings
  DROP COLUMN IF EXISTS embedding,
  DROP COLUMN IF EXISTS embedding_model,
  DROP COLUMN IF EXISTS embedding_generated_at;

ALTER TABLE officials
  DROP COLUMN IF EXISTS embedding,
  DROP COLUMN IF EXISTS embedding_model,
  DROP COLUMN IF EXISTS embedding_generated_at;

ALTER TABLE motions
  DROP COLUMN IF EXISTS embedding,
  DROP COLUMN IF EXISTS embedding_model,
  DROP COLUMN IF EXISTS embedding_generated_at;

-- ── RLS on sidecars: anon SELECT (Layer 3 must be readable from the public client) ──

ALTER TABLE agenda_items_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE officials_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE motions_embeddings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agenda_items_embeddings_anon_read ON agenda_items_embeddings;
CREATE POLICY agenda_items_embeddings_anon_read ON agenda_items_embeddings
  FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS meetings_embeddings_anon_read ON meetings_embeddings;
CREATE POLICY meetings_embeddings_anon_read ON meetings_embeddings
  FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS officials_embeddings_anon_read ON officials_embeddings;
CREATE POLICY officials_embeddings_anon_read ON officials_embeddings
  FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS motions_embeddings_anon_read ON motions_embeddings;
CREATE POLICY motions_embeddings_anon_read ON motions_embeddings
  FOR SELECT TO anon USING (true);

-- ── Rewrite RPCs to JOIN against sidecars ─────────────────────

-- search_hybrid: FTS + vector similarity via RRF. Vector arm now joins
-- *_embeddings instead of selecting from the base table.

DROP FUNCTION IF EXISTS search_hybrid(TEXT, vector, TEXT, TEXT, INT, INT);

CREATE OR REPLACE FUNCTION search_hybrid(
  p_query TEXT,
  p_query_embedding vector(1536) DEFAULT NULL,
  p_city_fips TEXT DEFAULT '0660620',
  p_result_type TEXT DEFAULT NULL,
  p_limit INT DEFAULT 20,
  p_offset INT DEFAULT 0
)
RETURNS TABLE (
  id UUID,
  result_type TEXT,
  title TEXT,
  snippet TEXT,
  url_path TEXT,
  relevance_score REAL,
  match_type TEXT,
  metadata JSONB
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  tsq tsquery;
  k CONSTANT INT := 60;  -- RRF constant
BEGIN
  tsq := plainto_tsquery('english', p_query);

  RETURN QUERY
  WITH
  fts_results AS (
    SELECT * FROM search_site(p_query, p_city_fips, p_result_type, 50, 0)
  ),
  fts_ranked AS (
    SELECT
      f.id, f.result_type, f.title, f.snippet, f.url_path,
      f.relevance_score, f.metadata,
      ROW_NUMBER() OVER (ORDER BY f.relevance_score DESC) AS fts_rank
    FROM fts_results f
  ),

  vec_results AS (
    SELECT * FROM (
      SELECT
        ai.id,
        'agenda_item'::TEXT AS result_type,
        ai.title,
        left(coalesce(ai.plain_language_summary, ai.description, ''), 160) AS snippet,
        '/meetings/' || ai.meeting_id AS url_path,
        (1 - (aie.embedding <=> p_query_embedding))::REAL AS sim_score,
        jsonb_build_object(
          'meeting_date', m.meeting_date,
          'category', ai.category,
          'item_number', ai.item_number,
          'topic_label', ai.topic_label
        ) AS metadata
      FROM agenda_items_embeddings aie
      JOIN agenda_items ai ON ai.id = aie.id
      JOIN meetings m ON m.id = ai.meeting_id
      WHERE p_query_embedding IS NOT NULL
        AND m.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'agenda_item')
      ORDER BY aie.embedding <=> p_query_embedding
      LIMIT 50
    ) ai_sub

    UNION ALL

    SELECT * FROM (
      SELECT
        mo.id,
        'vote_explainer'::TEXT,
        coalesce(ai.title, 'Motion on item ' || ai.item_number),
        left(coalesce(mo.vote_explainer, ''), 160),
        '/meetings/' || m.id,
        (1 - (moe.embedding <=> p_query_embedding))::REAL,
        jsonb_build_object(
          'meeting_date', m.meeting_date,
          'agenda_item_title', ai.title
        )
      FROM motions_embeddings moe
      JOIN motions mo ON mo.id = moe.id
      JOIN agenda_items ai ON ai.id = mo.agenda_item_id
      JOIN meetings m ON m.id = ai.meeting_id
      WHERE p_query_embedding IS NOT NULL
        AND m.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'vote_explainer')
      ORDER BY moe.embedding <=> p_query_embedding
      LIMIT 50
    ) mo_sub

    UNION ALL

    SELECT * FROM (
      SELECT
        o.id,
        'official'::TEXT,
        o.name,
        left(coalesce(o.bio_summary, ''), 160),
        '/council/' || lower(regexp_replace(regexp_replace(o.name, '\s+', '-', 'g'), '[^a-z0-9-]', '', 'g')),
        (1 - (oe.embedding <=> p_query_embedding))::REAL,
        jsonb_build_object('role', o.role, 'is_current', o.is_current)
      FROM officials_embeddings oe
      JOIN officials o ON o.id = oe.id
      WHERE p_query_embedding IS NOT NULL
        AND o.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'official')
      ORDER BY oe.embedding <=> p_query_embedding
      LIMIT 20
    ) o_sub

    UNION ALL

    SELECT * FROM (
      SELECT
        m.id,
        'meeting'::TEXT,
        initcap(coalesce(m.meeting_type, 'regular')) || ' Meeting — ' ||
          to_char(m.meeting_date, 'FMMonth DD, YYYY'),
        left(coalesce(m.meeting_summary, ''), 160),
        '/meetings/' || m.id,
        (1 - (me.embedding <=> p_query_embedding))::REAL,
        jsonb_build_object('meeting_date', m.meeting_date, 'meeting_type', m.meeting_type)
      FROM meetings_embeddings me
      JOIN meetings m ON m.id = me.id
      WHERE p_query_embedding IS NOT NULL
        AND m.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'meeting')
      ORDER BY me.embedding <=> p_query_embedding
      LIMIT 20
    ) m_sub
  ),
  vec_ranked AS (
    SELECT
      v.id, v.result_type, v.title, v.snippet, v.url_path,
      v.sim_score, v.metadata,
      ROW_NUMBER() OVER (ORDER BY v.sim_score DESC) AS vec_rank
    FROM vec_results v
    WHERE v.sim_score > 0.2
  ),

  merged AS (
    SELECT
      coalesce(f.id, v.id) AS id,
      coalesce(f.result_type, v.result_type) AS result_type,
      coalesce(f.title, v.title) AS title,
      coalesce(f.snippet, v.snippet) AS snippet,
      coalesce(f.url_path, v.url_path) AS url_path,
      (coalesce(1.0 / (k + f.fts_rank), 0) +
       coalesce(1.0 / (k + v.vec_rank), 0))::REAL AS relevance_score,
      CASE
        WHEN f.id IS NOT NULL AND v.id IS NOT NULL THEN 'both'
        WHEN f.id IS NOT NULL THEN 'keyword'
        ELSE 'semantic'
      END AS match_type,
      coalesce(f.metadata, v.metadata) AS metadata
    FROM fts_ranked f
    FULL OUTER JOIN vec_ranked v
      ON f.id = v.id AND f.result_type = v.result_type
  )

  SELECT m.id, m.result_type, m.title, m.snippet, m.url_path,
         m.relevance_score, m.match_type, m.metadata
  FROM merged m
  ORDER BY m.relevance_score DESC
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;

-- find_similar_items: same shape as before, just JOIN agenda_items_embeddings.

CREATE OR REPLACE FUNCTION find_similar_items(
  p_item_id UUID,
  p_city_fips TEXT DEFAULT '0660620',
  p_limit INT DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  title TEXT,
  summary_headline TEXT,
  meeting_id UUID,
  meeting_date DATE,
  item_number TEXT,
  similarity REAL,
  vote_outcome TEXT,
  public_comment_count INTEGER,
  financial_amount TEXT,
  category TEXT,
  topic_label TEXT
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  source_embedding vector(1536);
BEGIN
  SELECT aie.embedding INTO source_embedding
  FROM agenda_items_embeddings aie
  WHERE aie.id = p_item_id;

  IF source_embedding IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    ai.id,
    ai.title,
    ai.summary_headline,
    ai.meeting_id,
    m.meeting_date,
    ai.item_number::TEXT,
    (1 - (aie.embedding <=> source_embedding))::REAL AS similarity,
    CASE
      WHEN m.meeting_date > CURRENT_DATE THEN 'upcoming'
      WHEN mo.id IS NULL AND m.minutes_url IS NULL THEN 'minutes pending'
      WHEN mo.id IS NULL THEN 'no vote'
      WHEN lower(mo.motion_result) LIKE '%pass%' OR lower(mo.motion_result) LIKE '%approv%' OR lower(mo.motion_result) LIKE '%adopt%' THEN 'passed'
      ELSE 'failed'
    END AS vote_outcome,
    ai.public_comment_count,
    ai.financial_amount::TEXT,
    ai.category::TEXT,
    ai.topic_label::TEXT
  FROM agenda_items_embeddings aie
  JOIN agenda_items ai ON ai.id = aie.id
  JOIN meetings m ON m.id = ai.meeting_id
  LEFT JOIN LATERAL (
    SELECT mo2.id, mo2.result AS motion_result
    FROM motions mo2
    WHERE mo2.agenda_item_id = ai.id
    ORDER BY mo2.id
    LIMIT 1
  ) mo ON true
  WHERE ai.id != p_item_id
    AND m.city_fips = p_city_fips
    AND (1 - (aie.embedding <=> source_embedding)) > 0.3
  ORDER BY aie.embedding <=> source_embedding
  LIMIT p_limit;
END;
$$;
