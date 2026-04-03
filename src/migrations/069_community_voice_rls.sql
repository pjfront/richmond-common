-- Migration 069: Add RLS read policies for S21 Community Voice tables.
-- Tables were created with RLS enabled (Supabase default) but no policies,
-- blocking PostgREST reads via anon role.
-- Idempotent: safe to re-run.

DROP POLICY IF EXISTS "Public read" ON comment_themes;
CREATE POLICY "Public read" ON comment_themes FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON comment_theme_assignments;
CREATE POLICY "Public read" ON comment_theme_assignments FOR SELECT USING (true);

DROP POLICY IF EXISTS "Public read" ON item_theme_narratives;
CREATE POLICY "Public read" ON item_theme_narratives FOR SELECT USING (true);
