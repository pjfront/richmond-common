-- Migration 097: Dedup 2022 candidacies for Cesar Zepeda and Doria Robinson
--
-- Surfaced via: liveness expectation `no_duplicate_candidacies_per_election`
-- (2 failures), confirmed manually via diagnostic query 2026-04-27.
--
-- Pattern (same as Claudia Jimenez 2024 in manifest expectation rationale):
-- ────────────────────────────────────────────────────────────────────
-- Each official has TWO rows for election 2022-11-08 (id ec5f43ee-…):
--
--   Row A (research seed, 2026-03-25):
--     status='elected', fppc_id=NULL,
--     committee_id → the official's CURRENT 2026 committee (WRONG cycle)
--
--   Row B (FPPC sync,    2026-04-04):
--     status='filed',   fppc_id present,
--     committee_id → the actual 2022 committee (CORRECT cycle)
--
-- Row B has the better data (FPPC link + correct committee) but the wrong
-- final status (they were 'elected', not just 'filed'). Row A has the right
-- status but wrong everything else.
--
-- Fix: promote Row B to status='elected' and delete Row A. This collapses
-- each pair into one accurate record. Three downstream liveness expectations
-- clear:
--   - no_duplicate_candidacies_per_election (both pairs)
--   - candidacy_committee_cycle_matches    (Zepeda 2022, Robinson 2022 entries)
--
-- Idempotent: each statement is keyed by (candidate_name, election_id, status).
-- Re-running after success is a no-op (UPDATE finds no row matching old status,
-- DELETE finds no row matching the seed-row predicate).

BEGIN;

-- Cesar Zepeda — promote 'filed' → 'elected'
UPDATE election_candidates
   SET status = 'elected',
       updated_at = NOW()
 WHERE city_fips = '0660620'
   AND election_id = 'ec5f43ee-b4a0-4103-944d-457af3f8dba5'
   AND candidate_name = 'Cesar Zepeda'
   AND status = 'filed'
   AND fppc_id = '1450629';

-- Cesar Zepeda — delete the duplicate seed row (no FPPC, wrong committee)
DELETE FROM election_candidates
 WHERE city_fips = '0660620'
   AND election_id = 'ec5f43ee-b4a0-4103-944d-457af3f8dba5'
   AND candidate_name = 'Cesar Zepeda'
   AND status = 'elected'
   AND fppc_id IS NULL
   AND committee_id = '83ca3946-1a97-49b6-9bf0-3ac3fcd5b384';  -- "Cesar Zepeda for Richmond City Council 2026" (wrong-cycle)

-- Doria Robinson — promote 'filed' → 'elected'
UPDATE election_candidates
   SET status = 'elected',
       updated_at = NOW()
 WHERE city_fips = '0660620'
   AND election_id = 'ec5f43ee-b4a0-4103-944d-457af3f8dba5'
   AND candidate_name = 'Doria Robinson'
   AND status = 'filed'
   AND fppc_id = '1451816';

-- Doria Robinson — delete the duplicate seed row
DELETE FROM election_candidates
 WHERE city_fips = '0660620'
   AND election_id = 'ec5f43ee-b4a0-4103-944d-457af3f8dba5'
   AND candidate_name = 'Doria Robinson'
   AND status = 'elected'
   AND fppc_id IS NULL
   AND committee_id = '1745fd6e-5cdf-4063-91f6-08d001712d80';  -- "Doria Robinson for Richmond City Council 2026" (wrong-cycle)

-- Sanity check: each candidate should now have exactly 1 row in this election.
DO $$
DECLARE
  zepeda_count int;
  robinson_count int;
BEGIN
  SELECT COUNT(*) INTO zepeda_count
    FROM election_candidates
   WHERE election_id = 'ec5f43ee-b4a0-4103-944d-457af3f8dba5'
     AND candidate_name = 'Cesar Zepeda';
  SELECT COUNT(*) INTO robinson_count
    FROM election_candidates
   WHERE election_id = 'ec5f43ee-b4a0-4103-944d-457af3f8dba5'
     AND candidate_name = 'Doria Robinson';

  IF zepeda_count <> 1 THEN
    RAISE EXCEPTION 'Expected 1 row for Cesar Zepeda after dedup, got %', zepeda_count;
  END IF;
  IF robinson_count <> 1 THEN
    RAISE EXCEPTION 'Expected 1 row for Doria Robinson after dedup, got %', robinson_count;
  END IF;
END $$;

COMMIT;
