-- DRAFT ONLY: promote to both migration trees after the cutover runbook passes.
-- This file is intentionally outside src/supabase migrations so it cannot
-- auto-apply before the external full-source reconciliation.

BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Keep the preflight snapshot, quarantine writes, policy replacement, and
-- postflight assertions on one stable source state. Public reads can continue;
-- source writers wait until this short operator-controlled transaction ends.
LOCK TABLE documents, meetings, agenda_items, agenda_item_attachments
  IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE source_reconciliation_cutover_audit (
  singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
  active_unsanitized_documents BIGINT NOT NULL,
  active_legacy_agenda_items BIGINT NOT NULL,
  active_null_revision_attachments BIGINT NOT NULL,
  active_legacy_parent_attachments BIGINT NOT NULL,
  active_attachment_quarantine_candidates BIGINT NOT NULL,
  before_public_documents BIGINT NOT NULL,
  expected_public_document_loss BIGINT NOT NULL,
  before_public_agenda_items BIGINT NOT NULL,
  expected_public_agenda_item_loss BIGINT NOT NULL,
  before_public_attachments BIGINT NOT NULL,
  expected_public_attachment_loss BIGINT NOT NULL
) ON COMMIT DROP;

DO $$
DECLARE
  missing_current_raw BIGINT;
  unsanitized_without_replacement BIGINT;
  unproven_active_agenda BIGINT;
  incomplete_current_attachments BIGINT;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM data_sync_log
    WHERE city_fips = '0660620'
      AND source = 'escribemeetings'
      AND sync_type = 'full'
      AND status = 'completed'
      AND completed_at >= NOW() - INTERVAL '48 hours'
      AND NOT COALESCE(metadata, '{}'::jsonb)
        @> '{"retryable_incomplete": true}'::jsonb
  ) THEN
    RAISE EXCEPTION
      'source reconciliation cutover blocked: no recent complete full sync';
  END IF;

  -- Every meeting already linked to a stable eSCRIBE GUID must have an active,
  -- sanitized raw revision that Layer 2 actually accepted.
  SELECT COUNT(*) INTO missing_current_raw
  FROM meetings m
  WHERE m.city_fips = '0660620'
    AND m.source_meeting_guid IS NOT NULL
    AND NOT EXISTS (
      SELECT 1 FROM documents d
      WHERE d.city_fips = m.city_fips
        AND d.source_type = 'escribemeetings'
        AND d.metadata->>'meeting_guid' = m.source_meeting_guid
        AND d.source_retired_at IS NULL
        AND COALESCE(d.metadata->>'raw_sanitized', 'false') = 'true'
        AND d.metadata ? 'agenda_revision_applied_sha256'
    );
  IF missing_current_raw <> 0 THEN
    RAISE EXCEPTION
      'source reconciliation cutover blocked: % meetings lack current sanitized raw proof',
      missing_current_raw;
  END IF;

  -- The UPDATE below hides every still-public unsanitized eSCRIBE raw row, not
  -- merely rows already linked through meetings. Prove a current sanitized
  -- replacement for each exact GUID; NULL-GUID rows therefore fail closed.
  SELECT COUNT(*) INTO unsanitized_without_replacement
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
    );
  IF unsanitized_without_replacement <> 0 THEN
    RAISE EXCEPTION
      'source reconciliation cutover blocked: % public unsanitized eSCRIBE documents lack a current sanitized GUID replacement',
      unsanitized_without_replacement;
  END IF;

  -- Legacy rows are an explicit quarantine candidate. Agenda-owned rows are
  -- not: every active agenda-owned row must carry the accepted revision proof.
  SELECT COUNT(*) INTO unproven_active_agenda
  FROM agenda_items ai
  WHERE ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority = 'agenda'
    AND ai.agenda_source_revision_sha256 IS NULL;
  IF unproven_active_agenda <> 0 THEN
    RAISE EXCEPTION
      'source reconciliation cutover blocked: % active agenda-owned rows lack revision proof',
      unproven_active_agenda;
  END IF;

  -- NULL-revision and legacy-parent attachments are explicit quarantine
  -- candidates. Other current attachments need stable source identity and
  -- downloaded-byte proof. Text extraction is enrichment eligibility, not
  -- publication proof.
  SELECT COUNT(*) INTO incomplete_current_attachments
  FROM agenda_item_attachments aia
  JOIN agenda_items ai ON ai.id = aia.agenda_item_id
  WHERE aia.source_retired_at IS NULL
    AND ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority <> 'legacy'
    AND aia.source_revision_sha256 IS NOT NULL
    AND (
      aia.document_id IS NULL
      OR aia.source_content_sha256 IS NULL
    );
  IF incomplete_current_attachments <> 0 THEN
    RAISE EXCEPTION
      'source reconciliation cutover blocked: % current attachments lack DocumentId/content-hash proof',
      incomplete_current_attachments;
  END IF;
