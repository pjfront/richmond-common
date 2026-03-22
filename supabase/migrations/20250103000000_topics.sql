-- Migration 049: Dynamic Topics + Item-Topic Junction
-- Creates the database-backed topic system for S14-P2.
-- Topics are the emergent layer on top of categories (structural taxonomy).
-- Seeded with 14 Richmond local issues from web/src/lib/local-issues.ts.

-- 1. Topics table
CREATE TABLE IF NOT EXISTS topics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
  slug VARCHAR(100) NOT NULL,
  name VARCHAR(200) NOT NULL,
  description TEXT,
  -- Which category this topic most closely aligns with (optional).
  -- Topics can span multiple categories, but one primary is useful for grouping.
  primary_category VARCHAR(50),
  -- Lifecycle: active (visible), merged (→ merged_into_id), archived (hidden)
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  merged_into_id UUID REFERENCES topics(id),
  -- Tailwind color classes for display consistency
  color_classes VARCHAR(100),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (city_fips, slug)
);

COMMENT ON TABLE topics IS
  'Dynamic civic topics discovered by LLM extraction or keyword matching. Emergent layer on top of categories.';

-- 2. Item-Topics junction table (many-to-many)
CREATE TABLE IF NOT EXISTS item_topics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agenda_item_id UUID NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
  topic_id UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
  -- How confident are we in this assignment?
  confidence REAL NOT NULL DEFAULT 1.0,
  -- How was this assignment made?
  -- 'keyword' = matched from keyword list, 'llm' = LLM extraction, 'manual' = operator
  source VARCHAR(20) NOT NULL DEFAULT 'keyword',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (agenda_item_id, topic_id)
);

COMMENT ON TABLE item_topics IS
  'Junction table linking agenda items to topics. An item can have multiple topics.';

-- 3. Indexes
CREATE INDEX IF NOT EXISTS idx_item_topics_topic_id ON item_topics(topic_id);
CREATE INDEX IF NOT EXISTS idx_item_topics_agenda_item_id ON item_topics(agenda_item_id);
CREATE INDEX IF NOT EXISTS idx_topics_status ON topics(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_topics_city_fips ON topics(city_fips);

-- 4. Summary view: topic stats
CREATE OR REPLACE VIEW v_topic_stats AS
SELECT
  t.id,
  t.slug,
  t.name,
  t.primary_category,
  t.status,
  t.color_classes,
  COUNT(DISTINCT it.agenda_item_id) AS item_count,
  MIN(m.meeting_date) AS first_seen,
  MAX(m.meeting_date) AS last_seen
FROM topics t
LEFT JOIN item_topics it ON it.topic_id = t.id
LEFT JOIN agenda_items ai ON ai.id = it.agenda_item_id
LEFT JOIN meetings m ON m.id = ai.meeting_id
WHERE t.status = 'active'
GROUP BY t.id, t.slug, t.name, t.primary_category, t.status, t.color_classes;

-- 5. Seed Richmond local issues as initial topics
-- These match the 14 issues in web/src/lib/local-issues.ts
INSERT INTO topics (city_fips, slug, name, description, primary_category, color_classes)
VALUES
  ('0660620', 'chevron', 'Chevron & the Refinery',
   'Chevron Richmond is the city''s largest employer, taxpayer, and political spender. The 2012 refinery fire and $3.1M in 2014 election spending are defining events.',
   'environment', 'bg-red-100 text-red-800'),
  ('0660620', 'point-molate', 'Point Molate',
   'Former Navy fuel depot on the Richmond shoreline. Decades of developer proposals, tribal interests, environmental concerns, and community debate.',
   'zoning', 'bg-emerald-100 text-emerald-800'),
  ('0660620', 'rent-board', 'Rent Board & Tenants',
   'Richmond passed rent control in 2016. The Rent Board sets annual adjustments and hears eviction cases. Tenant protection is a defining progressive policy.',
   'housing', 'bg-violet-100 text-violet-800'),
  ('0660620', 'hilltop', 'The Hilltop',
   'Hilltop Mall closed in 2020. Its redevelopment into housing, retail, and community space is the biggest land-use question in the city.',
   'zoning', 'bg-amber-100 text-amber-800'),
  ('0660620', 'terminal-port', 'Terminal 1 & the Port',
   'Terminal 1 is being redeveloped for mixed use. The Port of Richmond handles shipping and is exploring ferry service and offshore wind.',
   'infrastructure', 'bg-sky-100 text-sky-800'),
  ('0660620', 'ford-point', 'Ford Point & Richmond Village',
   'The former Ford Assembly plant is now mixed-use (Craneway Pavilion, Assemble). Richmond Village is a major housing development nearby.',
   'zoning', 'bg-cyan-100 text-cyan-800'),
  ('0660620', 'macdonald', 'Macdonald Avenue',
   'Richmond''s main commercial corridor through the Iron Triangle. The Macdonald Avenue Corridor Task Force is driving revitalization.',
   'infrastructure', 'bg-orange-100 text-orange-800'),
  ('0660620', 'police-reform', 'Police & Community Safety',
   'Richmond pioneered the Office of Neighborhood Safety and community policing reform. The Community Police Review Commission provides civilian oversight.',
   'public_safety', 'bg-blue-100 text-blue-800'),
  ('0660620', 'environment', 'Environmental Justice',
   'As a refinery town, Richmond faces unique air quality and contamination challenges. Environmental justice is deeply tied to neighborhood health equity.',
   'environment', 'bg-teal-100 text-teal-800'),
  ('0660620', 'labor', 'Labor & City Workers',
   'SEIU Local 1021 represents most city employees. MOU negotiations, overtime, pensions, and staffing levels are perennial budget tensions.',
   'personnel', 'bg-indigo-100 text-indigo-800'),
  ('0660620', 'cannabis', 'Cannabis',
   'Richmond has gone back and forth on dispensary regulations. Cannabis tax revenue and social equity licensing are active debates.',
   'governance', 'bg-lime-100 text-lime-800'),
  ('0660620', 'youth', 'Youth & Community Programs',
   'Richmond invests heavily in youth programs — RYSE Center, Youth Outdoors, mentoring, workforce development.',
   'budget', 'bg-pink-100 text-pink-800'),
  ('0660620', 'political-statements', 'Political Statements',
   'Richmond''s council regularly passes resolutions on national and international issues — from foreign policy to civil rights.',
   'governance', 'bg-fuchsia-100 text-fuchsia-800'),
  ('0660620', 'housing-development', 'Housing & Homelessness',
   'Beyond rent control, Richmond faces housing production pressure from the state, Homekey projects for homelessness, and Housing Element compliance.',
   'housing', 'bg-purple-100 text-purple-800')
ON CONFLICT (city_fips, slug) DO NOTHING;
