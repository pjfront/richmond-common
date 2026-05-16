-- Migration 113: Demote historic duplicate conflict_flag rows
--
-- Background (audit B3, Phase D-4 2026-05-16): conflict_flags has 4,941
-- rows with is_current=TRUE that are duplicates of each other by
-- (meeting_id, flag_type, description). All were created during weeks
-- of 2026-03-23 and 2026-03-30; no new dups have been added since
-- 2026-04-06 (the supersede gate now fires correctly in code).
--
-- The UI's `is_current = TRUE` filter — which IS the supersede gate —
-- still serves these as "current findings," so the operator sees
-- duplicate conflict flags in dashboards and citizens see them on
-- public reports pages.
--
-- This migration is a ONE-OFF cleanup: it marks the redundant rows
-- is_current=FALSE so the UI gate hides them, without DELETING any
-- audit-trail data. The kept row in each (meeting_id, flag_type,
-- description) group is the most-recently-created one — same
-- "newer-wins" rule the supersede_flags_for_meeting function uses.
--
-- Idempotent: re-running the migration is a no-op once the cleanup
-- has run (no rows match the dup-detection CTE on is_current=TRUE).
--
-- NO data is deleted. Superseded flags retain their full audit trail
-- (scan_run_id, created_at, evidence, etc.); only is_current flips.
--
-- Correlated audit findings: B7 (25 dup scan_runs in same era) is
-- the upstream cause of B3. We do NOT touch scan_runs in this
-- migration — keep_current cleanup is sufficient for the UI impact;
-- scan_run row cleanup would lose audit history of when the dup-
-- scanning happened. Leave scan_runs as-is; let B3 cleanup carry
-- the operator-visible win.

BEGIN;

DO $$
DECLARE
  pre_current INT;
  post_current INT;
  superseded INT;
BEGIN
  SELECT COUNT(*) INTO pre_current
  FROM conflict_flags
  WHERE is_current = TRUE;

  RAISE NOTICE 'Migration 113: pre-cleanup is_current=TRUE count = %', pre_current;

  -- For each (meeting_id, flag_type, description) group with multiple
  -- is_current=TRUE rows, keep the most-recently-created one; demote
  -- the rest to is_current=FALSE.
  WITH ranked AS (
    SELECT id,
           ROW_NUMBER() OVER (
             PARTITION BY meeting_id, flag_type, description
             ORDER BY
               created_at DESC,        -- newer wins (matches supersede rule)
               id ASC                   -- stable tiebreaker
           ) AS rn
    FROM conflict_flags
    WHERE is_current = TRUE
  )
  UPDATE conflict_flags
  SET is_current = FALSE
  WHERE id IN (SELECT id FROM ranked WHERE rn > 1);

  GET DIAGNOSTICS superseded = ROW_COUNT;

  SELECT COUNT(*) INTO post_current
  FROM conflict_flags
  WHERE is_current = TRUE;

  RAISE NOTICE 'Migration 113: demoted % rows, post-cleanup is_current=TRUE count = %',
               superseded, post_current;

  -- Sanity check: post-cleanup current-count should be roughly the
  -- unique-by-key count Phase B observed (~18,144). If it's wildly
  -- off, something went wrong.
  IF post_current > 20000 OR post_current < 15000 THEN
    RAISE EXCEPTION 'Migration 113 sanity check failed: post-current=% outside [15000, 20000]', post_current;
  END IF;
END $$;

COMMIT;
