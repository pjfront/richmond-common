-- Migration 039: Socrata regulatory dataset tables (B.44)
-- Five tables for cross-referencing regulatory actions against political connections.
-- Each table creates a surface for political influence detection (B.45).
-- Idempotent: safe to re-run.

-- ═══════════════════════════════════════════════════════════════
-- 1. city_permits — Building/development permits (permit_trak)
--    Cross-reference: permit applicant → campaign donor?
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS city_permits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    permit_no VARCHAR(50),
    permit_type VARCHAR(100),
    permit_subtype VARCHAR(100),
    description TEXT,
    status VARCHAR(50),
    situs_address VARCHAR(500),
    situs_apn VARCHAR(50),
    applied_date DATE,
    approved_date DATE,
    issued_date DATE,
    finaled_date DATE,
    expired_date DATE,
    applied_by VARCHAR(200),
    fees_charged NUMERIC,
    fees_paid NUMERIC,
    job_value NUMERIC,
    building_sqft NUMERIC,
    units INTEGER,
    project_number VARCHAR(100),
    source VARCHAR(50) NOT NULL DEFAULT 'socrata_permits',
    socrata_row_id VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_city_permit UNIQUE (city_fips, socrata_row_id)
);

CREATE INDEX IF NOT EXISTS idx_city_permits_fips ON city_permits(city_fips);
CREATE INDEX IF NOT EXISTS idx_city_permits_type ON city_permits(permit_type);
CREATE INDEX IF NOT EXISTS idx_city_permits_status ON city_permits(status);
CREATE INDEX IF NOT EXISTS idx_city_permits_applied ON city_permits(applied_date);
CREATE INDEX IF NOT EXISTS idx_city_permits_address ON city_permits(situs_address);
CREATE INDEX IF NOT EXISTS idx_city_permits_applied_by ON city_permits(applied_by);
CREATE INDEX IF NOT EXISTS idx_city_permits_job_value ON city_permits(job_value DESC NULLS LAST);

-- ═══════════════════════════════════════════════════════════════
-- 2. city_licenses — Business licenses (license_trak)
--    Cross-reference: license holder → campaign donor / vendor?
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS city_licenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    company VARCHAR(500),
    normalized_company VARCHAR(500),
    company_dba VARCHAR(500),
    business_type VARCHAR(200),
    classification VARCHAR(200),
    ownership_type VARCHAR(100),
    status VARCHAR(50),
    employees INTEGER,
    license_issued DATE,
    license_expired DATE,
    business_start_date DATE,
    loc_address VARCHAR(500),
    loc_city VARCHAR(100),
    loc_zip VARCHAR(20),
    site_address VARCHAR(500),
    site_apn VARCHAR(50),
    sic_code VARCHAR(50),
    neighborhood_council VARCHAR(100),
    source VARCHAR(50) NOT NULL DEFAULT 'socrata_licenses',
    socrata_row_id VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_city_license UNIQUE (city_fips, socrata_row_id)
);

CREATE INDEX IF NOT EXISTS idx_city_licenses_fips ON city_licenses(city_fips);
CREATE INDEX IF NOT EXISTS idx_city_licenses_company ON city_licenses(normalized_company);
CREATE INDEX IF NOT EXISTS idx_city_licenses_type ON city_licenses(business_type);
CREATE INDEX IF NOT EXISTS idx_city_licenses_status ON city_licenses(status);
CREATE INDEX IF NOT EXISTS idx_city_licenses_issued ON city_licenses(license_issued);

-- ═══════════════════════════════════════════════════════════════
-- 3. city_code_cases — Code enforcement cases (code_trak)
--    Cross-reference: selective enforcement patterns by address/area?
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS city_code_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    case_type VARCHAR(100),
    case_subtype VARCHAR(200),
    violation_type VARCHAR(200),
    violation VARCHAR(500),
    status VARCHAR(50),
    case_location VARCHAR(500),
    site_address VARCHAR(500),
    site_apn VARCHAR(50),
    site_zip VARCHAR(20),
    opened_date DATE,
    closed_date DATE,
    date_observed DATE,
    date_corrected DATE,
    neighborhood_council VARCHAR(100),
    source VARCHAR(50) NOT NULL DEFAULT 'socrata_code_cases',
    socrata_row_id VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_city_code_case UNIQUE (city_fips, socrata_row_id)
);

CREATE INDEX IF NOT EXISTS idx_city_code_cases_fips ON city_code_cases(city_fips);
CREATE INDEX IF NOT EXISTS idx_city_code_cases_type ON city_code_cases(case_type);
CREATE INDEX IF NOT EXISTS idx_city_code_cases_status ON city_code_cases(status);
CREATE INDEX IF NOT EXISTS idx_city_code_cases_opened ON city_code_cases(opened_date);
CREATE INDEX IF NOT EXISTS idx_city_code_cases_address ON city_code_cases(site_address);

