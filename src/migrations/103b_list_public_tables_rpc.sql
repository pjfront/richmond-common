-- Migration 103b: list_public_tables() RPC for /api/health single-round-trip probe
--
-- RETROACTIVELY RECOVERED 2026-05-11. Originally applied to live Supabase
-- on 2026-05-10 (timestamp 20260510043958) by an earlier Claude Code session
-- without committing the SQL to git. Recovered via SELECT FROM
-- supabase_migrations.schema_migrations and committed here for audit trail.
--
-- Note: the recovered SQL's header comment self-numbered as "Migration 104"
-- (the next sequence number at the time the past session ran). Our local
-- src/migrations/ source-of-truth tree had already filled 104 with the
-- operator_config anon-write fix, so this is renumbered 103b here to
-- preserve audit-trail ordering without colliding.
--
-- Pre-2026-05 /api/health ran 18 sequential `SELECT * FROM table LIMIT 0`
-- probes per call. This RPC returns the public table list in one round-trip;
-- the route handler then answers the per-group "applied?" question in JS.

CREATE OR REPLACE FUNCTION list_public_tables()
RETURNS TABLE (table_name TEXT)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT t.tablename::TEXT
  FROM pg_tables t
  WHERE t.schemaname = 'public'
  ORDER BY t.tablename;
$$;

GRANT EXECUTE ON FUNCTION list_public_tables() TO anon, authenticated, service_role;

COMMENT ON FUNCTION list_public_tables() IS
  'Returns public-schema table names. Used by /api/health to check applied migrations in one round-trip instead of probing each table individually.';
