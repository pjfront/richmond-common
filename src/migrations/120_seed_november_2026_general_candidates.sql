-- Migration 120: Seed November 2026 general election candidates from the
-- CERTIFIED June 2, 2026 primary results, and record primary outcomes on
-- the primary candidacy rows.
--
-- This is the re-seed that migration 119 (cleanup of the wrongly
-- pre-seeded November rows) left instructions for. Per 119's caveat and
-- Measure J (the Richmond Election Reform Act, adopted 2024): a candidate
-- who wins MORE than 50% of the votes cast in the June primary wins the
-- seat outright and the race does NOT appear on the November ballot.
-- Otherwise the top two vote-getters advance.
--
-- CERTIFIED RESULTS (Tier 1 source: Contra Costa County Elections
-- Division, "Statewide Direct Primary Election Official Results - Final",
-- report dated 2026-06-25, https://www.contracosta.ca.gov/DocumentCenter/View/91835/
-- — county certification completed ahead of the 2026-07-02 statutory
-- canvass deadline; corroborated by Richmondside and Richmond
-- Confidential, both Tier 2):
--
--   CITY OF RICHMOND, MAYOR (22,351 votes cast; 39.77% turnout):
--     Claudia Jimenez        8,619   38.56%  -> ADVANCES to November
--     Ahmad Anderson         6,254   27.98%  -> ADVANCES to November
--     Eduardo Martinez       4,355   19.48%  -> defeated (incumbent)
--     Demnlus Johnson III    2,213    9.90%  -> defeated
--     Mark Wassberg            910    4.07%  -> defeated
--     No candidate cleared 50% -> top two advance (only Richmond race
--     on the November 2026 ballot).
--
--   CITY COUNCIL DISTRICT 2 (2,583 votes cast):
--     Cesar Zepeda           2,583  100.00%  -> ELECTED outright (unopposed)
--
--   CITY COUNCIL DISTRICT 3 (2,363 votes cast):
--     Doria Robinson         1,629   68.94%  -> ELECTED outright
--     Brandon Evans            734   31.06%  -> defeated
--
--   CITY COUNCIL DISTRICT 4 (5,067 votes cast):
--     Soheila Bana           3,431   67.71%  -> ELECTED outright
--     Jamin Pursell          1,164   22.97%  -> defeated
--     Keycha Gallon            472    9.32%  -> defeated
--
-- Therefore the November 2026 general election gets exactly TWO candidate
-- rows: Claudia Jimenez and Ahmad J. Anderson, both office_sought =
-- 'Mayor' (no district-suffix races this cycle — all three council seats
-- were settled outright in June, per 119's caveat).
--
-- Name canonicalization: the county report prints "CLAUDIA JIMÉNEZ" and
-- "AHMAD ANDERSON"; this migration reuses the repo-canonical spellings
-- established by migration 072 from the City Clerk's nomination documents
-- ("Claudia Jimenez", "Ahmad J. Anderson") so normalized_name matching
-- against the primary rows and committee linkage stays consistent.
--
-- D1 provenance: election_candidates predates D1 and carries only
-- source_url of the four required columns (manifest: grandfathered,
-- missing source_tier + confidence_score). This migration adds the three
-- missing columns (nullable — no NOT NULL backfill here) and populates
-- all four on every row it touches. Certified county results are Tier 1,
-- confidence 1.00.
--
-- NOTE (from the P0.6 plan item): migration 119's re-seed template
-- verified writes with SELECT changes() — a SQLite-ism that does not
-- exist in Postgres. This migration uses GET DIAGNOSTICS instead.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS; INSERTs use ON CONFLICT on the
-- (city_fips, election_id, normalized_name, office_sought) unique index;
-- UPDATEs are bounded by election_id + normalized_name and converge to
-- the same terminal state on re-run.

-- ============================================================
-- 1. D1 provenance columns on election_candidates
--    (source_url already exists from migration 051)
-- ============================================================

ALTER TABLE election_candidates ADD COLUMN IF NOT EXISTS source_tier INTEGER;
ALTER TABLE election_candidates ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(3,2);
ALTER TABLE election_candidates ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ;

DO $$
DECLARE
  v_primary_id UUID;
  v_general_id UUID;
  v_jimenez_official_id UUID;
  v_results_url TEXT :=
    'https://www.contracosta.ca.gov/DocumentCenter/View/91835/';
  -- Timestamp of the county's final official results report.
  v_certified_at TIMESTAMPTZ := '2026-06-25 11:55:35-07';
  v_rows INTEGER;
  v_total INTEGER := 0;
BEGIN
  SELECT id INTO v_primary_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-06-02';

  SELECT id INTO v_general_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-11-03';

  IF v_primary_id IS NULL OR v_general_id IS NULL THEN
    RAISE NOTICE 'Missing 2026 election rows (primary: %, general: %) — skipping seed.',
      v_primary_id, v_general_id;
    RETURN;
  END IF;

  -- Jimenez is a sitting councilmember; link her official record when
  -- present so council-page candidacy badges pick up the Mayor run.
  -- (She is NOT the incumbent for the office sought — is_incumbent stays
  -- FALSE on both November rows; incumbent Mayor Martinez was eliminated.)
  SELECT id INTO v_jimenez_official_id
  FROM officials
  WHERE city_fips = '0660620'
    AND normalized_name = 'claudia jimenez'
    AND is_current = TRUE;

  -- ============================================================
  -- 2. November 2026 general: seed the two advancing candidates
  --    (office_sought keeps its suffix rules per 119 — 'Mayor' has
  --    no district suffix; no council races reach November).
  -- ============================================================

  INSERT INTO election_candidates
    (city_fips, election_id, official_id, candidate_name, normalized_name,
     office_sought, status, is_incumbent, source, source_url,
     source_tier, confidence_score, extracted_at)
  VALUES
    ('0660620', v_general_id, v_jimenez_official_id,
     'Claudia Jimenez', 'claudia jimenez', 'Mayor', 'qualified', FALSE,
     'certified_results', v_results_url, 1, 1.00, v_certified_at),
    ('0660620', v_general_id, NULL,
     'Ahmad J. Anderson', 'ahmad j. anderson', 'Mayor', 'qualified', FALSE,
     'certified_results', v_results_url, 1, 1.00, v_certified_at)
  ON CONFLICT (city_fips, election_id, normalized_name, office_sought)
  DO UPDATE SET
    status = EXCLUDED.status,
    official_id = COALESCE(EXCLUDED.official_id, election_candidates.official_id),
    is_incumbent = EXCLUDED.is_incumbent,
    source = EXCLUDED.source,
    source_url = EXCLUDED.source_url,
    source_tier = EXCLUDED.source_tier,
    confidence_score = EXCLUDED.confidence_score,
    extracted_at = EXCLUDED.extracted_at,
    updated_at = NOW();

  GET DIAGNOSTICS v_rows = ROW_COUNT;
  v_total := v_total + v_rows;
  RAISE NOTICE 'November 2026 general: % candidate rows seeded/updated (expected 2).', v_rows;

  -- ============================================================
  -- 3. Primary rows: record certified outcomes via the established
  --    status vocabulary ('elected' / 'defeated' — see migration 051
  --    comment and web CandidateStatus union). Advancing candidates
  --    (Jimenez, Anderson) keep status 'qualified'; their advancement
  --    is represented by the November rows above.
  -- ============================================================

  -- Outright winners (>50% under Measure J): seats settled in June.
  UPDATE election_candidates
  SET status = 'elected',
      source = 'certified_results',
      source_url = v_results_url,
      source_tier = 1,
      confidence_score = 1.00,
      extracted_at = v_certified_at,
      updated_at = NOW()
  WHERE city_fips = '0660620'
    AND election_id = v_primary_id
    AND normalized_name IN (
      'cesar zepeda',      -- D2: 2,583 votes, 100.00% (unopposed)
      'doria robinson',    -- D3: 1,629 votes, 68.94%
      'soheila bana'       -- D4: 3,431 votes, 67.71%
    );

  GET DIAGNOSTICS v_rows = ROW_COUNT;
  v_total := v_total + v_rows;
  RAISE NOTICE 'Primary outright winners marked elected: % rows (expected 3).', v_rows;

  -- Defeated candidates (eliminated in the primary).
  UPDATE election_candidates
  SET status = 'defeated',
      source = 'certified_results',
      source_url = v_results_url,
      source_tier = 1,
      confidence_score = 1.00,
      extracted_at = v_certified_at,
      updated_at = NOW()
  WHERE city_fips = '0660620'
    AND election_id = v_primary_id
    AND normalized_name IN (
      'eduardo martinez',     -- Mayor: 4,355 votes, 19.48%
      'demnlus johnson iii',  -- Mayor: 2,213 votes,  9.90%
      'mark wassberg',        -- Mayor:   910 votes,  4.07%
      'brandon evans',        -- D3:      734 votes, 31.06%
      'jamin pursell',        -- D4:    1,164 votes, 22.97%
      'keycha gallon'         -- D4:      472 votes,  9.32%
    );

  GET DIAGNOSTICS v_rows = ROW_COUNT;
  v_total := v_total + v_rows;
  RAISE NOTICE 'Primary defeated candidates marked: % rows (expected 6).', v_rows;

  -- Advancing candidates: stamp certified-results provenance on their
  -- primary rows too (status stays 'qualified').
  UPDATE election_candidates
  SET source = 'certified_results',
      source_url = v_results_url,
      source_tier = 1,
      confidence_score = 1.00,
      extracted_at = v_certified_at,
      updated_at = NOW()
  WHERE city_fips = '0660620'
    AND election_id = v_primary_id
    AND normalized_name IN (
      'claudia jimenez',     -- Mayor: 8,619 votes, 38.56% -> November
      'ahmad j. anderson'    -- Mayor: 6,254 votes, 27.98% -> November
    );

  GET DIAGNOSTICS v_rows = ROW_COUNT;
  v_total := v_total + v_rows;
  RAISE NOTICE 'Primary advancing candidates provenance-stamped: % rows (expected 2).', v_rows;

  -- ============================================================
  -- 4. Point the primary election row at the certified results.
  -- ============================================================

  UPDATE elections
  SET source = 'registrar',
      source_url = v_results_url,
      notes = 'California statewide primary. Richmond city council seats on ballot. '
              || 'Certified by Contra Costa County 2026-06-25 (final official results). '
              || 'Under Measure J, Zepeda (D2), Robinson (D3), and Bana (D4) won outright; '
              || 'only the Mayor race (Jimenez vs. Anderson) advances to November.',
      updated_at = NOW()
  WHERE id = v_primary_id;

  GET DIAGNOSTICS v_rows = ROW_COUNT;
  v_total := v_total + v_rows;

  RAISE NOTICE 'Migration 120 complete: % total rows written.', v_total;
END $$;
