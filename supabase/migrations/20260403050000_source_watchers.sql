-- Source change detection state for near-live polling.
-- The change_detector.py script reads/writes this table to track
-- whether external data sources have new content since last check.

CREATE TABLE IF NOT EXISTS source_watch_state (
    source TEXT PRIMARY KEY,
    city_fips TEXT NOT NULL DEFAULT '0660620',
    fingerprint JSONB NOT NULL DEFAULT '{}',
    last_checked_at TIMESTAMPTZ DEFAULT NOW(),
    last_changed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS: service role only (not public)
ALTER TABLE source_watch_state ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access to source_watch_state" ON source_watch_state;
CREATE POLICY "Service role full access to source_watch_state"
    ON source_watch_state FOR ALL
    USING (auth.role() = 'service_role');
