-- Track when the pre-meeting orientation preview email was sent to subscribers.
-- Set by /api/email/send-orientation. Used to keep the automated send idempotent
-- (only meetings where this is NULL are candidates for sending).
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS orientation_emailed_at TIMESTAMPTZ;
COMMENT ON COLUMN meetings.orientation_emailed_at IS 'When the pre-meeting orientation preview email was sent to subscribers';
