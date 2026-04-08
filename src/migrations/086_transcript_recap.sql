-- Transcript-based meeting recap: fast recap from YouTube/Granicus transcript
-- (separate from vote-based meeting_recap which requires official minutes).
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_recap TEXT;
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_recap_source VARCHAR(30);
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_recap_generated_at TIMESTAMPTZ;
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS transcript_recap_emailed_at TIMESTAMPTZ;
