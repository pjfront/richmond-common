-- Migration 099: Filing-period briefings table + Tier A/B/C column on conflict_flags.
--
-- This migration implements two pieces of the filing-period-briefings plan
-- (docs/plans/2026-04-28-filing-period-briefings.md) and the Scanner v4
-- significance model (docs/specs/signal-significance-spec.md):
--
--   1. filing_period_briefings — a new artifact alongside meetings, holding
--      the structured output of src/filing_period_briefing.py. Same shape
--      as a meeting recap row: trigger metadata, JSONB sections, provenance.
--
--   2. conflict_flags.significance_tier — adopts the A/B/C model so the
--      meeting briefing can tier-filter scanner output before publication
--      (Tier A = legal threshold, Tier B = pattern, Tier C = connection-only).
--
-- The briefing artifact is parallel to meetings, not a child of it. A
-- filing period (e.g., 2026-Q1) is its own civic event with its own
-- evidence base (NetFile + paper filings + form700 + city contracts), its
-- own generator (filing_period_briefing.py), and its own UI surfaces
-- (per-candidate sections on the candidate page; cross-candidate sections
-- on /elections/[slug]/finance).
--
-- Idempotent: CREATE TABLE IF NOT EXISTS, ADD COLUMN IF NOT EXISTS,
-- DROP POLICY IF EXISTS before CREATE POLICY. Re-run safe.

-- ============================================================
-- Table: filing_period_briefings
-- ============================================================
--
-- One row per (city, election, filing period). period_label is the
-- canonical operator-facing identifier ("2026-Q1", "2026-pre-primary-24h").
-- sections is a JSONB blob keyed by section id (F1..F9), each value an
-- array of structured statements with their own confidence + tier metadata
-- so the candidate page can render per-candidate slices and the dashboard
-- can render cross-candidate aggregates from the same row.

CREATE TABLE IF NOT EXISTS filing_period_briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    election_id UUID REFERENCES elections(id) ON DELETE SET NULL,

    -- Period identity
    period_label VARCHAR(100) NOT NULL,        -- '2026-Q1', '2026-pre-primary-24h'
    period_kind VARCHAR(40) NOT NULL,          -- 'quarterly' | 'pre_election_24h' | 'semi_annual' | 'annual'
    period_start DATE NOT NULL,                -- inclusive
    period_end DATE NOT NULL,                  -- inclusive (filing-deadline-aligned, not calendar)
    filed_through DATE,                        -- last contribution date covered (may exceed period_end)

    -- Briefing content (structured per signal-significance-spec)
    sections JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- Shape:
    --   {
    --     "F1_totals":          { "per_candidate": {...}, "cross_race": {...} },
    --     "F2_geography":       { "per_candidate": {...}, "cross_race": {...} },
    --     "F3_industry_pac":    { ... },
    --     "F4_self_related":    { ... },
    --     "F5_donor_clustering":{ ... },        // cross-candidate; framing-sensitive
    --     "F6_deadline_burst":  { ... },        // 24-hour reports
    --     "F7_compliance":      { ... },        // late filings, missing schedules
    --     "F8_vendor_employee": { ... },        // tier-aware
    --     "F9_levine_exposure": { ... }         // tier-aware; framing-sensitive
    --   }

    -- Per-section tier assignment so the renderer can filter by readiness.
    -- Initial briefings ship with most sections at Tier C (operator-only)
    -- and graduate per-section after operator review.
    section_tiers JSONB NOT NULL DEFAULT '{}'::JSONB,
    -- Shape: { "F1_totals": "A", "F5_donor_clustering": "C", ... }

    -- Provenance — same shape as meetings.*_provenance (see migration 095
    -- and src/provenance.py). Filing-period briefings will typically use
    -- a new provenance kind ('campaign_filing_period') added to the
    -- discriminated union when the renderer ships.
    provenance JSONB,

    -- Generation metadata
    generator VARCHAR(100) NOT NULL DEFAULT 'filing_period_briefing.py',
    generator_version VARCHAR(50),
    model_version VARCHAR(100),
    contributions_considered INTEGER,           -- audit / liveness check
    paper_filings_considered INTEGER,
    publication_tier VARCHAR(20) NOT NULL DEFAULT 'graduated',
                                                -- 'public' | 'operator' | 'graduated'
    is_current BOOLEAN NOT NULL DEFAULT TRUE,   -- supersession on regeneration

    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    superseded_at TIMESTAMPTZ,
    notes TEXT
);

-- One current briefing per (city, election, period_label) — older briefings
-- stay in the table with is_current=false for audit history.
CREATE UNIQUE INDEX IF NOT EXISTS uq_filing_period_briefings_current
    ON filing_period_briefings (city_fips, election_id, period_label)
    WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_fpb_city ON filing_period_briefings (city_fips);
