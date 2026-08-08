-- Migration 133: provenance-safe source reconciliation tombstones
--
-- Source list/detail APIs are mutable.  Preserve the local audit trail, but
-- make rows that a *complete authoritative fetch* no longer contains
-- ineligible for public reads and automatic downstream generation.

ALTER TABLE agenda_items
  ADD COLUMN IF NOT EXISTS agenda_source_authority TEXT NOT NULL DEFAULT 'legacy',
  ADD COLUMN IF NOT EXISTS agenda_source_revision_sha256 TEXT,
  ADD COLUMN IF NOT EXISTS agenda_source_retired_at TIMESTAMPTZ;

ALTER TABLE agenda_items
  DROP CONSTRAINT IF EXISTS agenda_items_source_authority_check;
ALTER TABLE agenda_items
  ADD CONSTRAINT agenda_items_source_authority_check
  CHECK (agenda_source_authority IN ('legacy', 'agenda', 'minutes'));

COMMENT ON COLUMN agenda_items.agenda_source_authority IS
  'Structured fact owner: legacy (unclassified), agenda (mutable plan), or minutes (adopted outcome; agenda may never overwrite/retire).';

COMMENT ON COLUMN agenda_items.agenda_source_revision_sha256 IS
  'Last complete eSCRIBE agenda revision that authoritatively confirmed this agenda-owned item. NULL is expected for legacy/minutes provenance; authority, not NULL alone, controls reconciliation.';
COMMENT ON COLUMN agenda_items.agenda_source_retired_at IS
  'Set only when a later complete eSCRIBE agenda omits a previously managed item; NULL rows are current.';

-- Evidence-based ownership retrofit. Only row-level minutes evidence proves
-- ownership. Meeting-level minutes_url/document_id provenance cannot prove
-- that every item came from minutes, and document_id was historically mutable.
-- Unproven rows remain unclassified (and outside automatic reconciliation)
-- until a complete future source load establishes exact ownership. Public
-- enforcement is deferred to the coverage-gated cutover described below.
UPDATE agenda_items ai
SET agenda_source_authority = 'minutes',
    agenda_source_revision_sha256 = NULL,
    agenda_source_retired_at = NULL
WHERE EXISTS (
  SELECT 1 FROM motions mo
  WHERE mo.agenda_item_id = ai.id AND mo.source = 'minutes'
);

-- No-motion items can still have exact adopted-minutes evidence in the
-- current Archive Center extraction. Promote only item-number matches from
-- the structured arrays; meeting-level document provenance alone is not
-- enough to classify a row.
UPDATE agenda_items ai
SET agenda_source_authority = 'minutes',
    agenda_source_revision_sha256 = NULL,
    agenda_source_retired_at = NULL
WHERE ai.agenda_source_authority = 'legacy'
  AND EXISTS (
    SELECT 1
    FROM meetings m
    JOIN documents d ON d.id = m.document_id
    JOIN extraction_runs er ON er.document_id = d.id AND er.is_current
    CROSS JOIN LATERAL (
      SELECT value AS item
      FROM jsonb_array_elements(
        CASE WHEN jsonb_typeof(
          er.extracted_data->'consent_calendar'->'items'
        ) = 'array'
        THEN er.extracted_data->'consent_calendar'->'items'
        ELSE '[]'::jsonb END
      )
      UNION ALL
      SELECT value
      FROM jsonb_array_elements(
        CASE WHEN jsonb_typeof(er.extracted_data->'action_items') = 'array'
        THEN er.extracted_data->'action_items'
        ELSE '[]'::jsonb END
      )
      UNION ALL
      SELECT value
      FROM jsonb_array_elements(
        CASE WHEN jsonb_typeof(
          er.extracted_data->'housing_authority_items'
        ) = 'array'
        THEN er.extracted_data->'housing_authority_items'
        ELSE '[]'::jsonb END
      )
    ) source_item
    WHERE m.id = ai.meeting_id
      AND d.source_type = 'archive_center'
      AND NULLIF(source_item.item->>'item_number', '') = ai.item_number
  );

