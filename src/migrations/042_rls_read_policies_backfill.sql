-- Migration 042: Backfill "Public read" RLS policies for all tables missing them
--
-- Root cause: Supabase enables RLS on all new tables by default. Migration 027
-- added policies only for tables that existed at that time. Every table created
-- after 027 was left with RLS enabled and zero policies, making them completely
-- invisible to the anonymous frontend client (zero rows, no error).
--
-- Impact: 18 tables affected. The staleness monitor reported "never synced"
-- because data_sync_log was invisible. Public records page showed 0 despite
-- 2,382 rows. All Socrata regulatory tables, court data, and documents invisible.
--
-- Fix: Add "Public read" SELECT policy to every table that has RLS enabled
-- but no read policy. Idempotent via DROP IF EXISTS.
--
-- Prevention: test_rls_policy_coverage in tests/ now enforces that every
-- public table with RLS has at least one SELECT policy.

-- ============================================================
-- Pipeline/operational tables
-- ============================================================

DROP POLICY IF EXISTS "Public read" ON data_sync_log;
CREATE POLICY "Public read" ON data_sync_log FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON scan_runs;
CREATE POLICY "Public read" ON scan_runs FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON extraction_runs;
CREATE POLICY "Public read" ON extraction_runs FOR SELECT USING (true);

-- ============================================================
-- NextRequest / CPRA tables
-- ============================================================

DROP POLICY IF EXISTS "Public read" ON nextrequest_requests;
CREATE POLICY "Public read" ON nextrequest_requests FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON nextrequest_documents;
CREATE POLICY "Public read" ON nextrequest_documents FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON cpra_requests;
CREATE POLICY "Public read" ON cpra_requests FOR SELECT USING (true);

-- ============================================================
-- Socrata regulatory tables
-- ============================================================

DROP POLICY IF EXISTS "Public read" ON city_permits;
CREATE POLICY "Public read" ON city_permits FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON city_licenses;
CREATE POLICY "Public read" ON city_licenses FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON city_code_cases;
CREATE POLICY "Public read" ON city_code_cases FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON city_service_requests;
CREATE POLICY "Public read" ON city_service_requests FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON city_projects;
CREATE POLICY "Public read" ON city_projects FOR SELECT USING (true);

-- ============================================================
-- Document and reference tables
-- ============================================================

DROP POLICY IF EXISTS "Public read" ON documents;
CREATE POLICY "Public read" ON documents FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON document_references;
CREATE POLICY "Public read" ON document_references FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON external_references;
CREATE POLICY "Public read" ON external_references FOR SELECT USING (true);

-- ============================================================
-- Entity and financial tables
-- ============================================================

DROP POLICY IF EXISTS "Public read" ON organizations;
CREATE POLICY "Public read" ON organizations FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON entity_links;
CREATE POLICY "Public read" ON entity_links FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON court_case_parties;
CREATE POLICY "Public read" ON court_case_parties FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON independent_expenditures;
CREATE POLICY "Public read" ON independent_expenditures FOR SELECT USING (true);
