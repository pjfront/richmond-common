-- Migration 040: Entity Resolution Infrastructure (B.46)
-- Two tables linking people to organizations via public registries.
-- Replaces fuzzy text matching in conflict scanner with structural ID matching.
-- Sources: CA Secretary of State, CSLB contractor licenses, ProPublica 990 filings.
-- Idempotent: safe to re-run.

-- ═══════════════════════════════════════════════════════════════
-- 1. organizations — Canonical organization records from external registries
--    Cross-reference: org officers → campaign donors, city vendors, officials
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    name VARCHAR(500) NOT NULL,
    normalized_name VARCHAR(500) NOT NULL,
    entity_number VARCHAR(50),          -- CA SOS entity number, EIN, license number
    entity_type VARCHAR(50),            -- 'corporation', 'llc', 'nonprofit', 'contractor', 'sole_prop'
    jurisdiction VARCHAR(50),           -- 'CA', 'US' (federal EIN), etc.
    status VARCHAR(30),                 -- 'active', 'dissolved', 'suspended', 'revoked'
    registered_agent VARCHAR(300),      -- CA SOS agent for service of process
    formation_date DATE,
    source VARCHAR(50) NOT NULL,        -- 'ca_sos', 'cslb', 'propublica_990', 'opencorporates'
    source_url TEXT,
    source_updated_at TIMESTAMPTZ,      -- when the source last refreshed this record
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_org_source UNIQUE (city_fips, source, entity_number)
);

CREATE INDEX IF NOT EXISTS idx_organizations_fips ON organizations(city_fips);
CREATE INDEX IF NOT EXISTS idx_organizations_normalized_name ON organizations(normalized_name);
CREATE INDEX IF NOT EXISTS idx_organizations_entity_number ON organizations(entity_number);
CREATE INDEX IF NOT EXISTS idx_organizations_source ON organizations(source);
CREATE INDEX IF NOT EXISTS idx_organizations_entity_type ON organizations(entity_type);
CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations(status);

-- ═══════════════════════════════════════════════════════════════
-- 2. entity_links — Person-to-organization relationships from public registries
--    Cross-reference: linked person → campaign donor, official, vendor
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS entity_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    person_name VARCHAR(300) NOT NULL,
    normalized_person_name VARCHAR(300) NOT NULL,
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role VARCHAR(100) NOT NULL,         -- 'officer', 'director', 'agent', 'rme', 'ceo', 'cfo', 'trustee'
    role_detail VARCHAR(200),           -- 'Chief Executive Officer', 'Responsible Managing Employee'
    donor_id UUID REFERENCES donors(id),       -- resolved link to existing donor
    official_id UUID REFERENCES officials(id), -- resolved link to existing official
    confidence NUMERIC(3,2) NOT NULL DEFAULT 0.80,
    source VARCHAR(50) NOT NULL,        -- 'ca_sos', 'cslb', 'propublica_990'
    source_url TEXT,
    effective_date DATE,                -- when this role started (from filing date)
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_entity_link UNIQUE (city_fips, normalized_person_name, organization_id, role, source)
);

CREATE INDEX IF NOT EXISTS idx_entity_links_fips ON entity_links(city_fips);
CREATE INDEX IF NOT EXISTS idx_entity_links_person ON entity_links(normalized_person_name);
CREATE INDEX IF NOT EXISTS idx_entity_links_org ON entity_links(organization_id);
CREATE INDEX IF NOT EXISTS idx_entity_links_donor ON entity_links(donor_id);
CREATE INDEX IF NOT EXISTS idx_entity_links_official ON entity_links(official_id);
CREATE INDEX IF NOT EXISTS idx_entity_links_source ON entity_links(source);

-- ═══════════════════════════════════════════════════════════════
-- 3. Summary view: entity connections per person
--    Quick lookup: who is connected to which organizations?
-- ═══════════════════════════════════════════════════════════════
CREATE OR REPLACE VIEW v_entity_connections AS
SELECT
    el.city_fips,
    el.person_name,
    el.normalized_person_name,
    el.role,
    el.role_detail,
    o.name AS organization_name,
    o.entity_type,
    o.entity_number,
    o.status AS org_status,
    o.source AS org_source,
    el.donor_id,
    el.official_id,
    el.confidence,
    el.effective_date
FROM entity_links el
JOIN organizations o ON o.id = el.organization_id
ORDER BY el.person_name, o.name;
