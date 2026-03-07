-- Migration 017: Widen varchar columns for LLM extraction output
--
-- Historical meeting minutes (2005-2023) produce longer values than
-- the original schema anticipated. Closed session "item_number" fields
-- contain full descriptions, resolution numbers can span dual resolutions,
-- and vote choices occasionally include qualifiers.
--
-- Must drop/recreate views that depend on the altered columns.

BEGIN;

-- ── Drop dependent views ──
DROP VIEW IF EXISTS v_votes_with_context;
DROP VIEW IF EXISTS v_donor_vote_crossref;
DROP VIEW IF EXISTS v_split_votes;

-- ── Widen columns ──

-- agenda_items.item_number: "Motion to Extend Meeting", "Emergency Budget Session"
ALTER TABLE agenda_items ALTER COLUMN item_number TYPE varchar(100);

-- closed_session_items.item_number: "CONFERENCE WITH LEGAL COUNSEL - EXISTING LITIGATION"
ALTER TABLE closed_session_items ALTER COLUMN item_number TYPE varchar(200);

-- votes.vote_choice: "aye on most, nay on Martinez", "nay (Andres Soto appointment only)"
ALTER TABLE votes ALTER COLUMN vote_choice TYPE varchar(100);

-- agenda_items.resolution_number: "Housing Authority Resolution No. 2143 and City Council Resolution No. 74-21"
ALTER TABLE agenda_items ALTER COLUMN resolution_number TYPE varchar(200);

-- motions.resolution_number: same pattern as above
ALTER TABLE motions ALTER COLUMN resolution_number TYPE varchar(200);

-- ── Recreate views ──

CREATE VIEW v_votes_with_context AS
SELECT m.city_fips,
    m.meeting_date,
    m.meeting_type,
    ai.item_number,
    ai.title AS item_title,
    ai.category,
    ai.is_consent_calendar,
    ai.financial_amount,
    mt.motion_type,
    mt.motion_text,
    mt.result AS motion_result,
    mt.vote_tally,
    v.official_name,
    v.official_role,
    v.vote_choice,
    o.id AS official_id
FROM votes v
    JOIN motions mt ON v.motion_id = mt.id
    JOIN agenda_items ai ON mt.agenda_item_id = ai.id
    JOIN meetings m ON ai.meeting_id = m.id
    LEFT JOIN officials o ON v.official_id = o.id;

CREATE VIEW v_donor_vote_crossref AS
SELECT co.city_fips,
    d.name AS donor_name,
    d.employer AS donor_employer,
    co.amount,
    co.contribution_date,
    cm.name AS committee_name,
    cm.candidate_name,
    o.name AS official_name,
    m.meeting_date,
    ai.item_number,
    ai.title AS item_title,
    ai.financial_amount,
    v.vote_choice
FROM contributions co
    JOIN donors d ON co.donor_id = d.id
    JOIN committees cm ON co.committee_id = cm.id
    LEFT JOIN officials o ON cm.official_id = o.id
    LEFT JOIN votes v ON v.official_id = o.id
    LEFT JOIN motions mt ON v.motion_id = mt.id
    LEFT JOIN agenda_items ai ON mt.agenda_item_id = ai.id
    LEFT JOIN meetings m ON ai.meeting_id = m.id;

CREATE VIEW v_split_votes AS
SELECT m.city_fips,
    m.meeting_date,
    ai.item_number,
    ai.title AS item_title,
    ai.category,
    mt.motion_type,
    mt.result,
    mt.vote_tally,
    mt.id AS motion_id
FROM motions mt
    JOIN agenda_items ai ON mt.agenda_item_id = ai.id
    JOIN meetings m ON ai.meeting_id = m.id
WHERE mt.vote_tally NOT LIKE '7-0'
    AND mt.vote_tally NOT LIKE '%-0'
    AND mt.result IS NOT NULL;

COMMIT;
