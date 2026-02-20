-- Migration 001: Cloud Pipeline Infrastructure
-- Adds scan_runs, data_sync_log tables and extends conflict_flags
-- for temporal integrity and cloud execution tracking.
--
-- Run against existing production Supabase database.
-- Idempotent: safe to re-run (uses IF NOT EXISTS / IF NOT EXISTS checks).

-- ============================================================
-- New Table: scan_runs
-- Immutable audit log of every conflict scan execution.
-- ============================================================

CREATE TABLE IF NOT EXISTS scan_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    meeting_id UUID REFERENCES meetings(id),
    scan_mode VARCHAR(20) NOT NULL,          -- 'prospective', 'retrospective'
    data_cutoff_date DATE,                   -- for prospective: only contributions on or before this date
    model_version VARCHAR(100),              -- Claude model used
    prompt_version VARCHAR(50),              -- extraction prompt version tag
    scanner_version VARCHAR(50),             -- conflict_scanner.py git SHA or version
    contributions_count INTEGER,             -- how many contributions were considered
    contributions_sources JSONB,             -- e.g. {"calaccess": 4892, "netfile": 22143}
    form700_count INTEGER,
    flags_found INTEGER NOT NULL DEFAULT 0,
    flags_by_tier JSONB,                     -- e.g. {"tier1": 0, "tier2": 1, "tier3": 3}
    clean_items_count INTEGER,
    enriched_items_count INTEGER,
    execution_time_seconds NUMERIC(8, 2),
    triggered_by VARCHAR(50),                -- 'scheduled', 'manual', 'reanalysis', 'data_refresh'
    pipeline_run_id VARCHAR(100),            -- GitHub Actions run ID or n8n execution ID
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- 'running', 'completed', 'failed'
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'     -- audit sidecar data (bias signals, filter funnel)
);

CREATE INDEX IF NOT EXISTS idx_scan_runs_city ON scan_runs(city_fips);
CREATE INDEX IF NOT EXISTS idx_scan_runs_meeting ON scan_runs(meeting_id);
CREATE INDEX IF NOT EXISTS idx_scan_runs_mode ON scan_runs(scan_mode);
CREATE INDEX IF NOT EXISTS idx_scan_runs_created ON scan_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_scan_runs_status ON scan_runs(status);


-- ============================================================
-- New Table: data_sync_log
-- Tracks every data collection run for observability and
-- "what data was available when" queries.
-- ============================================================

CREATE TABLE IF NOT EXISTS data_sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    source VARCHAR(50) NOT NULL,             -- 'netfile', 'calaccess', 'escribemeetings', 'archive_center', 'socrata', 'nextrequest'
    sync_type VARCHAR(30) NOT NULL,          -- 'full', 'incremental', 'manual'
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    records_fetched INTEGER,
    records_new INTEGER,
    records_updated INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- 'running', 'completed', 'failed'
    error_message TEXT,
    triggered_by VARCHAR(50),                -- 'n8n_cron', 'github_actions', 'manual'
    pipeline_run_id VARCHAR(100),            -- GitHub Actions run ID or n8n execution ID
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_sync_log_city ON data_sync_log(city_fips);
CREATE INDEX IF NOT EXISTS idx_sync_log_source ON data_sync_log(source);
CREATE INDEX IF NOT EXISTS idx_sync_log_status ON data_sync_log(status);
CREATE INDEX IF NOT EXISTS idx_sync_log_started ON data_sync_log(started_at);


-- ============================================================
-- Extend conflict_flags for scan run tracking
-- ============================================================

-- Add columns if they don't exist (PostgreSQL doesn't have IF NOT EXISTS for ADD COLUMN,
-- so we use a DO block to check first)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'conflict_flags' AND column_name = 'scan_run_id'
    ) THEN
        ALTER TABLE conflict_flags ADD COLUMN scan_run_id UUID REFERENCES scan_runs(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'conflict_flags' AND column_name = 'scan_mode'
    ) THEN
        ALTER TABLE conflict_flags ADD COLUMN scan_mode VARCHAR(20);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'conflict_flags' AND column_name = 'data_cutoff_date'
    ) THEN
        ALTER TABLE conflict_flags ADD COLUMN data_cutoff_date DATE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'conflict_flags' AND column_name = 'superseded_by'
    ) THEN
        ALTER TABLE conflict_flags ADD COLUMN superseded_by UUID REFERENCES conflict_flags(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'conflict_flags' AND column_name = 'is_current'
    ) THEN
        ALTER TABLE conflict_flags ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT TRUE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_flags_scan_run ON conflict_flags(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_flags_current ON conflict_flags(meeting_id) WHERE is_current = TRUE;
