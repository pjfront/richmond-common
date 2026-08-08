-- eSCRIBE source-reconciliation audit selectors (read-only)
-- Observed against Richmond Commons production on 2026-08-07.
--
-- Run only through a read-only connection or Supabase's
-- /database/query/read-only management endpoint. These SELECTs reproduce the
-- exact migration-134 candidate sets; they do not run the draft migration.

-- 1. Cutover gates and exact public deltas.
WITH metrics AS (
  SELECT 'recent_complete_full_sync' AS metric, COUNT(*)::bigint AS value
  FROM data_sync_log
  WHERE city_fips = '0660620'
    AND source = 'escribemeetings'
    AND sync_type = 'full'
    AND status = 'completed'
    AND completed_at >= NOW() - INTERVAL '48 hours'
    AND NOT COALESCE(metadata, '{}'::jsonb)
      @> '{"retryable_incomplete": true}'::jsonb

  UNION ALL
  SELECT 'meetings_with_guid', COUNT(*)
  FROM meetings
  WHERE city_fips = '0660620' AND source_meeting_guid IS NOT NULL

  UNION ALL
  SELECT 'missing_current_raw', COUNT(*)
  FROM meetings m
  WHERE m.city_fips = '0660620'
    AND m.source_meeting_guid IS NOT NULL
    AND NOT EXISTS (
      SELECT 1
      FROM documents d
      WHERE d.city_fips = m.city_fips
        AND d.source_type = 'escribemeetings'
        AND d.metadata->>'meeting_guid' = m.source_meeting_guid
        AND d.source_retired_at IS NULL
        AND COALESCE(d.metadata->>'raw_sanitized', 'false') = 'true'
        AND d.metadata ? 'agenda_revision_applied_sha256'
    )

  UNION ALL
  SELECT 'active_unsanitized_documents', COUNT(*)
  FROM documents d
  WHERE d.source_type = 'escribemeetings'
    AND d.source_retired_at IS NULL
    AND COALESCE(d.metadata->>'raw_sanitized', 'false') <> 'true'

  UNION ALL
  SELECT 'unsanitized_without_replacement', COUNT(*)
  FROM documents legacy_raw
  WHERE legacy_raw.source_type = 'escribemeetings'
    AND legacy_raw.source_retired_at IS NULL
    AND COALESCE(legacy_raw.metadata->>'raw_sanitized', 'false') <> 'true'
    AND (
      NULLIF(legacy_raw.metadata->>'meeting_guid', '') IS NULL
      OR NOT EXISTS (
        SELECT 1
        FROM documents current_raw
        WHERE current_raw.id <> legacy_raw.id
          AND current_raw.city_fips = legacy_raw.city_fips
          AND current_raw.source_type = 'escribemeetings'
          AND current_raw.source_retired_at IS NULL
          AND COALESCE(
                current_raw.metadata->>'raw_sanitized', 'false'
              ) = 'true'
          AND current_raw.metadata->>'meeting_guid'
                = legacy_raw.metadata->>'meeting_guid'
          AND current_raw.metadata ? 'agenda_revision_applied_sha256'
      )
    )

  UNION ALL
  SELECT 'active_legacy_agenda_items', COUNT(*)
  FROM agenda_items ai
  WHERE ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority = 'legacy'

  UNION ALL
  SELECT 'active_agenda_items', COUNT(*)
  FROM agenda_items ai
  WHERE ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority = 'agenda'

  UNION ALL
  SELECT 'active_minutes_items', COUNT(*)
  FROM agenda_items ai
  WHERE ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority = 'minutes'

  UNION ALL
  SELECT 'unproven_active_agenda', COUNT(*)
  FROM agenda_items ai
  WHERE ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority = 'agenda'
    AND ai.agenda_source_revision_sha256 IS NULL

  UNION ALL
  SELECT 'active_null_revision_attachments', COUNT(*)
  FROM agenda_item_attachments aia
  WHERE aia.source_retired_at IS NULL
    AND aia.source_revision_sha256 IS NULL

  UNION ALL
  SELECT 'active_legacy_parent_attachments', COUNT(*)
  FROM agenda_item_attachments aia
  JOIN agenda_items ai ON ai.id = aia.agenda_item_id
  WHERE aia.source_retired_at IS NULL
    AND ai.agenda_source_authority = 'legacy'

  UNION ALL
  SELECT 'active_attachment_quarantine_candidates', COUNT(*)
  FROM agenda_item_attachments aia
  JOIN agenda_items ai ON ai.id = aia.agenda_item_id
  WHERE aia.source_retired_at IS NULL
    AND (
      aia.source_revision_sha256 IS NULL
      OR ai.agenda_source_authority = 'legacy'
    )

  UNION ALL
  SELECT 'incomplete_current_attachments', COUNT(*)
  FROM agenda_item_attachments aia
  JOIN agenda_items ai ON ai.id = aia.agenda_item_id
  WHERE aia.source_retired_at IS NULL
    AND ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority <> 'legacy'
    AND aia.source_revision_sha256 IS NOT NULL
    AND (
      aia.document_id IS NULL
      OR aia.source_content_sha256 IS NULL
    )

  UNION ALL
  SELECT 'before_public_documents', COUNT(*)
  FROM documents d
  WHERE d.source_retired_at IS NULL

  UNION ALL
  SELECT 'before_public_agenda_items', COUNT(*)
  FROM agenda_items ai
  JOIN meetings m ON m.id = ai.meeting_id
  WHERE ai.agenda_source_retired_at IS NULL
    AND m.source_cancelled_at IS NULL

  UNION ALL
  SELECT 'expected_public_agenda_item_loss', COUNT(*)
  FROM agenda_items ai
  JOIN meetings m ON m.id = ai.meeting_id
  WHERE ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority = 'legacy'
    AND m.source_cancelled_at IS NULL

  UNION ALL
  SELECT 'before_public_attachments', COUNT(*)
  FROM agenda_item_attachments aia
  JOIN agenda_items ai ON ai.id = aia.agenda_item_id
  JOIN meetings m ON m.id = ai.meeting_id
  WHERE aia.source_retired_at IS NULL
    AND ai.agenda_source_retired_at IS NULL
    AND m.source_cancelled_at IS NULL

  UNION ALL
  SELECT 'expected_public_attachment_loss', COUNT(*)
  FROM agenda_item_attachments aia
  JOIN agenda_items ai ON ai.id = aia.agenda_item_id
  JOIN meetings m ON m.id = ai.meeting_id
  WHERE aia.source_retired_at IS NULL
    AND ai.agenda_source_retired_at IS NULL
    AND m.source_cancelled_at IS NULL
    AND (
      aia.source_revision_sha256 IS NULL
      OR ai.agenda_source_authority = 'legacy'
    )
)
SELECT metric, value FROM metrics ORDER BY metric;


