-- Migration 132: durable NextRequest document identity for reconciliation.
--
-- NextRequest's public API exposes a stable integer document ID. The original
-- table stored only a download URL and had no uniqueness constraint, so
-- periodic detail reconciliation would insert duplicate rows and could not
-- refresh metadata for a changed existing document.
--
-- Nullable preserves legacy/manual rows whose upstream ID was never captured.
-- The partial unique index makes all newly reconciled source rows idempotent.
-- Existing RLS/grants remain unchanged; this migration adds no public write
-- path and the service-role pipeline remains the only writer.

ALTER TABLE nextrequest_documents
  ADD COLUMN IF NOT EXISTS source_document_id BIGINT;

COMMENT ON COLUMN nextrequest_documents.source_document_id IS
  'Stable integer document ID from the NextRequest public API.';

CREATE UNIQUE INDEX IF NOT EXISTS uq_nextrequest_documents_source_id
  ON nextrequest_documents (request_id, source_document_id)
  WHERE source_document_id IS NOT NULL;
