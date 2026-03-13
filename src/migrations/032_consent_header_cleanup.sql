-- Migration 032: Consent Calendar Header Cleanup
-- B.49: Remove section header rows from agenda_items that were incorrectly
-- stored as agenda items (bare-letter item_numbers like "V", "M", "C").
-- These headers have no actionable content and cause uninformative scanner flags.
--
-- Idempotent: safe to re-run.

-- Step 1: Detach conflict flags from header items (set agenda_item_id to NULL).
-- These flags are uninformative ("CITY COUNCIL CONSENT CALENDAR" as the flagged item)
-- and will be superseded on next rescan.
UPDATE conflict_flags cf
SET agenda_item_id = NULL
FROM agenda_items ai
WHERE cf.agenda_item_id = ai.id
  AND ai.item_number ~ '^[A-Z]+$'
  AND LENGTH(ai.item_number) <= 4;

-- Step 2: Mark detached flags as not current (they'll be superseded on rescan).
UPDATE conflict_flags
SET is_current = FALSE
WHERE agenda_item_id IS NULL
  AND is_current = TRUE;

-- Step 3: Delete the header rows from agenda_items.
-- These are bare-letter items like "V" (CONSENT CALENDAR), "M" (HOUSING AUTHORITY),
-- "C" (CLOSED SESSION), "O" (OPEN SESSION), etc.
DELETE FROM agenda_items
WHERE item_number ~ '^[A-Z]+$'
  AND LENGTH(item_number) <= 4;

-- Step 4: Set was_pulled_from_consent for items that appear in action_items
-- but have is_consent_calendar = FALSE and item_number starts with consent
-- calendar prefixes (V., W.). These are items pulled for separate vote.
-- Note: This is a heuristic — the definitive source is items_pulled_for_separate_vote
-- from extraction JSON, which is now wired in db.py for future loads.
-- Existing data requires re-extraction to populate accurately, so this step
-- is intentionally omitted to avoid false positives.
