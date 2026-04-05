-- Backfill official_id and committee_id on election_candidates where missing.
--
-- Candidates seeded from City Clerk data (migration 072) lack these links,
-- causing the election detail page to show "No campaign finance filings linked yet"
-- even when the candidate has contributions visible on their council profile.
--
-- The profile page routes through officials.id → committees.official_id → contributions,
-- while the election page uses election_candidates.committee_id → contributions.
-- This migration bridges the gap by populating the missing FKs.

-- Step 1: Backfill official_id by matching normalized_name against current officials
UPDATE election_candidates ec
SET official_id = o.id,
    updated_at = NOW()
FROM officials o
WHERE ec.official_id IS NULL
  AND ec.city_fips = o.city_fips
  AND ec.normalized_name = o.normalized_name
  AND o.is_current = TRUE;

-- Step 2: Backfill committee_id from the linked official's committee
UPDATE election_candidates ec
SET committee_id = c.id,
    updated_at = NOW()
FROM committees c
WHERE ec.committee_id IS NULL
  AND ec.official_id IS NOT NULL
  AND ec.city_fips = c.city_fips
  AND c.official_id = ec.official_id;
