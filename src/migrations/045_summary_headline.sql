-- Migration 045: Add summary_headline column for S14-A compact cards
-- Part of R1 regeneration (S12.3/S14 cohesion decision 2026-03-20)
--
-- summary_headline: one-sentence (~15-20 words) short-form summary for
-- topic board compact cards (A1), hero item teasers (A3), and category
-- drill-through cards (B6). Generated alongside plain_language_summary
-- in the same LLM call during R1.

ALTER TABLE agenda_items
ADD COLUMN IF NOT EXISTS summary_headline TEXT;

COMMENT ON COLUMN agenda_items.summary_headline IS
  'One-sentence short-form summary (~15-20 words) for compact card display. Generated during R1 alongside plain_language_summary.';
