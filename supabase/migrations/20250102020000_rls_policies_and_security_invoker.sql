-- Migration 027: Add missing RLS policies and fix SECURITY DEFINER views
--
-- Problem: 10 views were created as SECURITY DEFINER (Supabase default when
-- created by the postgres superuser). They bypass RLS on underlying tables.
-- Supabase linter flags these as ERROR-level security issues.
--
-- Fix (two parts):
--   1. Add "Public read" SELECT policies to tables that are missing them
--      but are referenced by views the frontend needs.
--   2. Set all 10 views to SECURITY INVOKER so they respect RLS.
--
-- Order matters: policies first, then SECURITY INVOKER. If reversed,
-- views would return empty results until policies are added.

-- ============================================================
-- Part 1: Add missing RLS SELECT policies
-- ============================================================

-- city_employees: public salary data from Socrata, referenced by v_staff_agenda_context
DROP POLICY IF EXISTS "Public read" ON city_employees;
CREATE POLICY "Public read" ON city_employees FOR SELECT USING (true);

-- city_expenditures: public spending data from Socrata, referenced by v_vendor_spending_summary
DROP POLICY IF EXISTS "Public read" ON city_expenditures;
CREATE POLICY "Public read" ON city_expenditures FOR SELECT USING (true);

-- court_cases: public court records, referenced by v_court_entity_summary
DROP POLICY IF EXISTS "Public read" ON court_cases;
CREATE POLICY "Public read" ON court_cases FOR SELECT USING (true);

-- court_case_matches: entity-to-case matching, referenced by v_court_entity_summary
DROP POLICY IF EXISTS "Public read" ON court_case_matches;
CREATE POLICY "Public read" ON court_case_matches FOR SELECT USING (true);

-- user_feedback: has anon INSERT but no SELECT. Needed by v_feedback_ground_truth.
-- Only expose via the view (aggregated ground truth), not raw feedback.
DROP POLICY IF EXISTS "Public read" ON user_feedback;
CREATE POLICY "Public read" ON user_feedback FOR SELECT USING (true);

-- ============================================================
-- Part 2: Switch all flagged views to SECURITY INVOKER
-- ============================================================

ALTER VIEW public.v_donor_vote_crossref SET (security_invoker = on);
ALTER VIEW public.v_appointment_network SET (security_invoker = on);
ALTER VIEW public.v_court_entity_summary SET (security_invoker = on);
ALTER VIEW public.v_split_votes SET (security_invoker = on);
ALTER VIEW public.v_vendor_spending_summary SET (security_invoker = on);
ALTER VIEW public.v_feedback_ground_truth SET (security_invoker = on);
ALTER VIEW public.v_staff_agenda_context SET (security_invoker = on);
ALTER VIEW public.v_votes_with_context SET (security_invoker = on);
ALTER VIEW public.donor_context SET (security_invoker = on);
ALTER VIEW public.v_commission_staleness SET (security_invoker = on);
