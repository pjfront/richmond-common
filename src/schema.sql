-- Richmond Transparency Project — PostgreSQL Schema
-- Layer 1 (Document Lake) + Layer 2 (Structured Core) + Layer 3 (Embedding Index)
--
-- CRITICAL: Every table includes city_fips. Richmond CA = 0660620.
-- This is non-negotiable for scaling to 19,000 US cities.
--
-- Run against a PostgreSQL 15+ database with pgvector extension.

-- ============================================================
-- Extensions
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
-- pgvector: enable via Supabase Dashboard → Database → Extensions before uncommenting
-- CREATE EXTENSION IF NOT EXISTS "pgvector";

-- ============================================================
-- LAYER 1: Document Lake
-- Raw documents preserved exactly as received. Source of truth.
-- Re-extractable when prompts improve.
-- ============================================================

CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL,
    source_type VARCHAR(50) NOT NULL,  -- 'minutes', 'agenda', 'resolution', 'campaign_finance', 'form700', 'news', 'blog', 'newsletter', 'budget', 'socrata'
    source_url TEXT,
    source_identifier VARCHAR(100),    -- e.g. ADID for archive center docs, dataset ID for socrata
    raw_content BYTEA,                 -- original file bytes (PDF, HTML, etc.)
    raw_text TEXT,                     -- extracted plain text (for re-extraction without re-parsing)
    content_hash VARCHAR(64),          -- SHA-256 for deduplication
    mime_type VARCHAR(100),            -- 'application/pdf', 'text/html', etc.
    credibility_tier SMALLINT NOT NULL CHECK (credibility_tier BETWEEN 1 AND 4),
        -- 1: Official government records
        -- 2: Independent journalism
        -- 3: Stakeholder communications (disclose bias)
        -- 4: Community/social (context only)
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata JSONB NOT NULL DEFAULT '{}',  -- schema-less, varies by source
    CONSTRAINT uq_documents_hash UNIQUE (city_fips, content_hash)
);

CREATE INDEX idx_documents_city_fips ON documents(city_fips);
CREATE INDEX idx_documents_source_type ON documents(source_type);
CREATE INDEX idx_documents_ingested_at ON documents(ingested_at);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);

-- Extraction runs: track each time we extract structured data from a document.
-- Allows re-extraction when prompts improve without losing prior attempts.
CREATE TABLE extraction_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    extraction_model VARCHAR(100) NOT NULL,   -- e.g. 'claude-sonnet-4-20250514'
    extraction_prompt_version VARCHAR(50),     -- version tag for the prompt template
    extracted_data JSONB NOT NULL,             -- the full structured JSON output
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd NUMERIC(8, 4),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_current BOOLEAN NOT NULL DEFAULT TRUE   -- only one "current" extraction per document
);

CREATE INDEX idx_extraction_runs_document ON extraction_runs(document_id);
CREATE INDEX idx_extraction_runs_current ON extraction_runs(document_id) WHERE is_current = TRUE;


-- ============================================================
-- LAYER 2: Structured Core
-- Normalized tables for fast JOINs and conflict detection.
-- All foreign keys trace back to cities via city_fips.
-- ============================================================

-- Foundation --------------------------------------------------

CREATE TABLE cities (
    fips_code VARCHAR(7) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    state VARCHAR(2) NOT NULL,
    county VARCHAR(100),
    population INTEGER,
    timezone VARCHAR(50) NOT NULL DEFAULT 'America/Los_Angeles',
    charter_type VARCHAR(50),  -- 'charter', 'general_law'
    website_url TEXT,
    clerk_email VARCHAR(255),
    council_size SMALLINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed Richmond
INSERT INTO cities (fips_code, name, state, county, population, timezone, charter_type, website_url, clerk_email, council_size)
VALUES (
    '0660620', 'Richmond', 'CA', 'Contra Costa', 116448,
    'America/Los_Angeles', 'charter',
    'https://www.ci.richmond.ca.us', 'cityclerkdept@ci.richmond.ca.us', 7
) ON CONFLICT (fips_code) DO NOTHING;


CREATE TABLE officials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    name VARCHAR(200) NOT NULL,
    normalized_name VARCHAR(200) NOT NULL,  -- lowercase, stripped, for matching
    role VARCHAR(50) NOT NULL,              -- 'mayor', 'vice_mayor', 'councilmember'
    seat VARCHAR(20),                       -- district/seat number if applicable
    party_affiliation VARCHAR(50),
    term_start DATE,
    term_end DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    email VARCHAR(255),
    phone VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_officials_name_term UNIQUE (city_fips, normalized_name, term_start)
);

