-- Seed known 2026 primary candidates who haven't filed NetFile committees yet.
-- Source: Contra Costa County elections office, city clerk candidate filings.
-- These are public record — the candidates are on the ballot.

-- Get the 2026 primary election ID
DO $$
DECLARE
  v_election_id UUID;
  v_martinez_id UUID;
  v_bana_id UUID;
BEGIN
  SELECT id INTO v_election_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-06-02';

  IF v_election_id IS NULL THEN
    RAISE NOTICE 'No 2026 primary election found — skipping candidate seeding';
    RETURN;
  END IF;

  -- Look up officials for incumbent linking
  SELECT id INTO v_martinez_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = 'eduardo martinez' AND is_current = TRUE;

  SELECT id INTO v_bana_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = 'soheila bana' AND is_current = TRUE;

  -- Eduardo Martinez — incumbent Mayor, running for re-election
  INSERT INTO election_candidates
    (city_fips, election_id, official_id, candidate_name, normalized_name,
     office_sought, status, is_incumbent, source)
  VALUES
    ('0660620', v_election_id, v_martinez_id, 'Eduardo Martinez', 'eduardo martinez',
     'Mayor', 'filed', TRUE, 'county_elections')
  ON CONFLICT (city_fips, election_id, normalized_name, office_sought) DO UPDATE SET
    official_id = COALESCE(EXCLUDED.official_id, election_candidates.official_id),
    is_incumbent = EXCLUDED.is_incumbent,
    updated_at = NOW();

  -- Mark Wassberg — Mayor candidate
  INSERT INTO election_candidates
    (city_fips, election_id, candidate_name, normalized_name,
     office_sought, status, is_incumbent, source)
  VALUES
    ('0660620', v_election_id, 'Mark Wassberg', 'mark wassberg',
     'Mayor', 'filed', FALSE, 'county_elections')
  ON CONFLICT (city_fips, election_id, normalized_name, office_sought) DO NOTHING;

  -- Shawn Anderson — Mayor candidate
  INSERT INTO election_candidates
    (city_fips, election_id, candidate_name, normalized_name,
     office_sought, status, is_incumbent, source)
  VALUES
    ('0660620', v_election_id, 'Shawn Anderson', 'shawn anderson',
     'Mayor', 'filed', FALSE, 'county_elections')
  ON CONFLICT (city_fips, election_id, normalized_name, office_sought) DO NOTHING;

  -- Soheila Bana — incumbent District 4, running for re-election
  INSERT INTO election_candidates
    (city_fips, election_id, official_id, candidate_name, normalized_name,
     office_sought, status, is_incumbent, source)
  VALUES
    ('0660620', v_election_id, v_bana_id, 'Soheila Bana', 'soheila bana',
     'City Council District 4', 'filed', TRUE, 'county_elections')
  ON CONFLICT (city_fips, election_id, normalized_name, office_sought) DO UPDATE SET
    official_id = COALESCE(EXCLUDED.official_id, election_candidates.official_id),
    is_incumbent = EXCLUDED.is_incumbent,
    updated_at = NOW();

  -- Sharieff Gallon — District 4 challenger
  INSERT INTO election_candidates
    (city_fips, election_id, candidate_name, normalized_name,
     office_sought, status, is_incumbent, source)
  VALUES
    ('0660620', v_election_id, 'Sharieff Gallon', 'sharieff gallon',
     'City Council District 4', 'filed', FALSE, 'county_elections')
  ON CONFLICT (city_fips, election_id, normalized_name, office_sought) DO NOTHING;

  -- Fix existing candidates' office_sought to include district numbers
  -- Evans is running for District 3
  UPDATE election_candidates
  SET office_sought = 'City Council District 3'
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'evans' AND office_sought = 'City Council';

  -- Doria Robinson is running for District 3
  UPDATE election_candidates
  SET office_sought = 'City Council District 3'
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'doria robinson' AND office_sought = 'City Council';

  -- Cesar Zepeda is running for District 2
  UPDATE election_candidates
  SET office_sought = 'City Council District 2'
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'cesar zepeda' AND office_sought = 'City Council';

  -- Jamin Pursell is running for District 4
  UPDATE election_candidates
  SET office_sought = 'City Council District 4'
  WHERE city_fips = '0660620' AND election_id = v_election_id
    AND normalized_name = 'jamin pursell' AND office_sought = 'City Council';

END $$;
