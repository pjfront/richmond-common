-- Migration 024: Court Records Cross-Reference (S8.2)
--
-- Stores court case data from Tyler Odyssey portal lookups.
-- Cross-references case parties against known entities (officials, donors).
-- Publication tier: Graduated (legal data requires careful framing).
-- Credibility tier: 1 (official court records).
-- Idempotent: safe to re-run (uses IF NOT EXISTS).

-- ============================================================
-- Table: court_cases
-- Individual court cases with metadata.
-- Source: Tyler Odyssey portal (Contra Costa County initially).
-- Keyed by (county_fips, case_number) for multi-county support.
-- ============================================================

CREATE TABLE IF NOT EXISTS court_cases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    county_fips VARCHAR(5) NOT NULL,
    case_number VARCHAR(100) NOT NULL,
    case_type VARCHAR(100),
    case_category VARCHAR(200),
    case_title VARCHAR(1000),
    filing_date DATE,
    case_status VARCHAR(50),
    disposition VARCHAR(200),
    disposition_date DATE,
    court_name VARCHAR(200),
    judge VARCHAR(200),
    source_url TEXT,
    source VARCHAR(50) NOT NULL DEFAULT 'tyler_odyssey',
    credibility_tier INTEGER NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_court_case UNIQUE (county_fips, case_number)
);

CREATE INDEX IF NOT EXISTS idx_court_cases_city ON court_cases(city_fips);
CREATE INDEX IF NOT EXISTS idx_court_cases_county ON court_cases(county_fips);
CREATE INDEX IF NOT EXISTS idx_court_cases_filing ON court_cases(filing_date DESC);
CREATE INDEX IF NOT EXISTS idx_court_cases_status ON court_cases(case_status);

COMMENT ON TABLE court_cases
    IS 'Court cases from Tyler Odyssey portal lookups. Cross-referenced against officials/donors (S8.2).';

COMMENT ON COLUMN court_cases.county_fips
    IS 'County FIPS code (e.g., 06013 for Contra Costa). Supports multi-county lookup.';


-- ============================================================
-- Table: court_case_parties
-- Named parties (plaintiffs, defendants, etc.) in each case.
-- normalized_name enables cross-reference matching.
-- ============================================================

CREATE TABLE IF NOT EXISTS court_case_parties (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_id UUID NOT NULL REFERENCES court_cases(id) ON DELETE CASCADE,
    party_name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL,
    party_type VARCHAR(50) NOT NULL,
    is_organization BOOLEAN NOT NULL DEFAULT FALSE,
    attorney VARCHAR(300),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_court_parties_case ON court_case_parties(case_id);
CREATE INDEX IF NOT EXISTS idx_court_parties_name ON court_case_parties(normalized_name);
CREATE INDEX IF NOT EXISTS idx_court_parties_type ON court_case_parties(party_type);

COMMENT ON TABLE court_case_parties
    IS 'Parties in court cases. Normalized names enable cross-reference matching against officials/donors.';


-- ============================================================
-- Table: court_case_matches
-- Cross-reference linking court parties to known entities.
-- Confidence-scored, reviewable (false_positive flag).
-- ============================================================

CREATE TABLE IF NOT EXISTS court_case_matches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    court_party_id UUID NOT NULL REFERENCES court_case_parties(id) ON DELETE CASCADE,
    case_id UUID NOT NULL REFERENCES court_cases(id) ON DELETE CASCADE,
    official_id UUID REFERENCES officials(id),
    donor_id UUID REFERENCES donors(id),
    entity_type VARCHAR(30) NOT NULL,
    entity_name VARCHAR(500) NOT NULL,
    match_type VARCHAR(30) NOT NULL,
    confidence NUMERIC(3, 2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_at TIMESTAMPTZ,
    false_positive BOOLEAN,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_court_matches_city ON court_case_matches(city_fips);
CREATE INDEX IF NOT EXISTS idx_court_matches_official ON court_case_matches(official_id);
CREATE INDEX IF NOT EXISTS idx_court_matches_donor ON court_case_matches(donor_id);
CREATE INDEX IF NOT EXISTS idx_court_matches_case ON court_case_matches(case_id);
CREATE INDEX IF NOT EXISTS idx_court_matches_confidence ON court_case_matches(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_court_matches_unreviewed
    ON court_case_matches(city_fips) WHERE reviewed = FALSE;

COMMENT ON TABLE court_case_matches
    IS 'Cross-reference matches between court parties and known entities. Confidence-scored, reviewable.';

COMMENT ON COLUMN court_case_matches.match_type
    IS 'How the match was found: exact, contains, fuzzy, last_name_only';

COMMENT ON COLUMN court_case_matches.confidence
    IS 'Match confidence: 0.9=exact, 0.7=contains, 0.5=fuzzy, 0.3=last_name_only';


-- ============================================================
-- View: v_court_entity_summary
-- Aggregated court involvement by matched entity.
-- ============================================================

CREATE OR REPLACE VIEW v_court_entity_summary AS
SELECT
    cm.city_fips,
    cm.entity_type,
    cm.entity_name,
    cm.official_id,
    cm.donor_id,
    COUNT(DISTINCT cm.case_id) AS case_count,
    COUNT(DISTINCT cm.court_party_id) AS party_count,
    MAX(cm.confidence) AS max_confidence,
    AVG(cm.confidence) AS avg_confidence,
    ARRAY_AGG(DISTINCT cc.case_type) AS case_types,
    MIN(cc.filing_date) AS earliest_case,
    MAX(cc.filing_date) AS latest_case,
    SUM(CASE WHEN cm.false_positive = TRUE THEN 1 ELSE 0 END) AS false_positive_count
FROM court_case_matches cm
JOIN court_cases cc ON cm.case_id = cc.id
WHERE cm.false_positive IS NOT TRUE
GROUP BY cm.city_fips, cm.entity_type, cm.entity_name, cm.official_id, cm.donor_id;

COMMENT ON VIEW v_court_entity_summary
    IS 'Aggregated court case involvement by matched entity for conflict detection (S8.2)';
