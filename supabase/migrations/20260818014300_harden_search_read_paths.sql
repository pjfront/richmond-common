-- Migration 143: bound and harden the three public search read paths.
--
-- These functions are called from public pages and were measurable database
-- hotspots. The rewrite keeps their signatures and result shapes stable while:
--   * bounding query text, limits, offsets, and nearest-neighbor candidates;
--   * applying GIN/HNSW-friendly candidate limits before expensive rendering;
--   * bypassing repeated nested RLS checks with reviewed SECURITY DEFINER bodies;
--   * reproducing migration 133's active-source boundary inside those bodies;
--   * pinning search_path and API-role EXECUTE grants explicitly.
--
-- No rows are corrected, backfilled, or deleted by this migration.

-- Internal candidate helper. It is not executable by API roles; the public
-- wrappers below enforce their own smaller result limits before calling it.
CREATE OR REPLACE FUNCTION public._search_site_candidates(
  p_query TEXT,
  p_city_fips TEXT DEFAULT '0660620',
  p_result_type TEXT DEFAULT NULL,
  p_limit INTEGER DEFAULT 20,
  p_offset INTEGER DEFAULT 0
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
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
  v_query TEXT;
  v_tsq TSQUERY;
  v_limit INTEGER;
  v_offset INTEGER;
  v_candidate_limit INTEGER;
BEGIN
  v_query := left(trim(coalesce(p_query, '')), 200);
  IF v_query = '' THEN
    RETURN;
  END IF;

  IF p_result_type IS NOT NULL
     AND p_result_type NOT IN ('agenda_item', 'vote_explainer', 'official', 'meeting') THEN
    RETURN;
  END IF;

  v_limit := least(greatest(coalesce(p_limit, 20), 1), 250);
  v_offset := least(greatest(coalesce(p_offset, 0), 0), 200);
  v_candidate_limit := least(250, greatest(50, v_limit + v_offset));
  v_tsq := plainto_tsquery('english', v_query);

  IF v_tsq IS NULL OR v_tsq = ''::tsquery THEN
    RETURN;
  END IF;

  RETURN QUERY
  WITH results AS MATERIALIZED (
    SELECT *
    FROM (
      SELECT
        ai.id,
        'agenda_item'::TEXT AS result_type,
        ai.title,
        ts_headline(
          'english',
          coalesce(ai.plain_language_summary, ai.description, ai.title),
          v_tsq,
          'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
        ) AS snippet,
        '/meetings/' || ai.meeting_id AS url_path,
        ts_rank(
          to_tsvector(
            'english',
            coalesce(ai.title, '') || ' ' ||
            coalesce(ai.description, '') || ' ' ||
            coalesce(ai.plain_language_summary, '') || ' ' ||
            coalesce(ai.category, '') || ' ' ||
            coalesce(ai.topic_label, '') || ' ' ||
            coalesce(ai.summary_headline, '')
          ),
          v_tsq
        )::REAL AS relevance_score,
        jsonb_build_object(
          'meeting_date', mt.meeting_date,
          'category', ai.category,
          'item_number', ai.item_number,
          'topic_label', ai.topic_label
        ) AS metadata
      FROM public.agenda_items ai
      JOIN public.meetings mt ON mt.id = ai.meeting_id
      WHERE mt.city_fips = p_city_fips
        AND mt.source_cancelled_at IS NULL
        AND ai.agenda_source_retired_at IS NULL
        AND (p_result_type IS NULL OR p_result_type = 'agenda_item')
        AND to_tsvector(
              'english',
              coalesce(ai.title, '') || ' ' ||
              coalesce(ai.description, '') || ' ' ||
              coalesce(ai.plain_language_summary, '') || ' ' ||
              coalesce(ai.category, '') || ' ' ||
              coalesce(ai.topic_label, '') || ' ' ||
              coalesce(ai.summary_headline, '')
            ) @@ v_tsq
      ORDER BY 6 DESC, ai.id
      LIMIT v_candidate_limit
    ) agenda_candidates

    UNION ALL

    SELECT *
    FROM (
      SELECT
        mo.id,
        'vote_explainer'::TEXT AS result_type,
        coalesce(ai.title, 'Motion on item ' || ai.item_number) AS title,
        ts_headline(
          'english',
          coalesce(mo.vote_explainer, ''),
          v_tsq,
          'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
        ) AS snippet,
        '/meetings/' || mt.id AS url_path,
        ts_rank(
          to_tsvector('english', coalesce(mo.vote_explainer, '')),
          v_tsq
        )::REAL AS relevance_score,
        jsonb_build_object(
          'meeting_date', mt.meeting_date,
          'agenda_item_title', ai.title
        ) AS metadata
      FROM public.motions mo
      JOIN public.agenda_items ai ON ai.id = mo.agenda_item_id
      JOIN public.meetings mt ON mt.id = ai.meeting_id
      WHERE mt.city_fips = p_city_fips
        AND mt.source_cancelled_at IS NULL
        AND ai.agenda_source_retired_at IS NULL
        AND (p_result_type IS NULL OR p_result_type = 'vote_explainer')
        AND to_tsvector('english', coalesce(mo.vote_explainer, '')) @@ v_tsq
      ORDER BY 6 DESC, mo.id
      LIMIT v_candidate_limit
    ) motion_candidates

    UNION ALL

    SELECT *
    FROM (
      SELECT
        ofc.id,
        'official'::TEXT AS result_type,
        ofc.name AS title,
        ts_headline(
          'english',
          coalesce(ofc.bio_summary, ofc.name),
          v_tsq,
          'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
        ) AS snippet,
        '/council/' ||
          regexp_replace(
            regexp_replace(lower(ofc.name), '\s+', '-', 'g'),
            '[^a-z0-9-]',
            '',
            'g'
          ) AS url_path,
        (
          ts_rank(
            to_tsvector(
              'english',
              coalesce(ofc.name, '') || ' ' || coalesce(ofc.bio_summary, '')
            ),
            v_tsq
          ) * 2
        )::REAL AS relevance_score,
        jsonb_build_object(
          'role', ofc.role,
          'is_current', ofc.is_current
        ) AS metadata
      FROM public.officials ofc
      WHERE ofc.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'official')
        AND to_tsvector(
              'english',
              coalesce(ofc.name, '') || ' ' || coalesce(ofc.bio_summary, '')
            ) @@ v_tsq
      ORDER BY 6 DESC, ofc.id
      LIMIT v_candidate_limit
    ) official_candidates

    UNION ALL

    SELECT *
    FROM (
      SELECT
        mt.id,
        'meeting'::TEXT AS result_type,
        initcap(coalesce(mt.meeting_type, 'regular')) || ' Meeting — ' ||
          to_char(mt.meeting_date, 'FMMonth DD, YYYY') AS title,
        NULL::TEXT AS snippet,
        '/meetings/' || mt.id AS url_path,
        (
          ts_rank(
            to_tsvector(
              'english',
              coalesce(mt.meeting_type, '') || ' ' ||
              coalesce(to_char(mt.meeting_date, 'FMMonth YYYY FMMonth DD YYYY'), '')
            ),
            v_tsq
          ) * 1.5
        )::REAL AS relevance_score,
        jsonb_build_object(
          'meeting_date', mt.meeting_date,
          'meeting_type', mt.meeting_type
        ) AS metadata
      FROM public.meetings mt
      WHERE mt.city_fips = p_city_fips
        AND mt.source_cancelled_at IS NULL
        AND (p_result_type IS NULL OR p_result_type = 'meeting')
        AND to_tsvector(
              'english',
              coalesce(mt.meeting_type, '') || ' ' ||
              coalesce(to_char(mt.meeting_date, 'FMMonth YYYY FMMonth DD YYYY'), '')
            ) @@ v_tsq
      ORDER BY 6 DESC, mt.id
      LIMIT v_candidate_limit
    ) meeting_candidates
  )
  SELECT
    r.id,
    r.result_type,
    r.title,
    r.snippet,
    r.url_path,
    r.relevance_score,
    r.metadata
  FROM results r
  ORDER BY r.relevance_score DESC, r.result_type, r.id
  LIMIT v_limit
  OFFSET v_offset;
