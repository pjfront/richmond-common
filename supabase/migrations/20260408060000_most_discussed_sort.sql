-- Migration 084: Change "Most Discussed" sort to pure comment count
--
-- Replaces the weighted composite score (85% comments, 10% vote split,
-- 5% motions) with a transparent sort: comment count DESC, then vote
-- split closeness DESC, then motion count DESC.
--
-- The composite score obscured the ranking logic. A simple sort by
-- comment count with explicit tiebreakers is more honest and easier
-- to explain to citizens.

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
    SELECT mo2.agenda_item_id AS mc_item_id, count(*)::BIGINT AS mc_count
    FROM motions mo2
    GROUP BY mo2.agenda_item_id
  ),
  comment_counts AS (
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
      COALESCE(cc.cc_count, 0) AS item_comment_count,
      -- Vote split closeness: 1.0 = tied, 0.0 = unanimous, NULL = no vote data
      CASE
        WHEN fmv.fmv_ayes IS NULL OR (fmv.fmv_ayes + fmv.fmv_nays) = 0 THEN 0.0
        ELSE (1.0 - abs(fmv.fmv_ayes - fmv.fmv_nays)::NUMERIC / (fmv.fmv_ayes + fmv.fmv_nays))
      END AS vote_split_factor
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN first_motion_votes fmv ON fmv.fmv_item_id = ai.id
    LEFT JOIN motion_counts mc ON mc.mc_item_id = ai.id
    LEFT JOIN comment_counts cc ON cc.cc_item_id = ai.id
    WHERE mt.city_fips = p_city_fips
      AND ai.is_consent_calendar = false
  )
  SELECT
    s.item_id,
    s.item_meeting_id,
    s.item_meeting_date,
    s.item_num::TEXT,
    s.item_title::TEXT,
    s.item_category::TEXT,
    -- Keep controversy_score column for backward compat; set to comment count
    s.item_comment_count::NUMERIC,
    s.fmv_vote_tally::TEXT,
    CASE WHEN s.fmv_ayes IS NOT NULL THEN s.item_result ELSE 'unknown' END::TEXT,
    s.item_comment_count,
    s.item_motion_count
  FROM item_data s
  WHERE s.item_comment_count > 0
     OR s.fmv_ayes IS NOT NULL
  ORDER BY
    s.item_comment_count DESC,
    s.vote_split_factor DESC,
    s.item_motion_count DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;
