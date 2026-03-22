-- Migration 035: Governing Bodies registry + body_id on meetings
-- Formalizes the governing body model: City Council, commissions, boards, committees.
-- All meeting/vote/attendance records gain body_id FK for multi-body support.
-- Idempotent: safe to re-run (uses IF NOT EXISTS / DO $$ blocks).
--
-- Depends on: 005_commissions (commissions table must exist)
-- Unblocks: S8.3 (commission meetings), S8.5 (body type context fix),
--           B.23 (civic role history), B.26 (unified decision index),
--           B.43 (historical cohort filtering)

-- ============================================================
-- New Table: bodies
-- Canonical registry of all governing bodies in a city.
-- Superset of commissions — includes City Council, authorities, etc.
-- ============================================================

CREATE TABLE IF NOT EXISTS bodies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    name VARCHAR(300) NOT NULL,
    body_type VARCHAR(50) NOT NULL,
        -- 'city_council', 'commission', 'board', 'authority', 'committee', 'joint'
    short_name VARCHAR(100),               -- abbreviated display name (e.g. "Planning" for "Planning Commission")
    parent_body_id UUID REFERENCES bodies(id),  -- subcommittees reference parent body
    commission_id UUID REFERENCES commissions(id) ON DELETE SET NULL,  -- link to existing commission infrastructure
    is_elected BOOLEAN NOT NULL DEFAULT FALSE,   -- true for city council, false for appointed bodies
    num_seats SMALLINT,
    meeting_schedule VARCHAR(200),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bodies UNIQUE (city_fips, name)
);

CREATE INDEX IF NOT EXISTS idx_bodies_fips ON bodies(city_fips);
CREATE INDEX IF NOT EXISTS idx_bodies_type ON bodies(body_type);
CREATE INDEX IF NOT EXISTS idx_bodies_commission ON bodies(commission_id);
CREATE INDEX IF NOT EXISTS idx_bodies_active ON bodies(city_fips, is_active) WHERE is_active = TRUE;

-- ============================================================
-- RLS Policy: public read access
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'bodies' AND policyname = 'Public read'
    ) THEN
        DROP POLICY IF EXISTS "Public read" ON bodies;
CREATE POLICY "Public read" ON bodies FOR SELECT USING (true);
    END IF;
END $$;

-- Enable RLS (matches pattern of other tables — Supabase requires it)
ALTER TABLE bodies ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- Seed Richmond City Council as a body
-- ============================================================

INSERT INTO bodies (city_fips, name, body_type, short_name, is_elected, num_seats, meeting_schedule)
VALUES (
    '0660620',
    'City Council',
    'city_council',
    'Council',
    TRUE,
    7,
    '1st and 3rd Tuesday, 6:30 PM'
) ON CONFLICT (city_fips, name) DO NOTHING;

-- ============================================================
-- Seed commission-type bodies from existing commissions table
-- Links each body to its commission record via commission_id.
-- ============================================================

INSERT INTO bodies (city_fips, name, body_type, short_name, commission_id, is_elected, num_seats, meeting_schedule)
SELECT
    c.city_fips,
    c.name,
    CASE c.commission_type
        WHEN 'authority' THEN 'authority'
        WHEN 'board' THEN 'board'
        ELSE 'commission'
    END,
    -- Generate short name: strip trailing "Commission", "Board", etc.
    CASE
        WHEN c.name LIKE '% Commission' THEN LEFT(c.name, LENGTH(c.name) - 11)
        WHEN c.name LIKE '% Board' THEN LEFT(c.name, LENGTH(c.name) - 6)
        ELSE c.name
    END,
    c.id,
    FALSE,
    c.num_seats,
    c.meeting_schedule
FROM commissions c
ON CONFLICT (city_fips, name) DO UPDATE SET
    commission_id = EXCLUDED.commission_id,
    num_seats = EXCLUDED.num_seats,
    meeting_schedule = EXCLUDED.meeting_schedule;

