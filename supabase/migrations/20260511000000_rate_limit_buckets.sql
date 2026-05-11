-- Migration 106: Postgres-backed rate limiting (see src/migrations/106_*.sql for context)

CREATE TABLE IF NOT EXISTS rate_limit_buckets (
  bucket_key    TEXT        NOT NULL,
  window_start  TIMESTAMPTZ NOT NULL,
  count         INTEGER     NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket_key, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_buckets_window
  ON rate_limit_buckets (window_start);

ALTER TABLE rate_limit_buckets ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS rate_limit_buckets_service ON rate_limit_buckets;
CREATE POLICY rate_limit_buckets_service
  ON rate_limit_buckets FOR ALL TO service_role USING (true);

CREATE OR REPLACE FUNCTION check_and_increment_rate_limit(
  p_bucket_key  TEXT,
  p_window_secs INTEGER,
  p_max_count   INTEGER
)
RETURNS TABLE (allowed BOOLEAN, retry_after_secs INTEGER)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_window_start TIMESTAMPTZ;
  v_count INTEGER;
BEGIN
  v_window_start := to_timestamp(
    (EXTRACT(EPOCH FROM NOW())::BIGINT / p_window_secs) * p_window_secs
  );

  INSERT INTO rate_limit_buckets (bucket_key, window_start, count)
  VALUES (p_bucket_key, v_window_start, 1)
  ON CONFLICT (bucket_key, window_start)
  DO UPDATE SET count = rate_limit_buckets.count + 1
  RETURNING count INTO v_count;

  RETURN QUERY SELECT
    v_count <= p_max_count,
    GREATEST(
      0,
      p_window_secs - EXTRACT(EPOCH FROM (NOW() - v_window_start))::INTEGER
    );
END;
$$;

GRANT EXECUTE ON FUNCTION check_and_increment_rate_limit(TEXT, INTEGER, INTEGER)
  TO anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION cleanup_rate_limit_buckets()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_deleted INTEGER;
BEGIN
  DELETE FROM rate_limit_buckets
   WHERE window_start < NOW() - INTERVAL '1 day';
  GET DIAGNOSTICS v_deleted = ROW_COUNT;
  RETURN v_deleted;
END;
$$;

GRANT EXECUTE ON FUNCTION cleanup_rate_limit_buckets() TO service_role;
