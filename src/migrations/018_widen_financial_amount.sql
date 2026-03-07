-- Migration 018: Widen financial_amount for LLM extraction output
--
-- Historical meeting minutes contain verbose financial descriptions like
-- "$65,000 for the first year start-up (includes a 10 percent contingency)..."
-- that exceed varchar(100). Must drop/recreate views that reference the column.

BEGIN;

DROP VIEW IF EXISTS v_votes_with_context;
DROP VIEW IF EXISTS v_donor_vote_crossref;

ALTER TABLE agenda_items ALTER COLUMN financial_amount TYPE varchar(500);

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

COMMIT;