CREATE INDEX idx_officials_city ON officials(city_fips);
CREATE INDEX idx_officials_current ON officials(city_fips) WHERE is_current = TRUE;
CREATE INDEX idx_officials_normalized_name ON officials(normalized_name);


-- Meetings & Votes --------------------------------------------

CREATE TABLE meetings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    document_id UUID REFERENCES documents(id),        -- link back to Layer 1
    meeting_date DATE NOT NULL,
    meeting_type VARCHAR(30) NOT NULL,                 -- 'regular', 'special', 'closed_session', 'joint'
    call_to_order_time VARCHAR(100),
    adjournment_time VARCHAR(50),
    presiding_officer VARCHAR(200),
    minutes_url TEXT,
    agenda_url TEXT,
    video_url TEXT,
    adjourned_in_memory_of TEXT,
    next_meeting_date VARCHAR(100),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_meetings_date_type UNIQUE (city_fips, meeting_date, meeting_type)
);

CREATE INDEX idx_meetings_city ON meetings(city_fips);
CREATE INDEX idx_meetings_date ON meetings(meeting_date);


CREATE TABLE meeting_attendance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    official_id UUID NOT NULL REFERENCES officials(id),
    status VARCHAR(20) NOT NULL,   -- 'present', 'absent', 'late'
    notes TEXT,                     -- e.g. 'arrived after roll call'
    CONSTRAINT uq_attendance UNIQUE (meeting_id, official_id)
);

CREATE INDEX idx_attendance_meeting ON meeting_attendance(meeting_id);


CREATE TABLE agenda_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    item_number VARCHAR(20) NOT NULL,    -- e.g. 'O.1.a', 'P.1', 'C.2'
    title TEXT NOT NULL,
    description TEXT,
    department VARCHAR(200),
    staff_contact VARCHAR(500),
    category VARCHAR(50),                -- maps to AgendaCategory enum
    is_consent_calendar BOOLEAN NOT NULL DEFAULT FALSE,
    was_pulled_from_consent BOOLEAN NOT NULL DEFAULT FALSE,
    resolution_number VARCHAR(50),
    financial_amount VARCHAR(100),       -- dollar amount if contract/expenditure
    continued_from VARCHAR(100),
    continued_to VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_agenda_item UNIQUE (meeting_id, item_number)
);

CREATE INDEX idx_agenda_items_meeting ON agenda_items(meeting_id);
CREATE INDEX idx_agenda_items_category ON agenda_items(category);


CREATE TABLE motions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agenda_item_id UUID NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
    motion_type VARCHAR(30) NOT NULL,    -- 'original', 'substitute', 'friendly_amendment', 'reconsider', 'call_the_question'
    motion_text TEXT NOT NULL,
    moved_by VARCHAR(200),
    seconded_by VARCHAR(200),
    result VARCHAR(50) NOT NULL,           -- 'passed', 'failed', 'died for lack of a second'
    vote_tally TEXT,                       -- e.g. '5-2', '7-0', or full verbose tally
    resolution_number VARCHAR(50),
    sequence_number SMALLINT NOT NULL DEFAULT 1,  -- order of motions on same item
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_motions_agenda_item ON motions(agenda_item_id);


CREATE TABLE votes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    motion_id UUID NOT NULL REFERENCES motions(id) ON DELETE CASCADE,
    official_id UUID REFERENCES officials(id),       -- NULL if we can't resolve the name yet
    official_name VARCHAR(200) NOT NULL,              -- raw name from extraction
    official_role VARCHAR(50),
    vote_choice VARCHAR(20) NOT NULL,                 -- 'aye', 'nay', 'abstain', 'absent'
    CONSTRAINT uq_votes UNIQUE (motion_id, official_name)
);

CREATE INDEX idx_votes_motion ON votes(motion_id);
CREATE INDEX idx_votes_official ON votes(official_id);
CREATE INDEX idx_votes_choice ON votes(vote_choice);


CREATE TABLE friendly_amendments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    motion_id UUID NOT NULL REFERENCES motions(id) ON DELETE CASCADE,
    proposed_by VARCHAR(200) NOT NULL,
    description TEXT NOT NULL,
    accepted BOOLEAN NOT NULL
);


