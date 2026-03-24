-- Migration 053: Server-side flag count aggregation RPC
-- Fixes statement timeout on reports page: getMeetingsWithFlags was fetching
-- all 17,955 conflict_flags rows with JSONB evidence client-side, exceeding
-- the anon role's 3-second statement timeout. This RPC aggregates in SQL.

-- Drop if exists for idempotency
DROP FUNCTION IF EXISTS get_meeting_flag_counts(text);

CREATE OR REPLACE FUNCTION get_meeting_flag_counts(p_city_fips text)
RETURNS TABLE (
  meeting_id uuid,
  flags_total bigint,
  flags_published bigint,
  items_scanned bigint
)
LANGUAGE sql
STABLE
AS $$
  WITH filtered_flags AS (
    SELECT
      cf.meeting_id,
      cf.confidence,
      cf.flag_type,
      -- Extract fields needed for government entity filtering from first evidence element
      cf.evidence->0->>'vendor' AS vendor,
      cf.evidence->0->>'match_type' AS match_type,
      cf.evidence->0->>'donor_employer' AS donor_employer
    FROM conflict_flags cf
    WHERE cf.city_fips = p_city_fips
      AND cf.is_current = true
  ),
  non_gov_flags AS (
    SELECT meeting_id, confidence
    FROM filtered_flags
    WHERE NOT (
      -- Case 1: donor_vendor_expenditure with government entity vendor
      (flag_type = 'donor_vendor_expenditure' AND vendor IS NOT NULL AND (
        lower(trim(vendor)) LIKE 'city of%'
        OR lower(trim(vendor)) LIKE 'city and county%'
        OR lower(trim(vendor)) LIKE 'city &%'
        OR lower(trim(vendor)) LIKE 'county of%'
        OR lower(trim(vendor)) LIKE 'state of%'
        OR lower(trim(vendor)) LIKE 'town of%'
        OR lower(trim(vendor)) LIKE 'district of%'
        OR lower(trim(vendor)) LIKE 'village of%'
        OR lower(trim(vendor)) LIKE 'borough of%'
        OR lower(trim(vendor)) LIKE '% county'
        OR lower(trim(vendor)) LIKE '% city'
        OR lower(trim(vendor)) LIKE '% state'
        OR lower(trim(vendor)) LIKE '% department'
      ))
      OR
      -- Case 2: employer-matched flags with government entity employer
      (match_type IS NOT NULL AND match_type LIKE 'employer_to_%' AND donor_employer IS NOT NULL AND (
        lower(trim(donor_employer)) LIKE 'city of%'
        OR lower(trim(donor_employer)) LIKE 'city and county%'
        OR lower(trim(donor_employer)) LIKE 'city &%'
        OR lower(trim(donor_employer)) LIKE 'county of%'
        OR lower(trim(donor_employer)) LIKE 'state of%'
        OR lower(trim(donor_employer)) LIKE 'town of%'
        OR lower(trim(donor_employer)) LIKE 'district of%'
        OR lower(trim(donor_employer)) LIKE 'village of%'
        OR lower(trim(donor_employer)) LIKE 'borough of%'
        OR lower(trim(donor_employer)) LIKE '% county'
        OR lower(trim(donor_employer)) LIKE '% city'
        OR lower(trim(donor_employer)) LIKE '% state'
        OR lower(trim(donor_employer)) LIKE '% department'
      ))
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
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
    GROUP BY ai.meeting_id
  )
  SELECT
    fa.meeting_id,
    fa.flags_total,
    fa.flags_published,
    COALESCE(ia.items_scanned, 0) AS items_scanned
  FROM flag_agg fa
  LEFT JOIN item_agg ia ON ia.meeting_id = fa.meeting_id;
$$;

-- Grant access to anon role (required for Supabase client)
GRANT EXECUTE ON FUNCTION get_meeting_flag_counts(text) TO anon;
GRANT EXECUTE ON FUNCTION get_meeting_flag_counts(text) TO authenticated;
GRANT EXECUTE ON FUNCTION get_meeting_flag_counts(text) TO service_role;
