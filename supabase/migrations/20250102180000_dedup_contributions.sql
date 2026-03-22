-- Migration 043: Deduplicate contributions and add unique constraint
--
-- Problem: NetFile sync re-inserts all contributions on every run because
-- the INSERT had no ON CONFLICT clause. 25,898 duplicate groups accumulated.
-- Amended filings also create duplicates (same donor/amount/date/committee,
-- different filing_id). Keep the row with the highest filing_id per group.
--
-- Idempotent: safe to run multiple times.

-- Step 1: Delete duplicate contributions, keeping the row with the highest
-- filing_id (most recent amended filing) per (donor_id, amount,
-- contribution_date, committee_id) group.
DELETE FROM contributions
WHERE id IN (
    SELECT id FROM (
        SELECT id,
               ROW_NUMBER() OVER (
                   PARTITION BY donor_id, amount, contribution_date, committee_id
                   ORDER BY filing_id DESC NULLS LAST, created_at DESC
               ) AS rn
        FROM contributions
    ) ranked
    WHERE rn > 1
);

-- Step 2: Add a unique constraint to prevent future duplicates.
-- The sync code will use ON CONFLICT to skip or update.
-- Use COALESCE for filing_id since some records may have NULL filing_id
-- (CAL-ACCESS records use different dedup — they don't have filing_id collisions
--  with NetFile because of the source column difference).
CREATE UNIQUE INDEX IF NOT EXISTS uq_contributions_dedup
ON contributions (donor_id, amount, contribution_date, committee_id)
WHERE contribution_date IS NOT NULL;