CREATE TABLE closed_session_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    item_number VARCHAR(20) NOT NULL,
    legal_authority TEXT NOT NULL,
    description TEXT NOT NULL,
    parties TEXT[],
    reportable_action TEXT,
    CONSTRAINT uq_closed_session UNIQUE (meeting_id, item_number)
);


CREATE TABLE public_comments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    agenda_item_id UUID REFERENCES agenda_items(id),  -- NULL for open forum
    speaker_name VARCHAR(200) NOT NULL,
    method VARCHAR(30) NOT NULL,              -- 'in_person', 'zoom', 'phone', 'email', 'ecomment'
    summary TEXT,
    comment_type VARCHAR(30) NOT NULL DEFAULT 'public',  -- 'public', 'written', 'system_generated'
    submitted_by_system BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_comments_meeting ON public_comments(meeting_id);


-- Campaign Finance --------------------------------------------

CREATE TABLE donors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    name VARCHAR(300) NOT NULL,
    normalized_name VARCHAR(300) NOT NULL,   -- lowercase, stripped, for matching
    employer VARCHAR(300),
    normalized_employer VARCHAR(300),
    occupation VARCHAR(200),
    address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- Uniqueness enforced via expression index below (constraints can't use COALESCE)
);

CREATE UNIQUE INDEX uq_donors ON donors(city_fips, normalized_name, COALESCE(employer, ''));
CREATE INDEX idx_donors_city ON donors(city_fips);
CREATE INDEX idx_donors_normalized ON donors(normalized_name);
CREATE INDEX idx_donors_employer ON donors(normalized_employer);


CREATE TABLE committees (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    name VARCHAR(500) NOT NULL,
    filer_id VARCHAR(50),              -- CAL-ACCESS filer ID
    committee_type VARCHAR(50),         -- 'candidate', 'pac', 'independent_expenditure'
    candidate_name VARCHAR(200),        -- if candidate-controlled committee
    official_id UUID REFERENCES officials(id),  -- link to our officials table
    status VARCHAR(20),                 -- 'active', 'terminated'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_committees_city ON committees(city_fips);
CREATE INDEX idx_committees_filer ON committees(filer_id);
CREATE INDEX idx_committees_official ON committees(official_id);


CREATE TABLE contributions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    donor_id UUID NOT NULL REFERENCES donors(id),
    committee_id UUID NOT NULL REFERENCES committees(id),
    amount NUMERIC(12, 2) NOT NULL,
    contribution_date DATE NOT NULL,
    contribution_type VARCHAR(30) NOT NULL,    -- 'monetary', 'nonmonetary', 'loan'
    filing_id VARCHAR(100),                    -- FPPC filing reference
    schedule VARCHAR(10),                      -- 'A', 'B', 'C', etc.
    source VARCHAR(50) NOT NULL,               -- 'calaccess', 'city_clerk', 'fppc'
    document_id UUID REFERENCES documents(id), -- link to raw source document
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_contributions_city ON contributions(city_fips);
CREATE INDEX idx_contributions_donor ON contributions(donor_id);
CREATE INDEX idx_contributions_committee ON contributions(committee_id);
CREATE INDEX idx_contributions_date ON contributions(contribution_date);
CREATE INDEX idx_contributions_amount ON contributions(amount);


-- Conflict Detection ------------------------------------------

CREATE TABLE economic_interests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    official_id UUID NOT NULL REFERENCES officials(id),
    filing_year INTEGER NOT NULL,
    schedule VARCHAR(10) NOT NULL,         -- 'A-1', 'A-2', 'B', 'C', 'D', 'E'
    interest_type VARCHAR(50) NOT NULL,    -- 'real_property', 'investment', 'income', 'gift', 'business_position'
    description TEXT NOT NULL,
    value_range VARCHAR(100),              -- e.g. '$100,001 - $1,000,000'
    location TEXT,                          -- address for real property
    source_url TEXT,
    document_id UUID REFERENCES documents(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_interests_official ON economic_interests(official_id);
CREATE INDEX idx_interests_type ON economic_interests(interest_type);


CREATE TABLE conflict_flags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    agenda_item_id UUID REFERENCES agenda_items(id),
    meeting_id UUID REFERENCES meetings(id),
    official_id UUID REFERENCES officials(id),
    flag_type VARCHAR(50) NOT NULL,            -- 'campaign_contribution', 'form700_real_property', 'form700_investment', 'vendor_donor_match'
    description TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]',       -- array of source docs and specifics
    confidence NUMERIC(3, 2) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    legal_reference TEXT,
    reviewed BOOLEAN NOT NULL DEFAULT FALSE,
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(200),
    false_positive BOOLEAN,
    scan_run_id UUID REFERENCES scan_runs(id),
    scan_mode VARCHAR(20),                     -- denormalized: 'prospective', 'retrospective'
    data_cutoff_date DATE,                     -- denormalized from scan_run
    superseded_by UUID REFERENCES conflict_flags(id),  -- if a later scan replaces this flag
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_flags_city ON conflict_flags(city_fips);
CREATE INDEX idx_flags_meeting ON conflict_flags(meeting_id);
CREATE INDEX idx_flags_official ON conflict_flags(official_id);
CREATE INDEX idx_flags_type ON conflict_flags(flag_type);
CREATE INDEX idx_flags_unreviewed ON conflict_flags(city_fips) WHERE reviewed = FALSE;
CREATE INDEX idx_flags_scan_run ON conflict_flags(scan_run_id);
CREATE INDEX idx_flags_current ON conflict_flags(meeting_id) WHERE is_current = TRUE;


-- Scan Runs (Cloud Pipeline Audit Trail) ---------------------

CREATE TABLE scan_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    meeting_id UUID REFERENCES meetings(id),
    scan_mode VARCHAR(20) NOT NULL,          -- 'prospective', 'retrospective'
    data_cutoff_date DATE,                   -- for prospective: only contributions on or before this date
    model_version VARCHAR(100),              -- Claude model used
    prompt_version VARCHAR(50),              -- extraction prompt version tag
    scanner_version VARCHAR(50),             -- conflict_scanner.py git SHA or version
    contributions_count INTEGER,             -- how many contributions were considered
    contributions_sources JSONB,             -- e.g. {"calaccess": 4892, "netfile": 22143}
    form700_count INTEGER,
    flags_found INTEGER NOT NULL DEFAULT 0,
    flags_by_tier JSONB,                     -- e.g. {"tier1": 0, "tier2": 1, "tier3": 3}
    clean_items_count INTEGER,
    enriched_items_count INTEGER,
    execution_time_seconds NUMERIC(8, 2),
    triggered_by VARCHAR(50),                -- 'scheduled', 'manual', 'reanalysis', 'data_refresh'
    pipeline_run_id VARCHAR(100),            -- GitHub Actions run ID or n8n execution ID
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- 'running', 'completed', 'failed'
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'     -- audit sidecar data (bias signals, filter funnel)
);

