-- Migration 145: quarantine NextRequest from unscoped detector retry drains.
--
-- The 15-minute watcher is observation-only for NextRequest. Existing
-- NextRequest outbox rows remain durable and unchanged for operator review;
-- an unscoped drain cannot lease, charge, dead-letter, or dispatch them.
-- Passing their exact change_id remains atomic and available for an explicit
-- future reconciliation decision. No civic data or outbox rows are rewritten.

CREATE OR REPLACE FUNCTION claim_due_source_change_jobs(
    p_change_id VARCHAR DEFAULT NULL,
    p_limit INTEGER DEFAULT 1,
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
          AND (p_change_id IS NOT NULL OR j.source <> 'nextrequest')
          AND (
              (j.status IN ('pending', 'retry_wait')
               AND j.next_attempt_at <= NOW())
              OR
              (j.status IN ('dispatched', 'running')
               AND COALESCE(j.lease_expires_at, NOW()) <= NOW())
          )
        ORDER BY j.next_attempt_at, j.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 1), 100))
    ), dead AS (
        UPDATE source_change_jobs AS j
        SET status = 'dead_letter',
            lease_expires_at = NULL,
            completed_at = NOW(),
            last_error = COALESCE(
                j.last_error,
                'Manual reconciliation required: dispatch or worker lease '
                'expired after maximum attempts'
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

REVOKE ALL ON FUNCTION claim_due_source_change_jobs(VARCHAR, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION claim_due_source_change_jobs(VARCHAR, INTEGER, INTEGER)
    TO service_role;

COMMENT ON FUNCTION claim_due_source_change_jobs(VARCHAR, INTEGER, INTEGER) IS
    'Atomically claims due source changes; unscoped drains quarantine NextRequest while exact-ID claims remain available.';