-- ============================================================
-- Add body_id FK to meetings table
-- Nullable initially: existing meetings get backfilled below.
-- ============================================================

ALTER TABLE meetings ADD COLUMN IF NOT EXISTS body_id UUID REFERENCES bodies(id);

CREATE INDEX IF NOT EXISTS idx_meetings_body ON meetings(body_id);

-- ============================================================
-- Backfill: tag all existing meetings as City Council
-- (All 784+ meetings in the DB are council meetings)
-- ============================================================

UPDATE meetings
SET body_id = (
    SELECT id FROM bodies
    WHERE city_fips = '0660620' AND name = 'City Council'
    LIMIT 1
)
WHERE body_id IS NULL
  AND city_fips = '0660620';

-- ============================================================
-- Replace unique constraint on meetings to include body_id
-- Old: (city_fips, meeting_date, meeting_type) — breaks with multi-body
-- New: (city_fips, meeting_date, meeting_type, body_id) — allows same
--      date + type for different bodies
--
-- Uses partial unique index (WHERE body_id IS NOT NULL) since body_id
-- is nullable during migration transition. Also keeps old constraint
-- as a fallback for any rows without body_id.
-- ============================================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_meetings_date_type_body
    ON meetings (city_fips, meeting_date, meeting_type, body_id)
    WHERE body_id IS NOT NULL;

-- ============================================================
-- Add body_id FK to meeting_attendance (denormalized for query perf)
-- ============================================================

ALTER TABLE meeting_attendance ADD COLUMN IF NOT EXISTS body_id UUID REFERENCES bodies(id);

CREATE INDEX IF NOT EXISTS idx_attendance_body ON meeting_attendance(body_id);

-- Backfill attendance body_id from meetings
UPDATE meeting_attendance ma
SET body_id = m.body_id
FROM meetings m
WHERE ma.meeting_id = m.id
  AND ma.body_id IS NULL
  AND m.body_id IS NOT NULL;

-- ============================================================
-- View: v_body_meeting_counts
-- How many meetings each body has held, for frontend display.
-- ============================================================

CREATE OR REPLACE VIEW v_body_meeting_counts AS
SELECT
    b.id AS body_id,
    b.city_fips,
    b.name AS body_name,
    b.body_type,
    b.short_name,
    b.is_active,
    COUNT(m.id) AS meeting_count,
    MIN(m.meeting_date) AS first_meeting,
    MAX(m.meeting_date) AS last_meeting
FROM bodies b
LEFT JOIN meetings m ON b.id = m.body_id
GROUP BY b.id, b.city_fips, b.name, b.body_type, b.short_name, b.is_active;

-- ============================================================
-- View: v_body_roster
-- Current members of each body (council from officials,
-- commissions from commission_members).
-- Unified view for downstream features (B.23, B.43).
-- ============================================================

CREATE OR REPLACE VIEW v_body_roster AS
-- Council members (from officials table)
SELECT
    b.id AS body_id,
    b.city_fips,
    b.name AS body_name,
    b.body_type,
    o.id AS member_id,
    o.name AS member_name,
    o.normalized_name,
    o.role,
    o.term_start,
    o.term_end,
    o.is_current,
    'officials' AS source_table
FROM bodies b
JOIN officials o ON o.city_fips = b.city_fips AND o.is_current = TRUE
WHERE b.body_type = 'city_council'
  AND o.role IN ('mayor', 'vice_mayor', 'councilmember')

UNION ALL

-- Commission/board members (from commission_members table)
SELECT
    b.id AS body_id,
    b.city_fips,
    b.name AS body_name,
    b.body_type,
    cm.id AS member_id,
    cm.name AS member_name,
    cm.normalized_name,
    cm.role,
    cm.term_start,
    cm.term_end,
    cm.is_current,
    'commission_members' AS source_table
FROM bodies b
JOIN commission_members cm ON cm.commission_id = b.commission_id AND cm.is_current = TRUE
WHERE b.commission_id IS NOT NULL;
