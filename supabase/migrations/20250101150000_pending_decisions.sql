-- Migration 016: Operator Decision Queue (S7.1 + S7.2)
--
-- Structured queue for decisions requiring operator judgment.
-- Decisions are created by pipeline producers (staleness, anomaly,
-- self-assessment, conflict review) and resolved by the operator
-- through Claude Code sessions.
--
-- Three-layer hybrid architecture:
--   1. Database (this table) — persistence and deduplication
--   2. Python CLI (decision_briefing.py) — primary interface via Claude Code
--   3. Web dashboard (/operator/decisions) — async read-only view
--
-- Run manually in Supabase SQL Editor:
-- https://supabase.com/dashboard/project/ahrwvmizzykyyfavdvfv/sql/

-- ── Decision Queue ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pending_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL,
    decision_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence JSONB DEFAULT '{}',
    source VARCHAR(50) NOT NULL,
    entity_type VARCHAR(50),
    entity_id TEXT,
    link TEXT,
    dedup_key VARCHAR(200),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    resolution_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- decision_type values:
--   staleness_alert     -- data source exceeded freshness threshold
--   anomaly             -- statistical deviation in meeting data
--   tier_graduation     -- feature ready for public promotion
--   conflict_review     -- conflict flag needing operator review
--   assessment_finding  -- self-assessment flagged an issue
--   pipeline_failure    -- pipeline step or run failed
--   general             -- catch-all for manual decisions

-- severity values: critical, high, medium, low, info

-- status values: pending, approved, rejected, deferred

-- ── Indexes ───────────────────────────────────────────────

-- Primary query path: pending decisions for a city, newest first
CREATE INDEX IF NOT EXISTS idx_pd_city_status
    ON pending_decisions(city_fips, status, created_at DESC);

-- Severity ordering for pending decisions
CREATE INDEX IF NOT EXISTS idx_pd_severity
    ON pending_decisions(severity, created_at DESC)
    WHERE status = 'pending';

-- Type filtering for pending decisions
CREATE INDEX IF NOT EXISTS idx_pd_type
    ON pending_decisions(decision_type)
    WHERE status = 'pending';

-- Dedup: prevent duplicate pending decisions with the same key.
-- Resolved decisions do NOT block new ones with the same key.
CREATE UNIQUE INDEX IF NOT EXISTS idx_pd_dedup_unique
    ON pending_decisions(dedup_key)
    WHERE status = 'pending' AND dedup_key IS NOT NULL;

-- Recently resolved (for dashboard "resolved" section)
CREATE INDEX IF NOT EXISTS idx_pd_resolved
    ON pending_decisions(city_fips, resolved_at DESC)
    WHERE status != 'pending';

COMMENT ON TABLE pending_decisions IS
    'Operator decision queue (S7). Created by pipeline producers, resolved in Claude Code sessions.';

-- ── RLS (match existing pattern) ──────────────────────────

ALTER TABLE pending_decisions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'pending_decisions' AND policyname = 'pending_decisions_service_all'
    ) THEN
        DROP POLICY IF EXISTS pending_decisions_service_all ON pending_decisions;
CREATE POLICY pending_decisions_service_all ON pending_decisions
            FOR ALL
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;
