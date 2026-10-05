-- Reviewed local export allowlist. Each section is one SELECT in a single
-- REPEATABLE READ, READ ONLY transaction; never copy a whole source row.
-- The original full archive remains the recovery authority.

-- relation: bodies
SELECT id, city_fips, name, body_type, short_name, parent_body_id, is_elected,
       num_seats, meeting_schedule, is_active, created_at
FROM public.bodies WHERE city_fips = '0660620' ORDER BY id;

-- relation: officials
SELECT id, city_fips, name, normalized_name, role, seat, party_affiliation,
       term_start, term_end, is_current, created_at
FROM public.officials WHERE city_fips = '0660620' ORDER BY id;

-- relation: meetings
SELECT id, city_fips, document_id, body_id, meeting_date, meeting_type,
       call_to_order_time, adjournment_time, presiding_officer, minutes_url,
       agenda_url, video_url, adjourned_in_memory_of, next_meeting_date,
       source_cancelled_at, source_meeting_guid, created_at
FROM public.meetings
WHERE city_fips = '0660620' AND source_cancelled_at IS NULL ORDER BY id;

-- relation: agenda_items
SELECT ai.id, ai.meeting_id, ai.item_number, ai.title, ai.description,
       ai.department, ai.category, ai.is_consent_calendar,
       ai.was_pulled_from_consent, ai.resolution_number, ai.financial_amount,
       ai.continued_from, ai.continued_to, ai.topic_label, ai.proceeding_type,
       ai.agenda_source_authority, ai.agenda_source_revision_sha256,
       ai.agenda_source_retired_at, ai.created_at
FROM public.agenda_items ai JOIN public.meetings mt ON mt.id = ai.meeting_id
WHERE mt.city_fips = '0660620' AND mt.source_cancelled_at IS NULL
  AND ai.agenda_source_retired_at IS NULL ORDER BY ai.id;

-- relation: motions
SELECT mo.id, mo.agenda_item_id, mo.motion_type, mo.motion_text, mo.moved_by,
       mo.seconded_by, mo.result, mo.vote_tally, mo.resolution_number,
       mo.sequence_number, mo.source, mo.created_at
FROM public.motions mo
JOIN public.agenda_items ai ON ai.id = mo.agenda_item_id
JOIN public.meetings mt ON mt.id = ai.meeting_id
WHERE mt.city_fips = '0660620' AND mt.source_cancelled_at IS NULL
  AND ai.agenda_source_retired_at IS NULL
  AND NOT (ai.id = '9cf375c8-edc1-413c-8ee0-6485348fbc6f'::uuid
    AND ai.meeting_id = '5f560013-daea-499a-8ecd-ca1a089c8a0c'::uuid
    AND lower(ai.item_number) = 'j-2') ORDER BY mo.id;

-- relation: votes
SELECT vo.id, vo.motion_id, vo.official_id, vo.official_name,
       vo.official_role, vo.vote_choice, vo.source
FROM public.votes vo JOIN public.motions mo ON mo.id = vo.motion_id
JOIN public.agenda_items ai ON ai.id = mo.agenda_item_id
JOIN public.meetings mt ON mt.id = ai.meeting_id
WHERE mt.city_fips = '0660620' AND mt.source_cancelled_at IS NULL
  AND ai.agenda_source_retired_at IS NULL
  AND NOT (ai.id = '9cf375c8-edc1-413c-8ee0-6485348fbc6f'::uuid
    AND ai.meeting_id = '5f560013-daea-499a-8ecd-ca1a089c8a0c'::uuid
    AND lower(ai.item_number) = 'j-2') ORDER BY vo.id;

-- relation: meeting_attendance
SELECT ma.id, ma.meeting_id, ma.official_id, ma.body_id, ma.status, ma.notes
FROM public.meeting_attendance ma JOIN public.meetings mt ON mt.id = ma.meeting_id
WHERE mt.city_fips = '0660620' AND mt.source_cancelled_at IS NULL ORDER BY ma.id;

-- relation: topics
SELECT id, city_fips, slug, name, description, primary_category, status,
       merged_into_id, color_classes, keywords, created_at, updated_at
FROM public.topics WHERE city_fips = '0660620' ORDER BY id;

-- relation: item_topics
SELECT it.id, it.agenda_item_id, it.topic_id, it.confidence, it.source, it.created_at
FROM public.item_topics it
JOIN public.agenda_items ai ON ai.id = it.agenda_item_id
JOIN public.meetings mt ON mt.id = ai.meeting_id
JOIN public.topics tp ON tp.id = it.topic_id
WHERE mt.city_fips = '0660620' AND tp.city_fips = '0660620'
  AND mt.source_cancelled_at IS NULL AND ai.agenda_source_retired_at IS NULL ORDER BY it.id;

-- relation: closed_session_items
SELECT cs.id, cs.meeting_id, cs.item_number, cs.legal_authority,
       cs.description, cs.parties, cs.reportable_action
FROM public.closed_session_items cs JOIN public.meetings mt ON mt.id = cs.meeting_id
WHERE mt.city_fips = '0660620' AND mt.source_cancelled_at IS NULL ORDER BY cs.id;

-- relation: public_comments
-- Off by default. An explicit comments_from enables only recent minutes-sourced
-- public records; no email bodies, generated summaries or identity enrichment.
SELECT pc.id, pc.meeting_id, pc.agenda_item_id, pc.speaker_name, pc.method,
       pc.comment_type, pc.source, pc.confidence, pc.name_confidence,
       pc.extracted_at, pc.created_at, pc.city_fips
FROM public.public_comments pc JOIN public.meetings mt ON mt.id = pc.meeting_id
LEFT JOIN public.agenda_items ai ON ai.id = pc.agenda_item_id
WHERE %(comments_from)s::date IS NOT NULL AND mt.meeting_date >= %(comments_from)s::date
  AND mt.city_fips = '0660620' AND mt.source_cancelled_at IS NULL
  AND (pc.agenda_item_id IS NULL OR
       (ai.meeting_id = pc.meeting_id AND ai.agenda_source_retired_at IS NULL))
  AND pc.source = 'minutes' AND pc.confidence >= 0.90 ORDER BY pc.id;

-- relation: finance_public_events
SELECT event_key, scope_key, event_kind, donor_name, donor_fppc_id,
       recipient_name, recipient_fppc_id, reporting_filer_name,
       reporting_filer_fppc_id, amount, amount_kind, activity_date,
       support_oppose, candidate_name, measure_name, election_date,
       filing_ids, source_urls, source_url, extracted_at, source_tier,
       confidence_score, reconciliation_status
FROM public.finance_public_events
WHERE scope_key = '0660620:calendar-2026'
  AND activity_date >= DATE '2026-01-01' AND activity_date <= DATE '2026-11-03'
  AND confidence_score >= 0.90
  AND reconciliation_status IN ('source_reported', 'matched_exact') ORDER BY event_key;

-- relation: finance_public_coverage
SELECT source, form_type, scope_key, status, checked_at, activity_from,
       activity_through, filing_count, assertion_count, pending_count,
       limitations, source_url, extracted_at, source_tier, confidence_score
FROM public.finance_public_coverage WHERE scope_key = '0660620:calendar-2026'
ORDER BY source, form_type, scope_key;
