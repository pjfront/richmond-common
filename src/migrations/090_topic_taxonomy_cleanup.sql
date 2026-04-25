-- Migration 089: Topic Taxonomy Cleanup — DB as Source of Truth (S28.0)
--
-- Makes the `topics` table the authoritative source for the topic taxonomy.
-- Before this migration: taxonomy was duplicated across src/topic_tagger.py
-- (Python TOPIC_DEFS), web/src/lib/local-issues.ts (RICHMOND_LOCAL_ISSUES),
-- and the `topics` table (seeded without keywords in migration 049).
--
-- This migration:
--   1. Adds a `keywords TEXT[]` column to `topics` for keyword-based matching
--   2. Backfills keywords for all 14 existing topics (data mirrored from
--      src/topic_tagger.py TOPIC_DEFS as of 2026-04-15)
--
-- After this migration, src/topic_tagger.py can load TopicDef list from the
-- database via load_topic_defs_from_db(), and web/src/lib/queries.ts exposes
-- getTopicTaxonomy() as the frontend's source of truth.
--
-- Idempotent: safe to re-run.

-- 1. Add keywords column
ALTER TABLE topics
  ADD COLUMN IF NOT EXISTS keywords TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN topics.keywords IS
  'Lowercased substrings matched against agenda item text and news article text. Case-insensitive substring match; any hit counts.';

-- 2. GIN index for array containment and overlap queries
CREATE INDEX IF NOT EXISTS idx_topics_keywords_gin
  ON topics USING GIN (keywords);

-- 3. Backfill keywords for each active topic
-- Data mirrors src/topic_tagger.py TOPIC_DEFS as of 2026-04-15.
-- Updates are idempotent: re-running will reset to this canonical list.

UPDATE topics SET keywords = ARRAY[
  'chevron', 'refinery', 'richmond refinery',
  'flaring', 'flare', 'crude oil', 'hydrogen',
  'community benefits agreement', 'cba',
  'richmond standard'
] WHERE city_fips = '0660620' AND slug = 'chevron';

UPDATE topics SET keywords = ARRAY[
  'point molate', 'pt. molate', 'pt molate',
  'winehaven', 'wine haven'
] WHERE city_fips = '0660620' AND slug = 'point-molate';

UPDATE topics SET keywords = ARRAY[
  'rent control', 'rent board', 'rent program',
  'rent stabilization', 'rent adjustment',
  'just cause', 'just cause eviction',
  'tenant', 'tenants', 'tenant protection',
  'eviction', 'relocation payment',
  'habitability', 'rental inspection'
] WHERE city_fips = '0660620' AND slug = 'rent-board';

UPDATE topics SET keywords = ARRAY[
  'hilltop', 'hilltop mall', 'hilltop district',
  'dream fleetwood'
] WHERE city_fips = '0660620' AND slug = 'hilltop';

UPDATE topics SET keywords = ARRAY[
  'terminal 1', 'terminal one',
  'port of richmond', 'port director',
  'maritime', 'ferry service', 'ferry terminal',
  'offshore wind', 'wharf'
] WHERE city_fips = '0660620' AND slug = 'terminal-port';

UPDATE topics SET keywords = ARRAY[
  'ford assembly', 'ford point', 'ford building',
  'richmond village', 'craneway',
  'assemble', 'marina bay'
] WHERE city_fips = '0660620' AND slug = 'ford-point';

UPDATE topics SET keywords = ARRAY[
  'macdonald avenue', 'macdonald corridor',
  'macdonald task force',
  'iron triangle',
  'downtown richmond'
] WHERE city_fips = '0660620' AND slug = 'macdonald';

UPDATE topics SET keywords = ARRAY[
  'police', 'rpd', 'police department',
  'public safety', 'law enforcement',
  'officer involved', 'officer-involved',
  'use of force', 'body-worn camera', 'body worn camera',
  'community police review', 'cprc',
  'crisis intervention', 'crisis response',
  'neighborhood safety', 'ons',
  'gun violence', 'firearm',
  'crime report', 'crime prevention'
] WHERE city_fips = '0660620' AND slug = 'police-reform';

UPDATE topics SET keywords = ARRAY[
  'climate', 'environmental',
  'greenhouse', 'carbon', 'emissions',
  'air quality', 'air monitoring',
  'pollution', 'contamination', 'contaminated',
  'brownfield', 'remediation', 'superfund',
  'toxic', 'hazardous',
  'green new deal', 'solar', 'sustainability',
  'transformative climate',
  'urban greening', 'greenway', 'richmond greenway'
] WHERE city_fips = '0660620' AND slug = 'environment';

UPDATE topics SET keywords = ARRAY[
  'seiu', 'local 1021',
  'memorandum of understanding',
  'collective bargaining',
  'overtime report', 'pension',
  'opeb', 'other post-employment',
  'staffing', 'vacancy', 'vacancies',
  'cost of living increase'
] WHERE city_fips = '0660620' AND slug = 'labor';

UPDATE topics SET keywords = ARRAY[
  'cannabis', 'marijuana',
  'dispensary', 'dispensaries',
  'cannabis tax'
] WHERE city_fips = '0660620' AND slug = 'cannabis';

UPDATE topics SET keywords = ARRAY[
  'youth', 'young adults',
  'youth outdoors richmond',
  'ryse', 'mentoring', 'mentor',
  'afterschool', 'after-school', 'after school',
  'workforce development board',
  'job training', 'job center',
  'american job centers'
] WHERE city_fips = '0660620' AND slug = 'youth';

UPDATE topics SET keywords = ARRAY[
  'opposing', 'condemning',
  'in support of', 'in opposition to',
  'urging', 'calling upon',
  'ceasefire', 'solidarity',
  'resolution declaring', 'resolution opposing',
  'resolution supporting', 'resolution urging',
  'sanctuary', 'immigrant', 'immigration',
  'juneteenth', 'pride month',
  'day of remembrance', 'black history',
  'military intervention'
] WHERE city_fips = '0660620' AND slug = 'political-statements';

UPDATE topics SET keywords = ARRAY[
  'affordable housing', 'housing element',
  'housing authority', 'homekey',
  'homeless', 'homelessness', 'encampment',
  'transitional housing', 'supportive housing',
  'section 8', 'housing voucher',
  'inclusionary'
] WHERE city_fips = '0660620' AND slug = 'housing-development';

-- 4. Sanity check: every active topic should now have keywords
DO $$
DECLARE
  empty_count integer;
BEGIN
  SELECT COUNT(*) INTO empty_count
  FROM topics
  WHERE city_fips = '0660620'
    AND status = 'active'
    AND (keywords IS NULL OR array_length(keywords, 1) IS NULL);

  IF empty_count > 0 THEN
    RAISE WARNING 'Migration 089: % active topics still have empty keywords. Check slug mismatches.', empty_count;
  END IF;
END $$;
