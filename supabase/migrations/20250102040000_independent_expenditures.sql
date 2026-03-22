-- Migration 029: Independent expenditures table for CAL-ACCESS EXPN_CD data
-- Connects PAC money to specific candidates (support/oppose)
-- Different entity shape than contributions: committee → candidate, not donor → committee

CREATE TABLE IF NOT EXISTS independent_expenditures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL,
    committee_name VARCHAR(500) NOT NULL,
    candidate_name VARCHAR(255),
    support_or_oppose VARCHAR(1),  -- S=Support, O=Oppose
    amount NUMERIC(12,2),
    expenditure_date DATE,
    description TEXT,
    expenditure_code VARCHAR(10),
    payee_name VARCHAR(500),
    filing_id VARCHAR(50),
    source VARCHAR(50) DEFAULT 'calaccess',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ie_city_fips ON independent_expenditures(city_fips);
CREATE INDEX IF NOT EXISTS idx_ie_candidate ON independent_expenditures(city_fips, candidate_name);
CREATE INDEX IF NOT EXISTS idx_ie_committee ON independent_expenditures(city_fips, committee_name);
