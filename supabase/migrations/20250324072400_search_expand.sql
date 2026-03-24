-- Migration 054: Expand search to officials, vote explainers, and meetings
-- Also adds category to agenda item search index for tag-based search

-- ─── Update GIN index to include category ─────────────────────
DROP INDEX IF EXISTS idx_agenda_items_fts;
CREATE INDEX idx_agenda_items_fts
  ON agenda_items USING GIN(
    to_tsvector('english',
      coalesce(title, '') || ' ' ||
      coalesce(description, '') || ' ' ||
      coalesce(plain_language_summary, '') || ' ' ||
      coalesce(category, '')
    )
  );

-- Meeting search: ~240 rows, no GIN index needed (seq scan is fine)
-- to_char is STABLE not IMMUTABLE, so can't be in expression index

-- ─── Updated search_site function ─────────────────────────────
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
  tsq := plainto_tsquery('english', p_query);

  IF tsq IS NULL OR tsq = ''::tsquery THEN
    RETURN;
  END IF;

  RETURN QUERY
  WITH results AS (
    -- 1. Agenda items: title + description + plain_language_summary + category
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
          coalesce(ai.plain_language_summary, '') || ' ' ||
          coalesce(ai.category, '')
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
            coalesce(ai.plain_language_summary, '') || ' ' ||
            coalesce(ai.category, '')
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
      (ts_rank(
        to_tsvector('english', coalesce(o.name, '') || ' ' || coalesce(o.bio_summary, '')),
        tsq
      ) * 2)::REAL AS relevance_score,  -- boost officials above agenda items
      jsonb_build_object(
        'role', o.role,
        'is_current', o.is_current
      ) AS metadata
    FROM officials o
    WHERE o.city_fips = p_city_fips
      AND to_tsvector('english', coalesce(o.name, '') || ' ' || coalesce(o.bio_summary, '')) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'official')

    UNION ALL

    -- 4. Meetings: meeting_type + formatted date
    SELECT
      m.id,
      'meeting'::TEXT AS result_type,
      initcap(coalesce(m.meeting_type, 'regular')) || ' Meeting — ' ||
        to_char(m.meeting_date, 'FMMonth DD, YYYY') AS title,
      NULL::TEXT AS snippet,
      '/meetings/' || m.id AS url_path,
      (ts_rank(
        to_tsvector('english',
          coalesce(m.meeting_type, '') || ' ' ||
          coalesce(to_char(m.meeting_date, 'FMMonth YYYY FMMonth DD YYYY'), '')
        ),
        tsq
      ) * 1.5)::REAL AS relevance_score,  -- boost meetings above agenda items
      jsonb_build_object(
        'meeting_date', m.meeting_date,
        'meeting_type', m.meeting_type
      ) AS metadata
    FROM meetings m
    WHERE m.city_fips = p_city_fips
      AND to_tsvector('english',
            coalesce(m.meeting_type, '') || ' ' ||
            coalesce(to_char(m.meeting_date, 'FMMonth YYYY FMMonth DD YYYY'), '')
          ) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'meeting')
  )
  SELECT r.id, r.result_type, r.title, r.snippet, r.url_path, r.relevance_score, r.metadata
  FROM results r
  ORDER BY r.relevance_score DESC
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;
