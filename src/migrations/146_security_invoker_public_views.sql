-- Migration 146: Make public summary views honor caller RLS
--
-- Supabase's Security Advisor reports these nine views because PostgreSQL
-- views run with the owner's permissions by default.  Every underlying table
-- already has RLS plus an intended public SELECT policy, so these views should
-- evaluate permissions and row policies as the invoking API role instead.
--
-- This migration changes view reloptions only.  It does not redefine a view,
-- change grants or policies, call a function, or rewrite data.
--
-- Rollback each statement with:
--   ALTER VIEW public.<view_name> RESET (security_invoker);

ALTER VIEW public.v_permit_activity
    SET (security_invoker = true);

ALTER VIEW public.v_license_summary
    SET (security_invoker = true);

ALTER VIEW public.v_code_enforcement_summary
    SET (security_invoker = true);

ALTER VIEW public.v_behested_by_official
    SET (security_invoker = true);

ALTER VIEW public.v_lobbyist_clients
    SET (security_invoker = true);

ALTER VIEW public.v_body_meeting_counts
    SET (security_invoker = true);

ALTER VIEW public.v_body_roster
    SET (security_invoker = true);

ALTER VIEW public.v_entity_connections
    SET (security_invoker = true);

ALTER VIEW public.v_topic_stats
    SET (security_invoker = true);
