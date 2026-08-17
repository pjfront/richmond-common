-- Migration 140: contain durable source-change retries after the Aug 14-15
-- NextRequest replay storm.
--
-- Forward-only function replacement. This file does not alter or correct
-- production civic data. Migration 134 remains forbidden and untouched.

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
                    CASE WHEN j.source = 'nextrequest' THEN 360 ELSE 60 END,
                    CAST(
                        (CASE WHEN j.source = 'nextrequest' THEN 30 ELSE 1 END)
                        * power(2, GREATEST(j.attempt_count - 1, 0))
                        AS INTEGER
                    )
                )
            )
        END,
        lease_expires_at = NULL,
        completed_at = CASE
            WHEN j.attempt_count >= j.max_attempts THEN NOW()
            ELSE NULL
        END,
        last_error = CASE
            WHEN j.attempt_count >= j.max_attempts THEN LEFT(
                format(
                    'Manual reconciliation required after %s/%s automated '
                    'attempts: %s',
                    j.attempt_count,
                    j.max_attempts,
                    COALESCE(p_error, 'Unknown source-change failure')
                ),
                4000
            )
            ELSE LEFT(
                COALESCE(p_error, 'Unknown source-change failure'),
                4000
            )
        END,
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

REVOKE ALL ON FUNCTION claim_due_source_change_jobs(VARCHAR, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION retry_source_change_job(VARCHAR, TEXT, INTEGER, VARCHAR)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION claim_due_source_change_jobs(VARCHAR, INTEGER, INTEGER)
    TO service_role;
GRANT EXECUTE ON FUNCTION retry_source_change_job(VARCHAR, TEXT, INTEGER, VARCHAR)
    TO service_role;

COMMENT ON FUNCTION retry_source_change_job(VARCHAR, TEXT, INTEGER, VARCHAR) IS
    'Bounded source-aware retry: NextRequest waits 30/60/... minutes (6h cap); exhausted work is retained for manual reconciliation.';
