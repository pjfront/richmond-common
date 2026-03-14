-- Migration 034: Server-side contested votes RPC for coalition analysis
-- Replaces client-side triple-nested PostgREST join (votes → motions → agenda_items → meetings)
-- that fetched 55K+ rows and was timing out on Vercel serverless functions.
--
-- This function:
-- 1. Joins votes through to meetings using native SQL (proper query planning + indexes)
-- 2. Filters to contested motions IN SQL (motions with both aye and nay votes)
-- 3. Returns only the columns needed for pairwise alignment computation
-- 4. Avoids PostgREST's default 1000-row limit
--
-- Reduces data transfer from ~55K rows to ~10-15K rows (contested votes only).

CREATE OR REPLACE FUNCTION get_contested_votes(p_city_fips TEXT DEFAULT '0660620')
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
    -- All aye/nay votes for this city, joined through to meetings
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
  ),
  contested AS (
    -- Motions where at least one member voted aye AND one voted nay
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

-- Add indexes if not already present to speed up the join chain
CREATE INDEX IF NOT EXISTS idx_votes_motion_id ON votes(motion_id);
CREATE INDEX IF NOT EXISTS idx_votes_vote_choice ON votes(vote_choice);
CREATE INDEX IF NOT EXISTS idx_motions_agenda_item_id ON motions(agenda_item_id);
CREATE INDEX IF NOT EXISTS idx_agenda_items_meeting_id ON agenda_items(meeting_id);
CREATE INDEX IF NOT EXISTS idx_meetings_city_fips ON meetings(city_fips);