CREATE INDEX IF NOT EXISTS idx_agenda_items_active_meeting
  ON agenda_items (meeting_id, item_number)
  WHERE agenda_source_retired_at IS NULL;

ALTER TABLE agenda_item_attachments
  ADD COLUMN IF NOT EXISTS source_revision_sha256 TEXT,
  ADD COLUMN IF NOT EXISTS source_content_sha256 TEXT,
  ADD COLUMN IF NOT EXISTS source_retired_at TIMESTAMPTZ;

COMMENT ON COLUMN agenda_item_attachments.source_revision_sha256 IS
  'Complete eSCRIBE agenda revision that last confirmed this DocumentId on its exact item.';
COMMENT ON COLUMN agenda_item_attachments.source_content_sha256 IS
  'SHA-256 of the downloaded current attachment bytes; prevents stale text from masquerading as a same-ID replacement.';
COMMENT ON COLUMN agenda_item_attachments.source_retired_at IS
  'Set when a complete later agenda omits this attachment; extracted text is preserved for service-role audit.';

CREATE INDEX IF NOT EXISTS idx_agenda_item_attachments_active
  ON agenda_item_attachments (agenda_item_id, document_id)
  WHERE source_retired_at IS NULL;

ALTER TABLE meetings
  ADD COLUMN IF NOT EXISTS source_cancelled_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS source_meeting_guid TEXT;

COMMENT ON COLUMN meetings.source_cancelled_at IS
  'Authoritative eSCRIBE cancellation; cleared by agenda revival or adopted minutes.';
COMMENT ON COLUMN meetings.source_meeting_guid IS
  'Stable upstream eSCRIBE meeting GUID. Date/name/type may change without creating a second logical meeting.';

CREATE INDEX IF NOT EXISTS idx_meetings_source_active
  ON meetings (city_fips, meeting_date DESC)
  WHERE source_cancelled_at IS NULL;

ALTER TABLE nextrequest_requests
  ADD COLUMN IF NOT EXISTS source_removed_at TIMESTAMPTZ;

ALTER TABLE nextrequest_documents
  ADD COLUMN IF NOT EXISTS source_removed_at TIMESTAMPTZ;

ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS source_retired_at TIMESTAMPTZ;

COMMENT ON COLUMN documents.source_retired_at IS
  'Superseded/withdrawn source revision. Service-role audit remains available; public reads see current revisions only.';

-- Historic eSCRIBE rows used mutable name+date identifiers and many expose
-- local_path/text_path fields inside raw JSON. Derive GUID only for operator
-- reconciliation. Existing rows remain visible during the additive phase;
-- the later cutover quarantines them only after sanitized replacements pass
-- coverage checks.
CREATE OR REPLACE FUNCTION migration_133_safe_escribe_guid(payload BYTEA)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
STRICT
AS $$
BEGIN
  RETURN NULLIF(convert_from(payload, 'UTF8')::jsonb->>'guid', '');
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END;
$$;

WITH parsed AS (
  SELECT id, migration_133_safe_escribe_guid(raw_content) AS meeting_guid
  FROM documents
  WHERE source_type = 'escribemeetings'
    AND raw_content IS NOT NULL
)
UPDATE documents d
SET metadata = jsonb_set(
      COALESCE(d.metadata, '{}'::jsonb),
      '{meeting_guid}',
      to_jsonb(parsed.meeting_guid),
      TRUE
    ),
    source_identifier = 'escribemeetings_' || parsed.meeting_guid
FROM parsed
WHERE d.id = parsed.id
  AND parsed.meeting_guid IS NOT NULL;

UPDATE meetings m
SET source_meeting_guid = d.metadata->>'meeting_guid'
FROM documents d
WHERE d.id = m.document_id
  AND d.source_type = 'escribemeetings'
  AND NULLIF(d.metadata->>'meeting_guid', '') IS NOT NULL;

