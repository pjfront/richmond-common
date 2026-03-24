-- Migration 051: Election Cycle Tracking (B.24)
-- Tracks election cycles, candidate registrations, and links existing
-- financial data (contributions, committees) to specific elections.
-- First target: Richmond June 2026 primary.
--
-- Two new tables: elections, election_candidates
-- Two FK additions: committees.election_id, contributions.election_id

-- ============================================================
-- New Table: elections
-- Election cycles with dates, types, and jurisdictions.
-- ============================================================

CREATE TABLE IF NOT EXISTS elections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    election_date DATE NOT NULL,
    election_type VARCHAR(30) NOT NULL,        -- 'primary', 'general', 'special', 'runoff'
    election_name VARCHAR(300),                -- e.g. "Richmond June 2026 Primary"
    jurisdiction VARCHAR(200),                 -- 'City of Richmond', 'Contra Costa County'
    filing_deadline DATE,                      -- candidate filing deadline if known
    source VARCHAR(50) NOT NULL DEFAULT 'seed',  -- 'seed', 'registrar', 'sos', 'manual'
    source_url TEXT,
    source_tier INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_elections_city_date_type
    ON elections(city_fips, election_date, election_type);
CREATE INDEX IF NOT EXISTS idx_elections_city ON elections(city_fips);
CREATE INDEX IF NOT EXISTS idx_elections_date ON elections(election_date);

ALTER TABLE elections ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON elections;
CREATE POLICY "Public read" ON elections FOR SELECT USING (true);


-- ============================================================
-- New Table: election_candidates
-- Candidate registrations per election, linked to officials.
-- ============================================================

CREATE TABLE IF NOT EXISTS election_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    election_id UUID NOT NULL REFERENCES elections(id) ON DELETE CASCADE,
    official_id UUID REFERENCES officials(id) ON DELETE SET NULL,
    candidate_name VARCHAR(300) NOT NULL,
    normalized_name VARCHAR(300) NOT NULL,
    office_sought VARCHAR(200) NOT NULL,        -- 'Mayor', 'City Council District 1'
    party VARCHAR(100),
    fppc_id VARCHAR(50),                        -- FPPC filer ID from NetFile
    committee_id UUID REFERENCES committees(id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'filed', -- 'filed', 'qualified', 'withdrawn', 'elected', 'defeated'
    is_incumbent BOOLEAN NOT NULL DEFAULT FALSE,
    source VARCHAR(50) NOT NULL DEFAULT 'netfile',
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_election_candidates
    ON election_candidates(city_fips, election_id, normalized_name, office_sought);
CREATE INDEX IF NOT EXISTS idx_ec_city ON election_candidates(city_fips);
CREATE INDEX IF NOT EXISTS idx_ec_election ON election_candidates(election_id);
CREATE INDEX IF NOT EXISTS idx_ec_official ON election_candidates(official_id);
CREATE INDEX IF NOT EXISTS idx_ec_committee ON election_candidates(committee_id);
CREATE INDEX IF NOT EXISTS idx_ec_name ON election_candidates(normalized_name);

ALTER TABLE election_candidates ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON election_candidates;
CREATE POLICY "Public read" ON election_candidates FOR SELECT USING (true);


-- ============================================================
-- Extend committees: link to election cycle
-- ============================================================

ALTER TABLE committees ADD COLUMN IF NOT EXISTS election_id UUID REFERENCES elections(id);
CREATE INDEX IF NOT EXISTS idx_committees_election ON committees(election_id);


-- ============================================================
-- Extend contributions: link to election cycle
-- ============================================================

ALTER TABLE contributions ADD COLUMN IF NOT EXISTS election_id UUID REFERENCES elections(id);
CREATE INDEX IF NOT EXISTS idx_contributions_election ON contributions(election_id);


-- ============================================================
-- Seed data: Richmond 2026 elections
-- CA Secretary of State confirmed dates:
--   Primary: June 2, 2026
--   General: November 3, 2026
-- ============================================================

INSERT INTO elections (city_fips, election_date, election_type, election_name, jurisdiction, source, source_url, source_tier, notes)
VALUES (
    '0660620',
    '2026-06-02',
    'primary',
    'Richmond June 2026 Primary',
    'City of Richmond',
    'seed',
    'https://www.sos.ca.gov/elections/upcoming-elections/primary-election-june-2-2026',
    1,
    'California statewide primary. Richmond city council seats on ballot.'
)
ON CONFLICT (city_fips, election_date, election_type) DO NOTHING;

INSERT INTO elections (city_fips, election_date, election_type, election_name, jurisdiction, source, source_url, source_tier, notes)
VALUES (
    '0660620',
    '2026-11-03',
    'general',
    'Richmond November 2026 General Election',
    'City of Richmond',
    'seed',
    'https://www.sos.ca.gov/elections/upcoming-elections',
    1,
    'California statewide general election. Richmond city council general.'
)
ON CONFLICT (city_fips, election_date, election_type) DO NOTHING;
