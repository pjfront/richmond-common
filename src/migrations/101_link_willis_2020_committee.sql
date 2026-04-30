-- Re-link Willis 2020 candidacy to the correct cycle's committee.
-- Caught by candidacy_committee_cycle_matches liveness check on 2026-04-29.
-- Willis's 2020 candidacy was pointing at his 2024-suffixed committee
-- ("Reelect Melvin Willis for Richmond City Council District 1 2024",
-- contributions span 2024-03 to 2024-12) when it should point at the
-- no-year-suffix committee ("Reelect Melvin Willis for Richmond City
-- Council District 1", contributions span 2020-05 to 2024-07) — that
-- committee covers Willis's 2020 reelection cycle.
--
-- Same hand-curated UPDATE pattern as 089/100. Idempotent.

DO $$
DECLARE
  v_2020_election_id UUID;
  v_committee_id     UUID;
BEGIN
  SELECT id INTO v_2020_election_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2020-11-03';

  SELECT id INTO v_committee_id
  FROM committees
  WHERE city_fips = '0660620'
    AND name = 'Reelect Melvin Willis for Richmond City Council District 1';

  IF v_committee_id IS NOT NULL AND v_2020_election_id IS NOT NULL THEN
    UPDATE election_candidates
    SET committee_id = v_committee_id, updated_at = NOW()
    WHERE city_fips = '0660620'
      AND election_id = v_2020_election_id
      AND normalized_name = 'melvin willis';
  END IF;

END $$;
