-- Migration 116: Grant anon read access to form_summary_cache
--
-- Fixes a silent failure in D56b Option 1 (shipped 2026-05-17): the
-- candidate-profile page reads form_summary_cache via the anon Supabase
-- client to display each candidate's Form 460 cycle-to-date as their
-- headline total. Migration 114 created the table with RLS enabled but
-- only service_role had access, so the anon read returned empty, the
-- Option 1 helper fell back to summing DB rows, and the live site
-- continued showing the pre-Option-1 over-counts (Anderson: $47,602
-- instead of $40,602, etc.).
--
-- Caught by manual spot-check 2026-05-18 ~2 hours after the deploy.
-- The existing `tests/test_anon_visibility.py` pattern would have caught
-- this automatically, but form_summary_cache wasn't added to PUBLIC_TABLES
-- when the new query path was introduced — corrected in the same commit.
--
-- The cache holds only Form 460 cover-page extractions — public data
-- from public filings. No PII, no embargo. Safe for anon.
--
-- Idempotent: DROP IF EXISTS before CREATE so reapplying is a no-op.

BEGIN;

DROP POLICY IF EXISTS form_summary_cache_anon_read ON form_summary_cache;

CREATE POLICY form_summary_cache_anon_read
  ON form_summary_cache
  FOR SELECT
  TO anon, authenticated
  USING (true);

COMMIT;
