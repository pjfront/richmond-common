-- Migration 031: Add page_url to user_feedback
-- Tracks which page the user was on when submitting feedback.
-- Valuable for operator review context and search analytics (S10.3).
-- Idempotent: safe to re-run.

ALTER TABLE user_feedback ADD COLUMN IF NOT EXISTS page_url TEXT;
