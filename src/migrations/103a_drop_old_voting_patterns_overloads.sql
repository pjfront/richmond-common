-- Migration 103a: drop old voting_patterns RPC overloads
--
-- RETROACTIVELY RECOVERED 2026-05-11. Originally applied to live Supabase
-- on 2026-04-30 (timestamp 20260430221721) by an earlier Claude Code session
-- without committing the SQL to git. Recovered via SELECT FROM
-- supabase_migrations.schema_migrations and committed here for audit trail.
--
-- Cleanup pass after 103 (voting_patterns_filter_pushdown): drops the
-- pre-pushdown function overloads that had the old single-TEXT signature.

DROP FUNCTION IF EXISTS get_contested_votes(TEXT);
DROP FUNCTION IF EXISTS get_divergent_motions_detail(TEXT);
