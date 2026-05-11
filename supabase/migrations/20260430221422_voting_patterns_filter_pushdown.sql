-- Migration 20260430221422: voting_patterns_filter_pushdown
-- RETROACTIVELY RECOVERED 2026-05-11. Originally applied by an
-- earlier Claude Code session without committing the SQL to git.
-- Recovered via SELECT FROM supabase_migrations.schema_migrations.

CREATE OR REPLACE FUNCTION get_contested_votes(
  p_city_fips TEXT DEFAULT '0660620',
  p_official_ids UUID[] DEFAULT NULL
)
RETURNS TABLE (
  motion_id UUID,
  official_id UUID,
  official_name TEXT,
  vote_choice TEXT,
  category TEXT
) AS $$
BEGIN
  RETURN QUERY
  WITH city_votes AS (
    SELECT
      v.motion_id,
      v.official_id,
      v.official_name::TEXT,
      v.vote_choice::TEXT,
      ai.category::TEXT
    FROM votes v
    JOIN motions m ON m.id = v.motion_id
    JOIN agenda_items ai ON ai.id = m.agenda_item_id
    JOIN meetings mt ON mt.id = ai.meeting_id
    WHERE mt.city_fips = p_city_fips
      AND v.official_id IS NOT NULL
      AND v.vote_choice IN ('aye', 'nay')
      AND (p_official_ids IS NULL OR v.official_id = ANY(p_official_ids))
  ),
  contested AS (
    SELECT cv.motion_id
    FROM city_votes cv
    GROUP BY cv.motion_id
    HAVING COUNT(DISTINCT cv.vote_choice) > 1
  )
  SELECT
    cv.motion_id,
    cv.official_id,
    cv.official_name,
    cv.vote_choice,
    cv.category
  FROM city_votes cv
  INNER JOIN contested c ON c.motion_id = cv.motion_id;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION get_divergent_motions_detail(
  p_city_fips TEXT DEFAULT '0660620',
  p_official_ids UUID[] DEFAULT NULL
)
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
      AND (p_official_ids IS NULL OR v.official_id = ANY(p_official_ids))
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

COMMENT ON FUNCTION get_contested_votes(TEXT, UUID[]) IS
  'Contested aye/nay votes for a city. When p_official_ids is provided, votes are pre-filtered to those officials and contestedness is re-evaluated within that subset.';

COMMENT ON FUNCTION get_divergent_motions_detail(TEXT, UUID[]) IS
  'Per-(motion, official) rows for contested motions in a city. When p_official_ids is provided, votes are pre-filtered to those officials and contestedness is re-evaluated within that subset.';
