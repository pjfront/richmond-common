-- Migration 083: Reweight controversy score to prioritize public engagement
--
-- Old weights: vote split 60% (6pts), comments 30% (3pts), motions 10% (1pt)
-- New weights: comments 85% (8.5pts), vote split 10% (1pt), motions 5% (0.5pt)
--
-- The old formula surfaced mundane items with close votes over items that
-- generated massive public testimony (e.g., ceasefire resolutions that pass
-- unanimously). "Most debated" should mean most debated by the *public*.
--
-- Also: items without parsed vote data are no longer excluded — an item with
-- 50 public speakers but no recorded vote tally should still rank.
-- Comment normalization changed from per-meeting max to global max so items
-- with high absolute comment counts rank above items that merely dominate
-- a low-engagement meeting.

-- ────────────────────────────────────────────────────────────────
-- get_category_stats: update controversy score weights
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
    SELECT mo2.agenda_item_id AS mc_item_id, count(*)::INT AS mc_count
    FROM motions mo2
    GROUP BY mo2.agenda_item_id
  ),
  comment_counts AS (
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
        ELSE round((
          LEAST(COALESCE(cc.cc_count, 0)::NUMERIC, 1) * 8.5
          + CASE
              WHEN fmv.fmv_ayes IS NULL OR (fmv.fmv_ayes + fmv.fmv_nays) = 0 THEN 0.0
              ELSE (1.0 - abs(fmv.fmv_ayes - fmv.fmv_nays)::NUMERIC / (fmv.fmv_ayes + fmv.fmv_nays)) * 1.0
            END
          + CASE WHEN mc.mc_count > 1 THEN 0.5 ELSE 0 END
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
-- get_controversial_items: reweight + allow items without vote data
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
      COALESCE(cc.cc_count, 0) AS item_comment_count
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN first_motion_votes fmv ON fmv.fmv_item_id = ai.id
    LEFT JOIN motion_counts mc ON mc.mc_item_id = ai.id
    LEFT JOIN comment_counts cc ON cc.cc_item_id = ai.id
    WHERE mt.city_fips = p_city_fips
      AND ai.is_consent_calendar = false
  ),
  global_max AS (
    SELECT GREATEST(max(d.item_comment_count), 1) AS max_comments
    FROM item_data d
  )
  SELECT
    s.item_id,
    s.item_meeting_id,
    s.item_meeting_date,
    s.item_num::TEXT,
    s.item_title::TEXT,
    s.item_category::TEXT,
    round((
      (s.item_comment_count::NUMERIC / gm.max_comments) * 8.5
      + CASE
          WHEN s.fmv_ayes IS NULL OR (s.fmv_ayes + s.fmv_nays) = 0 THEN 0.0
          ELSE (1.0 - abs(s.fmv_ayes - s.fmv_nays)::NUMERIC / (s.fmv_ayes + s.fmv_nays)) * 1.0
        END
      + CASE WHEN s.item_motion_count > 1 THEN 0.5 ELSE 0 END
    )::NUMERIC, 1),
    s.fmv_vote_tally::TEXT,
    CASE WHEN s.fmv_ayes IS NOT NULL THEN s.item_result ELSE 'unknown' END::TEXT,
    s.item_comment_count,
    s.item_motion_count
  FROM item_data s
  CROSS JOIN global_max gm
  WHERE s.item_comment_count > 0
     OR s.fmv_ayes IS NOT NULL
  ORDER BY 7 DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;
