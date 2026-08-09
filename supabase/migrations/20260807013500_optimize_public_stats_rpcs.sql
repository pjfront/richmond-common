-- Migration 135: keep public statistics RPCs below the anon timeout
--
-- Migration 133 made source-retirement enforcement non-omissible with RLS.
-- These two whole-corpus aggregations then inherited the caller's nested RLS
-- policy checks on meetings, agenda_items, motions, votes, and conflict_flags.
-- Production EXPLAIN showed ~943K shared-buffer hits for the anonymous
-- get_controversial_items call versus ~9.7K for the table owner, and a 6.6x
-- slowdown for get_meeting_flag_counts. Concurrent ISR prerenders could cross
-- the anonymous role's statement timeout even though both functions degrade
-- safely in the frontend.
--
-- Run these read-only, parameterized functions as their postgres owner so the
-- planner does not recursively re-evaluate RLS. Because SECURITY DEFINER
-- bypasses table RLS, each function reproduces the migration-133 public
-- boundary explicitly: cancelled meetings and retired agenda items remain
-- excluded. A fixed, catalog-only search_path prevents object shadowing.
--
-- POLICY DEPENDENCY: these definer bodies are now part of the public RLS
-- boundary. Any future migration that tightens a public SELECT policy on a
-- dependency table (including the non-executable draft 134 authority gate)
-- must use a new prefix after 135 and redefine both functions in that same
-- migration with the new predicate. The focused contract test enforces this.

