-- Migration 023: City expenditures from Socrata
-- Stores actual spending records from Transparent Richmond open data portal.
-- Idempotent: safe to re-run (uses IF NOT EXISTS).

-- ============================================================
-- New Table: city_expenditures
-- Actual spending records with vendor, department, fund, and amount.
-- Source: Socrata dataset "expenditures" (86qj-wgke for Richmond).
-- ============================================================

CREATE TABLE IF NOT EXISTS city_expenditures (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    vendor_name VARCHAR(500),
    normalized_vendor VARCHAR(500),
    description VARCHAR(1000),
    amount NUMERIC,
    department VARCHAR(300),
    fund VARCHAR(300),
    fiscal_year VARCHAR(4),
    expenditure_date DATE,
    source VARCHAR(50) NOT NULL DEFAULT 'socrata_expenditures',
    socrata_row_id VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_city_expenditure UNIQUE (city_fips, socrata_row_id)
);

CREATE INDEX IF NOT EXISTS idx_city_expenditures_fips ON city_expenditures(city_fips);
CREATE INDEX IF NOT EXISTS idx_city_expenditures_vendor ON city_expenditures(normalized_vendor);
CREATE INDEX IF NOT EXISTS idx_city_expenditures_dept ON city_expenditures(department);
CREATE INDEX IF NOT EXISTS idx_city_expenditures_fy ON city_expenditures(fiscal_year, city_fips);
CREATE INDEX IF NOT EXISTS idx_city_expenditures_date ON city_expenditures(expenditure_date DESC);
CREATE INDEX IF NOT EXISTS idx_city_expenditures_amount ON city_expenditures(amount DESC);

-- ============================================================
-- View: v_vendor_spending_summary
-- Aggregates spending by vendor for conflict cross-referencing.
-- ============================================================

CREATE OR REPLACE VIEW v_vendor_spending_summary AS
SELECT
    city_fips,
    vendor_name,
    normalized_vendor,
    fiscal_year,
    COUNT(*) AS transaction_count,
    SUM(amount) AS total_amount,
    MIN(expenditure_date) AS first_payment,
    MAX(expenditure_date) AS last_payment
FROM city_expenditures
GROUP BY city_fips, vendor_name, normalized_vendor, fiscal_year;
