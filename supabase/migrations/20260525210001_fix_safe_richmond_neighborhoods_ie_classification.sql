-- Reclassify the "Safe Richmond Neighborhoods supporting Ahmad Anderson for
-- Mayor 2026 sponsored by the Richmond Police Officers Association" committee
-- and link it to the 2026 primary.
--
-- Surfaced by the L5 emergent-backlog investigation in the post-election
-- rearchitecture sprint (docs/plans/2026-05-25-post-election-rearchitecture-
-- sprint.md). The committee was auto-created on 2026-05-15 when the $30K
-- RPOA contribution dated 2026-05-12 was synced (NetFile filing 216768996).
--
-- Two issues:
--   1. committee_type was set to 'candidate'. It's an Independent
--      Expenditure committee, not a candidate's own controlled committee.
--      The name pattern ("supporting X for Y sponsored by Z") and the
--      "sponsored by" phrasing are CA campaign finance indicators of a
--      committee-major-purpose IE. Set committee_type = 'pac' (existing
--      schema values are only 'candidate' and 'pac' — IE committees are
--      a CA-campaign-finance subtype of PAC, not a separate type).
--   2. election_id was NULL. Link to the 2026-06-02 primary so the IE
--      surfaces in election-cycle queries.
--
-- Pre-election relevance: with 8 days to the 2026-06-02 primary, the
-- RPOA-backed IE supporting Anderson is exactly the late-breaking
-- influence flow the project exists to surface. Misclassification means
-- it gets bucketed with candidate committees, not with IE PACs, in any
-- type-filtered view.
--
-- Idempotent: bounded by exact committee name + city. Rerunning is a
-- no-op once classification + election_id are correct.

DO $$
DECLARE
  v_june_2026_id UUID;
BEGIN
  SELECT id INTO v_june_2026_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-06-02';

  IF v_june_2026_id IS NOT NULL THEN
    UPDATE committees
    SET committee_type = 'pac',
        election_id = v_june_2026_id
    WHERE city_fips = '0660620'
      AND name = 'Safe Richmond Neighborhoods supporting Ahmad Anderson for Mayor 2026 sponsored by the Richmond Police Officers Association'
      AND (committee_type IS DISTINCT FROM 'pac' OR election_id IS DISTINCT FROM v_june_2026_id);
  END IF;

END $$;
