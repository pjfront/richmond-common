-- Migration 009: Sprint 5 — Financial Intelligence
-- Form 700 ingestion (S5.1) + Contribution context enrichment (S5.2)
--
-- Creates form700_filings parent table for filing-level metadata.
-- Adds filing_id FK to economic_interests for one-to-many relationship.
-- Adds donor enrichment columns for contribution pattern analysis.
-- Publication tier: Graduated (operator-only until framing validated).
-- Idempotent: safe to run multiple times.

-- ── S5.1: Form 700 Filings ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS form700_filings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    official_id UUID REFERENCES officials(id),
    filer_name VARCHAR(300) NOT NULL,
    filer_agency VARCHAR(300),
    filer_position VARCHAR(300),
    statement_type VARCHAR(30) NOT NULL,  -- 'annual', 'assuming_office', 'leaving_office', 'candidate', 'amendment'
    period_start DATE,
    period_end DATE,
    filing_year INTEGER NOT NULL,
    source VARCHAR(50) NOT NULL,          -- 'fppc', 'netfile_sei', 'city_clerk'
    source_url TEXT,
    document_id UUID REFERENCES documents(id),
    no_interests_declared BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Deduplicate across sources by filer + year + type + source
CREATE UNIQUE INDEX IF NOT EXISTS uq_form700_filing
    ON form700_filings (city_fips, filer_name, filing_year, statement_type, source);

CREATE INDEX IF NOT EXISTS idx_form700_filings_official
    ON form700_filings (official_id);

CREATE INDEX IF NOT EXISTS idx_form700_filings_year
    ON form700_filings (filing_year);

CREATE INDEX IF NOT EXISTS idx_form700_filings_city
    ON form700_filings (city_fips);

COMMENT ON TABLE form700_filings
    IS 'Form 700 (Statement of Economic Interests) filing metadata. Parent table for economic_interests.';

COMMENT ON COLUMN form700_filings.statement_type
    IS 'Filing type: annual, assuming_office, leaving_office, candidate, amendment';

COMMENT ON COLUMN form700_filings.source
    IS 'Where the filing was obtained: fppc, netfile_sei, city_clerk';

COMMENT ON COLUMN form700_filings.no_interests_declared
    IS 'True if filer checked "No reportable interests" on all schedules';


-- ── Link economic_interests to filings ──────────────────────────

ALTER TABLE economic_interests
    ADD COLUMN IF NOT EXISTS filing_id UUID REFERENCES form700_filings(id);

CREATE INDEX IF NOT EXISTS idx_interests_filing
    ON economic_interests (filing_id);

-- Make official_id nullable for filings we cannot yet match to an official
ALTER TABLE economic_interests
    ALTER COLUMN official_id DROP NOT NULL;

COMMENT ON COLUMN economic_interests.filing_id
    IS 'FK to form700_filings. Links individual interest entries to their parent filing.';


-- ── S5.2: Donor Enrichment Columns ──────────────────────────────

ALTER TABLE donors
    ADD COLUMN IF NOT EXISTS donor_pattern VARCHAR(20);

ALTER TABLE donors
    ADD COLUMN IF NOT EXISTS total_contributed NUMERIC(12, 2);

ALTER TABLE donors
    ADD COLUMN IF NOT EXISTS contribution_span_days INTEGER;

ALTER TABLE donors
    ADD COLUMN IF NOT EXISTS distinct_recipients INTEGER;

COMMENT ON COLUMN donors.donor_pattern
    IS 'Computed pattern: grassroots, targeted, mega, pac, regular';

COMMENT ON COLUMN donors.total_contributed
    IS 'Denormalized sum of all contributions from this donor';

COMMENT ON COLUMN donors.contribution_span_days
    IS 'Days between first and last contribution';

COMMENT ON COLUMN donors.distinct_recipients
    IS 'Number of distinct committees this donor has contributed to';


-- ── Donor Context View ──────────────────────────────────────────

CREATE OR REPLACE VIEW donor_context AS
SELECT
    d.id AS donor_id,
    d.city_fips,
    d.name AS donor_name,
    d.normalized_name,
    d.employer,
    d.normalized_employer,
    d.occupation,
    COUNT(c.id) AS contribution_count,
    COALESCE(SUM(c.amount), 0) AS total_contributed,
    AVG(c.amount) AS avg_contribution,
    MIN(c.amount) AS min_contribution,
    MAX(c.amount) AS max_contribution,
    COUNT(DISTINCT c.committee_id) AS distinct_recipients,
    MIN(c.contribution_date) AS first_contribution,
    MAX(c.contribution_date) AS last_contribution,
    (MAX(c.contribution_date) - MIN(c.contribution_date))
        AS contribution_span_days,
    -- Employer network: how many other donors share this employer?
    (SELECT COUNT(DISTINCT d2.id)
     FROM donors d2
     WHERE d2.normalized_employer = d.normalized_employer
       AND d2.id != d.id
       AND d.normalized_employer IS NOT NULL
       AND d.normalized_employer != '') AS employer_network_size
FROM donors d
LEFT JOIN contributions c ON c.donor_id = d.id AND c.city_fips = d.city_fips
GROUP BY d.id, d.city_fips, d.name, d.normalized_name,
         d.employer, d.normalized_employer, d.occupation;

COMMENT ON VIEW donor_context
    IS 'Aggregated donor statistics for contribution pattern analysis (S5.2)';
