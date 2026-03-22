-- Migration 028: Meeting data quality cleanup
-- Fixes several data quality issues found during March 2026 audit:
--   1. <UNKNOWN> sentinel strings stored instead of NULL
--   2. Closed session item_number concatenated into title (empty item_number)
--   3. Duplicate "special" meeting on April 15, 2025 (identical to "joint")
--   4. Duplicate agenda items on Dec 2, 2025 (cross-meeting duplicates)
--   5. Trailing commas in financial_amount values
--   6. Incorrect financial_amount "$8" for Homekey project (should be $10,300,000)
--
-- All operations are idempotent.

-- ═══════════════════════════════════════════════════════════════════
-- 1. Fix <UNKNOWN> sentinel strings → NULL
-- ═══════════════════════════════════════════════════════════════════

UPDATE meetings
SET presiding_officer = NULL
WHERE presiding_officer IN ('<UNKNOWN>', '<unknown>', 'N/A', 'Unknown', '');

UPDATE meetings
SET call_to_order_time = NULL
WHERE call_to_order_time IN ('<UNKNOWN>', '<unknown>', 'N/A', 'Unknown', '');

-- ═══════════════════════════════════════════════════════════════════
-- 2. Fix closed session items: extract item_number from title
--    Pattern: empty item_number + title starts with "C.1", "C.2", etc.
-- ═══════════════════════════════════════════════════════════════════

UPDATE agenda_items
SET item_number = (regexp_match(title, '^([A-Z]\.\d+(?:\.[a-z])?)'))[1],
    title = regexp_replace(title, '^[A-Z]\.\d+(?:\.[a-z])?\s*', '')
WHERE item_number = ''
  AND title ~ '^[A-Z]\.\d+';

-- ═══════════════════════════════════════════════════════════════════
-- 3. Delete duplicate April 15, 2025 "special" meeting
--    The "joint" meeting (9bb766ed) has the document_id and is correct.
--    The "special" meeting (a751e614) has no document_id and identical items.
-- ═══════════════════════════════════════════════════════════════════

-- First delete child records, then the meeting
DELETE FROM votes
WHERE motion_id IN (
  SELECT mo.id FROM motions mo
  JOIN agenda_items ai ON mo.agenda_item_id = ai.id
  WHERE ai.meeting_id = 'a751e614-08cc-4cd5-965f-63eaf85f165f'
);

DELETE FROM motions
WHERE agenda_item_id IN (
  SELECT id FROM agenda_items
  WHERE meeting_id = 'a751e614-08cc-4cd5-965f-63eaf85f165f'
);

DELETE FROM conflict_flags
WHERE meeting_id = 'a751e614-08cc-4cd5-965f-63eaf85f165f';

DELETE FROM closed_session_items
WHERE meeting_id = 'a751e614-08cc-4cd5-965f-63eaf85f165f';

DELETE FROM public_comments
WHERE meeting_id = 'a751e614-08cc-4cd5-965f-63eaf85f165f';

DELETE FROM scan_runs
WHERE meeting_id = 'a751e614-08cc-4cd5-965f-63eaf85f165f';

UPDATE commission_members
SET source_meeting_id = NULL
WHERE source_meeting_id = 'a751e614-08cc-4cd5-965f-63eaf85f165f';

DELETE FROM agenda_items
WHERE meeting_id = 'a751e614-08cc-4cd5-965f-63eaf85f165f';

DELETE FROM meeting_attendance
WHERE meeting_id = 'a751e614-08cc-4cd5-965f-63eaf85f165f';

DELETE FROM meetings
WHERE id = 'a751e614-08cc-4cd5-965f-63eaf85f165f';

-- ═══════════════════════════════════════════════════════════════════
-- 4. Delete duplicate agenda items on Dec 2, 2025
--    The "regular" meeting (276f7d20) has items duplicated from the
--    "joint" meeting (832f13ff). Keep items on the meeting that has
--    the correct context (joint items stay on joint, regular on regular).
--    Strategy: for each duplicated item_number, keep the one on the
--    meeting that has motions/votes (the minutes-sourced meeting).
-- ═══════════════════════════════════════════════════════════════════

