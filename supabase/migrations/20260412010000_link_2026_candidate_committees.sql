-- Link newly discovered 2026 candidate committees from paper/late filings.
-- Eduardo Martinez has a new 2026 Mayor committee (separate from his 2022 one).
-- Claudia Jimenez's committee discovered via IAFF Local 188 Form 497.

DO $$
DECLARE
  v_election_id UUID;
  v_committee_id UUID;
BEGIN
  SELECT id INTO v_election_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-06-02';

  IF v_election_id IS NULL THEN
    RAISE NOTICE 'No 2026 primary election found — skipping';
    RETURN;
  END IF;

  -- Eduardo Martinez for Mayor 2026 (FPPC #1485208)
  -- Overwrites any prior committee link — candidates with old committees from
  -- previous election cycles should be linked to their current 2026 committee.
  SELECT id INTO v_committee_id
  FROM committees
  WHERE city_fips = '0660620' AND name = 'Eduardo Martinez for Mayor 2026';

  IF v_committee_id IS NOT NULL THEN
    UPDATE election_candidates
    SET committee_id = v_committee_id, updated_at = NOW()
    WHERE city_fips = '0660620'
      AND election_id = v_election_id
      AND normalized_name = 'eduardo martinez';
  END IF;

  -- Claudia Jimenez for Mayor of Richmond 2026 (FPPC #1488504)
  SELECT id INTO v_committee_id
  FROM committees
  WHERE city_fips = '0660620' AND name = 'Claudia Jimenez for Mayor of Richmond 2026';

  IF v_committee_id IS NOT NULL THEN
    UPDATE election_candidates
    SET committee_id = v_committee_id, updated_at = NOW()
    WHERE city_fips = '0660620'
      AND election_id = v_election_id
      AND normalized_name = 'claudia jimenez';
  END IF;

END $$;
