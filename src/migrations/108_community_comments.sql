-- Community comments: residents discuss agenda items on the platform.
-- Threaded replies supported. Comments can be batch-submitted to the City Clerk
-- as part of the public record before meeting deadlines.
--
-- Publication tier: Graduated (new user-generated content, needs operator review)

CREATE TABLE IF NOT EXISTS community_comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
    agenda_item_id UUID NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
    parent_comment_id UUID REFERENCES community_comments(id) ON DELETE CASCADE,
    author_name VARCHAR(200) NOT NULL,
    author_email VARCHAR(320),
    comment_text TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'published',
    submitted_to_clerk BOOLEAN NOT NULL DEFAULT FALSE,
    clerk_batch_id UUID,
    ip_hash VARCHAR(64),
    session_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_community_comments_item
    ON community_comments(agenda_item_id);
CREATE INDEX IF NOT EXISTS idx_community_comments_parent
    ON community_comments(parent_comment_id);
CREATE INDEX IF NOT EXISTS idx_community_comments_status
    ON community_comments(status);
CREATE INDEX IF NOT EXISTS idx_community_comments_batch
    ON community_comments(clerk_batch_id)
    WHERE clerk_batch_id IS NOT NULL;

-- Clerk submission batches: tracks when comments were packaged and sent
CREATE TABLE IF NOT EXISTS clerk_submission_batches (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
    agenda_item_id UUID NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    comment_count INTEGER NOT NULL,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submission_method VARCHAR(30) NOT NULL DEFAULT 'manual',
    submission_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    submitted_by VARCHAR(200),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_clerk_batches_item
    ON clerk_submission_batches(agenda_item_id);

-- RLS: anonymous users can INSERT community comments, only service role can read/update
ALTER TABLE community_comments ENABLE ROW LEVEL SECURITY;
ALTER TABLE clerk_submission_batches ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS community_comments_anon_insert ON community_comments;
CREATE POLICY community_comments_anon_insert ON community_comments
    FOR INSERT TO anon WITH CHECK (true);

DROP POLICY IF EXISTS community_comments_anon_select ON community_comments;
CREATE POLICY community_comments_anon_select ON community_comments
    FOR SELECT TO anon USING (status = 'published');

DROP POLICY IF EXISTS community_comments_service ON community_comments;
CREATE POLICY community_comments_service ON community_comments
    FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS clerk_batches_service ON clerk_submission_batches;
CREATE POLICY clerk_batches_service ON clerk_submission_batches
    FOR ALL TO service_role USING (true) WITH CHECK (true);