END;
$$;

-- Snapshot both the complete quarantine candidate sets and the effective
-- public predicates installed by migration 133. These counts are the only
-- losses this transaction is allowed to cause.
INSERT INTO source_reconciliation_cutover_audit (
  active_unsanitized_documents,
  active_legacy_agenda_items,
  active_null_revision_attachments,
  active_legacy_parent_attachments,
  active_attachment_quarantine_candidates,
  before_public_documents,
  expected_public_document_loss,
  before_public_agenda_items,
  expected_public_agenda_item_loss,
  before_public_attachments,
  expected_public_attachment_loss
)
SELECT
  (
    SELECT COUNT(*) FROM documents d
    WHERE d.source_type = 'escribemeetings'
      AND d.source_retired_at IS NULL
      AND COALESCE(d.metadata->>'raw_sanitized', 'false') <> 'true'
  ),
  (
    SELECT COUNT(*) FROM agenda_items ai
    WHERE ai.agenda_source_retired_at IS NULL
      AND ai.agenda_source_authority = 'legacy'
  ),
  (
    SELECT COUNT(*) FROM agenda_item_attachments aia
    WHERE aia.source_retired_at IS NULL
      AND aia.source_revision_sha256 IS NULL
  ),
  (
    SELECT COUNT(*)
    FROM agenda_item_attachments aia
    JOIN agenda_items ai ON ai.id = aia.agenda_item_id
    WHERE aia.source_retired_at IS NULL
      AND ai.agenda_source_authority = 'legacy'
  ),
  (
    SELECT COUNT(*)
    FROM agenda_item_attachments aia
    JOIN agenda_items ai ON ai.id = aia.agenda_item_id
    WHERE aia.source_retired_at IS NULL
      AND (
        aia.source_revision_sha256 IS NULL
        OR ai.agenda_source_authority = 'legacy'
      )
  ),
  (
    SELECT COUNT(*) FROM documents d
    WHERE d.source_retired_at IS NULL
  ),
  (
    SELECT COUNT(*) FROM documents d
    WHERE d.source_type = 'escribemeetings'
      AND d.source_retired_at IS NULL
      AND COALESCE(d.metadata->>'raw_sanitized', 'false') <> 'true'
  ),
  (
    SELECT COUNT(*)
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE ai.agenda_source_retired_at IS NULL
      AND m.source_cancelled_at IS NULL
  ),
  (
    SELECT COUNT(*)
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE ai.agenda_source_retired_at IS NULL
      AND ai.agenda_source_authority = 'legacy'
      AND m.source_cancelled_at IS NULL
  ),
  (
    SELECT COUNT(*)
    FROM agenda_item_attachments aia
    JOIN agenda_items ai ON ai.id = aia.agenda_item_id
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE aia.source_retired_at IS NULL
      AND ai.agenda_source_retired_at IS NULL
      AND m.source_cancelled_at IS NULL
  ),
  (
    SELECT COUNT(*)
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
  );

