-- Migration 058: Fix confidence_tier_desync for 2 conflict flags
--
-- Two conflict flags have confidence=0.50 with stored publication_tier=4,
-- but canonical thresholds (tier3 >= 0.50) require tier=3.
-- These were written by the scanner before S9 threshold changes.
-- Detected by data_quality_checks CI check.
--
-- This is a targeted fix for the 2 known records. S19 batch rescan
-- will reconcile all flags comprehensively.

UPDATE conflict_flags
SET publication_tier = CASE
    WHEN confidence >= 0.85 THEN 1
    WHEN confidence >= 0.70 THEN 2
    WHEN confidence >= 0.50 THEN 3
    ELSE 4
END
WHERE is_current = TRUE
  AND publication_tier IS NOT NULL
  AND publication_tier != (
      CASE
          WHEN confidence >= 0.85 THEN 1
          WHEN confidence >= 0.70 THEN 2
          WHEN confidence >= 0.50 THEN 3
          ELSE 4
      END
  );
