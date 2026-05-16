-- Migration 112: Re-dedup independent_expenditures + add UNIQUE constraint
--
-- Background (audit B1, Phase D-2 2026-05-16): Migration 102 collapsed
-- 122,326 IE rows down to 2,252 in April 2026 — but did NOT add a unique
-- constraint. Every subsequent CAL-ACCESS bulk sync ran `INSERT ...`
-- with no ON CONFLICT, repopulating the dups. The table grew back to
-- 54,800 rows by 2026-05-16 (96% dup rate; ~2,260 unique).
--
-- Phase B finding B1 (docs/audits/2026-05-idempotency-audit.md):
-- the root cause was `src/db/expenditures.py::load_expenditures_to_db`
-- using a plain INSERT. Phase D-2 fixes the loader (ON CONFLICT +
-- RETURNING xmax=0) AND ships this migration in the SAME commit so
-- the existing dups don't survive the fix.
--
-- Two-step migration:
--   1. Dedup current rows (same logic as migration 102 — natural key
--      is (committee_name, payee_name, amount, expenditure_date,
--      support_or_oppose, candidate_name); keep highest filing_id
--      then oldest created_at).
--   2. Add a UNIQUE INDEX on that 6-tuple so the constraint is
--      structural going forward. The loader's ON CONFLICT clause
--      then has a target.
--
-- Idempotent: dedup CTE returns 0 rows once the table is clean;
-- UNIQUE INDEX uses IF NOT EXISTS.
--
-- Naming note: NULL values in candidate_name / support_or_oppose /
-- payee_name are common in the raw data. PostgreSQL treats NULL as
-- distinct from NULL for UNIQUE INDEX purposes, which would let dups
-- with NULLs re-enter the table. We use COALESCE to a sentinel
-- empty-string in the UNIQUE INDEX to make NULLs collide as expected.
-- The 6-tuple matches migration 102's dedup partition key exactly.

BEGIN;

-- Step 1: Dedup current rows
DO $$
DECLARE
  pre_count INT;
  post_count INT;
  deleted INT;
BEGIN
  SELECT COUNT(*) INTO pre_count
  FROM independent_expenditures
  WHERE city_fips = '0660620';

  RAISE NOTICE 'Migration 112: pre-dedup count = %', pre_count;

  WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
             PARTITION BY committee_name, payee_name, amount,
                          expenditure_date, support_or_oppose, candidate_name
             ORDER BY
               filing_id DESC NULLS LAST,
               created_at ASC,
               id ASC
           ) AS rn
    FROM independent_expenditures
    WHERE city_fips = '0660620'
  )
  DELETE FROM independent_expenditures
  WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

  GET DIAGNOSTICS deleted = ROW_COUNT;

  SELECT COUNT(*) INTO post_count
  FROM independent_expenditures
  WHERE city_fips = '0660620';

  RAISE NOTICE 'Migration 112: deleted %, post-dedup count = %', deleted, post_count;

  -- Sanity check: post-count should match the post-migration-102 range.
  -- If we're seeing far more than expected, something is loading rows
  -- the dedup query doesn't catch.
  IF post_count > 5000 OR post_count < 1500 THEN
    RAISE EXCEPTION 'Migration 112 sanity check failed: post-count % outside [1500, 5000]', post_count;
  END IF;
END $$;

-- Step 2: Add UNIQUE INDEX on natural key (with NULL-safe COALESCE)
-- This is the structural enforcement the loader's ON CONFLICT clause
-- targets. After this, the previous "INSERT without ON CONFLICT" would
-- raise a constraint violation rather than silently dup-writing.
CREATE UNIQUE INDEX IF NOT EXISTS uq_independent_expenditures_natural_key
  ON independent_expenditures (
    city_fips,
    committee_name,
    COALESCE(payee_name, ''),
    amount,
    expenditure_date,
    COALESCE(support_or_oppose, ''),
    COALESCE(candidate_name, '')
  );

COMMIT;
