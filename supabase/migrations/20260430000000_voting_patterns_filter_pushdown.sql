-- Migration 103: Push voting-patterns filtering into the RPCs.
--
-- Both `get_contested_votes` (migration 034) and `get_divergent_motions_detail`
-- (migration 096) returned every contested motion across all of Richmond's
-- council history (~9.6K and ~10.6K rows respectively) and relied on the
-- frontend to filter to current council members. Two problems:
--
-- 1. PostgREST caps RPC responses at 10K rows, so `get_divergent_motions_detail`
--    was already being silently truncated (10559 rows reduced to 10000).
-- 2. The 10K-row payloads pushed the queries close to the anon role's
--    statement_timeout under load, and any timeout during ISR build/revalidation
--    caused the page's try/catch to render an empty state which then got cached
--    indefinitely. That's the user-visible "no data" symptom.
--
-- Fix: add an optional `p_official_ids UUID[]` parameter. When provided, the
-- RPC filters votes to those officials in SQL and only returns motions that
-- remain contested (>= 1 aye AND >= 1 nay) among that subset. This collapses
-- the result from 10K+ rows to ~600-1000 rows, runs in under 1s, and removes
-- the need for client-side re-checking.
--
-- Backward compatible: passing NULL (or omitting the parameter) preserves the
-- original behavior. Existing callers continue to work unchanged.
--
-- The previous single-arg overloads must be dropped explicitly — Postgres
-- treats `(text)` and `(text, uuid[])` as separate functions, and PostgREST
-- returns HTTP 300 (ambiguous resolution) when a single-arg call could match
-- either. Dropping the old signature leaves only the new one.

DROP FUNCTION IF EXISTS get_contested_votes(TEXT);
DROP FUNCTION IF EXISTS get_divergent_motions_detail(TEXT);

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
    -- "Contested" must be evaluated within the official-id filter so a motion
    -- where the only dissenter was a former member doesn't appear when the
    -- caller asks for the current council only.
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