DO $$
DECLARE
  audit source_reconciliation_cutover_audit%ROWTYPE;
BEGIN
  SELECT * INTO STRICT audit FROM source_reconciliation_cutover_audit;
  RAISE NOTICE
    'source reconciliation candidates: % unsanitized documents, % legacy agenda items, % NULL-revision attachments, % legacy-parent attachments (% distinct attachments)',
    audit.active_unsanitized_documents,
    audit.active_legacy_agenda_items,
    audit.active_null_revision_attachments,
    audit.active_legacy_parent_attachments,
    audit.active_attachment_quarantine_candidates;
  RAISE NOTICE
    'approved public deltas: documents -%, agenda_items -%, agenda_item_attachments -%',
    audit.expected_public_document_loss,
    audit.expected_public_agenda_item_loss,
    audit.expected_public_attachment_loss;
END;
$$;

DO $$
DECLARE
  audit source_reconciliation_cutover_audit%ROWTYPE;
  affected_rows BIGINT;
BEGIN
  SELECT * INTO STRICT audit FROM source_reconciliation_cutover_audit;

  UPDATE documents
  SET source_retired_at = NOW()
  WHERE source_type = 'escribemeetings'
    AND source_retired_at IS NULL
    AND COALESCE(metadata->>'raw_sanitized', 'false') <> 'true';
  GET DIAGNOSTICS affected_rows = ROW_COUNT;
  IF affected_rows <> audit.active_unsanitized_documents THEN
    RAISE EXCEPTION
      'source reconciliation cutover aborted: retired % unsanitized documents, expected %',
      affected_rows, audit.active_unsanitized_documents;
  END IF;

  UPDATE agenda_item_attachments aia
  SET source_retired_at = NOW()
  FROM agenda_items ai
  WHERE ai.id = aia.agenda_item_id
    AND aia.source_retired_at IS NULL
    AND (
      aia.source_revision_sha256 IS NULL
      OR ai.agenda_source_authority = 'legacy'
    );
  GET DIAGNOSTICS affected_rows = ROW_COUNT;
  IF affected_rows <> audit.active_attachment_quarantine_candidates THEN
    RAISE EXCEPTION
      'source reconciliation cutover aborted: retired % attachments, expected %',
      affected_rows, audit.active_attachment_quarantine_candidates;
  END IF;

  -- Tombstone the reviewed legacy set as well as excluding it in policy. This
  -- keeps reruns truly idempotent and makes every migration-133 child policy
  -- inherit the same quarantine boundary through its retired-parent check.
  UPDATE agenda_items
  SET agenda_source_retired_at = NOW()
  WHERE agenda_source_retired_at IS NULL
    AND agenda_source_authority = 'legacy';
  GET DIAGNOSTICS affected_rows = ROW_COUNT;
  IF affected_rows <> audit.active_legacy_agenda_items THEN
    RAISE EXCEPTION
      'source reconciliation cutover aborted: retired % legacy agenda items, expected %',
      affected_rows, audit.active_legacy_agenda_items;
  END IF;
END;
$$;

DROP POLICY IF EXISTS "Public read" ON agenda_items;
CREATE POLICY "Public read" ON agenda_items FOR SELECT USING (
  agenda_source_retired_at IS NULL
  AND agenda_source_authority <> 'legacy'
  AND EXISTS (
    SELECT 1 FROM meetings parent_meeting
    WHERE parent_meeting.id = agenda_items.meeting_id
      AND parent_meeting.source_cancelled_at IS NULL
  )
);

DROP POLICY IF EXISTS "Public read" ON agenda_item_attachments;
CREATE POLICY "Public read" ON agenda_item_attachments FOR SELECT USING (
  source_retired_at IS NULL
  AND EXISTS (
    SELECT 1
    FROM agenda_items ai
    JOIN meetings parent_meeting ON parent_meeting.id = ai.meeting_id
    WHERE ai.id = agenda_item_attachments.agenda_item_id
      AND ai.agenda_source_retired_at IS NULL
      AND ai.agenda_source_authority <> 'legacy'
      AND parent_meeting.source_cancelled_at IS NULL
  )
);

