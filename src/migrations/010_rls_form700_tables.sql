-- Migration 010: Add RLS policies for form700_filings and economic_interests
-- These were missed in migration 009. Frontend queries via anon key return
-- empty results without SELECT policies.

-- form700_filings: public read
ALTER TABLE form700_filings ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "Public read" ON form700_filings
  FOR SELECT TO public USING (true);

-- economic_interests: public read
ALTER TABLE economic_interests ENABLE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS "Public read" ON economic_interests
  FOR SELECT TO public USING (true);