CREATE INDEX idx_scan_runs_city ON scan_runs(city_fips);
CREATE INDEX idx_scan_runs_meeting ON scan_runs(meeting_id);
CREATE INDEX idx_scan_runs_mode ON scan_runs(scan_mode);
CREATE INDEX idx_scan_runs_created ON scan_runs(created_at);
CREATE INDEX idx_scan_runs_status ON scan_runs(status);


-- Data Sync Log (Pipeline Observability) ---------------------

CREATE TABLE data_sync_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    source VARCHAR(50) NOT NULL,             -- 'netfile', 'calaccess', 'escribemeetings', 'archive_center', 'socrata', 'nextrequest'
    sync_type VARCHAR(30) NOT NULL,          -- 'full', 'incremental', 'manual'
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    records_fetched INTEGER,
    records_new INTEGER,
    records_updated INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'running',  -- 'running', 'completed', 'failed'
    error_message TEXT,
    triggered_by VARCHAR(50),                -- 'n8n_cron', 'github_actions', 'manual'
    pipeline_run_id VARCHAR(100),            -- GitHub Actions run ID or n8n execution ID
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_sync_log_city ON data_sync_log(city_fips);
CREATE INDEX idx_sync_log_source ON data_sync_log(source);
CREATE INDEX idx_sync_log_status ON data_sync_log(status);
CREATE INDEX idx_sync_log_started ON data_sync_log(started_at);


-- Document Tracking & CPRA -----------------------------------