-- ═══════════════════════════════════════════════════════════════
-- 4. city_service_requests — Citizen requests/complaints (crm_trak)
--    Cross-reference: complaint patterns, response times by area
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS city_service_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    issue_type VARCHAR(300),
    department VARCHAR(200),
    description TEXT,
    status VARCHAR(50),
    created_via VARCHAR(100),
    issue_address VARCHAR(500),
    created_date DATE,
    due_date DATE,
    completed_date DATE,
    linked_doc VARCHAR(500),
    latitude NUMERIC,
    longitude NUMERIC,
    source VARCHAR(50) NOT NULL DEFAULT 'socrata_service_requests',
    socrata_row_id VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_city_service_request UNIQUE (city_fips, socrata_row_id)
);

CREATE INDEX IF NOT EXISTS idx_city_service_requests_fips ON city_service_requests(city_fips);
CREATE INDEX IF NOT EXISTS idx_city_service_requests_type ON city_service_requests(issue_type);
CREATE INDEX IF NOT EXISTS idx_city_service_requests_dept ON city_service_requests(department);
CREATE INDEX IF NOT EXISTS idx_city_service_requests_status ON city_service_requests(status);
CREATE INDEX IF NOT EXISTS idx_city_service_requests_created ON city_service_requests(created_date);

-- ═══════════════════════════════════════════════════════════════
-- 5. city_projects — Capital/development projects (project_trak)
--    Cross-reference: project applicant → donor? Resolution → vote?
-- ═══════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS city_projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    project_no VARCHAR(50),
    project_name VARCHAR(500),
    project_type VARCHAR(100),
    project_subtype VARCHAR(200),
    description TEXT,
    status VARCHAR(50),
    site_address VARCHAR(500),
    site_apn VARCHAR(50),
    site_zip VARCHAR(20),
    zoning_code VARCHAR(50),
    land_use VARCHAR(200),
    occupancy_description VARCHAR(200),
    resolution_no VARCHAR(100),
    parent_project_no VARCHAR(50),
    applied_date DATE,
    approved_date DATE,
    closed_date DATE,
    expired_date DATE,
    status_date DATE,
    applied_by VARCHAR(200),
    approved_by VARCHAR(200),
    affordability_level_applied VARCHAR(100),
    affordability_level_approved VARCHAR(100),
    neighborhood_council VARCHAR(100),
    latitude NUMERIC,
    longitude NUMERIC,
    source VARCHAR(50) NOT NULL DEFAULT 'socrata_projects',
    socrata_row_id VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_city_project UNIQUE (city_fips, socrata_row_id)
);

CREATE INDEX IF NOT EXISTS idx_city_projects_fips ON city_projects(city_fips);
CREATE INDEX IF NOT EXISTS idx_city_projects_type ON city_projects(project_type);
CREATE INDEX IF NOT EXISTS idx_city_projects_status ON city_projects(status);
CREATE INDEX IF NOT EXISTS idx_city_projects_applied ON city_projects(applied_date);
CREATE INDEX IF NOT EXISTS idx_city_projects_resolution ON city_projects(resolution_no);
CREATE INDEX IF NOT EXISTS idx_city_projects_applied_by ON city_projects(applied_by);
CREATE INDEX IF NOT EXISTS idx_city_projects_address ON city_projects(site_address);

-- ═══════════════════════════════════════════════════════════════
-- Summary views for operator dashboard
-- ═══════════════════════════════════════════════════════════════

-- Permit activity summary by type and year
CREATE OR REPLACE VIEW v_permit_activity AS
SELECT
    city_fips,
    permit_type,
    EXTRACT(YEAR FROM applied_date)::INTEGER AS year,
    COUNT(*) AS total_permits,
    COUNT(*) FILTER (WHERE status = 'ISSUED') AS issued,
    COUNT(*) FILTER (WHERE status = 'FINALED') AS finaled,
    SUM(job_value) AS total_job_value,
    SUM(fees_charged) AS total_fees
FROM city_permits
WHERE applied_date IS NOT NULL
GROUP BY city_fips, permit_type, EXTRACT(YEAR FROM applied_date);

-- Business license summary by type
CREATE OR REPLACE VIEW v_license_summary AS
SELECT
    city_fips,
    business_type,
    status,
    COUNT(*) AS total,
    SUM(employees) AS total_employees
FROM city_licenses
GROUP BY city_fips, business_type, status;

-- Code enforcement summary by type and year
CREATE OR REPLACE VIEW v_code_enforcement_summary AS
SELECT
    city_fips,
    case_type,
    EXTRACT(YEAR FROM opened_date)::INTEGER AS year,
    COUNT(*) AS total_cases,
    COUNT(*) FILTER (WHERE closed_date IS NOT NULL) AS closed_cases,
    AVG(closed_date - opened_date)::INTEGER AS avg_days_to_close
FROM city_code_cases
WHERE opened_date IS NOT NULL
GROUP BY city_fips, case_type, EXTRACT(YEAR FROM opened_date);
