-- Migration 102: Dedup independent_expenditures table
--
-- Captured as D49 in AI-PARKING-LOT. The CAL-ACCESS bulk import of
-- EXPN_CD created amendment-duplication artifacts: every filing
-- amendment expanded each row into 28 copies, sometimes higher
-- multiples (up to 504 copies per group).
--
-- Pre-migration state (audited 2026-04-29 against Richmond fips=0660620):
--   Total rows:    122,326
--   Distinct rows: 2,252 (by committee + payee + amount + date + S/O + candidate)
--   Average dup factor: 54x
--   Multi-cycle pattern: 28, 56, 84, 112, 140, 168, 224, 252, 280, 308,
--   336, 420, 448, 504 copies per group (all multiples of 28).
--
-- Effect of dups: any aggregation of IE spending is wildly inflated.
-- East Bay Working Families' real ~$2M of activity reads as $147M in
-- the raw table. Coalition for Richmond's Future ($635K real) reads
-- much higher. This is why PAC profile pages V1 omit the IE detail
-- table entirely.
--
-- Dedup strategy: keep one row per
--   (committee_name, payee_name, amount, expenditure_date,
--    support_or_oppose, candidate_name)
-- group. Tiebreaker: highest filing_id (most recent amendment
-- supersedes earlier copies, matching the NetFile dedup pattern).
--
-- Post-migration expected count: ~2,252 rows for Richmond.
--
-- Idempotent: re-running the migration is a no-op once the table
-- is deduped (no rows match the dup-detection CTE).

BEGIN;

-- Capture pre-state for audit log (only commits if migration succeeds)
DO $$
DECLARE
  pre_count INT;
  post_count INT;
  deleted INT;
BEGIN
  SELECT COUNT(*) INTO pre_count
  FROM independent_expenditures
  WHERE city_fips = '0660620';

  RAISE NOTICE 'Migration 102 starting: % IE rows for Richmond pre-dedup', pre_count;

  WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
             PARTITION BY committee_name, payee_name, amount,
                          expenditure_date, support_or_oppose, candidate_name
             ORDER BY
               -- Prefer rows with highest filing_id (most recent amendment).
               -- NULLS LAST puts rows with no filing_id at the end.
               filing_id DESC NULLS LAST,
               -- Stable tiebreaker so the migration is deterministic
               -- across reruns: oldest created_at wins.
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

  RAISE NOTICE 'Migration 102 complete: deleted %, % IE rows remain', deleted, post_count;

  -- Sanity check: post-count should be in the expected range.
  -- If it's wildly off, something went wrong and we want to abort.
  IF post_count > 5000 OR post_count < 1500 THEN
    RAISE EXCEPTION 'Migration 102 sanity check failed: post-count % is outside expected [1500, 5000] range', post_count;
  END IF;
END $$;

COMMIT;