CREATE OR REPLACE FUNCTION public.get_meeting_flag_counts(p_city_fips TEXT)
RETURNS TABLE (
  meeting_id UUID,
  flags_total BIGINT,
  flags_published BIGINT,
  items_scanned BIGINT
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
  WITH active_meetings AS MATERIALIZED (
    SELECT m.id
    FROM public.meetings m
    WHERE m.city_fips = p_city_fips
      AND m.source_cancelled_at IS NULL
  ),
  active_items AS MATERIALIZED (
    SELECT ai.id, ai.meeting_id
    FROM public.agenda_items ai
    JOIN active_meetings am ON am.id = ai.meeting_id
    WHERE ai.agenda_source_retired_at IS NULL
  ),
  normalized_flags AS MATERIALIZED (
    SELECT
      cf.meeting_id,
      cf.confidence,
      cf.flag_type,
      lower(btrim(cf.evidence->0->>'vendor')) AS vendor,
      cf.evidence->0->>'match_type' AS match_type,
      lower(btrim(cf.evidence->0->>'donor_employer')) AS donor_employer
    FROM public.conflict_flags cf
    LEFT JOIN active_meetings flag_meeting ON flag_meeting.id = cf.meeting_id
    LEFT JOIN active_items flag_item ON flag_item.id = cf.agenda_item_id
    WHERE cf.city_fips = p_city_fips
      AND cf.is_current = TRUE
      -- Explicit equivalents of conflict_flags' migration-133 public policy.
      AND (cf.meeting_id IS NULL OR flag_meeting.id IS NOT NULL)
      AND (cf.agenda_item_id IS NULL OR flag_item.id IS NOT NULL)
  ),
  non_gov_flags AS (
    SELECT nf.meeting_id, nf.confidence
    FROM normalized_flags nf
    WHERE NOT (
      (
        nf.flag_type = 'donor_vendor_expenditure'
        AND nf.vendor IS NOT NULL
        AND (
          nf.vendor LIKE 'city of%'
          OR nf.vendor LIKE 'city and county%'
          OR nf.vendor LIKE 'city &%'
          OR nf.vendor LIKE 'county of%'
          OR nf.vendor LIKE 'state of%'
          OR nf.vendor LIKE 'town of%'
          OR nf.vendor LIKE 'district of%'
          OR nf.vendor LIKE 'village of%'
          OR nf.vendor LIKE 'borough of%'
          OR nf.vendor LIKE '% county'
          OR nf.vendor LIKE '% city'
          OR nf.vendor LIKE '% state'
          OR nf.vendor LIKE '% department'
        )
      )
      OR
      (
        nf.match_type IS NOT NULL
        AND nf.match_type LIKE 'employer_to_%'
        AND nf.donor_employer IS NOT NULL
        AND (
          nf.donor_employer LIKE 'city of%'
          OR nf.donor_employer LIKE 'city and county%'
          OR nf.donor_employer LIKE 'city &%'
          OR nf.donor_employer LIKE 'county of%'
          OR nf.donor_employer LIKE 'state of%'
          OR nf.donor_employer LIKE 'town of%'
          OR nf.donor_employer LIKE 'district of%'
          OR nf.donor_employer LIKE 'village of%'
          OR nf.donor_employer LIKE 'borough of%'
          OR nf.donor_employer LIKE '% county'
          OR nf.donor_employer LIKE '% city'
          OR nf.donor_employer LIKE '% state'
          OR nf.donor_employer LIKE '% department'
        )
      )
    )
  ),
  flag_agg AS (
    SELECT
      ngf.meeting_id,
      count(*) AS flags_total,
      count(*) FILTER (WHERE ngf.confidence >= 0.50) AS flags_published
    FROM non_gov_flags ngf
    GROUP BY ngf.meeting_id
  ),
  item_agg AS (
    SELECT ai.meeting_id, count(*) AS items_scanned
    FROM active_items ai
    GROUP BY ai.meeting_id
  )
  SELECT
    fa.meeting_id,
    fa.flags_total,
    fa.flags_published,
    COALESCE(ia.items_scanned, 0) AS items_scanned
  FROM flag_agg fa
  LEFT JOIN item_agg ia ON ia.meeting_id = fa.meeting_id;
$function$;

REVOKE ALL ON FUNCTION public.get_meeting_flag_counts(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.get_meeting_flag_counts(TEXT)
  TO anon, authenticated, service_role;


CREATE OR REPLACE FUNCTION public.get_controversial_items(
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
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
  WITH active_items AS MATERIALIZED (
    SELECT
      ai.id,
      ai.meeting_id,
      mt.meeting_date,
      ai.item_number,
      ai.title,
      ai.category,
      ai.public_comment_count
    FROM public.agenda_items ai
    JOIN public.meetings mt ON mt.id = ai.meeting_id
    WHERE mt.city_fips = p_city_fips
      AND mt.source_cancelled_at IS NULL
      AND ai.agenda_source_retired_at IS NULL
      AND ai.is_consent_calendar = FALSE
  ),
  motion_vote_counts AS (
    SELECT
      mo.agenda_item_id,
      mo.id AS motion_id,
      mo.vote_tally,
      mo.result,
      count(*) FILTER (WHERE v.vote_choice = 'aye') AS ayes,
      count(*) FILTER (WHERE v.vote_choice = 'nay') AS nays
    FROM public.motions mo
    JOIN active_items ai ON ai.id = mo.agenda_item_id
    JOIN public.votes v ON v.motion_id = mo.id
    GROUP BY mo.id, mo.agenda_item_id, mo.vote_tally, mo.result
  ),
  first_motion_votes AS (
    SELECT DISTINCT ON (mvc.agenda_item_id)
      mvc.agenda_item_id,
      mvc.vote_tally,
      mvc.result,
      mvc.ayes,
      mvc.nays
    FROM motion_vote_counts mvc
    ORDER BY mvc.agenda_item_id, mvc.motion_id
  ),
  motion_counts AS (
    SELECT mo.agenda_item_id, count(*)::BIGINT AS motion_count
    FROM public.motions mo
    JOIN active_items ai ON ai.id = mo.agenda_item_id
    GROUP BY mo.agenda_item_id
  ),
  item_data AS (
    SELECT
      ai.id AS item_id,
      ai.meeting_id AS item_meeting_id,
      ai.meeting_date AS item_meeting_date,
      ai.item_number AS item_num,
      ai.title AS item_title,
      ai.category AS item_category,
      fmv.vote_tally,
      COALESCE(fmv.result, 'unknown') AS item_result,
      fmv.ayes,
      fmv.nays,
      COALESCE(mc.motion_count, 0) AS item_motion_count,
      COALESCE(ai.public_comment_count, 0)::BIGINT AS item_comment_count,
      CASE
        WHEN fmv.ayes IS NULL OR (fmv.ayes + fmv.nays) = 0 THEN 0.0
        ELSE (
          1.0
          - abs(fmv.ayes - fmv.nays)::NUMERIC / (fmv.ayes + fmv.nays)
        )
      END AS vote_split_factor
    FROM active_items ai
    LEFT JOIN first_motion_votes fmv ON fmv.agenda_item_id = ai.id
    LEFT JOIN motion_counts mc ON mc.agenda_item_id = ai.id
  )
  SELECT
    s.item_id,
    s.item_meeting_id,
    s.item_meeting_date,
    s.item_num::TEXT,
    s.item_title::TEXT,
    s.item_category::TEXT,
    -- Backward-compatible score: migration 084 made comments the primary sort.
    s.item_comment_count::NUMERIC,
    s.vote_tally::TEXT,
    CASE WHEN s.ayes IS NOT NULL THEN s.item_result ELSE 'unknown' END::TEXT,
    s.item_comment_count,
    s.item_motion_count
  FROM item_data s
  WHERE s.item_comment_count > 0
     OR s.ayes IS NOT NULL
  ORDER BY
    s.item_comment_count DESC,
    s.vote_split_factor DESC,
    s.item_motion_count DESC
  LIMIT p_limit;
$function$;

REVOKE ALL ON FUNCTION public.get_controversial_items(TEXT, INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.get_controversial_items(TEXT, INT)
  TO anon, authenticated, service_role;
