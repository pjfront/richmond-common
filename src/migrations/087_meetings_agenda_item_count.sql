-- Migration 087: Add agenda_item_count column to meetings table
--
-- The agenda item count was previously computed dynamically via the
-- get_meeting_counts RPC on every page load. This was fragile — RPC
-- failures, ISR cache, and pipeline timing all caused "0 agenda items"
-- to display. The count doesn't change once items are loaded, so store
-- it directly on the row and maintain it via trigger.

-- 1. Add the column (nullable during backfill, then default 0)
ALTER TABLE meetings ADD COLUMN IF NOT EXISTS agenda_item_count INT;

-- 2. Backfill from current data
UPDATE meetings m
SET agenda_item_count = (
    SELECT COUNT(*)::INT FROM agenda_items ai WHERE ai.meeting_id = m.id
)
WHERE agenda_item_count IS NULL;

-- 3. Set default for future rows
ALTER TABLE meetings ALTER COLUMN agenda_item_count SET DEFAULT 0;
ALTER TABLE meetings ALTER COLUMN agenda_item_count SET NOT NULL;

-- 4. Trigger function to keep count in sync on INSERT/DELETE to agenda_items
CREATE OR REPLACE FUNCTION update_meeting_agenda_item_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE meetings SET agenda_item_count = agenda_item_count + 1
        WHERE id = NEW.meeting_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE meetings SET agenda_item_count = agenda_item_count - 1
        WHERE id = OLD.meeting_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Drop if exists for idempotency
DROP TRIGGER IF EXISTS trg_agenda_item_count ON agenda_items;
CREATE TRIGGER trg_agenda_item_count
    AFTER INSERT OR DELETE ON agenda_items
    FOR EACH ROW
    EXECUTE FUNCTION update_meeting_agenda_item_count();
