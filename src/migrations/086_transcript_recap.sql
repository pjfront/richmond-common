-- Transcript-based recap columns on meetings table.
-- Separate from meeting_recap (agenda-based). Generated from YouTube
-- transcript via Claude API, captures spoken-word content and debate tone.
--
-- Columns already applied via Supabase dashboard; this migration documents them.

ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_recap TEXT;
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_recap_source VARCHAR(50);
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_recap_generated_at TIMESTAMPTZ;
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_recap_emailed_at TIMESTAMPTZ;

COMMENT ON COLUMN meetings.transcript_recap IS 'Narrative recap generated from YouTube transcript (spoken-word content)';
COMMENT ON COLUMN meetings.transcript_recap_source IS 'Transcript source: youtube, granicus';
COMMENT ON COLUMN meetings.transcript_recap_generated_at IS 'When the transcript recap was generated';
COMMENT ON COLUMN meetings.transcript_recap_emailed_at IS 'When the transcript recap email was sent';
