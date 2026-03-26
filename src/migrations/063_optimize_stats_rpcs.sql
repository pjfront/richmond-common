-- Migration 063: Optimize stats RPCs to eliminate LATERAL join timeouts
-- Both get_category_stats and get_controversial_items used LATERAL subqueries
-- that re-executed per agenda item (~7K rows), causing 6-14 second runtimes.
-- Fix: pre-aggregate with DISTINCT ON and regular joins instead of LATERAL.
-- Also alias all CTE columns to avoid PL/pgSQL variable name collisions.

-- ────────────────────────────────────────────────────────────────
-- get_category_stats: aggregate voting/controversy stats by category
-- Optimized: replaces 2 LATERAL joins with pre-aggregated CTEs
-- ────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION get_category_stats(p_city_fips TEXT DEFAULT '0660620')
RETURNS TABLE (
  category TEXT,
  item_count BIGINT,
  vote_count BIGINT,
  split_vote_count BIGINT,
  unanimous_vote_count BIGINT,
  avg_controversy_score NUMERIC,
  max_controversy_score NUMERIC,
  total_public_comments BIGINT,
  percentage_of_agenda NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  WITH first_motion_votes AS (
    -- Pre-aggregate: first motion's aye/nay counts per agenda item (single pass)
    SELECT DISTINCT ON (mo.agenda_item_id)
      mo.agenda_item_id AS fmv_item_id,
      count(*) FILTER (WHERE v.vote_choice = 'aye') AS fmv_ayes,
      count(*) FILTER (WHERE v.vote_choice = 'nay') AS fmv_nays
    FROM motions mo
    JOIN votes v ON v.motion_id = mo.id
    GROUP BY mo.id, mo.agenda_item_id
    ORDER BY mo.agenda_item_id, mo.id
  ),
  motion_counts AS (
    -- Pre-aggregate: total motions per agenda item (single pass)
    SELECT mo2.agenda_item_id AS mc_item_id, count(*)::INT AS mc_count
    FROM motions mo2
    GROUP BY mo2.agenda_item_id
  ),
  comment_counts AS (
    -- Pre-aggregate: comments per agenda item (single pass)
    SELECT pc2.agenda_item_id AS cc_item_id, count(*) AS cc_count
    FROM public_comments pc2
    WHERE pc2.agenda_item_id IS NOT NULL
    GROUP BY pc2.agenda_item_id
  ),
  item_scores AS (
    SELECT
      ai.id AS item_id,
      COALESCE(ai.category, 'other') AS item_cat,
      COALESCE(mc.mc_count, 0) AS item_motion_count,
      fmv.fmv_ayes,
      fmv.fmv_nays,
      COALESCE(cc.cc_count, 0) AS item_comment_count,
      CASE
        WHEN ai.is_consent_calendar THEN 0.0
        WHEN fmv.fmv_ayes IS NULL THEN 0.0
        WHEN (fmv.fmv_ayes + fmv.fmv_nays) = 0 THEN 0.0
        ELSE round((
          (1.0 - abs(fmv.fmv_ayes - fmv.fmv_nays)::NUMERIC / (fmv.fmv_ayes + fmv.fmv_nays)) * 6
          + LEAST(COALESCE(cc.cc_count, 0)::NUMERIC, 1) * 3
          + CASE WHEN mc.mc_count > 1 THEN 1 ELSE 0 END
        )::NUMERIC, 1)
      END AS item_controversy_score
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN first_motion_votes fmv ON fmv.fmv_item_id = ai.id
    LEFT JOIN motion_counts mc ON mc.mc_item_id = ai.id
    LEFT JOIN comment_counts cc ON cc.cc_item_id = ai.id
    WHERE mt.city_fips = p_city_fips
  ),
  total AS (
    SELECT count(*) AS total_items FROM item_scores
  )
  SELECT
    s.item_cat::TEXT,
    count(*)::BIGINT,
    COALESCE(sum(s.item_motion_count), 0)::BIGINT,
    count(*) FILTER (WHERE s.fmv_nays > 0)::BIGINT,
    count(*) FILTER (WHERE s.fmv_ayes IS NOT NULL AND s.fmv_nays = 0)::BIGINT,
    CASE
      WHEN count(*) FILTER (WHERE s.item_controversy_score IS NOT NULL) > 0
      THEN round(avg(s.item_controversy_score)::NUMERIC, 1)
      ELSE 0
    END,
    COALESCE(max(s.item_controversy_score), 0),
    COALESCE(sum(s.item_comment_count), 0)::BIGINT,
    round((count(*)::NUMERIC / NULLIF((SELECT total_items FROM total), 0) * 100)::NUMERIC, 1)
  FROM item_scores s
  GROUP BY s.item_cat
  ORDER BY count(*) DESC;
END;
$$ LANGUAGE plpgsql STABLE;

-- ────────────────────────────────────────────────────────────────
-- get_controversial_items: top-N most controversial agenda items
-- Optimized: replaces 2 LATERAL joins with pre-aggregated CTEs
-- ────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION get_controversial_items(
  p_city_fips TEXT DEFAULT '0660620',
  p_limit INT DEFAULT 20
)
RETURNS TABLE (
  agenda_item_id UUID,
  meeting_id UUID,
  meeting_date DATE,
  item_number TEXT,
  title TEXT,
  category TEXT,
  controversy_score NUMERIC,
  vote_tally TEXT,
  result TEXT,
  public_comment_count BIGINT,
  motion_count BIGINT
) AS $$
BEGIN
  RETURN QUERY
  WITH first_motion_votes AS (
    -- Pre-aggregate: first motion's vote data per agenda item (single pass)
    SELECT DISTINCT ON (mo.agenda_item_id)
      mo.agenda_item_id AS fmv_item_id,
      mo.vote_tally AS fmv_vote_tally,
      mo.result AS fmv_result,
      count(*) FILTER (WHERE v.vote_choice = 'aye') AS fmv_ayes,
      count(*) FILTER (WHERE v.vote_choice = 'nay') AS fmv_nays
    FROM motions mo
    JOIN votes v ON v.motion_id = mo.id
    GROUP BY mo.id, mo.agenda_item_id, mo.vote_tally, mo.result
    ORDER BY mo.agenda_item_id, mo.id
  ),
  motion_counts AS (
    -- Pre-aggregate: total motions per agenda item (single pass)
    SELECT mo2.agenda_item_id AS mc_item_id, count(*)::BIGINT AS mc_count
    FROM motions mo2
    GROUP BY mo2.agenda_item_id
  ),
  comment_counts AS (
    -- Pre-aggregate: comments per agenda item (single pass)
    SELECT pc2.agenda_item_id AS cc_item_id, count(*) AS cc_count
    FROM public_comments pc2
    WHERE pc2.agenda_item_id IS NOT NULL
    GROUP BY pc2.agenda_item_id
  ),
  item_data AS (
    SELECT
      ai.id AS item_id,
      ai.meeting_id AS item_meeting_id,
      mt.meeting_date AS item_meeting_date,
      ai.item_number AS item_num,
      ai.title AS item_title,
      ai.category AS item_category,
      fmv.fmv_vote_tally,
      COALESCE(fmv.fmv_result, 'unknown') AS item_result,
      fmv.fmv_ayes,
      fmv.fmv_nays,
      COALESCE(mc.mc_count, 0) AS item_motion_count,
      COALESCE(cc.cc_count, 0) AS item_comment_count
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN first_motion_votes fmv ON fmv.fmv_item_id = ai.id
    LEFT JOIN motion_counts mc ON mc.mc_item_id = ai.id
    LEFT JOIN comment_counts cc ON cc.cc_item_id = ai.id
    WHERE mt.city_fips = p_city_fips
      AND ai.is_consent_calendar = false
  ),
  meeting_max AS (
    SELECT d.item_meeting_id AS mm_meeting_id, GREATEST(max(d.item_comment_count), 1) AS max_comments
    FROM item_data d
    GROUP BY d.item_meeting_id
  ),
  scored AS (
    SELECT
      d.item_id,
      d.item_meeting_id,
      d.item_meeting_date,
      d.item_num,
      d.item_title,
      d.item_category,
      d.fmv_vote_tally,
      d.item_result,
      d.item_comment_count,
      d.item_motion_count,
      d.fmv_ayes,
      d.fmv_nays,
      mm.max_comments
    FROM item_data d
    JOIN meeting_max mm ON mm.mm_meeting_id = d.item_meeting_id
  )
  SELECT
    s.item_id,
    s.item_meeting_id,
    s.item_meeting_date,
    s.item_num::TEXT,
    s.item_title::TEXT,
    s.item_category::TEXT,
    CASE
      WHEN s.fmv_ayes IS NULL THEN 0.0
      WHEN (s.fmv_ayes + s.fmv_nays) = 0 THEN 0.0
      ELSE round((
        (1.0 - abs(s.fmv_ayes - s.fmv_nays)::NUMERIC / (s.fmv_ayes + s.fmv_nays)) * 6
        + (s.item_comment_count::NUMERIC / s.max_comments) * 3
        + CASE WHEN s.item_motion_count > 1 THEN 1 ELSE 0 END
      )::NUMERIC, 1)
    END,
    s.fmv_vote_tally::TEXT,
    s.item_result::TEXT,
    s.item_comment_count,
    s.item_motion_count
  FROM scored s
  WHERE s.fmv_ayes IS NOT NULL
    AND (s.fmv_ayes + s.fmv_nays) > 0
  ORDER BY 7 DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;
