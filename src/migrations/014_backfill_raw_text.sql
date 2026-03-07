-- Migration 014: Backfill raw_text from raw_content for archive_center documents
--
-- Context: save_to_documents was populating raw_content (bytea) but not raw_text (text).
-- sync_minutes_extraction queries raw_text, so extraction found 0 documents.
-- This backfill decodes existing raw_content into raw_text for all affected rows.
--
-- Safe to re-run: only updates rows where raw_text IS NULL and raw_content IS NOT NULL.

UPDATE documents
SET raw_text = convert_from(raw_content, 'UTF8')
WHERE source_type = 'archive_center'
  AND raw_content IS NOT NULL
  AND (raw_text IS NULL OR raw_text = '');
