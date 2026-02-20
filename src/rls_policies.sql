-- Row Level Security policies for Supabase
-- All data is public (no auth needed for MVP reads)
-- Run this in Supabase SQL Editor after deploying schema.sql

-- Enable RLS and allow public reads on all tables
ALTER TABLE cities ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON cities FOR SELECT USING (true);

ALTER TABLE officials ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON officials FOR SELECT USING (true);

ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON meetings FOR SELECT USING (true);

ALTER TABLE meeting_attendance ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON meeting_attendance FOR SELECT USING (true);

ALTER TABLE agenda_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON agenda_items FOR SELECT USING (true);

ALTER TABLE motions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON motions FOR SELECT USING (true);

ALTER TABLE votes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON votes FOR SELECT USING (true);

ALTER TABLE contributions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON contributions FOR SELECT USING (true);

ALTER TABLE donors ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON donors FOR SELECT USING (true);

ALTER TABLE committees ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON committees FOR SELECT USING (true);

ALTER TABLE conflict_flags ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON conflict_flags FOR SELECT USING (true);

ALTER TABLE closed_session_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON closed_session_items FOR SELECT USING (true);

ALTER TABLE public_comments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON public_comments FOR SELECT USING (true);

ALTER TABLE friendly_amendments ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read" ON friendly_amendments FOR SELECT USING (true);