-- 2. Exact unsanitized-document candidate rows.
SELECT
  d.id,
  d.source_identifier,
  d.metadata->>'meeting_guid' AS meeting_guid,
  d.metadata->>'meeting_date' AS meeting_date,
  d.metadata->>'meeting_name' AS meeting_name,
  d.ingested_at,
  d.source_url,
  EXISTS (
    SELECT 1
    FROM documents replacement
    WHERE replacement.id <> d.id
      AND replacement.city_fips = d.city_fips
      AND replacement.source_type = 'escribemeetings'
      AND replacement.source_retired_at IS NULL
      AND COALESCE(
            replacement.metadata->>'raw_sanitized', 'false'
          ) = 'true'
      AND replacement.metadata->>'meeting_guid'
            = d.metadata->>'meeting_guid'
      AND replacement.metadata ? 'agenda_revision_applied_sha256'
  ) AS has_current_sanitized_replacement
FROM documents d
WHERE d.source_type = 'escribemeetings'
  AND d.source_retired_at IS NULL
  AND COALESCE(d.metadata->>'raw_sanitized', 'false') <> 'true'
ORDER BY
  d.metadata->>'meeting_date',
  d.metadata->>'meeting_guid',
  d.ingested_at,
  d.id;


-- 3. Exact legacy agenda-item candidate rows, with the conservative
-- out-of-current-reconciliation marker used in the decision packet.
SELECT
  ai.id,
  ai.meeting_id,
  m.meeting_date,
  m.meeting_type,
  b.name AS body_name,
  meeting_document.source_type AS meeting_document_source,
  ai.item_number,
  ai.title,
  ai.plain_language_summary IS NOT NULL AS has_plain_language_summary,
  (
    m.meeting_date < DATE '2022-01-01'
    OR COALESCE(b.name, '') <> 'City Council'
    OR meeting_document.source_type IS DISTINCT FROM 'escribemeetings'
  ) AS clearly_outside_current_full_reconciliation
FROM agenda_items ai
JOIN meetings m ON m.id = ai.meeting_id
LEFT JOIN bodies b ON b.id = m.body_id
LEFT JOIN documents meeting_document ON meeting_document.id = m.document_id
WHERE ai.agenda_source_retired_at IS NULL
  AND ai.agenda_source_authority = 'legacy'
ORDER BY m.meeting_date, b.name, ai.item_number, ai.id;


-- 4. Exact attachment candidate rows.
SELECT
  aia.id,
  aia.agenda_item_id,
  m.id AS meeting_id,
  m.meeting_date,
  ai.item_number,
  ai.title AS agenda_item_title,
  ai.agenda_source_authority,
  aia.document_id AS source_document_id,
  aia.filename,
  aia.source_url,
  aia.source_revision_sha256,
  aia.source_content_sha256,
  aia.extracted_text IS NOT NULL AS has_extracted_text
FROM agenda_item_attachments aia
JOIN agenda_items ai ON ai.id = aia.agenda_item_id
JOIN meetings m ON m.id = ai.meeting_id
WHERE aia.source_retired_at IS NULL
  AND (
    aia.source_revision_sha256 IS NULL
    OR ai.agenda_source_authority = 'legacy'
  )
ORDER BY m.meeting_date, ai.item_number, aia.document_id, aia.id;


-- 5. Exact GUID-linked meetings without an accepted sanitized raw revision.
SELECT
  m.id,
  m.meeting_date,
  m.meeting_type,
  m.source_meeting_guid,
  m.agenda_url,
  m.minutes_url
FROM meetings m
WHERE m.city_fips = '0660620'
  AND m.source_meeting_guid IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM documents d
    WHERE d.city_fips = m.city_fips
      AND d.source_type = 'escribemeetings'
      AND d.metadata->>'meeting_guid' = m.source_meeting_guid
      AND d.source_retired_at IS NULL
      AND COALESCE(d.metadata->>'raw_sanitized', 'false') = 'true'
      AND d.metadata ? 'agenda_revision_applied_sha256'
  )
ORDER BY m.meeting_date, m.source_meeting_guid;


-- 6. Full-sync evidence for the migration-134 48-hour gate.
SELECT
  id,
  status,
  started_at,
  completed_at,
  records_fetched,
  records_new,
  records_updated,
  error_message,
  metadata
FROM data_sync_log
WHERE city_fips = '0660620'
  AND source = 'escribemeetings'
  AND sync_type = 'full'
ORDER BY started_at DESC
LIMIT 20;
