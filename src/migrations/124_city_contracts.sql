-- Migration 124: City contracts table (S26.2 entity resolution)
-- Tracks Richmond city contracts for cross-referencing with campaign
-- contributions via entity_name_matches (source_table='contracts').
--
-- Design: mirrors the pattern from 047_business_entities — normalized
-- vendor data with D1 provenance. Matches flow through the existing
-- entity_name_matches bridge table (no new linking table needed).

-- ============================================================
-- city_contracts — Richmond municipal contracts
-- ============================================================
CREATE TABLE IF NOT EXISTS city_contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips TEXT NOT NULL,
    vendor_name TEXT NOT NULL,
    description TEXT,
    annual_cost NUMERIC(12,2),
    total_cost NUMERIC(12,2),
    contract_type TEXT,                    -- e.g., 'goods', 'services', 'construction', 'professional'
    department TEXT,                       -- Awarding department
    approval_date DATE,
    expiration_date DATE,
    contract_number TEXT,                  -- City-assigned identifier if available
    awarding_body TEXT,                    -- e.g., 'City Council', 'City Manager'
    approval_action TEXT,                  -- Resolution number, motion reference
    -- D1 provenance (non-nullable)
    source_url TEXT NOT NULL,
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_tier INTEGER NOT NULL DEFAULT 1,
    confidence_score NUMERIC(3,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_city_contracts_city_fips
    ON city_contracts(city_fips);
CREATE INDEX IF NOT EXISTS idx_city_contracts_vendor_name
    ON city_contracts(vendor_name);
CREATE INDEX IF NOT EXISTS idx_city_contracts_department
    ON city_contracts(department);
CREATE INDEX IF NOT EXISTS idx_city_contracts_approval_date
    ON city_contracts(approval_date);
CREATE INDEX IF NOT EXISTS idx_city_contracts_contract_type
    ON city_contracts(contract_type);

-- Prevent duplicate contract records (same vendor + contract number + approval date)
CREATE UNIQUE INDEX IF NOT EXISTS uq_city_contracts_vendor_number_date
    ON city_contracts(vendor_name, contract_number, approval_date)
    WHERE contract_number IS NOT NULL;

-- ============================================================
-- RLS — public read
-- ============================================================
ALTER TABLE city_contracts ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'city_contracts' AND policyname = 'Public read') THEN
    DROP POLICY IF EXISTS "Public read" ON city_contracts;
    CREATE POLICY "Public read" ON city_contracts FOR SELECT USING (true);
  END IF;
END $$;
