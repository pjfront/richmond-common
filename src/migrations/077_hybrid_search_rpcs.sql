-- Migration 077: Hybrid search and similarity RPCs
--
-- search_hybrid() — Reciprocal Rank Fusion of FTS + vector similarity.
--   When query_embedding is NULL, degrades gracefully to pure FTS.
--
-- find_similar_items() — Cosine similarity nearest neighbors for
--   the "Similar Discussions" feature on item detail pages.


-- Ensure vector type is resolvable (Supabase installs pgvector in 'extensions' schema)
SET search_path TO public, extensions;

-- ── search_hybrid ──────────────────────────────────────────────

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
  -- CTE 1: Full-text search results (reuse search_site logic)
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

  -- CTE 2: Vector similarity results (skip if no embedding provided)
  -- Each member wrapped in subquery because ORDER BY + LIMIT inside UNION ALL
  -- requires it in PostgreSQL.
  vec_results AS (
    SELECT * FROM (
      SELECT
        ai.id,
        'agenda_item'::TEXT AS result_type,
        ai.title,
        left(coalesce(ai.plain_language_summary, ai.description, ''), 160) AS snippet,
        '/meetings/' || ai.meeting_id AS url_path,
        (1 - (ai.embedding <=> p_query_embedding))::REAL AS sim_score,
        jsonb_build_object(
          'meeting_date', m.meeting_date,
          'category', ai.category,
          'item_number', ai.item_number,
          'topic_label', ai.topic_label
        ) AS metadata
      FROM agenda_items ai
      JOIN meetings m ON m.id = ai.meeting_id
      WHERE p_query_embedding IS NOT NULL
        AND ai.embedding IS NOT NULL
        AND m.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'agenda_item')
      ORDER BY ai.embedding <=> p_query_embedding
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
        (1 - (mo.embedding <=> p_query_embedding))::REAL,
        jsonb_build_object(
          'meeting_date', m.meeting_date,
          'agenda_item_title', ai.title
        )
      FROM motions mo
      JOIN agenda_items ai ON ai.id = mo.agenda_item_id
      JOIN meetings m ON m.id = ai.meeting_id
      WHERE p_query_embedding IS NOT NULL
        AND mo.embedding IS NOT NULL
        AND m.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'vote_explainer')
      ORDER BY mo.embedding <=> p_query_embedding
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
        (1 - (o.embedding <=> p_query_embedding))::REAL,
        jsonb_build_object('role', o.role, 'is_current', o.is_current)
      FROM officials o
      WHERE p_query_embedding IS NOT NULL
        AND o.embedding IS NOT NULL
        AND o.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'official')
      ORDER BY o.embedding <=> p_query_embedding
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
        (1 - (m.embedding <=> p_query_embedding))::REAL,
        jsonb_build_object('meeting_date', m.meeting_date, 'meeting_type', m.meeting_type)
      FROM meetings m
      WHERE p_query_embedding IS NOT NULL
        AND m.embedding IS NOT NULL
        AND m.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'meeting')
      ORDER BY m.embedding <=> p_query_embedding
      LIMIT 20
    ) m_sub
  ),
  vec_ranked AS (
    SELECT
      v.id, v.result_type, v.title, v.snippet, v.url_path,
      v.sim_score, v.metadata,
      ROW_NUMBER() OVER (ORDER BY v.sim_score DESC) AS vec_rank
    FROM vec_results v
    WHERE v.sim_score > 0.2  -- minimum similarity threshold
  ),

  -- CTE 3: Merge via Reciprocal Rank Fusion
  merged AS (
    SELECT
      coalesce(f.id, v.id) AS id,
      coalesce(f.result_type, v.result_type) AS result_type,
      coalesce(f.title, v.title) AS title,
      coalesce(f.snippet, v.snippet) AS snippet,
      coalesce(f.url_path, v.url_path) AS url_path,
      -- RRF score: sum of reciprocal ranks from each signal
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


-- ── find_similar_items ─────────────────────────────────────────
-- Returns the N most semantically similar agenda items for a given item.
-- Used by the "Similar Discussions" feature on item detail pages.

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
  -- Get the source item's embedding
  SELECT ai.embedding INTO source_embedding
  FROM agenda_items ai
  WHERE ai.id = p_item_id;

  -- If no embedding, return empty
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
    ai.item_number,
    (1 - (ai.embedding <=> source_embedding))::REAL AS similarity,
    -- Derive vote outcome (same logic as related_topic_items in queries.ts)
    CASE
      WHEN m.meeting_date > CURRENT_DATE THEN 'upcoming'
      WHEN mo.id IS NULL AND m.minutes_url IS NULL THEN 'minutes pending'
      WHEN mo.id IS NULL THEN 'no vote'
      WHEN mo.passed THEN 'passed'
      ELSE 'failed'
    END AS vote_outcome,
    ai.public_comment_count,
    ai.financial_amount,
    ai.category,
    ai.topic_label
  FROM agenda_items ai
  JOIN meetings m ON m.id = ai.meeting_id
  LEFT JOIN LATERAL (
    SELECT mo2.id, mo2.passed
    FROM motions mo2
    WHERE mo2.agenda_item_id = ai.id
    ORDER BY mo2.id
    LIMIT 1
  ) mo ON true
  WHERE ai.id != p_item_id
    AND ai.embedding IS NOT NULL
    AND m.city_fips = p_city_fips
    AND (1 - (ai.embedding <=> source_embedding)) > 0.3
  ORDER BY ai.embedding <=> source_embedding
  LIMIT p_limit;
END;
$$;
