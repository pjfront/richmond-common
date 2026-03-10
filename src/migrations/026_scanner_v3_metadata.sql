-- Migration 026: Add scanner v3 metadata columns to conflict_flags
-- Stores composite confidence factor breakdown and scanner version tracking.
-- Idempotent: safe to re-run.

-- JSONB column storing the breakdown of composite confidence scoring.
-- Example: {"match_strength": 0.85, "temporal_factor": 0.7, "financial_factor": 0.6, "anomaly_factor": 0.5}
ALTER TABLE conflict_flags ADD COLUMN IF NOT EXISTS confidence_factors JSONB;

-- Scanner version that produced each flag (2=monolithic, 3=signal-based v3).
-- Allows batch rescan comparisons and rollback.
ALTER TABLE conflict_flags ADD COLUMN IF NOT EXISTS scanner_version INT DEFAULT 2;

-- Index for filtering by scanner version (useful for batch rescan comparisons)
CREATE INDEX IF NOT EXISTS idx_conflict_flags_scanner_version
    ON conflict_flags(scanner_version);

-- Index for querying confidence factor breakdowns (GIN for JSONB containment queries)
CREATE INDEX IF NOT EXISTS idx_conflict_flags_confidence_factors
    ON conflict_flags USING GIN(confidence_factors);
