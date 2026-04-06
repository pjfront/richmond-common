-- Migration 075: Add pre-meeting orientation preview to meetings
-- AI-generated narrative preview of what's on the agenda and why it matters.
-- Complements meeting_summary (post-meeting "what happened") with
-- a forward-looking "what to watch for" generated from agenda data.

ALTER TABLE meetings ADD COLUMN IF NOT EXISTS orientation_preview TEXT;
