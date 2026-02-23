-- Migration 004: City employees & leadership hierarchy
-- Ingests payroll data from Socrata, classifies org hierarchy by title.
-- Idempotent: safe to re-run (uses IF NOT EXISTS).

-- ============================================================
-- New Table: city_employees
-- Employee payroll records with inferred org hierarchy.
-- ============================================================

CREATE TABLE IF NOT EXISTS city_employees (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    name VARCHAR(300) NOT NULL,
    normalized_name VARCHAR(300) NOT NULL,
    job_title VARCHAR(300),
    department VARCHAR(200),
    is_department_head BOOLEAN NOT NULL DEFAULT FALSE,
    hierarchy_level SMALLINT NOT NULL DEFAULT 0,
    annual_salary NUMERIC,
    total_compensation NUMERIC,
    fiscal_year VARCHAR(4),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    source VARCHAR(50) NOT NULL DEFAULT 'socrata_payroll',
    socrata_record_id VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_city_employee UNIQUE (city_fips, normalized_name, department, fiscal_year)
);

CREATE INDEX IF NOT EXISTS idx_city_employees_fips ON city_employees(city_fips);
CREATE INDEX IF NOT EXISTS idx_city_employees_current ON city_employees(is_current, city_fips);
CREATE INDEX IF NOT EXISTS idx_city_employees_dept ON city_employees(department);
CREATE INDEX IF NOT EXISTS idx_city_employees_name ON city_employees(normalized_name);
CREATE INDEX IF NOT EXISTS idx_city_employees_hierarchy ON city_employees(hierarchy_level, city_fips);
CREATE INDEX IF NOT EXISTS idx_city_employees_salary ON city_employees(annual_salary DESC);

-- ============================================================
-- View: v_staff_agenda_context
-- Joins agenda items to department heads for staff context.
-- ============================================================

CREATE OR REPLACE VIEW v_staff_agenda_context AS
SELECT
    ai.id AS agenda_item_id,
    ai.title AS item_title,
    ai.department AS item_department,
    m.meeting_date,
    m.city_fips,
    ce.name AS dept_head_name,
    ce.job_title AS dept_head_title,
    ce.department AS employee_department,
    ce.annual_salary,
    ce.hierarchy_level
FROM agenda_items ai
JOIN meetings m ON ai.meeting_id = m.id
LEFT JOIN city_employees ce
    ON m.city_fips = ce.city_fips
    AND ce.is_current = TRUE
    AND ce.is_department_head = TRUE
    AND LOWER(ai.department) = LOWER(ce.department)
WHERE ai.department IS NOT NULL;
