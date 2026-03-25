-- Migration 060: Add meeting_summary column
-- Stores a 3-5 bullet narrative summary of the entire meeting,
-- generated from the meeting's agenda items, votes, and key decisions.
-- Used on the home page LatestMeetingCard and meeting detail pages.

ALTER TABLE meetings
ADD COLUMN IF NOT EXISTS meeting_summary TEXT;
