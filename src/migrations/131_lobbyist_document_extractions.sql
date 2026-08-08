-- Durable source-closest cache for paid lobbyist PDF vision extraction.
--
-- Document Center PDFs are immutable by content hash but the extraction used
-- to run on every CI invocation.  Persist the structurally validated model
-- result (including an explicit empty list) so a crash before the downstream
-- loader can reconstruct records without buying the same generation again.

CREATE TABLE IF NOT EXISTS lobbyist_document_extractions (
  city_fips           VARCHAR(7) NOT NULL DEFAULT '0660620',
  document_id         BIGINT NOT NULL,
  content_sha256      TEXT NOT NULL
                      CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  records             JSONB NOT NULL
                      CHECK (jsonb_typeof(records) = 'array'),
  extraction_provider TEXT NOT NULL CHECK (BTRIM(extraction_provider) <> ''),
  extraction_model    TEXT NOT NULL CHECK (BTRIM(extraction_model) <> ''),
  prompt_version      TEXT NOT NULL CHECK (BTRIM(prompt_version) <> ''),

  -- D1 provenance quartet plus the non-omissible D5 AI marker. This table is
  -- operator-only; public rows are written later to lobbyist_registrations.
  source_url           TEXT NOT NULL CHECK (BTRIM(source_url) <> ''),
  extracted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source_tier          SMALLINT NOT NULL DEFAULT 1
                       CHECK (source_tier BETWEEN 1 AND 4),
  confidence_score     NUMERIC(3,2) NOT NULL
                       CHECK (confidence_score BETWEEN 0 AND 1),
  ai_generated         BOOLEAN NOT NULL DEFAULT TRUE CHECK (ai_generated),

  PRIMARY KEY (
    city_fips, document_id, content_sha256,
    extraction_provider, extraction_model, prompt_version
  )
);

CREATE INDEX IF NOT EXISTS idx_lobbyist_document_extractions_latest
  ON lobbyist_document_extractions (city_fips, document_id, extracted_at DESC);

COMMENT ON TABLE lobbyist_document_extractions IS
  'Service-only cache of structurally validated AI extraction results for '
  'official Richmond lobbyist registration PDFs, keyed by exact content hash.';

COMMENT ON COLUMN lobbyist_document_extractions.confidence_score IS
  'Confidence in the structurally validated extraction receipt, not an '
  'independent factual verification of every model-read checkmark.';

ALTER TABLE lobbyist_document_extractions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lobbyist_document_extractions_service_all
  ON lobbyist_document_extractions;
CREATE POLICY lobbyist_document_extractions_service_all
  ON lobbyist_document_extractions
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
