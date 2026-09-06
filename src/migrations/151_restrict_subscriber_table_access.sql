-- Migration 151: private subscriber tables use service access only.
-- RLS continues to scope rows, but does not govern table-level operations
-- such as TRUNCATE. Remove implicit/default API-role table privileges too.
-- Keep existing service-role grants, policies, functions, and rows unchanged.

REVOKE ALL PRIVILEGES ON TABLE public.email_subscribers
    FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON TABLE public.email_preferences
    FROM PUBLIC, anon, authenticated;