CREATE TABLE document_references (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_document_id UUID NOT NULL REFERENCES documents(id),
    referenced_description TEXT NOT NULL,
    expected_url TEXT,
    found BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_document_id UUID REFERENCES documents(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE cpra_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    request_text TEXT NOT NULL,
    target_department VARCHAR(200),
    legal_basis TEXT DEFAULT 'California Public Records Act (Gov. Code § 6250 et seq.)',
    filed_date DATE,
    response_due DATE,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',  -- 'draft', 'filed', 'acknowledged', 'fulfilled', 'denied', 'appealed'
    response_notes TEXT,
    document_id UUID REFERENCES documents(id),  -- link to response if received
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_cpra_city ON cpra_requests(city_fips);
CREATE INDEX idx_cpra_status ON cpra_requests(status);


-- News & Media Integration ------------------------------------

CREATE TABLE external_references (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id),
    entity_type VARCHAR(50) NOT NULL,      -- 'official', 'company', 'topic', 'agenda_item'
    entity_id UUID,                         -- reference to the relevant table's ID
    entity_name VARCHAR(300),               -- human-readable name (for cases where entity_id is NULL)
    mention_type VARCHAR(50),               -- 'quoted', 'discussed', 'criticized', 'endorsed'
    excerpt TEXT,
    sentiment VARCHAR(20),                  -- 'positive', 'negative', 'neutral'
    confidence NUMERIC(3, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ext_refs_document ON external_references(document_id);
CREATE INDEX idx_ext_refs_entity ON external_references(entity_type, entity_id);


-- ============================================================
-- LAYER 3: Embedding Index (pgvector)
-- Single query combines vector similarity + SQL filtering.
-- Requires pgvector extension — enable in Supabase Dashboard
-- then uncomment this section.
-- ============================================================

-- CREATE TABLE chunks (
--     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
--     document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
--     chunk_index INTEGER NOT NULL,              -- position within document
--     chunk_text TEXT NOT NULL,
--     embedding vector(1536),                    -- text-embedding-3-small dimensions
--     meeting_id UUID REFERENCES meetings(id),
--     agenda_item_id UUID REFERENCES agenda_items(id),
--     official_id UUID REFERENCES officials(id),  -- if chunk is about a specific official
--     chunk_type VARCHAR(50),                     -- 'vote', 'comment', 'discussion', 'report', 'motion'
--     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
-- );
--
-- CREATE INDEX idx_chunks_document ON chunks(document_id);
-- CREATE INDEX idx_chunks_meeting ON chunks(meeting_id);
-- ivfflat index requires rows to build; uncomment after loading embedding data
-- CREATE INDEX idx_chunks_embedding ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);


-- ============================================================
-- Useful views
-- ============================================================

-- All votes with context: who voted how on what
CREATE VIEW v_votes_with_context AS
SELECT
    m.city_fips,
    m.meeting_date,
    m.meeting_type,
    ai.item_number,
    ai.title AS item_title,
    ai.category,
    ai.is_consent_calendar,
    ai.financial_amount,
    mt.motion_type,
    mt.motion_text,
    mt.result AS motion_result,
    mt.vote_tally,
    v.official_name,
    v.official_role,
    v.vote_choice,
    o.id AS official_id
FROM votes v
JOIN motions mt ON v.motion_id = mt.id
JOIN agenda_items ai ON mt.agenda_item_id = ai.id
JOIN meetings m ON ai.meeting_id = m.id
LEFT JOIN officials o ON v.official_id = o.id;


-- Contribution-to-vote join for conflict detection
CREATE VIEW v_donor_vote_crossref AS
SELECT
    co.city_fips,
    d.name AS donor_name,
    d.employer AS donor_employer,
    co.amount,
    co.contribution_date,
    cm.name AS committee_name,
    cm.candidate_name,
    o.name AS official_name,
    m.meeting_date,
    ai.item_number,
    ai.title AS item_title,
    ai.financial_amount,
    v.vote_choice
FROM contributions co
JOIN donors d ON co.donor_id = d.id
JOIN committees cm ON co.committee_id = cm.id
LEFT JOIN officials o ON cm.official_id = o.id
LEFT JOIN votes v ON v.official_id = o.id
LEFT JOIN motions mt ON v.motion_id = mt.id
LEFT JOIN agenda_items ai ON mt.agenda_item_id = ai.id
LEFT JOIN meetings m ON ai.meeting_id = m.id;


-- Split votes only (non-unanimous) — the politically interesting ones
CREATE VIEW v_split_votes AS
SELECT
    m.city_fips,
    m.meeting_date,
    ai.item_number,
    ai.title AS item_title,
    ai.category,
    mt.motion_type,
    mt.result,
    mt.vote_tally,
    mt.id AS motion_id
FROM motions mt
JOIN agenda_items ai ON mt.agenda_item_id = ai.id
JOIN meetings m ON ai.meeting_id = m.id
WHERE mt.vote_tally NOT LIKE '7-0'
  AND mt.vote_tally NOT LIKE '%-0'
  AND mt.result IS NOT NULL;
