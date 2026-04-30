-- Migration 096: Per-motion vote breakdown RPC for divergent motions display
--
-- The existing get_contested_votes() RPC (migration 034) returns one row per
-- (motion, official) but only carries minimal columns (motion_id, official_id,
-- official_name, vote_choice, category). For Leisa Johnson's "show me the
-- actual motions where council split, with each member's vote" view, the
-- frontend needs richer per-motion context: motion text, agenda item title,
-- meeting date, item number, topic label, and a procedural flag.
--
-- This RPC is additive — get_contested_votes() is unchanged so existing
-- coalition/alignment/bloc analysis continues to work. The new function adds
-- the columns the per-motion table needs.
--
-- Returns one row per (motion, official) pair for every contested motion
-- (motions with at least one aye AND one nay). Frontend groups by motion
-- and renders columns per current member.

CREATE OR REPLACE FUNCTION get_divergent_motions_detail(p_city_fips TEXT DEFAULT '0660620')
RETURNS TABLE (
  motion_id UUID,
  motion_text TEXT,
  motion_result TEXT,
  vote_tally TEXT,
  meeting_id UUID,
  meeting_date DATE,
  agenda_item_id UUID,
  agenda_item_title TEXT,
  agenda_item_number TEXT,
  category TEXT,
  topic_label TEXT,
  is_procedural BOOLEAN,
  official_id UUID,
  official_name TEXT,
  vote_choice TEXT
) AS $$
BEGIN
  RETURN QUERY
  WITH city_votes AS (
    SELECT
      v.motion_id,
      m.motion_text::TEXT AS motion_text,
      m.result::TEXT AS motion_result,
      m.vote_tally::TEXT AS vote_tally,
      ai.meeting_id,
      mt.meeting_date,
      ai.id AS agenda_item_id,
      ai.title::TEXT AS agenda_item_title,
      ai.item_number::TEXT AS agenda_item_number,
      ai.category::TEXT AS category,
      ai.topic_label::TEXT AS topic_label,
      (ai.category = 'procedural') AS is_procedural,
      v.official_id,
      v.official_name::TEXT AS official_name,
      v.vote_choice::TEXT AS vote_choice
    FROM votes v
    JOIN motions m ON m.id = v.motion_id
    JOIN agenda_items ai ON ai.id = m.agenda_item_id
    JOIN meetings mt ON mt.id = ai.meeting_id
    WHERE mt.city_fips = p_city_fips
      AND v.official_id IS NOT NULL
      AND v.vote_choice IN ('aye', 'nay', 'abstain', 'absent')
  ),
  contested AS (
    SELECT cv.motion_id
    FROM city_votes cv
    WHERE cv.vote_choice IN ('aye', 'nay')
    GROUP BY cv.motion_id
    HAVING COUNT(DISTINCT cv.vote_choice) > 1
  )
  SELECT
    cv.motion_id,
    cv.motion_text,
    cv.motion_result,
    cv.vote_tally,
    cv.meeting_id,
    cv.meeting_date,
    cv.agenda_item_id,
    cv.agenda_item_title,
    cv.agenda_item_number,
    cv.category,
    cv.topic_label,
    cv.is_procedural,
    cv.official_id,
    cv.official_name,
    cv.vote_choice
  FROM city_votes cv
  INNER JOIN contested c ON c.motion_id = cv.motion_id;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION get_divergent_motions_detail(TEXT) IS
  'Per-(motion, official) rows for every contested motion in a city. Used by the public voting-patterns page to render member-vs-motion tables. Includes motion text, meeting date, and is_procedural flag so the frontend can filter and label.';
