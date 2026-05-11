-- Migration 20260430221721: drop_old_voting_patterns_overloads
-- RETROACTIVELY RECOVERED 2026-05-11. Originally applied by an
-- earlier Claude Code session without committing the SQL to git.
-- Recovered via SELECT FROM supabase_migrations.schema_migrations.

DROP FUNCTION IF EXISTS get_contested_votes(TEXT);
DROP FUNCTION IF EXISTS get_divergent_motions_detail(TEXT);
