-- Migration 052: Backfill RLS read policies for tables missing them
-- agenda_item_attachments (046), topics (049), item_topics (049)

ALTER TABLE agenda_item_attachments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON agenda_item_attachments;
CREATE POLICY "Public read" ON agenda_item_attachments FOR SELECT USING (true);

ALTER TABLE topics ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON topics;
CREATE POLICY "Public read" ON topics FOR SELECT USING (true);

ALTER TABLE item_topics ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON item_topics;
CREATE POLICY "Public read" ON item_topics FOR SELECT USING (true);
