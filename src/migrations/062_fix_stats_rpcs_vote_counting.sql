-- Migration 062: Fix vote counting in stats RPCs
-- Both get_category_stats and get_controversial_items used parse_vote_tally()
-- on the stored vote_tally text, which incorrectly counts absent/abstain members
-- as nay votes. Now counts actual aye/nay votes from the votes table.

-- ────────────────────────────────────────────────────────────────
-- get_category_stats: aggregate voting/controversy stats by category
-- Fixed: uses actual vote records instead of parsing vote_tally text
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
  WITH motion_vote_counts AS (
    -- Count actual aye/nay votes per motion from the votes table
    SELECT
      mo.id AS motion_id,
      mo.agenda_item_id,
      count(*) FILTER (WHERE v.vote_choice = 'aye') AS ayes,
      count(*) FILTER (WHERE v.vote_choice = 'nay') AS nays
    FROM motions mo
    JOIN votes v ON v.motion_id = mo.id
    GROUP BY mo.id, mo.agenda_item_id
  ),
  item_motions AS (
    -- Per agenda item: use the first motion's vote counts + total motion count
    SELECT
      ai.id AS item_id,
      COALESCE(ai.category, 'other') AS cat,
      ai.is_consent_calendar,
      mvc.ayes,
      mvc.nays,
      m_count.motion_count
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN LATERAL (
      -- First motion's actual vote counts
      SELECT mvc2.ayes, mvc2.nays
      FROM motion_vote_counts mvc2
      JOIN motions mo2 ON mo2.id = mvc2.motion_id
      WHERE mo2.agenda_item_id = ai.id
      ORDER BY mo2.id
      LIMIT 1
    ) mvc ON true
    LEFT JOIN LATERAL (
      SELECT count(*)::INT AS motion_count
      FROM motions mo3
      WHERE mo3.agenda_item_id = ai.id
    ) m_count ON true
    WHERE mt.city_fips = p_city_fips
  ),
  item_scores AS (
    -- Compute per-item controversy score
    -- Formula: splitWeight * 6 + commentWeight * 3 + multipleMotions * 1
    SELECT
      im.item_id,
      im.cat,
      im.motion_count,
      im.ayes,
      im.nays,
      COALESCE(pc.comment_count, 0) AS comment_count,
      CASE
        WHEN im.is_consent_calendar THEN 0.0
        WHEN im.ayes IS NULL THEN 0.0
        WHEN (im.ayes + im.nays) = 0 THEN 0.0
        ELSE round((
          (1.0 - abs(im.ayes - im.nays)::NUMERIC / (im.ayes + im.nays)) * 6
          + LEAST(COALESCE(pc.comment_count, 0)::NUMERIC, 1) * 3
          + CASE WHEN im.motion_count > 1 THEN 1 ELSE 0 END
        )::NUMERIC, 1)
      END AS controversy_score
    FROM item_motions im
    LEFT JOIN (
      SELECT pc2.agenda_item_id, count(*) AS comment_count
      FROM public_comments pc2
      WHERE pc2.agenda_item_id IS NOT NULL
      GROUP BY pc2.agenda_item_id
    ) pc ON pc.agenda_item_id = im.item_id
  ),
  total AS (
    SELECT count(*) AS total_items FROM item_scores
  )
  SELECT
    s.cat::TEXT AS category,
    count(*)::BIGINT AS item_count,
    COALESCE(sum(s.motion_count), 0)::BIGINT AS vote_count,
    count(*) FILTER (WHERE s.nays > 0)::BIGINT AS split_vote_count,
    count(*) FILTER (WHERE s.ayes IS NOT NULL AND s.nays = 0)::BIGINT AS unanimous_vote_count,
    CASE
      WHEN count(*) FILTER (WHERE s.controversy_score IS NOT NULL) > 0
      THEN round(avg(s.controversy_score)::NUMERIC, 1)
      ELSE 0
    END AS avg_controversy_score,
    COALESCE(max(s.controversy_score), 0) AS max_controversy_score,
    COALESCE(sum(s.comment_count), 0)::BIGINT AS total_public_comments,
    round((count(*)::NUMERIC / NULLIF((SELECT total_items FROM total), 0) * 100)::NUMERIC, 1) AS percentage_of_agenda
  FROM item_scores s
  GROUP BY s.cat
  ORDER BY count(*) DESC;
