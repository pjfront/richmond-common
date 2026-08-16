-- Migration 139: bound current conflict-flag lookups by agenda item.
-- Forward-only index migration; do not apply as part of this PR.
-- Migration 134 remains untouched and forbidden.

-- Operator agenda-item detail loads filter on agenda_item_id + is_current.
-- The existing partial index is meeting_id-first, so PostgreSQL otherwise
-- scans current flags for every agenda-item lookup.
CREATE INDEX IF NOT EXISTS idx_conflict_flags_current_agenda_item
  ON public.conflict_flags (agenda_item_id)
  WHERE is_current = TRUE;