END;
$function$;

CREATE OR REPLACE FUNCTION public.search_site(
  p_query TEXT,
  p_city_fips TEXT DEFAULT '0660620',
  p_result_type TEXT DEFAULT NULL,
  p_limit INTEGER DEFAULT 20,
  p_offset INTEGER DEFAULT 0
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
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
  SELECT candidates.*
  FROM public._search_site_candidates(
    p_query,
    p_city_fips,
    p_result_type,
    least(greatest(coalesce(p_limit, 20), 1), 50),
    least(greatest(coalesce(p_offset, 0), 0), 200)
  ) candidates
  ORDER BY candidates.relevance_score DESC, candidates.result_type, candidates.id;
$function$;

CREATE OR REPLACE FUNCTION public.search_hybrid(
  p_query TEXT,
  p_query_embedding extensions.vector(1536) DEFAULT NULL,
  p_city_fips TEXT DEFAULT '0660620',
  p_result_type TEXT DEFAULT NULL,
  p_limit INTEGER DEFAULT 20,
  p_offset INTEGER DEFAULT 0
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
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
  v_query TEXT;
  v_limit INTEGER;
  v_offset INTEGER;
  v_candidate_limit INTEGER;
  k CONSTANT INTEGER := 60;
BEGIN
  v_query := left(trim(coalesce(p_query, '')), 200);
  IF v_query = '' THEN
    RETURN;
  END IF;

  IF p_result_type IS NOT NULL
     AND p_result_type NOT IN ('agenda_item', 'vote_explainer', 'official', 'meeting') THEN
    RETURN;
  END IF;

  v_limit := least(greatest(coalesce(p_limit, 20), 1), 50);
  v_offset := least(greatest(coalesce(p_offset, 0), 0), 200);
  v_candidate_limit := least(250, greatest(50, v_limit + v_offset));

  RETURN QUERY
  WITH
  fts_results AS MATERIALIZED (
    SELECT *
    FROM public._search_site_candidates(
      v_query,
      p_city_fips,
      p_result_type,
      v_candidate_limit,
      0
    )
  ),
  fts_ranked AS (
    SELECT
      f.id,
      f.result_type,
      f.title,
      f.snippet,
      f.url_path,
      f.relevance_score,
      f.metadata,
      row_number() OVER (
        ORDER BY f.relevance_score DESC, f.result_type, f.id
      ) AS fts_rank
    FROM fts_results f
  ),
  agenda_nearest AS MATERIALIZED (
    SELECT
      aie.id,
      aie.embedding OPERATOR(extensions.<=>)
        p_query_embedding::extensions.halfvec(1536) AS distance
    FROM public.agenda_items_embeddings aie
    WHERE p_query_embedding IS NOT NULL
      AND (p_result_type IS NULL OR p_result_type = 'agenda_item')
    ORDER BY aie.embedding OPERATOR(extensions.<=>)
      p_query_embedding::extensions.halfvec(1536)
    LIMIT v_candidate_limit
  ),
  motion_nearest AS MATERIALIZED (
    SELECT
      moe.id,
      moe.embedding OPERATOR(extensions.<=>)
        p_query_embedding::extensions.halfvec(1536) AS distance
    FROM public.motions_embeddings moe
    WHERE p_query_embedding IS NOT NULL
      AND (p_result_type IS NULL OR p_result_type = 'vote_explainer')
    ORDER BY moe.embedding OPERATOR(extensions.<=>)
      p_query_embedding::extensions.halfvec(1536)
    LIMIT v_candidate_limit
  ),
  official_nearest AS MATERIALIZED (
    SELECT
      oe.id,
      oe.embedding OPERATOR(extensions.<=>)
        p_query_embedding::extensions.halfvec(1536) AS distance
    FROM public.officials_embeddings oe
    WHERE p_query_embedding IS NOT NULL
      AND (p_result_type IS NULL OR p_result_type = 'official')
    ORDER BY oe.embedding OPERATOR(extensions.<=>)
      p_query_embedding::extensions.halfvec(1536)
    LIMIT v_candidate_limit
  ),
  meeting_nearest AS MATERIALIZED (
    SELECT
      me.id,
      me.embedding OPERATOR(extensions.<=>)
        p_query_embedding::extensions.halfvec(1536) AS distance
    FROM public.meetings_embeddings me
    WHERE p_query_embedding IS NOT NULL
      AND (p_result_type IS NULL OR p_result_type = 'meeting')
    ORDER BY me.embedding OPERATOR(extensions.<=>)
      p_query_embedding::extensions.halfvec(1536)
    LIMIT v_candidate_limit
  ),
  vector_results AS (
    SELECT
      ai.id,
      'agenda_item'::TEXT AS result_type,
      ai.title,
      left(coalesce(ai.plain_language_summary, ai.description, ''), 160) AS snippet,
      '/meetings/' || ai.meeting_id AS url_path,
      (1 - nearest.distance)::REAL AS similarity,
      jsonb_build_object(
        'meeting_date', mt.meeting_date,
        'category', ai.category,
        'item_number', ai.item_number,
        'topic_label', ai.topic_label
      ) AS metadata
    FROM agenda_nearest nearest
    JOIN public.agenda_items ai ON ai.id = nearest.id
    JOIN public.meetings mt ON mt.id = ai.meeting_id
    WHERE nearest.distance < 0.8
      AND mt.city_fips = p_city_fips
      AND mt.source_cancelled_at IS NULL
      AND ai.agenda_source_retired_at IS NULL

    UNION ALL

    SELECT
      mo.id,
      'vote_explainer'::TEXT,
      coalesce(ai.title, 'Motion on item ' || ai.item_number),
      left(coalesce(mo.vote_explainer, ''), 160),
      '/meetings/' || mt.id,
      (1 - nearest.distance)::REAL,
      jsonb_build_object(
        'meeting_date', mt.meeting_date,
        'agenda_item_title', ai.title
      )
    FROM motion_nearest nearest
    JOIN public.motions mo ON mo.id = nearest.id
    JOIN public.agenda_items ai ON ai.id = mo.agenda_item_id
    JOIN public.meetings mt ON mt.id = ai.meeting_id
    WHERE nearest.distance < 0.8
      AND mt.city_fips = p_city_fips
      AND mt.source_cancelled_at IS NULL
      AND ai.agenda_source_retired_at IS NULL

    UNION ALL

    SELECT
      ofc.id,
      'official'::TEXT,
      ofc.name,
      left(coalesce(ofc.bio_summary, ''), 160),
      '/council/' ||
        regexp_replace(
          regexp_replace(lower(ofc.name), '\s+', '-', 'g'),
          '[^a-z0-9-]',
          '',
          'g'
        ),
      (1 - nearest.distance)::REAL,
      jsonb_build_object('role', ofc.role, 'is_current', ofc.is_current)
    FROM official_nearest nearest
    JOIN public.officials ofc ON ofc.id = nearest.id
    WHERE nearest.distance < 0.8
      AND ofc.city_fips = p_city_fips

    UNION ALL

    SELECT
      mt.id,
      'meeting'::TEXT,
      initcap(coalesce(mt.meeting_type, 'regular')) || ' Meeting — ' ||
        to_char(mt.meeting_date, 'FMMonth DD, YYYY'),
      left(coalesce(mt.meeting_summary, ''), 160),
      '/meetings/' || mt.id,
      (1 - nearest.distance)::REAL,
      jsonb_build_object(
        'meeting_date', mt.meeting_date,
        'meeting_type', mt.meeting_type
      )
    FROM meeting_nearest nearest
    JOIN public.meetings mt ON mt.id = nearest.id
    WHERE nearest.distance < 0.8
      AND mt.city_fips = p_city_fips
      AND mt.source_cancelled_at IS NULL
  ),
  vector_ranked AS (
    SELECT
      v.id,
      v.result_type,
      v.title,
      v.snippet,
      v.url_path,
      v.similarity,
      v.metadata,
      row_number() OVER (
        ORDER BY v.similarity DESC, v.result_type, v.id
      ) AS vector_rank
    FROM vector_results v
  ),
  merged AS (
    SELECT
      coalesce(f.id, v.id) AS id,
      coalesce(f.result_type, v.result_type) AS result_type,
      coalesce(f.title, v.title) AS title,
      coalesce(f.snippet, v.snippet) AS snippet,
      coalesce(f.url_path, v.url_path) AS url_path,
      (
        coalesce(1.0 / (k + f.fts_rank), 0) +
        coalesce(1.0 / (k + v.vector_rank), 0)
      )::REAL AS relevance_score,
      CASE
        WHEN f.id IS NOT NULL AND v.id IS NOT NULL THEN 'both'
        WHEN f.id IS NOT NULL THEN 'keyword'
        ELSE 'semantic'
      END AS match_type,
      coalesce(f.metadata, v.metadata) AS metadata
    FROM fts_ranked f
    FULL OUTER JOIN vector_ranked v
      ON v.id = f.id AND v.result_type = f.result_type
  )
  SELECT
    m.id,
    m.result_type,
    m.title,
    m.snippet,
    m.url_path,
    m.relevance_score,
    m.match_type,
    m.metadata
  FROM merged m
  ORDER BY m.relevance_score DESC, m.result_type, m.id
  LIMIT v_limit
  OFFSET v_offset;
END;
$function$;

CREATE OR REPLACE FUNCTION public.find_similar_items(
  p_item_id UUID,
  p_city_fips TEXT DEFAULT '0660620',
  p_limit INTEGER DEFAULT 5
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
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
DECLARE
  v_source_embedding extensions.halfvec(1536);
  v_limit INTEGER;
  v_candidate_limit INTEGER;
BEGIN
  v_limit := least(greatest(coalesce(p_limit, 5), 1), 10);
  v_candidate_limit := least(100, greatest(20, v_limit * 10));

  SELECT aie.embedding
  INTO v_source_embedding
  FROM public.agenda_items_embeddings aie
  JOIN public.agenda_items source_item ON source_item.id = aie.id
  JOIN public.meetings source_meeting ON source_meeting.id = source_item.meeting_id
  WHERE aie.id = p_item_id
    AND source_meeting.city_fips = p_city_fips
    AND source_meeting.source_cancelled_at IS NULL
    AND source_item.agenda_source_retired_at IS NULL;

  IF v_source_embedding IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  WITH nearest AS MATERIALIZED (
    SELECT
      aie.id,
      aie.embedding OPERATOR(extensions.<=>) v_source_embedding AS distance
    FROM public.agenda_items_embeddings aie
    WHERE aie.id <> p_item_id
    ORDER BY aie.embedding OPERATOR(extensions.<=>) v_source_embedding
    LIMIT v_candidate_limit
  )
  SELECT
    ai.id,
    ai.title,
    ai.summary_headline,
    ai.meeting_id,
    mt.meeting_date,
    ai.item_number::TEXT,
    (1 - nearest.distance)::REAL AS similarity,
    CASE
      WHEN mt.meeting_date > current_date THEN 'upcoming'
      WHEN first_motion.id IS NULL AND mt.minutes_url IS NULL THEN 'minutes pending'
      WHEN first_motion.id IS NULL THEN 'no vote'
      WHEN lower(first_motion.motion_result) LIKE '%pass%'
        OR lower(first_motion.motion_result) LIKE '%approv%'
        OR lower(first_motion.motion_result) LIKE '%adopt%' THEN 'passed'
      ELSE 'failed'
    END AS vote_outcome,
    ai.public_comment_count,
    ai.financial_amount::TEXT,
    ai.category::TEXT,
    ai.topic_label::TEXT
  FROM nearest
  JOIN public.agenda_items ai ON ai.id = nearest.id
  JOIN public.meetings mt ON mt.id = ai.meeting_id
  LEFT JOIN LATERAL (
    SELECT mo.id, mo.result AS motion_result
    FROM public.motions mo
    WHERE mo.agenda_item_id = ai.id
    ORDER BY mo.id
    LIMIT 1
  ) first_motion ON true
  WHERE nearest.distance < 0.7
    AND mt.city_fips = p_city_fips
    AND mt.source_cancelled_at IS NULL
    AND ai.agenda_source_retired_at IS NULL
  ORDER BY nearest.distance, ai.id
  LIMIT v_limit;
END;
$function$;

REVOKE ALL PRIVILEGES ON FUNCTION public._search_site_candidates(
  TEXT, TEXT, TEXT, INTEGER, INTEGER
) FROM PUBLIC, anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.search_site(
  TEXT, TEXT, TEXT, INTEGER, INTEGER
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.search_site(
  TEXT, TEXT, TEXT, INTEGER, INTEGER
) TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.search_hybrid(
  TEXT, extensions.vector, TEXT, TEXT, INTEGER, INTEGER
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.search_hybrid(
  TEXT, extensions.vector, TEXT, TEXT, INTEGER, INTEGER
) TO anon, authenticated, service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.find_similar_items(
  UUID, TEXT, INTEGER
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.find_similar_items(
  UUID, TEXT, INTEGER
) TO anon, authenticated, service_role;
