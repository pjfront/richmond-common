-- Migration 081: Add ai_comment_summary column to agenda_items
-- Stores a 2-3 sentence AI-generated narrative synthesis of public comments
-- for agenda items that received public testimony.
-- Named ai_comment_summary to avoid collision with the computed
-- comment_summary field in the frontend (speaker counts + notable speakers).
-- Publication tier: Graduated (AI-generated content).

ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS ai_comment_summary TEXT;
