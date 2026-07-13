-- Migration 125: Influence pattern taxonomy (S26.3)
-- Classifies conflict_flags into documented influence pattern categories
-- from docs/research/political-influence-tracing.md.
--
-- Design: taxonomy table + optional FK on conflict_flags. Patterns are
-- assigned by classify_influence_patterns() in db/entities.py, not by
-- the scanner itself — the scanner produces raw signals; the taxonomy
-- layer classifies them post-scan. This keeps the scanner simple and
-- makes pattern definitions independently updatable.

-- ============================================================
-- influence_patterns — documented influence pattern taxonomy
-- ============================================================
CREATE TABLE IF NOT EXISTS influence_patterns (
    id SMALLINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    pattern_name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    -- Which conflict_flags.flag_type values feed this pattern
    signal_types TEXT[] NOT NULL DEFAULT '{}',
    -- Sort order for UI display
    sort_order SMALLINT NOT NULL DEFAULT 0,
    -- Research citation
    source_doc TEXT NOT NULL DEFAULT 'docs/research/political-influence-tracing.md',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- FK on conflict_flags — nullable, assigned post-scan
-- ============================================================
ALTER TABLE conflict_flags
    ADD COLUMN IF NOT EXISTS influence_pattern_id SMALLINT
    REFERENCES influence_patterns(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_conflict_flags_pattern
    ON conflict_flags(influence_pattern_id)
    WHERE influence_pattern_id IS NOT NULL;

-- ============================================================
-- Seed the 5 patterns targeted for S26
-- ============================================================
INSERT INTO influence_patterns (pattern_name, description, signal_types, sort_order) VALUES
(
    'Pay-to-play',
    'Campaign contributions temporally correlated with contract awards or procurement decisions. California SB 1439 (2023) explicitly targets this pattern. Detected when a donor contributes within 6-24 months of receiving a city contract.',
    ARRAY['campaign_contribution', 'donor_vendor_expenditure'],
    1
),
(
    'Contract steering',
    'Patterns of no-bid awards, repeat sole-source contracts, or procurement timeline deviations favoring specific vendors. San Francisco Nuru scandal (2008-2020): $1M+ in bribes, 28 charged, $95M recovered from Recology.',
    ARRAY['donor_vendor_expenditure'],
    2
),
(
    'Conflicts of interest (planning/zoning)',
    'Officials participating in decisions affecting their disclosed economic interests. FPPC processes ~2,500 complaints annually. Chicago aldermanic prerogative: 36+ aldermen indicted since 1970s for zoning-related corruption.',
    ARRAY['form700_investment', 'campaign_contribution'],
    3
),
(
    'Revolving door',
    'Officials moving between government positions and entities they regulated, or regulated entities hiring former officials. Detected via entity_links showing official ↔ organization connections with role transitions.',
    ARRAY['llc_ownership_chain', 'campaign_contribution'],
    4
),
(
    'Quid pro quo permit approvals',
    'Campaign donations followed by unusually favorable or fast permit/variance approvals. AB 571 prohibits contributions over $250 from permit-seekers. Detected via temporal correlation of contribution → permit application → approval.',
    ARRAY['campaign_contribution', 'donor_vendor_expenditure'],
    5
)
ON CONFLICT (pattern_name) DO NOTHING;

-- ============================================================
-- RLS — public read
-- ============================================================
ALTER TABLE influence_patterns ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'influence_patterns' AND policyname = 'Public read') THEN
    DROP POLICY IF EXISTS "Public read" ON influence_patterns;
    CREATE POLICY "Public read" ON influence_patterns FOR SELECT USING (true);
  END IF;
END $$;
