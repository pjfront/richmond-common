-- Migration 147: Scope operator state and civic registry writes to the service role.
-- Apply together with the operator decision route's service-client change.
-- No rows, table shapes, or unrelated policies change. Existing pipeline SQL
-- connections and service-role clients retain their access.

ALTER TABLE public.pending_decisions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pending_decisions_service_all ON public.pending_decisions;
CREATE POLICY pending_decisions_service_all ON public.pending_decisions
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL PRIVILEGES ON TABLE public.pending_decisions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.pending_decisions TO service_role;

ALTER TABLE public.pipeline_journal ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS pipeline_journal_service_all ON public.pipeline_journal;
CREATE POLICY pipeline_journal_service_all ON public.pipeline_journal
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL PRIVILEGES ON TABLE public.pipeline_journal FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.pipeline_journal TO service_role;

-- Neighborhood councils remain publicly readable. Maintenance is private.
ALTER TABLE public.neighborhood_councils ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS neighborhood_councils_service_write ON public.neighborhood_councils;
CREATE POLICY neighborhood_councils_service_write ON public.neighborhood_councils
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL PRIVILEGES ON TABLE public.neighborhood_councils FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.neighborhood_councils TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.neighborhood_councils TO service_role;