-- Cutover is intentionally not performed here. Existing raw documents,
-- attachments, and legacy agenda rows remain visible until the additive code
-- has completed a full authoritative reconciliation and coverage verification.
-- A later enforcement migration will quarantine unresolved legacy rows.

DROP FUNCTION migration_133_safe_escribe_guid(BYTEA);

CREATE UNIQUE INDEX IF NOT EXISTS idx_meetings_source_guid
  ON meetings (city_fips, source_meeting_guid)
  WHERE source_meeting_guid IS NOT NULL;

COMMENT ON COLUMN nextrequest_requests.source_removed_at IS
  'Set only after a complete unfiltered public-request listing proves the request is absent; cleared if it reappears.';
COMMENT ON COLUMN nextrequest_documents.source_removed_at IS
  'Set only after a complete per-request public-document listing proves the document is absent/private; cleared if it reappears.';

CREATE INDEX IF NOT EXISTS idx_nextrequest_requests_public
  ON nextrequest_requests (city_fips, submitted_date DESC)
  WHERE source_removed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_nextrequest_documents_public
  ON nextrequest_documents (request_id, released_date DESC)
  WHERE source_removed_at IS NULL;

-- The database boundary is the non-omissible public default.  PostgreSQL
-- owners/service-role connections retain BYPASSRLS access for operator audit
-- and source reconciliation; anon/authenticated Supabase reads see only
-- current upstream rows.
ALTER TABLE agenda_items ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON agenda_items;
CREATE POLICY "Public read" ON agenda_items
  FOR SELECT USING (
    agenda_source_retired_at IS NULL
    AND EXISTS (
      SELECT 1 FROM meetings parent_meeting
      WHERE parent_meeting.id = agenda_items.meeting_id
        AND parent_meeting.source_cancelled_at IS NULL
    )
  );

ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON meetings;
CREATE POLICY "Public read" ON meetings
  FOR SELECT USING (source_cancelled_at IS NULL);

DROP POLICY IF EXISTS "Public read" ON nextrequest_requests;
CREATE POLICY "Public read" ON nextrequest_requests
  FOR SELECT USING (source_removed_at IS NULL);

DROP POLICY IF EXISTS "Public read" ON nextrequest_documents;
CREATE POLICY "Public read" ON nextrequest_documents
  FOR SELECT USING (
    source_removed_at IS NULL
    AND EXISTS (
      SELECT 1
      FROM nextrequest_requests parent_request
      WHERE parent_request.id = nextrequest_documents.request_id
        AND parent_request.source_removed_at IS NULL
    )
  );

DROP POLICY IF EXISTS "Public read" ON documents;
CREATE POLICY "Public read" ON documents
  FOR SELECT USING (source_retired_at IS NULL);

ALTER TABLE extraction_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON extraction_runs;
CREATE POLICY "Public read" ON extraction_runs FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM documents parent_document
    WHERE parent_document.id = extraction_runs.document_id
      AND parent_document.source_retired_at IS NULL
  )
);

ALTER TABLE external_references ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON external_references;
CREATE POLICY "Public read" ON external_references FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM documents parent_document
    WHERE parent_document.id = external_references.document_id
      AND parent_document.source_retired_at IS NULL
  )
);

ALTER TABLE document_references ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON document_references;
CREATE POLICY "Public read" ON document_references FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM documents source_document
    WHERE source_document.id = document_references.source_document_id
      AND source_document.source_retired_at IS NULL
  )
  AND (
    resolved_document_id IS NULL
    OR EXISTS (
      SELECT 1 FROM documents resolved_document
      WHERE resolved_document.id = document_references.resolved_document_id
        AND resolved_document.source_retired_at IS NULL
    )
  )
);

