-- Migration 038: Server-side RPCs for stats page (D14)
-- Replaces client-side aggregation that fetched 14K+ agenda items + ~50 sequential
-- public_comments batch requests. Two RPCs reduce ~50 round-trips to 1 query each.
--
-- Functions:
--   parse_vote_tally(text) → (ayes int, nays int)  — reusable helper
--   get_category_stats(city_fips) → category aggregation rows
--   get_controversial_items(city_fips, limit) → top-N scored items

-- ────────────────────────────────────────────────────────────────
-- Helper: parse_vote_tally
-- Mirrors the TypeScript parseVoteTally() in queries.ts.
-- Handles 4 formats from Richmond minutes:
--   "7-0", "5 - 2"           → dash format
--   "7 to 0"                 → word format
--   "Ayes (6), Noes (1)"     → parenthetical count
--   "Ayes: Name, Name. Noes: Name." → name list (count commas)
-- Returns NULL for unparseable tallies (e.g., "died for lack of a second").
-- ────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION parse_vote_tally(tally TEXT)
RETURNS TABLE (ayes INT, nays INT) AS $$
DECLARE
  m TEXT[];
  aye_names TEXT;
  noe_names TEXT;
  aye_count INT;
  noe_count INT;
BEGIN
  IF tally IS NULL OR tally = '' THEN
    RETURN;
  END IF;

  -- Format 1: "7-0" or "5 - 2"
  m := regexp_match(tally, '^(\d+)\s*-\s*(\d+)');
  IF m IS NOT NULL THEN
    ayes := m[1]::INT;
    nays := m[2]::INT;
    RETURN NEXT;
    RETURN;
  END IF;

  -- Format 2: "7 to 0"
  m := regexp_match(tally, '^(\d+)\s+to\s+(\d+)', 'i');
  IF m IS NOT NULL THEN
    ayes := m[1]::INT;
    nays := m[2]::INT;
    RETURN NEXT;
    RETURN;
  END IF;

  -- Format 3: "Ayes (6)" with optional "Noes (1)" / "Nays (1)"
  m := regexp_match(tally, 'Ayes?\s*\((\d+)\)', 'i');
  IF m IS NOT NULL THEN
    aye_count := m[1]::INT;
    m := regexp_match(tally, 'No(?:e|ay)s?\s*\((\d+)\)', 'i');
    noe_count := COALESCE(m[1]::INT, 0);
    ayes := aye_count;
    nays := noe_count;
    RETURN NEXT;
    RETURN;
  END IF;

  -- Format 4: "Ayes: Name1, Name2. Noes: Name3."
  m := regexp_match(tally, 'Ayes:\s*([^.]+)\.', 'i');
  IF m IS NOT NULL THEN
    aye_names := m[1];
    -- Count names: split by comma, filter out "none"
    SELECT count(*) INTO aye_count
    FROM unnest(string_to_array(aye_names, ',')) AS name
    WHERE trim(name) != '' AND lower(trim(name)) != 'none'
      AND trim(name) !~ '^\s*and\s';

    noe_count := 0;
    m := regexp_match(tally, 'Noes:\s*([^.]+)\.', 'i');
    IF m IS NOT NULL THEN
      noe_names := m[1];
      SELECT count(*) INTO noe_count
      FROM unnest(string_to_array(noe_names, ',')) AS name
      WHERE trim(name) != '' AND lower(trim(name)) != 'none'
        AND trim(name) !~ '^\s*and\s';
    END IF;

    IF aye_count > 0 THEN
      ayes := aye_count;
      nays := noe_count;
      RETURN NEXT;
      RETURN;
    END IF;
  END IF;

  -- Unparseable
  RETURN;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ────────────────────────────────────────────────────────────────
-- get_category_stats: aggregate voting/controversy stats by category
-- Replaces getCategoryStats() in queries.ts (~50 round-trips → 1 query)
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
  WITH item_motions AS (
    -- All agenda items with their first motion's parsed vote tally
    SELECT
      ai.id AS item_id,
      COALESCE(ai.category, 'other') AS cat,
      ai.is_consent_calendar,
      m_first.vote_tally,
      m_first.motion_count,
      (parse_vote_tally(m_first.vote_tally)).*
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN LATERAL (
      -- Get first motion's vote_tally and total motion count per item
      SELECT
        (array_agg(mo.vote_tally ORDER BY mo.id))[1] AS vote_tally,
        count(*)::INT AS motion_count
      FROM motions mo
      WHERE mo.agenda_item_id = ai.id
    ) m_first ON true
    WHERE mt.city_fips = p_city_fips
  ),
  item_scores AS (
    -- Compute per-item controversy score
    -- Formula: splitWeight * 6 + commentWeight * 3 + multipleMotions * 1
    -- For category stats, commentWeight uses 1 as meetingMax (same as TS)
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
      SELECT agenda_item_id, count(*) AS comment_count
      FROM public_comments
      WHERE agenda_item_id IS NOT NULL
      GROUP BY agenda_item_id
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
-- Replaces getControversialItems() in queries.ts
-- Uses per-meeting max comment normalization for the comment weight
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
  WITH item_data AS (
    SELECT
      ai.id AS item_id,
      ai.meeting_id,
      mt.meeting_date,
      ai.item_number,
      ai.title,
      ai.category,
      ai.is_consent_calendar,
      (array_agg(mo.vote_tally ORDER BY mo.id))[1] AS first_vote_tally,
      (array_agg(mo.result ORDER BY mo.id))[1] AS first_result,
      count(mo.id) AS motion_count
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN motions mo ON mo.agenda_item_id = ai.id
    WHERE mt.city_fips = p_city_fips
      AND ai.is_consent_calendar = false
    GROUP BY ai.id, ai.meeting_id, mt.meeting_date, ai.item_number,
             ai.title, ai.category, ai.is_consent_calendar
  ),
  item_comments AS (
    SELECT
      d.item_id,
      d.meeting_id,
      d.meeting_date,
      d.item_number,
      d.title,
      d.category,
      d.first_vote_tally,
      d.first_result,
      d.motion_count,
      COALESCE(pc.cnt, 0) AS comment_count
    FROM item_data d
    LEFT JOIN (
      SELECT agenda_item_id, count(*) AS cnt
      FROM public_comments
      WHERE agenda_item_id IS NOT NULL
      GROUP BY agenda_item_id
    ) pc ON pc.agenda_item_id = d.item_id
  ),
  meeting_max AS (
    SELECT meeting_id, GREATEST(max(comment_count), 1) AS max_comments
    FROM item_comments
    GROUP BY meeting_id
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
      (parse_vote_tally(ic.first_vote_tally)).ayes AS parsed_ayes,
      (parse_vote_tally(ic.first_vote_tally)).nays AS parsed_nays,
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

-- Indexes (idempotent) — most already exist from migration 034,
-- but the public_comments index is new for this workload
CREATE INDEX IF NOT EXISTS idx_public_comments_agenda_item_id
  ON public_comments(agenda_item_id) WHERE agenda_item_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_agenda_items_meeting_id ON agenda_items(meeting_id);
CREATE INDEX IF NOT EXISTS idx_agenda_items_category ON agenda_items(category);
CREATE INDEX IF NOT EXISTS idx_meetings_city_fips ON meetings(city_fips);
