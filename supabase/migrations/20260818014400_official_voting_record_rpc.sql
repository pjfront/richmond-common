-- Migration 144: replace the nested PostgREST council-vote read with one flat
-- bounded SQL plan.
--
-- The old frontend select nested votes -> motions -> agenda items -> meetings
-- and then nested every vote on every motion again to detect split votes. Under
-- the public role that plan can exceed the statement timeout. This RPC returns
-- the exact display fields as flat rows and uses an indexed EXISTS probe for
-- split-vote status.
--
-- SECURITY DEFINER avoids repeated nested RLS policy evaluation. The body is
-- therefore schema-qualified, pins search_path, and reproduces migration 133's
-- active meeting/item boundary explicitly. It performs no writes or backfill.

CREATE OR REPLACE FUNCTION public.get_official_voting_record(
  p_official_id UUID
)
RETURNS TABLE (
  id UUID,
  vote_choice TEXT,
  official_name TEXT,
  motion_id UUID,
  motion_text TEXT,
  motion_result TEXT,
  vote_tally TEXT,
  meeting_id UUID,
  meeting_date DATE,
  meeting_type TEXT,
  agenda_item_id UUID,
  item_number TEXT,
  item_title TEXT,
  category TEXT,
  topic_label TEXT,
  public_comment_count INTEGER,
  is_consent_calendar BOOLEAN,
  has_nay_votes BOOLEAN
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $function$
  SELECT
    member_vote.id,
    member_vote.vote_choice::TEXT,
    member_vote.official_name::TEXT,
    mo.id AS motion_id,
    mo.motion_text,
    mo.result::TEXT AS motion_result,
    mo.vote_tally,
    mt.id AS meeting_id,
    mt.meeting_date,
    mt.meeting_type::TEXT,
    ai.id AS agenda_item_id,
    ai.item_number::TEXT,
    ai.title AS item_title,
    ai.category::TEXT,
    ai.topic_label::TEXT,
    coalesce(ai.public_comment_count, 0)::INTEGER,
    ai.is_consent_calendar,
    EXISTS (
      SELECT 1
      FROM public.votes motion_vote
      WHERE motion_vote.motion_id = mo.id
        AND lower(motion_vote.vote_choice) = 'nay'
    ) AS has_nay_votes
  FROM public.votes member_vote
  JOIN public.motions mo ON mo.id = member_vote.motion_id
  JOIN public.agenda_items ai ON ai.id = mo.agenda_item_id
  JOIN public.meetings mt ON mt.id = ai.meeting_id
  WHERE member_vote.official_id = p_official_id
    AND mt.city_fips = '0660620'
    AND mt.source_cancelled_at IS NULL
    AND ai.agenda_source_retired_at IS NULL
  ORDER BY
    mt.meeting_date DESC,
    ai.item_number,
    mo.sequence_number,
    member_vote.id;
$function$;

REVOKE ALL PRIVILEGES ON FUNCTION public.get_official_voting_record(UUID)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.get_official_voting_record(UUID)
  TO anon, authenticated, service_role;

COMMENT ON FUNCTION public.get_official_voting_record(UUID) IS
  'Flat, read-only Richmond council voting record for public profile pages; excludes cancelled meetings and retired agenda items.';
