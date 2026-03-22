-- Migration 047: Business entity resolution tables
-- Supports OpenCorporates integration for LLC ownership chain detection,
-- donor-vendor cross-reference, and permit-donor conflict signals.
-- Three tables: business_entities (Layer 2), officers, and name match bridge.

-- ============================================================
-- 1. business_entities — resolved corporate/LLC/LP registrations
-- ============================================================
CREATE TABLE IF NOT EXISTS business_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    entity_number TEXT,                    -- CA SOS number (e.g., C3268102)
    jurisdiction_code TEXT NOT NULL DEFAULT 'us_ca',
    entity_type TEXT,                      -- Domestic LLC, Domestic Stock, Foreign Stock, etc.
    current_status TEXT,                   -- Active, Dissolved, Suspended
    incorporation_date DATE,
    dissolution_date DATE,
    registered_address TEXT,
    agent_name TEXT,
    agent_address TEXT,
    opencorporates_url TEXT,
    raw_response JSONB,                    -- Full API response for re-extraction
    source_url TEXT NOT NULL,
    source_publisher TEXT NOT NULL DEFAULT 'California Secretary of State',
    source_tier INTEGER NOT NULL DEFAULT 1,
    retrieved_at TIMESTAMPTZ NOT NULL,     -- When OC last pulled from SOS
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confidence_score NUMERIC(3,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_business_entities_city_fips
    ON business_entities(city_fips);
CREATE INDEX IF NOT EXISTS idx_business_entities_name
    ON business_entities(entity_name);
CREATE INDEX IF NOT EXISTS idx_business_entities_number
    ON business_entities(entity_number);
CREATE INDEX IF NOT EXISTS idx_business_entities_jurisdiction
    ON business_entities(jurisdiction_code);

-- Prevent duplicate entities (same entity number in same jurisdiction)
CREATE UNIQUE INDEX IF NOT EXISTS uq_business_entities_number_jurisdiction
    ON business_entities(entity_number, jurisdiction_code)
    WHERE entity_number IS NOT NULL;


-- ============================================================
-- 2. business_entity_officers — officers/directors/agents
-- ============================================================
CREATE TABLE IF NOT EXISTS business_entity_officers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    business_entity_id UUID NOT NULL REFERENCES business_entities(id) ON DELETE CASCADE,
    officer_name TEXT NOT NULL,
    position TEXT,
    start_date DATE,
    end_date DATE,
    is_inactive BOOLEAN DEFAULT FALSE,
    opencorporates_officer_id BIGINT,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_officers_entity
    ON business_entity_officers(business_entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_officers_name
    ON business_entity_officers(officer_name);


-- ============================================================
-- 3. entity_name_matches — bridge table linking source records
--    (contributions, permits, contracts) to resolved entities
-- ============================================================
CREATE TABLE IF NOT EXISTS entity_name_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,             -- Name as it appears in source record
    source_table TEXT NOT NULL,            -- e.g., 'donors', 'permits'
    source_record_id UUID NOT NULL,
    business_entity_id UUID REFERENCES business_entities(id) ON DELETE SET NULL,
    match_confidence NUMERIC(3,2) NOT NULL,
    match_method TEXT NOT NULL,            -- 'exact', 'normalized', 'fuzzy', 'entity_number'
    reviewed BOOLEAN DEFAULT FALSE,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_name_matches_source
    ON entity_name_matches(source_name);
CREATE INDEX IF NOT EXISTS idx_name_matches_entity
    ON entity_name_matches(business_entity_id);
CREATE INDEX IF NOT EXISTS idx_name_matches_source_table
    ON entity_name_matches(source_table, source_record_id);
-- For operator review queue: unreviewed matches below auto-threshold
CREATE INDEX IF NOT EXISTS idx_name_matches_review_queue
    ON entity_name_matches(reviewed, match_confidence)
    WHERE reviewed = FALSE;


-- ============================================================
-- 4. API usage tracking for rate limit management
-- ============================================================
CREATE TABLE IF NOT EXISTS opencorporates_api_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint TEXT NOT NULL,                -- 'companies/search', 'companies/{number}', 'officers/search'
    query_params JSONB,                    -- What was searched
    response_status INTEGER NOT NULL,      -- HTTP status code
    called_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oc_api_usage_called_at
    ON opencorporates_api_usage(called_at);


-- ============================================================
-- 5. RLS policies — public read for data tables
-- ============================================================
ALTER TABLE business_entities ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'business_entities' AND policyname = 'Public read') THEN
    DROP POLICY IF EXISTS "Public read" ON business_entities;
CREATE POLICY "Public read" ON business_entities FOR SELECT USING (true);
  END IF;
END $$;

ALTER TABLE business_entity_officers ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'business_entity_officers' AND policyname = 'Public read') THEN
    DROP POLICY IF EXISTS "Public read" ON business_entity_officers;
CREATE POLICY "Public read" ON business_entity_officers FOR SELECT USING (true);
  END IF;
END $$;

ALTER TABLE entity_name_matches ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'entity_name_matches' AND policyname = 'Public read') THEN
    DROP POLICY IF EXISTS "Public read" ON entity_name_matches;
CREATE POLICY "Public read" ON entity_name_matches FOR SELECT USING (true);
  END IF;
END $$;
