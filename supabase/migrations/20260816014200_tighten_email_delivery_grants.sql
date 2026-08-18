-- Migration 142: remove implicit API-role privileges left by migration 141.
--
-- Supabase default privileges granted service_role more table access than the
-- delivery runtime needs and direct EXECUTE on a trigger-only function. Keep
-- the ledger writable by the bounded delivery service while reserving deletes
-- for the reviewed SECURITY DEFINER retention path.

REVOKE ALL PRIVILEGES ON TABLE public.email_deliveries
    FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE public.email_deliveries
    TO service_role;

REVOKE ALL PRIVILEGES ON FUNCTION public.record_subscription_activation_intent()
    FROM PUBLIC, anon, authenticated, service_role;
