-- Track when recap email was last sent to subscribers
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS recap_emailed_at TIMESTAMPTZ;
COMMENT ON COLUMN meetings.recap_emailed_at IS 'When the recap email was last sent to subscribers';
