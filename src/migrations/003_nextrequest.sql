-- Migration 003: NextRequest/CPRA tables
-- Adds tables for public records request tracking and document storage.
-- Idempotent: safe to re-run (uses IF NOT EXISTS).

-- ============================================================
-- New Table: nextrequest_requests
-- Tracks CPRA/public records requests from the NextRequest portal.
-- ============================================================

CREATE TABLE IF NOT EXISTS nextrequest_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    city_fips VARCHAR(7) NOT NULL REFERENCES cities(fips_code),
    request_number VARCHAR(50) NOT NULL,
    request_text TEXT NOT NULL,
    requester_name VARCHAR(200),
    department VARCHAR(200),
    status VARCHAR(50) NOT NULL,
    submitted_date DATE,
    due_date DATE,
    closed_date DATE,
    days_to_close INTEGER,
    document_count INTEGER DEFAULT 0,
    portal_url TEXT,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_nextrequest UNIQUE (city_fips, request_number)
);

CREATE INDEX IF NOT EXISTS idx_nextrequest_city ON nextrequest_requests(city_fips);
CREATE INDEX IF NOT EXISTS idx_nextrequest_status ON nextrequest_requests(status);
CREATE INDEX IF NOT EXISTS idx_nextrequest_dept ON nextrequest_requests(department);
CREATE INDEX IF NOT EXISTS idx_nextrequest_submitted ON nextrequest_requests(submitted_date);

-- ============================================================
-- New Table: nextrequest_documents
-- Documents released in response to CPRA requests.
-- ============================================================

CREATE TABLE IF NOT EXISTS nextrequest_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    request_id UUID NOT NULL REFERENCES nextrequest_requests(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id),
    filename VARCHAR(500),
    file_type VARCHAR(50),
    file_size_bytes INTEGER,
    page_count INTEGER,
    download_url TEXT,
    has_redactions BOOLEAN,
    released_date DATE,
    extracted_text TEXT,
    extraction_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    extraction_metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nextrequest_docs_request ON nextrequest_documents(request_id);
CREATE INDEX IF NOT EXISTS idx_nextrequest_docs_extraction ON nextrequest_documents(extraction_status);
