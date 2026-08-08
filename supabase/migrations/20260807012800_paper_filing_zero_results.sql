-- Migration 128: durable terminal-zero receipts for paper filings
--
-- The paper-filing extractor previously used contributions.filing_id as its
-- only cross-CI idempotency signal.  That works for filings with itemized
-- rows, but not for Form 410s (which carry no contributions) or for a valid
-- Form 460/497 extraction whose structured result is an empty list.  The
-- runner-local JSON records those outcomes, but CI discards that write, so
-- every later run paid to process the same source again.
--
-- This operator-only table stores only terminal outcomes that intentionally
-- create zero contribution rows.  Non-zero extractions continue to become
-- durable through contributions after the normal loader commits them; this
-- avoids a receipt-before-load crash window that could suppress real rows.

CREATE TABLE IF NOT EXISTS paper_filing_zero_results (
    city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
    filing_id VARCHAR NOT NULL,
    committee TEXT NOT NULL,
    form_type VARCHAR(3) NOT NULL
        CHECK (form_type IN ('410', '460', '497')),
    result_kind VARCHAR(40) NOT NULL
        CHECK (result_kind IN (
            'not_contribution_form',
            'extractor_returned_zero'
        )),
    extraction_method VARCHAR(24) NOT NULL
        CHECK (extraction_method IN (
            'rss_classification',
            'text_llm',
            'vision_llm'
        )),
    extraction_model VARCHAR(100) NOT NULL,

    -- D1-style provenance quartet.  This is an operational receipt, not a
    -- public factual assertion that the filing had zero economic activity.
    source_url TEXT NOT NULL CHECK (BTRIM(source_url) <> ''),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_tier SMALLINT NOT NULL DEFAULT 1
        CHECK (source_tier BETWEEN 1 AND 4),
    confidence_score NUMERIC(3,2) NOT NULL
        CHECK (confidence_score BETWEEN 0 AND 1),

    PRIMARY KEY (city_fips, filing_id)
);

COMMENT ON TABLE paper_filing_zero_results IS
    'Operator-only durable receipts for paper filings whose completed '
    'processing intentionally produced no contribution rows. Used for '
    'cross-CI idempotency; not a public claim of zero financial activity.';

COMMENT ON COLUMN paper_filing_zero_results.confidence_score IS
    'Confidence that the recorded terminal pipeline outcome occurred. '
    'A value of 1.00 records a deterministic Form 410 classification or '
    'a structurally validated tool result; it does not rate semantic OCR accuracy.';

-- The composite primary key covers the idempotency lookup
-- (city_fips, filing_id), so no additional index is needed.

ALTER TABLE paper_filing_zero_results ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS paper_filing_zero_results_service_all
    ON paper_filing_zero_results;
CREATE POLICY paper_filing_zero_results_service_all
    ON paper_filing_zero_results
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
