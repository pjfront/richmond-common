-- Migration 059: Update search_site RPC to return item-level URLs
--
-- Changes agenda_item results from /meetings/{meeting_id} to
-- /meetings/{meeting_id}/items/{item_number} for direct deep linking.
-- Also adds meeting_id to metadata for fallback navigation.

CREATE OR REPLACE FUNCTION search_site(
  p_query TEXT,
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
  metadata JSONB
)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
  tsq tsquery;
BEGIN
  tsq := websearch_to_tsquery('english', p_query);

  RETURN QUERY
  WITH ranked AS (
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
      '/meetings/' || ai.meeting_id || '/items/' || lower(ai.item_number) AS url_path,
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
        'meeting_id', ai.meeting_id,
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
      mo.motion_text AS title,
      ts_headline('english',
        coalesce(mo.vote_explainer, mo.motion_text),
        tsq,
        'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
      ) AS snippet,
      '/meetings/' || m.id AS url_path,
      ts_rank(
        to_tsvector('english',
          coalesce(mo.motion_text, '') || ' ' ||
          coalesce(mo.vote_explainer, '')
        ),
        tsq
      ) * 0.9 AS relevance_score,
      jsonb_build_object(
        'meeting_date', m.meeting_date,
        'agenda_item_title', ai.title
      ) AS metadata
    FROM motions mo
    JOIN agenda_items ai ON ai.id = mo.agenda_item_id
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
      AND mo.vote_explainer IS NOT NULL
      AND to_tsvector('english',
            coalesce(mo.motion_text, '') || ' ' ||
            coalesce(mo.vote_explainer, '')
          ) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'vote_explainer')

    UNION ALL

    -- 3. Officials: name + bio
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
        to_tsvector('english',
          coalesce(o.name, '') || ' ' ||
          coalesce(o.bio_summary, '') || ' ' ||
          coalesce(o.role, '')
        ),
        tsq
      ) AS relevance_score,
      jsonb_build_object(
        'role', o.role,
        'is_current', o.is_current
      ) AS metadata
    FROM officials o
    WHERE o.city_fips = p_city_fips
      AND to_tsvector('english',
            coalesce(o.name, '') || ' ' ||
            coalesce(o.bio_summary, '') || ' ' ||
            coalesce(o.role, '')
          ) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'official')

    UNION ALL

    -- 4. Meetings: full-text search on all agenda item titles for a meeting
    SELECT DISTINCT ON (m.id)
      m.id,
      'meeting'::TEXT AS result_type,
      m.meeting_type || ' Meeting — ' || to_char(m.meeting_date, 'Mon DD, YYYY') AS title,
      ts_headline('english',
        coalesce(ai.title, m.meeting_type),
        tsq,
        'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
      ) AS snippet,
      '/meetings/' || m.id AS url_path,
      ts_rank(
        to_tsvector('english', coalesce(ai.title, '')),
        tsq
      ) * 0.8 AS relevance_score,
      jsonb_build_object(
        'meeting_date', m.meeting_date,
        'meeting_type', m.meeting_type
      ) AS metadata
    FROM meetings m
    JOIN agenda_items ai ON ai.meeting_id = m.id
    WHERE m.city_fips = p_city_fips
      AND to_tsvector('english', coalesce(ai.title, '')) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'meeting')
  )
  SELECT r.id, r.result_type, r.title, r.snippet, r.url_path, r.relevance_score, r.metadata
  FROM ranked r
  ORDER BY r.relevance_score DESC
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;
