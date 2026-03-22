-- Migration 044: Behested Payments + Lobbyist Registrations (S13.1, S13.3)
-- Description: Track FPPC Form 803 behested payments and lobbyist registrations
-- for influence transparency pipeline.
--
-- Behested payments: payments made at the request/behest of elected officials
-- to third parties. Filed with FPPC under CA Gov Code §82015.
--
-- Lobbyist registrations: per Richmond Municipal Code Chapter 2.54, lobbyists
-- must register with the City Clerk. The *absence* of registration by vendor
-- representatives who are influencing procurement is itself a finding.

-- ── Behested Payments (FPPC Form 803) ────────────────────────

CREATE TABLE IF NOT EXISTS behested_payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    official_name VARCHAR(300) NOT NULL,
    official_id UUID REFERENCES officials(id),
    payor_name VARCHAR(500) NOT NULL,
    payor_city VARCHAR(200),
    payor_state VARCHAR(10),
    payee_name VARCHAR(500) NOT NULL,
    payee_description TEXT,
    amount NUMERIC(12, 2),
    payment_date DATE,
    filing_date DATE,
    description TEXT,
    source VARCHAR(50) NOT NULL DEFAULT 'fppc_form803',
    source_url TEXT,
    source_identifier VARCHAR(500),
    filing_id VARCHAR(100),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_behested_dedup UNIQUE (city_fips, source, source_identifier)
);

CREATE INDEX IF NOT EXISTS idx_behested_fips ON behested_payments(city_fips);
CREATE INDEX IF NOT EXISTS idx_behested_official ON behested_payments(official_id);
CREATE INDEX IF NOT EXISTS idx_behested_official_name ON behested_payments(official_name);
CREATE INDEX IF NOT EXISTS idx_behested_payor ON behested_payments(payor_name);
CREATE INDEX IF NOT EXISTS idx_behested_payee ON behested_payments(payee_name);
CREATE INDEX IF NOT EXISTS idx_behested_date ON behested_payments(payment_date);

-- ── Lobbyist Registrations (Richmond Municipal Code 2.54) ────

CREATE TABLE IF NOT EXISTS lobbyist_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    lobbyist_name VARCHAR(300) NOT NULL,
    lobbyist_firm VARCHAR(500),
    client_name VARCHAR(500) NOT NULL,
    registration_date DATE,
    expiration_date DATE,
    topics TEXT,
    city_agencies TEXT,
    lobbyist_address TEXT,
    lobbyist_phone VARCHAR(50),
    lobbyist_email VARCHAR(200),
    status VARCHAR(50) DEFAULT 'active',
    source VARCHAR(50) NOT NULL DEFAULT 'city_clerk',
    source_url TEXT,
    source_identifier VARCHAR(500),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_lobbyist_dedup UNIQUE (city_fips, source, source_identifier)
);

CREATE INDEX IF NOT EXISTS idx_lobbyist_fips ON lobbyist_registrations(city_fips);
CREATE INDEX IF NOT EXISTS idx_lobbyist_name ON lobbyist_registrations(lobbyist_name);
CREATE INDEX IF NOT EXISTS idx_lobbyist_client ON lobbyist_registrations(client_name);
CREATE INDEX IF NOT EXISTS idx_lobbyist_firm ON lobbyist_registrations(lobbyist_firm);
CREATE INDEX IF NOT EXISTS idx_lobbyist_status ON lobbyist_registrations(status);

-- ── Summary Views ─────────────────────────────────────────────

-- Behested payments per official: total $ requested, count, top payors
CREATE OR REPLACE VIEW v_behested_by_official AS
SELECT
    bp.city_fips,
    bp.official_name,
    bp.official_id,
    COUNT(*) AS payment_count,
    SUM(bp.amount) AS total_amount,
    MIN(bp.payment_date) AS earliest_payment,
    MAX(bp.payment_date) AS latest_payment,
    COUNT(DISTINCT bp.payor_name) AS unique_payors,
    COUNT(DISTINCT bp.payee_name) AS unique_payees
FROM behested_payments bp
GROUP BY bp.city_fips, bp.official_name, bp.official_id;

-- Lobbyist-client pairs with active status
CREATE OR REPLACE VIEW v_lobbyist_clients AS
SELECT
    lr.city_fips,
    lr.lobbyist_name,
    lr.lobbyist_firm,
    lr.client_name,
    lr.registration_date,
    lr.expiration_date,
    lr.topics,
    lr.status
FROM lobbyist_registrations lr
WHERE lr.status = 'active'
   OR lr.expiration_date IS NULL
   OR lr.expiration_date >= CURRENT_DATE;

-- ── RLS Policies ──────────────────────────────────────────────

ALTER TABLE behested_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE lobbyist_registrations ENABLE ROW LEVEL SECURITY;

-- Public read access (matches pattern from migration 042)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'behested_payments' AND policyname = 'behested_payments_read'
    ) THEN
        DROP POLICY IF EXISTS behested_payments_read ON behested_payments;
CREATE POLICY behested_payments_read ON behested_payments FOR SELECT USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'lobbyist_registrations' AND policyname = 'lobbyist_registrations_read'
    ) THEN
        DROP POLICY IF EXISTS lobbyist_registrations_read ON lobbyist_registrations;
CREATE POLICY lobbyist_registrations_read ON lobbyist_registrations FOR SELECT USING (true);
    END IF;
END $$;
