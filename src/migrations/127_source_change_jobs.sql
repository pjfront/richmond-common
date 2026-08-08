-- Durable outbox/inbox for source-change events.
--
-- source_watch_state records what the detector has observed. This table records
-- the separate obligation to process that observation. The detector inserts a
-- row before repository_dispatch, and data_sync only marks it succeeded after
-- the source sync and every required downstream enrichment have completed.

CREATE TABLE IF NOT EXISTS source_change_jobs (
    change_id VARCHAR(64) PRIMARY KEY,
    city_fips VARCHAR(7) NOT NULL DEFAULT '0660620'
        REFERENCES cities(fips_code),
    source VARCHAR(50) NOT NULL,
    watcher_source VARCHAR(50) NOT NULL,
    fingerprint JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'dispatched', 'running', 'retry_wait',
            'succeeded', 'dead_letter'
        )),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    dispatch_generation INTEGER NOT NULL DEFAULT 0
        CHECK (dispatch_generation >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_expires_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    base_completed_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    pipeline_run_id VARCHAR(100),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT source_change_jobs_change_id_format
        CHECK (change_id ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS idx_source_change_jobs_due
    ON source_change_jobs (status, next_attempt_at, lease_expires_at)
    WHERE status IN ('pending', 'dispatched', 'running', 'retry_wait');

CREATE INDEX IF NOT EXISTS idx_source_change_jobs_source_created
    ON source_change_jobs (source, created_at DESC);

ALTER TABLE source_change_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access to source_change_jobs"
    ON source_change_jobs;
CREATE POLICY "Service role full access to source_change_jobs"
    ON source_change_jobs FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

REVOKE ALL ON TABLE source_change_jobs FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE source_change_jobs TO service_role;

-- Atomically lease due work for repository_dispatch. Passing p_change_id
-- claims one newly-created job; NULL drains the retry queue. Expired dispatch
-- and worker leases are retried with the same deterministic change_id.
CREATE OR REPLACE FUNCTION claim_due_source_change_jobs(
    p_change_id VARCHAR DEFAULT NULL,
    p_limit INTEGER DEFAULT 25,
    p_lease_minutes INTEGER DEFAULT 360
)
RETURNS SETOF source_change_jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    WITH due AS MATERIALIZED (
        SELECT j.change_id
        FROM source_change_jobs AS j
        WHERE (p_change_id IS NULL OR j.change_id = p_change_id)
          AND (
              (j.status IN ('pending', 'retry_wait')
               AND j.next_attempt_at <= NOW())
              OR
              (j.status IN ('dispatched', 'running')
               AND COALESCE(j.lease_expires_at, NOW()) <= NOW())
          )
        ORDER BY j.next_attempt_at, j.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 25), 100))
    ), dead AS (
        UPDATE source_change_jobs AS j
        SET status = 'dead_letter',
            lease_expires_at = NULL,
            completed_at = NOW(),
            last_error = COALESCE(
                j.last_error,
                'Dispatch or worker lease expired after maximum attempts'
            ),
            updated_at = NOW()
        FROM due
        WHERE j.change_id = due.change_id
          AND j.attempt_count >= j.max_attempts
        RETURNING j.*
    ), claimed AS (
        UPDATE source_change_jobs AS j
        SET status = 'dispatched',
            attempt_count = j.attempt_count + 1,
            dispatch_generation = j.dispatch_generation + 1,
            dispatched_at = NOW(),
            lease_expires_at = NOW()
                + make_interval(mins => GREATEST(1, p_lease_minutes)),
            completed_at = NULL,
            pipeline_run_id = NULL,
            updated_at = NOW()
        FROM due
        WHERE j.change_id = due.change_id
          AND j.attempt_count < j.max_attempts
        RETURNING j.*
    )
    SELECT * FROM dead
    UNION ALL
    SELECT * FROM claimed;
END;
$$;

-- A delivered workflow must present the exact charged dispatch generation.
-- Delayed workflows cannot claim retry_wait/dead_letter rows or a newer
-- dispatch, so backoff and the failure budget remain authoritative.
CREATE OR REPLACE FUNCTION claim_source_change_job(
    p_change_id VARCHAR,
    p_source VARCHAR,
    p_dispatch_generation INTEGER,
    p_pipeline_run_id VARCHAR DEFAULT NULL,
    p_lease_minutes INTEGER DEFAULT 420
)
RETURNS SETOF source_change_jobs
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    UPDATE source_change_jobs AS j
    SET status = 'running',
        started_at = NOW(),
        lease_expires_at = NOW()
            + make_interval(mins => GREATEST(1, p_lease_minutes)),
        pipeline_run_id = p_pipeline_run_id,
        completed_at = NULL,
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND j.source = p_source
      AND j.status = 'dispatched'
      AND j.dispatch_generation = p_dispatch_generation
      AND j.lease_expires_at > NOW()
    RETURNING j.*;
$$;

CREATE OR REPLACE FUNCTION mark_source_change_base_completed(
    p_change_id VARCHAR,
    p_pipeline_run_id VARCHAR,
    p_dispatch_generation INTEGER
)
RETURNS SETOF source_change_jobs
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    UPDATE source_change_jobs AS j
    SET base_completed_at = COALESCE(j.base_completed_at, NOW()),
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND j.status = 'running'
      AND j.dispatch_generation = p_dispatch_generation
      AND j.pipeline_run_id IS NOT DISTINCT FROM p_pipeline_run_id
      AND j.lease_expires_at > NOW()
    RETURNING j.*;
$$;