-- Re-evaluate the effective public predicates after both quarantine writes and
-- the parent policy change. Any loss outside the snapshotted candidate sets
-- aborts and rolls back the entire cutover, including the policy replacement.
DO $$
DECLARE
  audit source_reconciliation_cutover_audit%ROWTYPE;
  after_public_documents BIGINT;
  after_public_agenda_items BIGINT;
  after_public_attachments BIGINT;
  remaining_unsanitized_documents BIGINT;
  remaining_legacy_agenda_items BIGINT;
  remaining_attachment_candidates BIGINT;
BEGIN
  SELECT * INTO STRICT audit FROM source_reconciliation_cutover_audit;

  SELECT COUNT(*) INTO after_public_documents
  FROM documents d
  WHERE d.source_retired_at IS NULL;

  SELECT COUNT(*) INTO after_public_agenda_items
  FROM agenda_items ai
  JOIN meetings m ON m.id = ai.meeting_id
  WHERE ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority <> 'legacy'
    AND m.source_cancelled_at IS NULL;

  SELECT COUNT(*) INTO after_public_attachments
  FROM agenda_item_attachments aia
  JOIN agenda_items ai ON ai.id = aia.agenda_item_id
  JOIN meetings m ON m.id = ai.meeting_id
  WHERE aia.source_retired_at IS NULL
    AND ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority <> 'legacy'
    AND m.source_cancelled_at IS NULL;

  SELECT COUNT(*) INTO remaining_unsanitized_documents
  FROM documents d
  WHERE d.source_type = 'escribemeetings'
    AND d.source_retired_at IS NULL
    AND COALESCE(d.metadata->>'raw_sanitized', 'false') <> 'true';

  SELECT COUNT(*) INTO remaining_legacy_agenda_items
  FROM agenda_items ai
  WHERE ai.agenda_source_retired_at IS NULL
    AND ai.agenda_source_authority = 'legacy';

  SELECT COUNT(*) INTO remaining_attachment_candidates
  FROM agenda_item_attachments aia
  JOIN agenda_items ai ON ai.id = aia.agenda_item_id
  WHERE aia.source_retired_at IS NULL
    AND (
      aia.source_revision_sha256 IS NULL
      OR ai.agenda_source_authority = 'legacy'
    );

  IF remaining_unsanitized_documents <> 0
     OR remaining_legacy_agenda_items <> 0
     OR remaining_attachment_candidates <> 0 THEN
    RAISE EXCEPTION
      'source reconciliation cutover aborted: quarantine incomplete (documents %, agenda_items %, attachments %)',
      remaining_unsanitized_documents,
      remaining_legacy_agenda_items,
      remaining_attachment_candidates;
  END IF;

  IF after_public_documents
       <> audit.before_public_documents
          - audit.expected_public_document_loss THEN
    RAISE EXCEPTION
      'source reconciliation cutover aborted: documents public count %, expected %',
      after_public_documents,
      audit.before_public_documents - audit.expected_public_document_loss;
  END IF;

  IF after_public_agenda_items
       <> audit.before_public_agenda_items
          - audit.expected_public_agenda_item_loss THEN
    RAISE EXCEPTION
      'source reconciliation cutover aborted: agenda_items public count %, expected %',
      after_public_agenda_items,
      audit.before_public_agenda_items
        - audit.expected_public_agenda_item_loss;
  END IF;

  IF after_public_attachments
       <> audit.before_public_attachments
          - audit.expected_public_attachment_loss THEN
    RAISE EXCEPTION
      'source reconciliation cutover aborted: agenda_item_attachments public count %, expected %',
      after_public_attachments,
      audit.before_public_attachments
        - audit.expected_public_attachment_loss;
  END IF;
END;
$$;

COMMIT;
