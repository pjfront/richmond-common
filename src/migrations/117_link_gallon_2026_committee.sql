-- Link Keycha Gallon (Council D4 2026 primary) to her existing committee.
-- Surfaced by the L4 emergent-backlog item in the post-election rearchitecture
-- sprint plan (docs/plans/2026-05-25-post-election-rearchitecture-sprint.md).
--
-- The committee "Keycha Gallon for Richmond City Council 2026" already exists
-- in the committees table (id a24f3801-9ee8-4ff2-8894-1aae09370d36, 7
-- contributions, last 2026-04-16). The election_candidates row was loaded
-- from the city_clerk source with committee_id=NULL because the candidacy
-- pre-dated the committee's first NetFile filing — the auto-linker only
-- matches at sync time when the committee already exists.
--
-- Same hand-curated UPDATE pattern as migrations 089, 100, 101.
-- Pre-election relevance: with 8 days to the 2026-06-02 primary, Gallon's
-- candidate page should show her contribution data (not appear empty).
-- Idempotent: each UPDATE is bounded by candidate name + election + city.
--
-- Wassberg (Mayor 2026 primary, also committee_id=NULL in the same liveness
-- finding) is NOT touched here — verified that no matching committee exists
-- in the DB. Wassberg is historically a perennial-no-committee candidate;
-- the NULL is correct.

DO $$
DECLARE
  v_june_2026_id UUID;
  v_committee_id UUID;
BEGIN
  SELECT id INTO v_june_2026_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-06-02';

  SELECT id INTO v_committee_id
  FROM committees
  WHERE city_fips = '0660620'
    AND name = 'Keycha Gallon for Richmond City Council 2026';

  IF v_committee_id IS NOT NULL AND v_june_2026_id IS NOT NULL THEN
    UPDATE election_candidates
    SET committee_id = v_committee_id, updated_at = NOW()
    WHERE city_fips = '0660620'
      AND election_id = v_june_2026_id
      AND normalized_name = 'keycha gallon';
  END IF;

END $$;
