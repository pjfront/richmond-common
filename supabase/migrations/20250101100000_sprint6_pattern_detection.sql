-- Migration 011: Sprint 6 — Pattern Detection
-- Adds fields for controversy scoring and time-spent stats.
-- Idempotent: safe to re-run.

-- discussion_duration_minutes: populated from video transcription (B.8).
-- Stays NULL until that pipeline exists.
ALTER TABLE agenda_items
ADD COLUMN IF NOT EXISTS discussion_duration_minutes INTEGER;

-- public_comment_count: optional materialization of COUNT from public_comments table.
-- v1 computes at query time via JOIN. This column enables future denormalization.
ALTER TABLE agenda_items
ADD COLUMN IF NOT EXISTS public_comment_count INTEGER;

-- Index for pattern detection queries: category + meeting for aggregation
CREATE INDEX IF NOT EXISTS idx_agenda_items_category_meeting
ON agenda_items(category, meeting_id);

-- Index for vote-based controversy scoring: quick tally lookups
CREATE INDEX IF NOT EXISTS idx_motions_result
ON motions(result);
