-- Bounded, deterministic retry state for agenda proceeding classification.
--
-- Previously invalid/model-error rows remained proceeding_type IS NULL
-- forever.  The unordered LIMIT 100 repeatedly selected the same poison rows,
-- spending on them and starving later agenda items.  Persist attempts on the
-- source row, order work deterministically, and dead-letter after three tries.

ALTER TABLE agenda_items
  ADD COLUMN IF NOT EXISTS proceeding_classification_attempts SMALLINT
    NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS proceeding_classification_last_error TEXT,
  ADD COLUMN IF NOT EXISTS proceeding_classification_last_attempted_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS proceeding_classification_dead_lettered_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS proceeding_classification_claim_token UUID,
  ADD COLUMN IF NOT EXISTS proceeding_classification_claim_expires_at TIMESTAMPTZ;

ALTER TABLE agenda_items
  DROP CONSTRAINT IF EXISTS agenda_items_proceeding_classification_attempts_check;
ALTER TABLE agenda_items
  ADD CONSTRAINT agenda_items_proceeding_classification_attempts_check
  CHECK (
    proceeding_classification_attempts >= 0
    AND proceeding_classification_attempts <= 3
  );

CREATE INDEX IF NOT EXISTS idx_agenda_items_proceeding_classification_pending
  ON agenda_items (proceeding_classification_attempts, id)
  WHERE proceeding_type IS NULL
    AND proceeding_classification_attempts < 3;

CREATE INDEX IF NOT EXISTS idx_agenda_items_proceeding_classification_claims
  ON agenda_items (proceeding_classification_claim_expires_at)
  WHERE proceeding_classification_claim_token IS NOT NULL;

COMMENT ON COLUMN agenda_items.proceeding_classification_attempts IS
  'Bounded LLM attempts; rows reaching 3 remain inspectable but leave the paid queue.';
COMMENT ON COLUMN agenda_items.proceeding_classification_last_error IS
  'Last provider or validation error, truncated by the application.';
COMMENT ON COLUMN agenda_items.proceeding_classification_dead_lettered_at IS
  'Set when the third unsuccessful classification attempt is recorded.';
COMMENT ON COLUMN agenda_items.proceeding_classification_claim_token IS
  'Ephemeral worker ownership token; success/failure writes must match it.';
COMMENT ON COLUMN agenda_items.proceeding_classification_claim_expires_at IS
  'Crash-recovery lease for claimed classification work.';
