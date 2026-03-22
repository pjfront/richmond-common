-- Migration 005: Commissions & board members
-- Schema for commission rosters, appointments, and staleness tracking.
-- Idempotent: safe to re-run (uses IF NOT EXISTS / OR REPLACE).

-- ============================================================
-- New Table: commissions
-- Registry of city commissions, boards, and committees.
-- ============================================================

CREATE TABLE IF NOT EXISTS commissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    name VARCHAR(300) NOT NULL,
    commission_type VARCHAR(50) NOT NULL DEFAULT 'advisory',
    num_seats SMALLINT,
    appointment_authority VARCHAR(100),
    form700_required BOOLEAN NOT NULL DEFAULT FALSE,
    term_length_years SMALLINT,
    meeting_schedule VARCHAR(200),
    escribemeetings_type VARCHAR(200),
    archive_center_amid INTEGER,
    website_roster_url VARCHAR(500),
    last_website_scrape TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_commission UNIQUE (city_fips, name)
);

CREATE INDEX IF NOT EXISTS idx_commissions_fips ON commissions(city_fips);
CREATE INDEX IF NOT EXISTS idx_commissions_type ON commissions(commission_type);
CREATE INDEX IF NOT EXISTS idx_commissions_form700 ON commissions(form700_required, city_fips);

-- ============================================================
-- New Table: commission_members
-- People serving on commissions with appointment provenance.
-- ============================================================

CREATE TABLE IF NOT EXISTS commission_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    commission_id UUID NOT NULL REFERENCES commissions(id) ON DELETE CASCADE,
    name VARCHAR(300) NOT NULL,
    normalized_name VARCHAR(300) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'member',
    appointed_by VARCHAR(300),
    appointed_by_official_id UUID REFERENCES officials(id),
    term_start DATE,
    term_end DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    source VARCHAR(50) NOT NULL DEFAULT 'city_website',
    source_meeting_id UUID REFERENCES meetings(id),
    website_stale_since DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_commission_member UNIQUE (city_fips, commission_id, normalized_name)
);

CREATE INDEX IF NOT EXISTS idx_commission_members_fips ON commission_members(city_fips);
CREATE INDEX IF NOT EXISTS idx_commission_members_commission ON commission_members(commission_id);
CREATE INDEX IF NOT EXISTS idx_commission_members_current ON commission_members(is_current, city_fips);
CREATE INDEX IF NOT EXISTS idx_commission_members_name ON commission_members(normalized_name);
CREATE INDEX IF NOT EXISTS idx_commission_members_source ON commission_members(source);
CREATE INDEX IF NOT EXISTS idx_commission_members_stale ON commission_members(website_stale_since)
    WHERE website_stale_since IS NOT NULL;

-- ============================================================
-- RLS Policies: public read access (matches pattern of other tables)
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'commissions' AND policyname = 'Public read'
    ) THEN
        DROP POLICY IF EXISTS "Public read" ON commissions;
CREATE POLICY "Public read" ON commissions FOR SELECT USING (true);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'commission_members' AND policyname = 'Public read'
    ) THEN
        DROP POLICY IF EXISTS "Public read" ON commission_members;
CREATE POLICY "Public read" ON commission_members FOR SELECT USING (true);
    END IF;
END $$;

-- ============================================================
-- View: v_commission_staleness
-- Commissions with website roster out-of-date vs. minutes record.
-- ============================================================

CREATE OR REPLACE VIEW v_commission_staleness AS
SELECT
    c.id AS commission_id,
    c.city_fips,
    c.name AS commission_name,
    c.last_website_scrape,
    COUNT(cm.id) FILTER (WHERE cm.website_stale_since IS NOT NULL) AS stale_members,
    COUNT(cm.id) FILTER (WHERE cm.is_current = TRUE) AS total_current_members,
    MIN(cm.website_stale_since) AS oldest_stale_since,
    CURRENT_DATE - MIN(cm.website_stale_since) AS max_days_stale,
    ARRAY_AGG(cm.name ORDER BY cm.name)
        FILTER (WHERE cm.website_stale_since IS NOT NULL) AS stale_member_names
FROM commissions c
LEFT JOIN commission_members cm ON c.id = cm.commission_id
GROUP BY c.id, c.city_fips, c.name, c.last_website_scrape
HAVING COUNT(cm.id) FILTER (WHERE cm.website_stale_since IS NOT NULL) > 0;

-- ============================================================
-- View: v_appointment_network
-- Maps which council members appointed which commissioners.
-- ============================================================

CREATE OR REPLACE VIEW v_appointment_network AS
SELECT
    cm.city_fips,
    cm.appointed_by,
    o.id AS appointing_official_id,
    o.name AS appointing_official_name,
    c.name AS commission_name,
    c.commission_type,
    cm.name AS commissioner_name,
    cm.role,
    cm.term_start,
    cm.term_end,
    cm.is_current,
    cm.source
FROM commission_members cm
JOIN commissions c ON cm.commission_id = c.id
LEFT JOIN officials o ON cm.appointed_by_official_id = o.id
WHERE cm.appointed_by IS NOT NULL;
