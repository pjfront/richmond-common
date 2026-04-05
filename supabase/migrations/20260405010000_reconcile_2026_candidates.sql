-- Reconcile 2026 primary candidates against the City Clerk's official
-- Nomination Documents (Tier 1 source).
--
-- Source: https://www.ci.richmond.ca.us/DocumentCenter/View/78675
-- "501's on File — Nomination documents issued, filed, qualified"
-- Data as of: 3/6/2026 — 5 PM filing deadline
--
-- Fixes:
--   1. "Shawn Anderson" → "Ahmad J. Anderson" (wrong first name)
--   2. "Sharieff Gallon" → "Keycha Gallon" (wrong first name)
--   3. "Johnson" → "Demnlus Johnson III" (last-name-only from committee)
--   4. "Evans" → "Brandon Evans" (last-name-only from committee)
--   5. Adds Claudia Jimenez (Mayor candidate, not in NetFile data)
--   6. Updates all candidates to 'qualified' status with qualification dates

-- Add qualification_date column to election_candidates
ALTER TABLE election_candidates
  ADD COLUMN IF NOT EXISTS qualification_date DATE;

DO $$
DECLARE
  v_election_id UUID;
  v_source_url TEXT := 'https://www.ci.richmond.ca.us/DocumentCenter/View/78675';
BEGIN
  SELECT id INTO v_election_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-06-02';

  IF v_election_id IS NULL THEN
    RAISE NOTICE 'No 2026 primary election found — skipping reconciliation';
    RETURN;
  END IF;

  -- ============================================================
  -- Fix 1: "Shawn Anderson" → "Ahmad J. Anderson"
  -- ============================================================
  UPDATE election_candidates
  SET candidate_name = 'Ahmad J. Anderson',
      normalized_name = 'ahmad j. anderson',
      status = 'qualified',
      qualification_date = '2026-03-06',
      source = 'city_clerk',
      source_url = v_source_url,
      updated_at = NOW()
  WHERE city_fips = '0660620'
    AND election_id = v_election_id
    AND normalized_name = 'shawn anderson';

  -- ============================================================
  -- Fix 2: "Sharieff Gallon" → "Keycha Gallon"
  -- ============================================================
  UPDATE election_candidates
  SET candidate_name = 'Keycha Gallon',
      normalized_name = 'keycha gallon',
      status = 'qualified',
      qualification_date = '2026-03-06',
      source = 'city_clerk',
      source_url = v_source_url,
      updated_at = NOW()
  WHERE city_fips = '0660620'
    AND election_id = v_election_id
    AND normalized_name = 'sharieff gallon';

  -- ============================================================
  -- Fix 3: "Johnson" → "Demnlus Johnson III"
  -- ============================================================
  UPDATE election_candidates
  SET candidate_name = 'Demnlus Johnson III',
      normalized_name = 'demnlus johnson iii',
      status = 'qualified',
      qualification_date = '2026-03-06',
      source = 'city_clerk',
      source_url = v_source_url,
      updated_at = NOW()
  WHERE city_fips = '0660620'
    AND election_id = v_election_id
    AND normalized_name = 'johnson';

  -- ============================================================
  -- Fix 4: "Evans" → "Brandon Evans"
  -- ============================================================
  UPDATE election_candidates
  SET candidate_name = 'Brandon Evans',
      normalized_name = 'brandon evans',
      status = 'qualified',
      qualification_date = '2026-03-06',
      source = 'city_clerk',
      source_url = v_source_url,
      updated_at = NOW()
  WHERE city_fips = '0660620'
    AND election_id = v_election_id
    AND normalized_name = 'evans';

  -- ============================================================
  -- Fix 5: Add Claudia Jimenez (Mayor candidate, not in NetFile)
  -- ============================================================
  INSERT INTO election_candidates
    (city_fips, election_id, candidate_name, normalized_name,
     office_sought, status, is_incumbent, source, source_url,
     qualification_date)
  VALUES
    ('0660620', v_election_id, 'Claudia Jimenez', 'claudia jimenez',
     'Mayor', 'qualified', FALSE, 'city_clerk', v_source_url,
     '2026-03-04')
  ON CONFLICT (city_fips, election_id, normalized_name, office_sought) DO UPDATE SET
    candidate_name = EXCLUDED.candidate_name,
    status = EXCLUDED.status,
    qualification_date = EXCLUDED.qualification_date,
    source = EXCLUDED.source,
    source_url = EXCLUDED.source_url,
    updated_at = NOW();

  -- ============================================================
  -- Update remaining candidates with qualification dates and
  -- Tier 1 source attribution from City Clerk filing
  -- ============================================================

  -- Eduardo Martinez — qualified 3/6
  UPDATE election_candidates
  SET status = 'qualified', qualification_date = '2026-03-06',
      source = 'city_clerk', source_url = v_source_url, updated_at = NOW()
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'eduardo martinez';

  -- Mark Wassberg — qualified 3/2
  UPDATE election_candidates
  SET status = 'qualified', qualification_date = '2026-03-02',
      source = 'city_clerk', source_url = v_source_url, updated_at = NOW()
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'mark wassberg';

  -- Cesar Zepeda — qualified 3/6
  UPDATE election_candidates
  SET status = 'qualified', qualification_date = '2026-03-06',
      source = 'city_clerk', source_url = v_source_url, updated_at = NOW()
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'cesar zepeda';

  -- Doria Robinson — qualified 3/4
  UPDATE election_candidates
  SET status = 'qualified', qualification_date = '2026-03-04',
      source = 'city_clerk', source_url = v_source_url, updated_at = NOW()
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'doria robinson';

  -- Soheila Bana — qualified 3/2
  UPDATE election_candidates
  SET status = 'qualified', qualification_date = '2026-03-02',
      source = 'city_clerk', source_url = v_source_url, updated_at = NOW()
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'soheila bana';

  -- Jamin Pursell — qualified 3/6
  UPDATE election_candidates
  SET status = 'qualified', qualification_date = '2026-03-06',
      source = 'city_clerk', source_url = v_source_url, updated_at = NOW()
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'jamin pursell';

END $$;