-- Parent RLS does not automatically protect rows selected directly from a
-- child table. Apply the same active-agenda boundary to public derivatives.
ALTER TABLE motions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON motions;
CREATE POLICY "Public read" ON motions FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM agenda_items ai
    WHERE ai.id = motions.agenda_item_id
      AND ai.agenda_source_retired_at IS NULL
  )
);

ALTER TABLE votes ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON votes;
CREATE POLICY "Public read" ON votes FOR SELECT USING (
  EXISTS (
    SELECT 1
    FROM motions mo
    JOIN agenda_items ai ON ai.id = mo.agenda_item_id
    WHERE mo.id = votes.motion_id
      AND ai.agenda_source_retired_at IS NULL
  )
);

ALTER TABLE friendly_amendments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON friendly_amendments;
CREATE POLICY "Public read" ON friendly_amendments FOR SELECT USING (
  EXISTS (
    SELECT 1
    FROM motions mo
    JOIN agenda_items ai ON ai.id = mo.agenda_item_id
    JOIN meetings parent_meeting ON parent_meeting.id = ai.meeting_id
    WHERE mo.id = friendly_amendments.motion_id
      AND ai.agenda_source_retired_at IS NULL
      AND parent_meeting.source_cancelled_at IS NULL
  )
);

ALTER TABLE public_comments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON public_comments;
CREATE POLICY "Public read" ON public_comments FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM meetings parent_meeting
    WHERE parent_meeting.id = public_comments.meeting_id
      AND parent_meeting.source_cancelled_at IS NULL
  )
  AND (
    agenda_item_id IS NULL
    OR EXISTS (
      SELECT 1 FROM agenda_items ai
      WHERE ai.id = public_comments.agenda_item_id
        AND ai.agenda_source_retired_at IS NULL
    )
  )
);

ALTER TABLE comment_theme_assignments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON comment_theme_assignments;
CREATE POLICY "Public read" ON comment_theme_assignments FOR SELECT USING (
  EXISTS (
    SELECT 1
    FROM public_comments pc
    JOIN meetings parent_meeting ON parent_meeting.id = pc.meeting_id
    LEFT JOIN agenda_items ai ON ai.id = pc.agenda_item_id
    WHERE pc.id = comment_theme_assignments.comment_id
      AND parent_meeting.source_cancelled_at IS NULL
      AND (
        pc.agenda_item_id IS NULL
        OR (
          ai.agenda_source_retired_at IS NULL
        )
      )
  )
);

ALTER TABLE conflict_flags ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON conflict_flags;
CREATE POLICY "Public read" ON conflict_flags FOR SELECT USING (
  (
    meeting_id IS NULL
    OR EXISTS (
      SELECT 1 FROM meetings parent_meeting
      WHERE parent_meeting.id = conflict_flags.meeting_id
        AND parent_meeting.source_cancelled_at IS NULL
    )
  )
  AND (
    agenda_item_id IS NULL
    OR EXISTS (
      SELECT 1 FROM agenda_items ai
      WHERE ai.id = conflict_flags.agenda_item_id
        AND ai.agenda_source_retired_at IS NULL
    )
  )
);

ALTER TABLE meeting_attendance ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON meeting_attendance;
CREATE POLICY "Public read" ON meeting_attendance FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM meetings parent_meeting
    WHERE parent_meeting.id = meeting_attendance.meeting_id
      AND parent_meeting.source_cancelled_at IS NULL
  )
);

ALTER TABLE closed_session_items ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON closed_session_items;
CREATE POLICY "Public read" ON closed_session_items FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM meetings parent_meeting
    WHERE parent_meeting.id = closed_session_items.meeting_id
      AND parent_meeting.source_cancelled_at IS NULL
  )
);

ALTER TABLE agenda_item_attachments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON agenda_item_attachments;
CREATE POLICY "Public read" ON agenda_item_attachments FOR SELECT USING (
  source_retired_at IS NULL
  AND
  EXISTS (
    SELECT 1 FROM agenda_items ai
    WHERE ai.id = agenda_item_attachments.agenda_item_id
      AND ai.agenda_source_retired_at IS NULL
  )
);

