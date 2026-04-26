-- Migration 094: Tag motions/votes with their extraction source.
--
-- S24.23 (2026-04-26) introduces transcript-based vote extraction —
-- preliminary motions+votes parsed from transcript_recap text by
-- extract_transcript_votes.py. These appear immediately after a meeting
-- (1-3 days, while we have the YouTube recording) instead of waiting
-- 4-6 weeks for official minutes_extraction.
--
-- The same (agenda_item, motion) can have BOTH a transcript-sourced row
-- (preliminary, may be incomplete) and later a minutes-sourced row
-- (ground truth). The pipeline rule: when minutes_extraction inserts
-- source='minutes' rows for an agenda_item, it first deletes any
-- existing source='transcript' rows for that item.
--
-- Frontend uses `source` to surface a "Tentative — based on KCRT
-- recording" badge on transcript-sourced motions.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS, DEFAULT 'minutes' so existing
-- rows keep their (correct) provenance.

ALTER TABLE motions
  ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'minutes';

ALTER TABLE votes
  ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'minutes';

COMMENT ON COLUMN motions.source IS
  'Origin of this motion record. ''minutes'' = extracted from official '
  'minutes PDF (ground truth, 4-6 week lag). ''transcript'' = preliminary '
  'extraction from transcript_recap text (1-3 day lag, may be incomplete). '
  'When minutes arrive, transcript-sourced rows for the same agenda_item '
  'are deleted before inserting minutes-sourced rows.';

COMMENT ON COLUMN votes.source IS
  'Origin of this vote record. Inherits semantics from motions.source.';

-- Filter index for the common "show me tentative motions" query path.
CREATE INDEX IF NOT EXISTS motions_source_idx ON motions(source);
CREATE INDEX IF NOT EXISTS votes_source_idx ON votes(source);