-- The joint meeting (832f13ff) was sourced from minutes and has motions.
-- The regular meeting (276f7d20) also has some items from eSCRIBE.
-- For duplicated item_numbers, delete the copy WITHOUT motions.
-- If both have motions, keep the one on the regular meeting.

-- First delete all child records referencing the duplicate agenda items
-- (conflict_flags, public_comments — motions are used to decide WHICH items to keep)
DELETE FROM public_comments
WHERE agenda_item_id IN (
  SELECT ai.id
  FROM agenda_items ai
  JOIN meetings m ON m.id = ai.meeting_id
  WHERE m.meeting_date = '2025-12-02'
    AND m.city_fips = '0660620'
    AND ai.item_number IN (
      SELECT ai2.item_number
      FROM agenda_items ai2
      JOIN meetings m2 ON m2.id = ai2.meeting_id
      WHERE m2.meeting_date = '2025-12-02'
        AND m2.city_fips = '0660620'
      GROUP BY ai2.item_number
      HAVING COUNT(DISTINCT m2.id) > 1
    )
    AND NOT EXISTS (
      SELECT 1 FROM motions mo WHERE mo.agenda_item_id = ai.id
    )
);

DELETE FROM conflict_flags
WHERE agenda_item_id IN (
  SELECT ai.id
  FROM agenda_items ai
  JOIN meetings m ON m.id = ai.meeting_id
  WHERE m.meeting_date = '2025-12-02'
    AND m.city_fips = '0660620'
    AND ai.item_number IN (
      SELECT ai2.item_number
      FROM agenda_items ai2
      JOIN meetings m2 ON m2.id = ai2.meeting_id
      WHERE m2.meeting_date = '2025-12-02'
        AND m2.city_fips = '0660620'
      GROUP BY ai2.item_number
      HAVING COUNT(DISTINCT m2.id) > 1
    )
    AND NOT EXISTS (
      SELECT 1 FROM motions mo WHERE mo.agenda_item_id = ai.id
    )
);

-- Then delete the duplicate agenda items themselves
DELETE FROM agenda_items
WHERE id IN (
  -- Find agenda items that are duplicates (same item_number on Dec 2, 2025)
  -- and belong to the meeting that does NOT have motions for that item
  SELECT ai.id
  FROM agenda_items ai
  JOIN meetings m ON m.id = ai.meeting_id
  WHERE m.meeting_date = '2025-12-02'
    AND m.city_fips = '0660620'
    AND ai.item_number IN (
      -- Item numbers that appear on both meetings
      SELECT ai2.item_number
      FROM agenda_items ai2
      JOIN meetings m2 ON m2.id = ai2.meeting_id
      WHERE m2.meeting_date = '2025-12-02'
        AND m2.city_fips = '0660620'
      GROUP BY ai2.item_number
      HAVING COUNT(DISTINCT m2.id) > 1
    )
    -- Keep items on the meeting that has motions for them
    AND NOT EXISTS (
      SELECT 1 FROM motions mo WHERE mo.agenda_item_id = ai.id
    )
);

-- ═══════════════════════════════════════════════════════════════════
-- 5. Fix trailing commas in financial_amount
-- ═══════════════════════════════════════════════════════════════════

UPDATE agenda_items
SET financial_amount = rtrim(financial_amount, ',')
WHERE financial_amount LIKE '%,';

-- ═══════════════════════════════════════════════════════════════════
-- 6. Fix specific known bad financial_amount values
--    "$8" for Homekey project should be "$10,300,000" (from description:
--    "increasing the City loan amount from $8.3 million to up to $10.3 million")
-- ═══════════════════════════════════════════════════════════════════

UPDATE agenda_items
SET financial_amount = '$10,300,000'
WHERE financial_amount = '$8'
  AND title LIKE '%Civic Center Apartments%Homekey%';
