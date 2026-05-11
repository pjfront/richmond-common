-- Migration 104: list_public_tables() RPC for the /api/health endpoint.
--
-- Pre-2026-05 the health route ran 18 sequential `SELECT * FROM table LIMIT 0`
-- probes per call to detect which migration groups had been applied. Per call
-- that's 18 round-trips. Each table SELECT is cheap on its own, but the
-- handler is configured to revalidate every 5 minutes via Vercel's edge
-- cache, and the cumulative load was a small but non-trivial contributor to
-- the 2026-05-06 Supabase I/O quota pause.
--
-- This RPC exposes the public-schema table list in a single round-trip. The
-- frontend handler now calls this once per request and answers the per-group
-- "applied?" question in JS, falling back to the per-table probe if the RPC
-- is missing on a given environment (e.g., before this migration runs).
--
-- Granted to anon and authenticated because the handler is public and the
-- output is just a list of table names — same information any reader of
-- pg_tables already has.

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