END;
$$ LANGUAGE plpgsql STABLE;

-- ────────────────────────────────────────────────────────────────
-- get_controversial_items: top-N most controversial agenda items
-- Fixed: uses actual vote records instead of parsing vote_tally text
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
  WITH motion_vote_counts AS (
    -- Count actual aye/nay votes per motion from the votes table
    SELECT
      mo.id AS motion_id,
      mo.agenda_item_id,
      mo.vote_tally,
      mo.result,
      count(*) FILTER (WHERE v.vote_choice = 'aye') AS ayes,
      count(*) FILTER (WHERE v.vote_choice = 'nay') AS nays
    FROM motions mo
    JOIN votes v ON v.motion_id = mo.id
    GROUP BY mo.id, mo.agenda_item_id, mo.vote_tally, mo.result
  ),
  item_data AS (
    SELECT
      ai.id AS item_id,
      ai.meeting_id,
      mt.meeting_date,
      ai.item_number,
      ai.title,
      ai.category,
      ai.is_consent_calendar,
      -- First motion's data
      first_m.vote_tally AS first_vote_tally,
      first_m.result AS first_result,
      first_m.ayes AS parsed_ayes,
      first_m.nays AS parsed_nays,
      m_count.motion_count
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN LATERAL (
      SELECT mvc.vote_tally, mvc.result, mvc.ayes, mvc.nays
      FROM motion_vote_counts mvc
      JOIN motions mo ON mo.id = mvc.motion_id
      WHERE mo.agenda_item_id = ai.id
      ORDER BY mo.id
      LIMIT 1
    ) first_m ON true
    LEFT JOIN LATERAL (
      SELECT count(*)::BIGINT AS motion_count
      FROM motions mo2
      WHERE mo2.agenda_item_id = ai.id
    ) m_count ON true
    WHERE mt.city_fips = p_city_fips
      AND ai.is_consent_calendar = false
  ),
  item_comments AS (
    SELECT
      d.*,
      COALESCE(pc.cnt, 0) AS comment_count
    FROM item_data d
    LEFT JOIN (
      SELECT pc2.agenda_item_id, count(*) AS cnt
      FROM public_comments pc2
      WHERE pc2.agenda_item_id IS NOT NULL
      GROUP BY pc2.agenda_item_id
    ) pc ON pc.agenda_item_id = d.item_id
  ),
  meeting_max AS (
    SELECT ic2.meeting_id, GREATEST(max(ic2.comment_count), 1) AS max_comments
    FROM item_comments ic2
    GROUP BY ic2.meeting_id
  ),
  scored AS (
    SELECT
      ic.item_id,
      ic.meeting_id,
      ic.meeting_date,
      ic.item_number,
      ic.title,
      ic.category,
      ic.first_vote_tally,
      COALESCE(ic.first_result, 'unknown') AS first_result,
      ic.comment_count,
      ic.motion_count,
      ic.parsed_ayes,
      ic.parsed_nays,
      mm.max_comments
    FROM item_comments ic
    JOIN meeting_max mm ON mm.meeting_id = ic.meeting_id
  )
  SELECT
    s.item_id AS agenda_item_id,
    s.meeting_id,
    s.meeting_date,
    s.item_number::TEXT,
    s.title::TEXT,
    s.category::TEXT,
    CASE
      WHEN s.parsed_ayes IS NULL THEN 0.0
      WHEN (s.parsed_ayes + s.parsed_nays) = 0 THEN 0.0
      ELSE round((
        (1.0 - abs(s.parsed_ayes - s.parsed_nays)::NUMERIC / (s.parsed_ayes + s.parsed_nays)) * 6
        + (s.comment_count::NUMERIC / s.max_comments) * 3
        + CASE WHEN s.motion_count > 1 THEN 1 ELSE 0 END
      )::NUMERIC, 1)
    END AS controversy_score,
    s.first_vote_tally::TEXT AS vote_tally,
    s.first_result::TEXT AS result,
    s.comment_count AS public_comment_count,
    s.motion_count
  FROM scored s
  WHERE s.parsed_ayes IS NOT NULL
    AND (s.parsed_ayes + s.parsed_nays) > 0
  ORDER BY controversy_score DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql STABLE;
