-- Migration 119: Remove wrongly pre-seeded November 2026 general election
-- candidates. Discovered 2026-06-03 when the November election page went
-- live and showed garbage data to the public.
--
-- ROOT CAUSE: Three independent problems in data seeded by migrations
-- 071/072/097/100 before primary results were known:
--
--   1. WRONG office_sought — candidates copied from June primary rows but
--      the November rows lost their district suffixes (e.g.,
--      "City Council District 2" became "City Council"). The frontend
--      groups by office_sought, so Cesar Zepeda (D2) and Doria Robinson
--      (D3) collapsed into a single fake "City Council" race.
--
--   2. WRONG candidate name — "Johnson" (Mayor, November) is a stub that
--      doesn't match any real person. Demnlus Johnson III ran in the June
--      primary under his full name; this row was a placeholder that never
--      got cleaned up.
--
--   3. PREMATURE — general election candidates can only be known after the
--      June primary is certified (2026-06-02 + canvass period). Seeding
--      November rows before primary results was purely for committee-
--      linking purposes (migrations 097/100) and was never meant to be
--      shown to users.
--
-- FIX: Delete all 7 rows. The November general election row in the
-- `elections` table stays (correct date, correct name). The
-- `election_candidates` table will be empty for the November election
-- until a future migration seeds the actual winners after certification.
-- The frontend now shows a "primary results pending" state when no
-- candidates exist for a general election.
--
-- HOW TO RE-SEED AFTER RESULTS ARE CERTIFIED:
-- Run a migration following this pattern, filling in actual winners.
-- All office_sought values must include the district suffix so the
-- frontend's byOffice grouping creates the right race sections:
--
--   INSERT INTO election_candidates
--     (city_fips, election_id, candidate_name, normalized_name,
--      office_sought, status, is_incumbent, source, source_url)
--   SELECT '0660620', e.id, '<NAME>', '<normalized>', '<OFFICE>', 'qualified',
--          <bool>, 'certified_results', '<results URL>'
--   FROM elections e
--   WHERE city_fips = '0660620' AND election_date = '2026-11-03'
--   ON CONFLICT (city_fips, election_id, normalized_name, office_sought)
--   DO UPDATE SET status = EXCLUDED.status, updated_at = NOW();
--
-- Seats on the November 2026 ballot (4-year terms; 2022 electees
-- are all up in 2026):
--   'Mayor'                    -- top-2 from June primary advance
--   'City Council District 2'  -- Zepeda (incumbent) + whoever advanced
--   'City Council District 3'  -- Robinson (incumbent) + Evans
--   'City Council District 4'  -- Bana (incumbent) vs Pursell
-- In California primaries, a candidate who clears 50%+1 wins outright
-- and the seat does not appear on the November ballot. Check certified
-- primary results before seeding — a district race may be settled in
-- June and should be omitted from the November rows.
--
-- Idempotent: DELETE WHERE is bounded to the specific election_id.

DO $$
DECLARE
  v_nov_2026_id UUID;
BEGIN
  SELECT id INTO v_nov_2026_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-11-03';

  IF v_nov_2026_id IS NOT NULL THEN
    DELETE FROM election_candidates
    WHERE city_fips = '0660620'
      AND election_id = v_nov_2026_id;

    RAISE NOTICE 'Deleted % pre-seeded November 2026 candidates.',
      (SELECT changes());
  END IF;
END $$;
