-- Track the most recent meeting whose orientation preview each subscriber received.
-- Used to avoid duplicate sends: new subscribers receive the next upcoming
-- meeting's preview immediately at signup; the daily broadcast then skips
-- subscribers whose last_orientation_meeting_id already matches the meeting
-- being broadcast.
ALTER TABLE email_subscribers
  ADD COLUMN IF NOT EXISTS last_orientation_meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL;
COMMENT ON COLUMN email_subscribers.last_orientation_meeting_id IS
  'Most recent meeting whose orientation preview was emailed to this subscriber. Set by /api/subscribe (signup-time send) and /api/email/send-orientation (broadcast). Broadcast filters by: meeting_id != last_orientation_meeting_id.';
