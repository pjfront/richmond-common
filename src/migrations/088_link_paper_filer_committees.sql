-- Link paper-filed committees to their election candidates.
-- Paper filers don't appear in NetFile's Connect2 API, so the automatic
-- committee-candidate linking in the NetFile sync doesn't work for them.
-- This migration links committees loaded from paper filing JSON data.

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

  -- Anderson for Mayor 2026 (FPPC #1481105) → Ahmad J. Anderson
  SELECT id INTO v_committee_id
  FROM committees
  WHERE city_fips = '0660620' AND name = 'Anderson for Mayor 2026';

  IF v_committee_id IS NOT NULL THEN
    UPDATE election_candidates
    SET committee_id = v_committee_id, updated_at = NOW()
    WHERE city_fips = '0660620'
      AND election_id = v_election_id
      AND normalized_name = 'ahmad j. anderson'
      AND committee_id IS NULL;
  END IF;

END $$;
