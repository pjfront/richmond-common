-- Migration 008: Sprint 3 — Citizen Clarity (continued)
-- Vote explainers for motions (S3.2)
--
-- Adds AI-generated contextual vote explanations to motions.
-- Answers: What was decided? Why does it matter? Was it contentious?
-- Publication tier: Graduated (operator-only until framing validated).
-- Idempotent: safe to run multiple times.

-- ── S3.2: Vote Explainers ────────────────────────────────────

ALTER TABLE motions
  ADD COLUMN IF NOT EXISTS vote_explainer TEXT;

ALTER TABLE motions
  ADD COLUMN IF NOT EXISTS vote_explainer_generated_at TIMESTAMPTZ;

ALTER TABLE motions
  ADD COLUMN IF NOT EXISTS vote_explainer_model VARCHAR(50);

COMMENT ON COLUMN motions.vote_explainer
  IS 'AI-generated contextual vote explanation (S3.2). What was decided, why it matters, was it contentious.';

COMMENT ON COLUMN motions.vote_explainer_generated_at
  IS 'When the vote explainer was generated';

COMMENT ON COLUMN motions.vote_explainer_model
  IS 'Which AI model generated the explainer (e.g. claude-sonnet-4-20250514)';