-- Both dispatcher failures and workflow failures use the same bounded retry
-- transition. The detector's 15-minute cadence supplies the outer retry loop.
CREATE OR REPLACE FUNCTION retry_source_change_job(
    p_change_id VARCHAR,
    p_error TEXT,
    p_dispatch_generation INTEGER,
    p_pipeline_run_id VARCHAR DEFAULT NULL
)
RETURNS SETOF source_change_jobs
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    UPDATE source_change_jobs AS j
    SET status = CASE
            WHEN j.attempt_count >= j.max_attempts THEN 'dead_letter'
            ELSE 'retry_wait'
        END,
        next_attempt_at = CASE
            WHEN j.attempt_count >= j.max_attempts THEN j.next_attempt_at
            ELSE NOW() + make_interval(
                mins => LEAST(
                    60,
                    CAST(power(2, GREATEST(j.attempt_count - 1, 0)) AS INTEGER)
                )
            )
        END,
        lease_expires_at = NULL,
        completed_at = CASE
            WHEN j.attempt_count >= j.max_attempts THEN NOW()
            ELSE NULL
        END,
        last_error = LEFT(COALESCE(p_error, 'Unknown source-change failure'), 4000),
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND (
          (
              p_pipeline_run_id IS NULL
              AND p_dispatch_generation IS NOT NULL
              AND j.status = 'dispatched'
              AND j.dispatch_generation = p_dispatch_generation
          )
          OR
          (
              p_pipeline_run_id IS NOT NULL
              AND p_dispatch_generation IS NOT NULL
              AND j.status = 'running'
              AND j.dispatch_generation = p_dispatch_generation
              AND j.pipeline_run_id IS NOT DISTINCT FROM p_pipeline_run_id
              AND j.lease_expires_at > NOW()
          )
      )
    RETURNING j.*;
$$;

-- A successful bounded slice is continuation, not failure.  Undo the claim
-- increment made by claim_due_source_change_jobs and make the same event due
-- again shortly.  Base-phase completion remains durable, so the next worker
-- resumes directly at enrichment.  Ownership and a live lease fence stale
-- workers from releasing a newer claim.
CREATE OR REPLACE FUNCTION continue_source_change_job(
    p_change_id VARCHAR,
    p_pipeline_run_id VARCHAR,
    p_dispatch_generation INTEGER,
    p_delay_seconds INTEGER DEFAULT 60
)
RETURNS SETOF source_change_jobs
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    UPDATE source_change_jobs AS j
    SET status = 'retry_wait',
        attempt_count = GREATEST(j.attempt_count - 1, 0),
        next_attempt_at = NOW() + make_interval(
            secs => GREATEST(1, LEAST(COALESCE(p_delay_seconds, 60), 900))
        ),
        lease_expires_at = NULL,
        completed_at = NULL,
        last_error = NULL,
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND j.status = 'running'
      AND j.base_completed_at IS NOT NULL
      AND j.dispatch_generation = p_dispatch_generation
      AND j.pipeline_run_id IS NOT DISTINCT FROM p_pipeline_run_id
      AND j.lease_expires_at > NOW()
    RETURNING j.*;
$$;

CREATE OR REPLACE FUNCTION complete_source_change_job(
    p_change_id VARCHAR,
    p_pipeline_run_id VARCHAR,
    p_dispatch_generation INTEGER
)
RETURNS SETOF source_change_jobs
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    UPDATE source_change_jobs AS j
    SET status = 'succeeded',
        lease_expires_at = NULL,
        next_attempt_at = NOW(),
        completed_at = NOW(),
        last_error = NULL,
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND j.status = 'running'
      AND j.base_completed_at IS NOT NULL
      AND j.dispatch_generation = p_dispatch_generation
      AND j.pipeline_run_id IS NOT DISTINCT FROM p_pipeline_run_id
      AND j.lease_expires_at > NOW()
    RETURNING j.*;
$$;

REVOKE ALL ON FUNCTION claim_due_source_change_jobs(VARCHAR, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION claim_source_change_job(VARCHAR, VARCHAR, INTEGER, VARCHAR, INTEGER)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION mark_source_change_base_completed(VARCHAR, VARCHAR, INTEGER)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION retry_source_change_job(VARCHAR, TEXT, INTEGER, VARCHAR)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION continue_source_change_job(VARCHAR, VARCHAR, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION complete_source_change_job(VARCHAR, VARCHAR, INTEGER)
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION claim_due_source_change_jobs(VARCHAR, INTEGER, INTEGER)
    TO service_role;
GRANT EXECUTE ON FUNCTION claim_source_change_job(VARCHAR, VARCHAR, INTEGER, VARCHAR, INTEGER)
    TO service_role;
GRANT EXECUTE ON FUNCTION mark_source_change_base_completed(VARCHAR, VARCHAR, INTEGER)
    TO service_role;
GRANT EXECUTE ON FUNCTION retry_source_change_job(VARCHAR, TEXT, INTEGER, VARCHAR)
    TO service_role;
GRANT EXECUTE ON FUNCTION continue_source_change_job(VARCHAR, VARCHAR, INTEGER, INTEGER)
    TO service_role;
GRANT EXECUTE ON FUNCTION complete_source_change_job(VARCHAR, VARCHAR, INTEGER)
    TO service_role;

COMMENT ON TABLE source_change_jobs IS
    'Private durable delivery and completion state for source-change events.';
COMMENT ON COLUMN source_change_jobs.base_completed_at IS
    'Set after the source phase succeeds; retries may resume at enrichment.';
