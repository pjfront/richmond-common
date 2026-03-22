-- Migration 050: Add match_details JSONB to conflict_flags
-- Stores structured metadata from scanner signal detectors (donor_name,
-- donor_employer, committee, amounts, temporal direction, etc.).
-- Previously this data was only in the human-readable description string,
-- making frontend narrative enrichment fragile.

ALTER TABLE conflict_flags ADD COLUMN IF NOT EXISTS match_details JSONB;

-- GIN index for JSONB containment queries (e.g., flags by donor_name)
CREATE INDEX IF NOT EXISTS idx_conflict_flags_match_details
    ON conflict_flags USING GIN(match_details);

-- Backfill: For v3 scanner flags that have confidence_factors but no
-- match_details, we can't reconstruct the data. New scans will populate
-- match_details going forward. A batch rescan will backfill historical flags.
