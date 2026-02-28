-- Migration 007: Sprint 3 — Citizen Clarity
-- Plain language summaries for agenda items (S3.1)
--
-- Adds AI-generated plain language explanations to agenda items.
-- Publication tier: Graduated (operator-only until pilot validation).
-- Idempotent: safe to run multiple times.

-- ── S3.1: Plain Language Summaries ──────────────────────────────

ALTER TABLE agenda_items
  ADD COLUMN IF NOT EXISTS plain_language_summary TEXT;

ALTER TABLE agenda_items
  ADD COLUMN IF NOT EXISTS plain_language_generated_at TIMESTAMPTZ;

ALTER TABLE agenda_items
  ADD COLUMN IF NOT EXISTS plain_language_model VARCHAR(50);

COMMENT ON COLUMN agenda_items.plain_language_summary
  IS 'AI-generated plain English explanation of this agenda item (S3.1)';

COMMENT ON COLUMN agenda_items.plain_language_generated_at
  IS 'When the plain language summary was generated';

COMMENT ON COLUMN agenda_items.plain_language_model
  IS 'Which AI model generated the summary (e.g. claude-sonnet-4-20250514)';
