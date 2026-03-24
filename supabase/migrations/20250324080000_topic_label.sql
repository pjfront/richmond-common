-- Migration 055: Add topic_label to agenda_items (S16.1)
-- Specific 1-4 word subject label extracted by LLM alongside summary.
-- Display gated by item significance (split votes, public comments).

ALTER TABLE agenda_items
ADD COLUMN IF NOT EXISTS topic_label VARCHAR(50);

COMMENT ON COLUMN agenda_items.topic_label IS
  'Specific 1-4 word subject label (e.g. "Point Molate", "Police Training Contract"). Extracted by LLM alongside summary. Display gated by item significance.';
