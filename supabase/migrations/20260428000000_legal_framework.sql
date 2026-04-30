-- Migration 098: Legal-framework classification + party-entity extraction on agenda_items.
--
-- Implements §1 ("Agenda Item Classification") and §2d ("Party Identification")
-- of docs/specs/signal-significance-spec.md (Scanner v4).
--
-- Column-name disambiguation:
--   The spec drafted on 2026-03-16 proposed a column called `proceeding_type`,
--   but migration 076 (pgvector + agenda intelligence, 2026-04) had already
--   introduced an `agenda_items.proceeding_type` column populated with a
--   PROCEDURAL classification — resolution / ordinance / appropriation /
--   appointment / hearing / proclamation / report / censure / appeal /
--   consent / other. That existing column answers "what kind of action
--   is this item?" and is consumed by batch_classify_proceeding.py, the
--   item-detail page, and the agenda-summary generators. Reusing the name
--   would conflate two distinct axes:
--
--     proceeding_type (existing, procedural):
--       What kind of action? — used by extraction & summary pipelines
--     legal_framework (this migration, jurisdictional):
--       Which California ethics law applies? — used by Scanner v4
--
--   Both axes are needed, neither is reducible to the other (a "resolution"
--   can be either legislative or entitlement depending on whether it
--   approves a specific parcel rezoning vs general policy). So this
--   migration adds a SEPARATE column rather than overloading the existing
--   one. Documenting the rename in 2026-04-28-filing-period-briefings.md
--   is a follow-on doc fix.
--
-- legal_framework values:
--
--   entitlement   → Levine Act (Gov. Code §84308) applies (>$500 threshold,
--                   12-month lookback, recusal required)
--   legislative   → Levine Act does NOT apply; PRA §87100 still applies
--   contract      → §1090 applies (any financial interest → entire board barred)
--   appointment   → Exempt from Levine Act (FPPC treats as employment contract)
--   uncertain     → Heuristic couldn't classify; LLM fallback or operator review
--
-- party_entities enables the second half of Tier A detection: knowing WHO
-- the party to the proceeding is, not just whose name appears in item text.
-- The Levine Act flags donors who are parties/participants in the specific
-- proceeding — a developer who happens to be cited in a staff report is
-- not a party. See spec §2d for the layered extraction approach (text
-- patterns → permits/licenses join → entity registry bridge).
--
-- Idempotent: ADD COLUMN IF NOT EXISTS. No backfill in this migration —
-- classification runs as a separate batch script (heuristic-first, LLM
-- fallback for ambiguous items) and writes via UPDATE.

-- ── agenda_items: legal-framework classification ───────────────────────

ALTER TABLE agenda_items
  ADD COLUMN IF NOT EXISTS legal_framework            TEXT,
  ADD COLUMN IF NOT EXISTS legal_framework_source     TEXT,
  ADD COLUMN IF NOT EXISTS legal_framework_classified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS party_entities             JSONB;

COMMENT ON COLUMN agenda_items.legal_framework IS
  'California ethics-law framework: entitlement | legislative | contract | '
  'appointment | uncertain. Determines which threshold model (Levine Act, '
  'PRA, §1090) applies to financial connections on this item. Distinct from '
  'agenda_items.proceeding_type (procedural classification — resolution, '
  'ordinance, etc.). NULL = not yet classified. See signal-significance-spec.md §1.';

COMMENT ON COLUMN agenda_items.legal_framework_source IS
  'How the framework was assigned: ''heuristic'' (keyword match), ''llm'' '
  '(LLM fallback for ambiguous items), ''manual'' (operator override). Used '
  'to audit precision and tune the heuristic over time.';

COMMENT ON COLUMN agenda_items.legal_framework_classified_at IS
  'When legal_framework was last set. NULL when legal_framework is NULL. '
  'Backfill scripts use this to find items needing reclassification after '
  'heuristic updates.';

COMMENT ON COLUMN agenda_items.party_entities IS
  'Array of {name, role, raw_text} extracted from the item. role values: '
  '''applicant'' (Levine party), ''vendor'' (contract awardee), ''licensee'', '
  '''subject'' (real property at issue). Empty array when item has no '
  'identifiable party (most legislative items). NULL when extraction has '
  'not yet run. See signal-significance-spec.md §2d.';

-- ── Indexes ─────────────────────────────────────────────────────────────

-- Partial index on the framework column — most queries filter to "items
-- with a Levine Act framework" (entitlement | contract) and the long tail
-- of legislative items doesn't need to live in the hot path.
CREATE INDEX IF NOT EXISTS agenda_items_legal_framework_idx
  ON agenda_items (legal_framework)
  WHERE legal_framework IS NOT NULL;

-- GIN index on party_entities for "find every item where a given entity
-- is a party" queries (the donor→party Tier A match path).
CREATE INDEX IF NOT EXISTS agenda_items_party_entities_idx
  ON agenda_items USING GIN (party_entities)
  WHERE party_entities IS NOT NULL;

-- ── Sanity constraints ──────────────────────────────────────────────────

-- Reject typos: only the documented values are allowed. NULL stays valid
-- (means "not yet classified"). Drop-then-create so the migration is
-- idempotent across re-runs and across edits to the value list.
ALTER TABLE agenda_items
  DROP CONSTRAINT IF EXISTS agenda_items_legal_framework_check;

ALTER TABLE agenda_items
  ADD CONSTRAINT agenda_items_legal_framework_check
  CHECK (legal_framework IS NULL OR legal_framework IN (
    'entitlement', 'legislative', 'contract', 'appointment', 'uncertain'
  ));

ALTER TABLE agenda_items
  DROP CONSTRAINT IF EXISTS agenda_items_legal_framework_source_check;

ALTER TABLE agenda_items
  ADD CONSTRAINT agenda_items_legal_framework_source_check
  CHECK (legal_framework_source IS NULL OR legal_framework_source IN (
    'heuristic', 'llm', 'manual'
  ));