CREATE INDEX IF NOT EXISTS idx_fpb_election ON filing_period_briefings (election_id);
CREATE INDEX IF NOT EXISTS idx_fpb_period_end ON filing_period_briefings (period_end);
CREATE INDEX IF NOT EXISTS idx_fpb_publication_tier ON filing_period_briefings (publication_tier);

ALTER TABLE filing_period_briefings ENABLE ROW LEVEL SECURITY;

-- Public read only for briefings whose publication_tier has been promoted
-- to 'public'. Operator-only and graduated briefings are gated by
-- service_role access (the OperatorGate cookie pattern in the frontend
-- relies on SSR + service_role; anon clients see only fully-graduated rows).
DROP POLICY IF EXISTS "Public read public-tier briefings" ON filing_period_briefings;
CREATE POLICY "Public read public-tier briefings"
    ON filing_period_briefings
    FOR SELECT
    USING (publication_tier = 'public' AND is_current);

COMMENT ON TABLE filing_period_briefings IS
    'Structured filing-period briefings — campaign-finance equivalent of '
    'meeting recaps. One row per (city, election, period). Sections are '
    'JSONB so per-candidate and cross-candidate views render from the same '
    'artifact. See docs/plans/2026-04-28-filing-period-briefings.md.';

COMMENT ON COLUMN filing_period_briefings.sections IS
    'JSONB blob keyed by section id (F1_totals through F9_levine_exposure). '
    'Each section value is structured per signal-significance-spec.md. '
    'The renderer slices this by candidate for the candidate page and by '
    'cross-race for the finance dashboard.';

COMMENT ON COLUMN filing_period_briefings.section_tiers IS
    'Per-section A/B/C tier (Scanner v4 model). Sections at Tier C are '
    'operator-only even when the briefing as a whole is published. Per-section '
    'tiering lets framing-sensitive sections (F5, F9) graduate independently.';

COMMENT ON COLUMN filing_period_briefings.publication_tier IS
    'Briefing-level publication tier (team-operations.md rubric): public | '
    'operator | graduated. Defaults to ''graduated'' per the briefing spec — '
    'a new feature category with AI-generated narrative needs operator review.';

-- ============================================================
-- Extend conflict_flags: significance_tier (Scanner v4)
-- ============================================================
--
-- Adopts the A/B/C model from signal-significance-spec.md so the meeting
-- briefing can tier-filter scanner output. confidence (existing column)
-- still answers "does this connection exist?" — significance_tier answers
-- "should anyone care?" Public summary counts include only Tier A + B.
-- Tier C connections remain in the table for operator review and pattern
-- detection but never appear in citizen-facing counts.

ALTER TABLE conflict_flags
    ADD COLUMN IF NOT EXISTS significance_tier         TEXT,
    ADD COLUMN IF NOT EXISTS significance_assigned_at  TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS significance_rationale    TEXT;

COMMENT ON COLUMN conflict_flags.significance_tier IS
    'Scanner v4 tier (signal-significance-spec.md): '
    '''legal_threshold'' (A — public, with statute citation) | '
    '''pattern'' (B — public, cross-meeting pattern with confidence ≥ 0.70) | '
    '''connection'' (C — operator-only, no legal threshold or pattern). '
    'NULL on legacy flags pre-classification. Public summary counts include '
    'only A + B. Frontend filters significance_tier IN (legal_threshold, pattern).';

COMMENT ON COLUMN conflict_flags.significance_assigned_at IS
    'When significance_tier was last computed. Used to find flags needing '
    'reclassification after threshold/pattern detector updates.';

COMMENT ON COLUMN conflict_flags.significance_rationale IS
    'Human-readable explanation of why this tier was assigned. Tier A flags '
    'cite the statute and amount ("Levine Act §84308 — $600 contribution >$500 '
    'threshold for entitlement proceedings"). Tier B flags cite the pattern '
    '("Donor X appears in 5 items across 3 meetings, total $4,200"). Tier C '
    'rows leave this NULL or short.';

-- Sanity constraint: only the documented enum values, NULL stays valid for
-- legacy rows. Drop-then-create so the migration is idempotent across edits
-- to the value list.
ALTER TABLE conflict_flags
    DROP CONSTRAINT IF EXISTS conflict_flags_significance_tier_check;

ALTER TABLE conflict_flags
    ADD CONSTRAINT conflict_flags_significance_tier_check
    CHECK (significance_tier IS NULL OR significance_tier IN (
        'legal_threshold', 'pattern', 'connection'
    ));

-- Partial index — most queries select WHERE significance_tier IN (A, B) to
-- exclude operator-only Tier C from public surfaces. Indexing only the
-- non-NULL rows keeps the index small while legacy NULL rows stay in the
-- heap (they're filtered out at query time anyway).
CREATE INDEX IF NOT EXISTS conflict_flags_significance_tier_idx
    ON conflict_flags (significance_tier)
    WHERE significance_tier IS NOT NULL;
