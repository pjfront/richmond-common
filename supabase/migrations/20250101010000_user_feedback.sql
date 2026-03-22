-- Migration 002: User Feedback System
-- Adds user_feedback table for crowdsourced accuracy feedback,
-- data corrections, tips, and missing conflict reports.
-- Bridges to bias audit ground truth via v_feedback_ground_truth view.
-- Idempotent: safe to re-run.

-- ─── Table ──────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    feedback_type VARCHAR(30) NOT NULL,
        -- 'flag_accuracy', 'data_correction', 'tip', 'missing_conflict', 'general'

    -- Polymorphic entity reference
    entity_type VARCHAR(50),            -- 'conflict_flag', 'vote', 'official', 'agenda_item', 'contribution', 'meeting'
    entity_id UUID,                      -- FK to the referenced entity

    -- Flag accuracy specific
    flag_verdict VARCHAR(20),            -- 'confirm', 'dispute', 'add_context'

    -- Data correction specific
    field_name VARCHAR(100),             -- which field is wrong
    current_value TEXT,                  -- what the system currently shows
    suggested_value TEXT,                -- what the user thinks it should be

    -- Missing conflict specific
    conflict_nature VARCHAR(50),         -- 'contribution', 'property', 'business', 'family', 'other'
    official_name VARCHAR(200),          -- who the conflict involves

    -- Universal fields
    description TEXT,                    -- free-form explanation
    evidence_url TEXT,                   -- link to supporting evidence
    evidence_text TEXT,                  -- pasted text evidence

    -- Submitter info (anonymous by default)
    submitter_email VARCHAR(255),        -- optional, for follow-up
    submitter_name VARCHAR(200),         -- optional
    is_anonymous BOOLEAN NOT NULL DEFAULT TRUE,
    session_id VARCHAR(100),             -- browser session for spam detection, NOT for identity

    -- Moderation
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
        -- 'pending', 'reviewing', 'accepted', 'rejected', 'duplicate', 'acted_on'
    moderator_notes TEXT,
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(200),

    -- If this feedback resulted in a data change
    action_taken TEXT,                   -- 'flag_marked_false_positive', 'vote_corrected', 'tip_forwarded', etc.
    action_entity_id UUID,              -- FK to the entity that was modified

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─── Indexes ────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_feedback_city ON user_feedback(city_fips);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON user_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_entity ON user_feedback(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_feedback_status ON user_feedback(status);
CREATE INDEX IF NOT EXISTS idx_feedback_pending ON user_feedback(city_fips)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_feedback_created ON user_feedback(created_at);

-- ─── Row-Level Security ─────────────────────────────────────

ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;

-- Anon users can INSERT only (anonymous feedback submission)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'user_feedback' AND policyname = 'anon_insert_feedback'
    ) THEN
        DROP POLICY IF EXISTS anon_insert_feedback ON user_feedback;
CREATE POLICY anon_insert_feedback ON user_feedback
            FOR INSERT TO anon
            WITH CHECK (true);
    END IF;
END $$;

-- Service role gets full access (for admin/moderation)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'user_feedback' AND policyname = 'service_full_access_feedback'
    ) THEN
        DROP POLICY IF EXISTS service_full_access_feedback ON user_feedback;
CREATE POLICY service_full_access_feedback ON user_feedback
            FOR ALL TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;

-- ─── Bias Audit Bridge View ────────────────────────────────

CREATE OR REPLACE VIEW v_feedback_ground_truth AS
SELECT
    uf.id AS feedback_id,
    uf.entity_id AS conflict_flag_id,
    cf.scan_run_id,
    CASE uf.flag_verdict
        WHEN 'confirm' THEN TRUE
        WHEN 'dispute' THEN FALSE
        ELSE NULL  -- 'add_context' requires manual review
    END AS ground_truth,
    'user_feedback' AS ground_truth_source,
    uf.description AS audit_notes,
    uf.created_at
FROM user_feedback uf
JOIN conflict_flags cf ON uf.entity_id = cf.id
WHERE uf.feedback_type = 'flag_accuracy'
  AND uf.status IN ('accepted', 'acted_on');