ALTER TABLE item_topics ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON item_topics;
CREATE POLICY "Public read" ON item_topics FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM agenda_items ai
    WHERE ai.id = item_topics.agenda_item_id
      AND ai.agenda_source_retired_at IS NULL
  )
);

ALTER TABLE item_theme_narratives ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Public read" ON item_theme_narratives;
CREATE POLICY "Public read" ON item_theme_narratives FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM agenda_items ai
    WHERE ai.id = item_theme_narratives.agenda_item_id
      AND ai.agenda_source_retired_at IS NULL
  )
);

DROP POLICY IF EXISTS agenda_items_embeddings_anon_read
  ON agenda_items_embeddings;
DROP POLICY IF EXISTS "Public read" ON agenda_items_embeddings;
CREATE POLICY "Public read" ON agenda_items_embeddings FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM agenda_items ai
    WHERE ai.id = agenda_items_embeddings.id
      AND ai.agenda_source_retired_at IS NULL
  )
);

DROP POLICY IF EXISTS motions_embeddings_anon_read ON motions_embeddings;
DROP POLICY IF EXISTS "Public read" ON motions_embeddings;
CREATE POLICY "Public read" ON motions_embeddings FOR SELECT USING (
  EXISTS (
    SELECT 1
    FROM motions mo
    JOIN agenda_items ai ON ai.id = mo.agenda_item_id
    WHERE mo.id = motions_embeddings.id
      AND ai.agenda_source_retired_at IS NULL
  )
);

DROP POLICY IF EXISTS meetings_embeddings_anon_read ON meetings_embeddings;
DROP POLICY IF EXISTS "Public read" ON meetings_embeddings;
CREATE POLICY "Public read" ON meetings_embeddings FOR SELECT USING (
  EXISTS (
    SELECT 1 FROM meetings parent_meeting
    WHERE parent_meeting.id = meetings_embeddings.id
      AND parent_meeting.source_cancelled_at IS NULL
  )
);

-- Migration 087 only observed INSERT/DELETE. Tombstoning/revival is an UPDATE,
-- so recompute the stored public count for all three operations and backfill.
CREATE OR REPLACE FUNCTION update_meeting_agenda_item_count()
RETURNS TRIGGER AS $$
DECLARE
  affected_meeting_id UUID;
BEGIN
  affected_meeting_id := COALESCE(NEW.meeting_id, OLD.meeting_id);
  UPDATE meetings m
  SET agenda_item_count = (
    SELECT COUNT(*)::INT
    FROM agenda_items ai
    WHERE ai.meeting_id = affected_meeting_id
      AND ai.agenda_source_retired_at IS NULL
  )
  WHERE m.id = affected_meeting_id;

  IF TG_OP = 'UPDATE' AND OLD.meeting_id IS DISTINCT FROM NEW.meeting_id THEN
    UPDATE meetings m
    SET agenda_item_count = (
      SELECT COUNT(*)::INT
      FROM agenda_items ai
      WHERE ai.meeting_id = OLD.meeting_id
        AND ai.agenda_source_retired_at IS NULL
    )
    WHERE m.id = OLD.meeting_id;
  END IF;

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agenda_item_count ON agenda_items;
CREATE TRIGGER trg_agenda_item_count
  AFTER INSERT OR DELETE OR UPDATE OF agenda_source_retired_at, meeting_id
  ON agenda_items
  FOR EACH ROW
  EXECUTE FUNCTION update_meeting_agenda_item_count();

UPDATE meetings m
SET agenda_item_count = (
  SELECT COUNT(*)::INT
  FROM agenda_items ai
  WHERE ai.meeting_id = m.id
    AND ai.agenda_source_retired_at IS NULL
);
