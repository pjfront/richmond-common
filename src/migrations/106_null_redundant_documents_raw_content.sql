-- Migration 105: NULL redundant raw_content bytes
--
-- COST FIX (2026-05-09 architecture audit, Phase 0.8):
-- The `documents` table stored each PDF twice: once as BYTEA in raw_content,
-- once as decoded TEXT in raw_text. For PDF sources, raw_content is fully
-- recoverable from the original URL on demand and is not used by any
-- runtime code path that already has raw_text. Estimated reclaim: hundreds
-- of MB, plausibly the line item that pushed Supabase past 500 MB free tier.
--
-- We NULL the redundant bytes here rather than DROP the column because eSCRIBE
-- documents store serialized JSON (not PDF) in raw_content and `data_sync.py`
-- hydrates from it. Phase 1 migrates eSCRIBE JSON to a dedicated JSONB column
-- and then drops raw_content entirely.
--
-- Idempotent: rows already nulled are no-ops. Re-runnable safely.

UPDATE documents
SET raw_content = NULL
WHERE raw_content IS NOT NULL
  AND raw_text IS NOT NULL
  AND length(raw_text) > 0
  AND source_type != 'escribemeetings';

-- VACUUM is owned by Supabase autovacuum; physical reclaim happens
-- automatically after deletion of dead tuples. No explicit VACUUM here
-- (would require AUTOCOMMIT and is non-transactional).
