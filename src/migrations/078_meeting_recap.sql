-- Migration 078: Add meeting_recap column for richer post-meeting narratives
-- Complements meeting_summary (terse bullets for listings) with a multi-paragraph
-- narrative for the detail page covering decisions, votes, and public comment themes.

ALTER TABLE meetings ADD COLUMN IF NOT EXISTS meeting_recap TEXT;
