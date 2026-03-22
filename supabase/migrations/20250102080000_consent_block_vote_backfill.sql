-- Migration 033: Consent Block Vote Backfill
-- I21: The consent calendar block vote was previously only attached to the
-- first consent sub-item. This migration copies it to all non-pulled consent
-- items that don't already have a motion.
--
-- Logic: For each meeting, find the motion on a consent item (the one that
-- already has it), then create identical motions+votes for all other consent
-- items in that meeting that lack a motion.
--
-- Idempotent: safe to re-run (uses NOT EXISTS checks).

-- Step 1: Create motions for consent items that don't have one.
-- We find the "template" motion from the first consent item in each meeting,
-- then replicate it to sibling consent items.
INSERT INTO motions (id, agenda_item_id, motion_type, motion_text,
                     moved_by, seconded_by, result, vote_tally, sequence_number)
SELECT
    gen_random_uuid(),
    ai_missing.id,
    m_template.motion_type,
    m_template.motion_text,
    m_template.moved_by,
    m_template.seconded_by,
    m_template.result,
    m_template.vote_tally,
    m_template.sequence_number
FROM agenda_items ai_missing
-- Find the "template" consent item in the same meeting that already has a motion
JOIN agenda_items ai_has ON ai_has.meeting_id = ai_missing.meeting_id
    AND ai_has.is_consent_calendar = TRUE
    AND ai_has.was_pulled_from_consent = FALSE
JOIN motions m_template ON m_template.agenda_item_id = ai_has.id
    AND m_template.motion_text = 'Approve consent calendar'
WHERE ai_missing.is_consent_calendar = TRUE
  AND ai_missing.was_pulled_from_consent = FALSE
  -- Only items that don't already have a consent motion
  AND NOT EXISTS (
      SELECT 1 FROM motions m_existing
      WHERE m_existing.agenda_item_id = ai_missing.id
        AND m_existing.motion_text = 'Approve consent calendar'
  )
  -- Avoid self-join creating duplicates: only copy FROM the item that
  -- already has the motion (the one with the lowest item_number)
  AND ai_has.id = (
      SELECT ai_first.id
      FROM agenda_items ai_first
      JOIN motions m_first ON m_first.agenda_item_id = ai_first.id
          AND m_first.motion_text = 'Approve consent calendar'
      WHERE ai_first.meeting_id = ai_missing.meeting_id
        AND ai_first.is_consent_calendar = TRUE
      ORDER BY ai_first.item_number
      LIMIT 1
  );

-- Step 2: Copy votes from template motions to the new motions.
-- For each newly created motion, copy all votes from the template motion.
INSERT INTO votes (id, motion_id, official_id, official_name, official_role, vote_choice)
SELECT
    gen_random_uuid(),
    m_new.id,
    v_template.official_id,
    v_template.official_name,
    v_template.official_role,
    v_template.vote_choice
FROM motions m_new
JOIN agenda_items ai_new ON ai_new.id = m_new.agenda_item_id
    AND ai_new.is_consent_calendar = TRUE
-- Find the template motion in the same meeting
JOIN agenda_items ai_template ON ai_template.meeting_id = ai_new.meeting_id
    AND ai_template.is_consent_calendar = TRUE
    AND ai_template.id != ai_new.id
JOIN motions m_template ON m_template.agenda_item_id = ai_template.id
    AND m_template.motion_text = 'Approve consent calendar'
JOIN votes v_template ON v_template.motion_id = m_template.id
WHERE m_new.motion_text = 'Approve consent calendar'
  -- Only copy to motions that don't already have votes
  AND NOT EXISTS (
      SELECT 1 FROM votes v_existing
      WHERE v_existing.motion_id = m_new.id
  )
  -- Same disambiguation: use the first consent item with a motion as template
  AND ai_template.id = (
      SELECT ai_first.id
      FROM agenda_items ai_first
      JOIN motions m_first ON m_first.agenda_item_id = ai_first.id
          AND m_first.motion_text = 'Approve consent calendar'
      WHERE ai_first.meeting_id = ai_new.meeting_id
        AND ai_first.is_consent_calendar = TRUE
      ORDER BY ai_first.item_number
      LIMIT 1
  );
