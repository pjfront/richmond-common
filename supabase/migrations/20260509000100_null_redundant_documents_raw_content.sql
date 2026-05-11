-- Migration 105: NULL redundant raw_content bytes (see src/migrations/105_*.sql for context)

UPDATE documents
SET raw_content = NULL
WHERE raw_content IS NOT NULL
  AND raw_text IS NOT NULL
  AND length(raw_text) > 0
  AND source_type != 'escribemeetings';
