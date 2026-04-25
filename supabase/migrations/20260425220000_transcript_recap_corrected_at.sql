-- Migration 093: Track when transcript_recap was post-processed by the
-- name-correction pass.
--
-- S24.22b (2026-04-25) introduced correct_recap_names.py which sends an
-- existing transcript_recap through Claude with canonical_names.md as
-- authority and writes back the corrected text. This column lets us:
--   * tell operators when a recap was last corrected
--   * skip re-running corrections on already-corrected recaps unless --force
--   * surface "corrected after generation" provenance in the UI if needed
--
-- Idempotent: ADD COLUMN IF NOT EXISTS.

ALTER TABLE meetings
  ADD COLUMN IF NOT EXISTS transcript_recap_corrected_at TIMESTAMPTZ;

COMMENT ON COLUMN meetings.transcript_recap_corrected_at IS
  'When transcript_recap was last post-processed by correct_recap_names.py '
  '(name-correction pass using canonical_names.md). NULL if never corrected.';
