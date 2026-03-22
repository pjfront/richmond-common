-- Migration 030: Full-text search infrastructure (S10.1)
-- GIN expression indexes + search_site RPC function
-- Run in Supabase SQL Editor

-- ─── GIN Expression Indexes ─────────────────────────────────
-- Expression indexes (no stored tsvector columns) — sufficient at ~6,700 rows

CREATE INDEX IF NOT EXISTS idx_agenda_items_fts
  ON agenda_items USING GIN(
    to_tsvector('english',
      coalesce(title, '') || ' ' ||
      coalesce(description, '') || ' ' ||
      coalesce(plain_language_summary, '')
    )
  );

CREATE INDEX IF NOT EXISTS idx_motions_fts
  ON motions USING GIN(
    to_tsvector('english', coalesce(vote_explainer, ''))
  );

CREATE INDEX IF NOT EXISTS idx_officials_fts
  ON officials USING GIN(
    to_tsvector('english', coalesce(name, '') || ' ' || coalesce(bio_summary, ''))
  );

CREATE INDEX IF NOT EXISTS idx_commissions_fts
  ON commissions USING GIN(
    to_tsvector('english', coalesce(name, ''))
  );

-- ─── search_site RPC Function ───────────────────────────────

CREATE OR REPLACE FUNCTION search_site(
  p_query TEXT,
  p_city_fips VARCHAR DEFAULT '0660620',
  p_result_type VARCHAR DEFAULT NULL,
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
  metadata JSONB
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  tsq tsquery;
BEGIN
  -- plainto_tsquery is safe for raw user input (no special syntax)
  tsq := plainto_tsquery('english', p_query);

  -- Early exit if query produces empty tsquery
  IF tsq IS NULL OR tsq = ''::tsquery THEN
    RETURN;
  END IF;

  RETURN QUERY
  WITH results AS (
    -- 1. Agenda items: title + description + plain_language_summary
    SELECT
      ai.id,
      'agenda_item'::TEXT AS result_type,
      ai.title,
      ts_headline('english',
        coalesce(ai.plain_language_summary, coalesce(ai.description, ai.title)),
        tsq,
        'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
      ) AS snippet,
      '/meetings/' || ai.meeting_id AS url_path,
      ts_rank(
        to_tsvector('english',
          coalesce(ai.title, '') || ' ' ||
          coalesce(ai.description, '') || ' ' ||
          coalesce(ai.plain_language_summary, '')
        ),
        tsq
      ) AS relevance_score,
      jsonb_build_object(
        'meeting_date', m.meeting_date,
        'category', ai.category,
        'item_number', ai.item_number
      ) AS metadata
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
      AND to_tsvector('english',
            coalesce(ai.title, '') || ' ' ||
            coalesce(ai.description, '') || ' ' ||
            coalesce(ai.plain_language_summary, '')
          ) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'agenda_item')

    UNION ALL

    -- 2. Motions (vote explainers)
    SELECT
      mo.id,
      'vote_explainer'::TEXT AS result_type,
      coalesce(ai.title, 'Motion on item ' || ai.item_number) AS title,
      ts_headline('english',
        coalesce(mo.vote_explainer, ''),
        tsq,
        'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
      ) AS snippet,
      '/meetings/' || m.id AS url_path,
      ts_rank(
        to_tsvector('english', coalesce(mo.vote_explainer, '')),
        tsq
      ) AS relevance_score,
      jsonb_build_object(
        'meeting_date', m.meeting_date,
        'agenda_item_title', ai.title
      ) AS metadata
    FROM motions mo
    JOIN agenda_items ai ON ai.id = mo.agenda_item_id
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
      AND to_tsvector('english', coalesce(mo.vote_explainer, '')) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'vote_explainer')

    UNION ALL

    -- 3. Officials: name + bio_summary
    SELECT
      o.id,
      'official'::TEXT AS result_type,
      o.name AS title,
      ts_headline('english',
        coalesce(o.bio_summary, o.name),
        tsq,
        'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
      ) AS snippet,
      '/council/' || lower(regexp_replace(regexp_replace(o.name, '\s+', '-', 'g'), '[^a-z0-9-]', '', 'g')) AS url_path,
      ts_rank(
        to_tsvector('english', coalesce(o.name, '') || ' ' || coalesce(o.bio_summary, '')),
        tsq
      ) AS relevance_score,
      jsonb_build_object(
        'role', o.role,
        'is_current', o.is_current
      ) AS metadata
    FROM officials o
    WHERE o.city_fips = p_city_fips
      AND to_tsvector('english', coalesce(o.name, '') || ' ' || coalesce(o.bio_summary, '')) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'official')

    UNION ALL

    -- 4. Commissions: name
    SELECT
      c.id,
      'commission'::TEXT AS result_type,
      c.name AS title,
      NULL::TEXT AS snippet,
      '/commissions/' || c.id AS url_path,
      ts_rank(
        to_tsvector('english', coalesce(c.name, '')),
        tsq
      ) AS relevance_score,
      jsonb_build_object(
        'commission_type', c.commission_type
      ) AS metadata
    FROM commissions c
    WHERE c.city_fips = p_city_fips
      AND to_tsvector('english', coalesce(c.name, '')) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'commission')
  )
  SELECT r.id, r.result_type, r.title, r.snippet, r.url_path, r.relevance_score, r.metadata
  FROM results r
  ORDER BY r.relevance_score DESC
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;
