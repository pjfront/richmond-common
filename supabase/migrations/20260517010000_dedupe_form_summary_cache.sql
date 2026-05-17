-- Migration 115: Dedupe form_summary_cache by (committee, period)
--
-- Resolves D56 (cache duplication, Bug A). The form_summary_cache table is
-- PK'd on filing_id, but a Form 460 can have multiple filing_ids over its
-- lifetime (original + one or more amendments). Each amendment's PDF was
-- being cached as a sibling row of the original, producing two rows for
-- the same underlying (committee, period_start, period_end) — see Jimenez
-- 2026 mayor and Zepeda 2026 council (each with two filings caching the
-- same Form 460 cover values, microsecond-identical extracted_at).
--
-- This migration:
--   1. Collapses existing duplicates. For each (committee, period) group
--      with >1 row, keeps the row whose filing_id actually has contribution
--      rows in the `contributions` table (the "canonical" filing — usually
--      the amendment, which the operator filed contributions under). Tie-
--      breaks by most recent updated_at.
--   2. Adds a unique expression index on (committee, period_start, period_end)
--      so the schema enforces "one cache row per (committee, period)" going
--      forward. The loader (src/load_paper_filings.py:_save_form_summary_cache)
--      is changed in the same commit to DELETE-then-INSERT, so amendments
--      replace originals instead of conflicting.
--
-- Idempotent: the DELETE uses ROW_NUMBER() so re-running the migration on
-- already-clean data is a no-op (nothing to delete). The CREATE INDEX uses
-- IF NOT EXISTS.

BEGIN;

-- Step 1: Collapse existing duplicates.
WITH ranked AS (
  SELECT fsc.filing_id,
         ROW_NUMBER() OVER (
           PARTITION BY fsc.committee,
                        fsc.summary->>'period_start',
                        fsc.summary->>'period_end'
           ORDER BY COALESCE(
                      (SELECT COUNT(*)
                         FROM contributions c
                        WHERE c.filing_id = fsc.filing_id), 0
                    ) DESC,
                    fsc.updated_at DESC,
                    fsc.filing_id DESC
         ) AS rn
    FROM form_summary_cache fsc
)
DELETE FROM form_summary_cache
 WHERE filing_id IN (SELECT filing_id FROM ranked WHERE rn > 1);

-- Step 2: Prevent regression at the schema level.
CREATE UNIQUE INDEX IF NOT EXISTS form_summary_cache_committee_period_uniq
  ON form_summary_cache (
       committee,
       (summary->>'period_start'),
       (summary->>'period_end')
     );

COMMIT;
