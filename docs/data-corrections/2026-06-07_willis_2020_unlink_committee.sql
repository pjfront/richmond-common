-- Data correction: unlink Melvin Willis's 2020 candidacy from wrong-cycle committee
--
-- Date applied: 2026-06-07 (via Supabase MCP execute_sql).
-- Trigger: liveness expectation `candidacy_committee_cycle_matches` failing
--   with "candidacy for Melvin Willis (2020) links to committee 'Reelect
--   Melvin Willis for Richmond City Council District 1' (2024)".
--
-- Diagnosis:
--   - election_candidates row 353590a8-d073-47aa-b5f0-c55982f3724d
--     (candidate_name='Melvin Willis', election_year=2020) had
--     committee_id pointing at 3341fca3-bdc8-4b67-a6e7-5d2108f16cfb
--     ("Reelect Melvin Willis for Richmond City Council District 1",
--     election_year=2024).
--   - Three Willis-related committees exist in our DB:
--       * b7449d5e-c870-4333-9d36-6d0890339d15 — "Melvin Willis for Mayor
--         of Richmond 2018" (filer 1403955, classified election_year=2020).
--         Filer IDs persist across cycles; this filer plausibly carried
--         Willis's 2020 D1 race, but the committee name's "Mayor 2018"
--         framing makes that ambiguous.
--       * d6c7891d-0cef-4fb4-bba6-1408b16b5874 — "Reelect Melvin Willis
--         for Richmond City Council District 1 2024" (filer 1468146, 2024)
--       * 3341fca3-bdc8-4b67-a6e7-5d2108f16cfb — "Reelect Melvin Willis
--         for Richmond City Council District 1" (filer 1426846, 2024)
--   - The 2024 committees are the wrong cycle for a 2020 candidacy.
--   - The 2018 Mayor committee may or may not be the right answer.
--
-- Choice: NULL the committee_id rather than guess. NULL says "we don't
-- know which committee filed for this candidacy" — accurate. The 2024
-- link said "his 2024 reelection committee was his 2020 committee" —
-- false, and produced cycle-mismatched contribution displays on his
-- 2020 council profile page.
--
-- Per .claude/rules/judgment-boundaries.md, "Decision queue triage for
-- data quality bugs" where the fix is mechanical is AI-delegable.
--
-- Rollback (if a future research pass identifies the actual 2020
-- committee for Willis's D1 race):
--   UPDATE election_candidates SET committee_id = '<correct_uuid>'
--     WHERE id = '353590a8-d073-47aa-b5f0-c55982f3724d';

UPDATE election_candidates
SET committee_id = NULL
WHERE id = '353590a8-d073-47aa-b5f0-c55982f3724d'::uuid
  AND candidate_name = 'Melvin Willis'
  AND committee_id = '3341fca3-bdc8-4b67-a6e7-5d2108f16cfb'::uuid;

-- Verify:
-- SELECT id, candidate_name, election_id, committee_id
--   FROM election_candidates
--   WHERE id = '353590a8-d073-47aa-b5f0-c55982f3724d';
-- Expected: committee_id IS NULL.
