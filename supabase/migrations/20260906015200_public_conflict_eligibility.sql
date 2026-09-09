-- Align public flag rows and aggregate counts with the existing display threshold.
-- This is eligibility for display, not an operator approval or legal finding.
-- Source validity remains enforced by migration 133's existing public policy.
-- Workers retain their existing service-role privileges and source evidence.

ALTER TABLE public.conflict_flags ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.conflict_flags FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.conflict_flags TO anon, authenticated;

DROP POLICY IF EXISTS conflict_flags_public_eligibility ON public.conflict_flags;
CREATE POLICY conflict_flags_public_eligibility ON public.conflict_flags
  AS RESTRICTIVE FOR SELECT TO anon, authenticated
  USING (is_current IS TRUE AND confidence >= 0.70 AND false_positive IS NOT TRUE);

-- This definer RPC bypasses RLS for bounded read performance, so repeat the
-- same eligibility test in its cohort. Preserve all existing source-validity
-- and government-entity exclusions, shape, search path, and execution ACL.
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
      AND cf.confidence >= 0.70
      AND cf.false_positive IS NOT TRUE
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
      count(*) FILTER (WHERE ngf.confidence >= 0.70) AS flags_published
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
