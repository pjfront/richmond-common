-- Migration 015: Pipeline Journal (Autonomy Zones Phase A)
--
-- Append-only journal for pipeline self-assessment.
-- Entries are NEVER deleted or modified. The system's institutional memory.
--
-- Phase A is observation only: logs pipeline steps, anomalies, and
-- AI-generated health assessments. No self-modification.
--
-- Run manually in Supabase SQL Editor:
-- https://supabase.com/dashboard/project/ahrwvmizzykyyfavdvfv/sql/

-- ── Pipeline Journal ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pipeline_journal (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL,
    session_id UUID NOT NULL,
    entry_type VARCHAR(50) NOT NULL,
    zone VARCHAR(20) NOT NULL DEFAULT 'observation',
    target_artifact TEXT,
    description TEXT NOT NULL,
    metrics JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- entry_type values (Phase A):
--   step_completed   -- a pipeline step finished successfully
--   step_failed      -- a pipeline step failed
--   anomaly_detected -- unexpected count/timing deviation
--   run_started      -- pipeline or sync run began
--   run_completed    -- pipeline or sync run completed
--   run_failed       -- pipeline or sync run failed
--   assessment       -- self-assessment report generated

-- zone values:
--   observation  -- Phase A default (logging only, no modification)
--   free         -- Phase B: system-owned artifacts
--   proposal     -- Phase C: human-approved changes
--   sovereign    -- read-only to self-modification loop

CREATE INDEX IF NOT EXISTS idx_pj_city_created
    ON pipeline_journal(city_fips, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pj_session
    ON pipeline_journal(session_id);

CREATE INDEX IF NOT EXISTS idx_pj_type_created
    ON pipeline_journal(entry_type, created_at DESC);

-- Partial index for assessments (most common query path)
CREATE INDEX IF NOT EXISTS idx_pj_assessments
    ON pipeline_journal(city_fips, created_at DESC)
    WHERE entry_type = 'assessment';

-- Partial index for anomalies
CREATE INDEX IF NOT EXISTS idx_pj_anomalies
    ON pipeline_journal(city_fips, created_at DESC)
    WHERE entry_type = 'anomaly_detected';

COMMENT ON TABLE pipeline_journal IS
    'Append-only log for pipeline self-assessment (Autonomy Zones Phase A). Never delete or update rows.';

-- ── RLS (match existing pattern) ────────────────────────────

ALTER TABLE pipeline_journal ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'pipeline_journal' AND policyname = 'pipeline_journal_service_all'
    ) THEN
        CREATE POLICY pipeline_journal_service_all ON pipeline_journal
            FOR ALL
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;
