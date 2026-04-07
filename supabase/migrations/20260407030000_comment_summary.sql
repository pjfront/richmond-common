-- Migration 081: Add comment_summary column to agenda_items
-- Stores a 2-3 sentence AI-generated narrative synthesis of public comments
-- for agenda items that received public testimony.
-- Publication tier: Graduated (AI-generated content).

ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS comment_summary TEXT;
