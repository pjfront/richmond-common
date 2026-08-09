-- Migration 136: contain the unvalidated influence-pattern taxonomy.
--
-- Migration 125 accidentally published both the taxonomy table and its
-- aggregate view to anon/authenticated clients.  These labels are analytical
-- hypotheses, not validated public findings.  Keep the data and internal
-- classifier intact, but make both relations operator/service-role only.

ALTER TABLE public.influence_patterns ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read" ON public.influence_patterns;
DROP POLICY IF EXISTS "Service role full access to influence_patterns"
    ON public.influence_patterns;
CREATE POLICY "Service role full access to influence_patterns"
    ON public.influence_patterns
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

REVOKE ALL PRIVILEGES ON TABLE public.influence_patterns
    FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON SEQUENCE public.influence_patterns_id_seq
    FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.v_influence_pattern_summary
    FROM PUBLIC, anon, authenticated;

-- Reassert the intended internal read path explicitly.  Existing broader
-- service_role grants used by operator tooling remain in place.
GRANT SELECT ON TABLE public.influence_patterns TO service_role;
GRANT USAGE, SELECT ON SEQUENCE public.influence_patterns_id_seq TO service_role;
GRANT SELECT ON TABLE public.v_influence_pattern_summary TO service_role;
