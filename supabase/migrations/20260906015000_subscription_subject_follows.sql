-- Migration 150: Explicit council-mail consent and four reviewed subject follows.
-- Existing subscribers retain council updates. Public email-only signup may
-- initialize/reactivate preferences, but cannot modify an active subscription.
ALTER TABLE public.email_subscribers
    ADD COLUMN IF NOT EXISTS receive_council_updates boolean NOT NULL DEFAULT true;

ALTER TABLE public.email_preferences DROP CONSTRAINT IF EXISTS email_preferences_preference_type_check;
ALTER TABLE public.email_preferences ADD CONSTRAINT email_preferences_preference_type_check
    CHECK (preference_type IN ('topic', 'district', 'candidate', 'subject'));
ALTER TABLE public.email_preferences DROP CONSTRAINT IF EXISTS email_preferences_subject_check;
ALTER TABLE public.email_preferences ADD CONSTRAINT email_preferences_subject_check CHECK (
    preference_type <> 'subject' OR preference_value IN (
      'chevron-settlement-and-city-budget', 'fire-stations-and-emergency-response',
      'flock-cameras-and-data-privacy', '2026-general'
    )
);

-- Keep four-argument clients compatible: they replace only the categories
-- they understand and cannot erase subject choices or change council consent.
CREATE OR REPLACE FUNCTION public.replace_email_preferences(
    p_subscriber_id uuid, p_topics text[] DEFAULT ARRAY[]::text[],
    p_districts text[] DEFAULT ARRAY[]::text[], p_candidates text[] DEFAULT ARRAY[]::text[]
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM 1 FROM public.email_subscribers
        WHERE id = p_subscriber_id AND status = 'active' AND city_fips = '0660620' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Subscription is not active' USING ERRCODE = '42501'; END IF;
    DELETE FROM public.email_preferences WHERE subscriber_id = p_subscriber_id
        AND preference_type IN ('topic', 'district', 'candidate');
    INSERT INTO public.email_preferences(subscriber_id,preference_type,preference_value,city_fips)
    SELECT p_subscriber_id, category, value, '0660620' FROM (
      SELECT 'topic' AS category, unnest(p_topics) AS value UNION ALL
      SELECT 'district', unnest(p_districts) UNION ALL SELECT 'candidate', unnest(p_candidates)
    ) preferences WHERE value <> '' ON CONFLICT DO NOTHING;
END;
$$;

-- NULL new fields mean an older API client omitted them; [] explicitly clears.
-- Recheck the bearer token under the subscriber lock, including token rotation.
CREATE OR REPLACE FUNCTION public.replace_email_preferences_v2(
    p_subscriber_id uuid, p_manage_token uuid, p_topics text[], p_districts text[],
    p_candidates text[], p_subjects text[], p_receive_council_updates boolean
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    PERFORM 1 FROM public.email_subscribers WHERE id = p_subscriber_id
      AND unsubscribe_token = p_manage_token AND status = 'active' AND city_fips = '0660620' FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Invalid or inactive management link' USING ERRCODE = '42501'; END IF;
    PERFORM public.replace_email_preferences(p_subscriber_id, p_topics, p_districts, p_candidates);
    IF p_subjects IS NOT NULL THEN
        DELETE FROM public.email_preferences WHERE subscriber_id = p_subscriber_id AND preference_type = 'subject';
        INSERT INTO public.email_preferences(subscriber_id,preference_type,preference_value,city_fips)
        SELECT p_subscriber_id, 'subject', value, '0660620' FROM unnest(p_subjects) value
        ON CONFLICT DO NOTHING;
    END IF;
    IF p_receive_council_updates IS NOT NULL THEN
        UPDATE public.email_subscribers SET receive_council_updates = p_receive_council_updates WHERE id = p_subscriber_id;
    END IF;
END;
$$;

-- The v141 trigger records the activation and pending welcome inside this
-- transaction. Any subject failure rolls back subscription, token rotation,
-- activation history, preferences and welcome together. No email is sent here.
CREATE OR REPLACE FUNCTION public.activate_email_subscription_v2(
    p_email text, p_name text, p_surface text, p_subject text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    subscriber public.email_subscribers%ROWTYPE;
    activation_id uuid := gen_random_uuid();
    activation_at timestamptz := clock_timestamp();
    normalized_email text := lower(trim(p_email));
BEGIN
    IF normalized_email IS NULL OR length(normalized_email) > 255
       OR normalized_email !~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'
       OR length(p_name) > 200 OR p_surface IS NULL OR p_surface NOT IN (
         'homepage','nav','footer','meeting','subscribe_page','november_election'
       ) OR (p_subject IS NOT NULL AND p_subject NOT IN (
         'chevron-settlement-and-city-budget','fire-stations-and-emergency-response',
         'flock-cameras-and-data-privacy','2026-general'
       )) THEN RAISE EXCEPTION 'Invalid subscription request' USING ERRCODE = '22023'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(normalized_email, 150));
    SELECT * INTO subscriber FROM public.email_subscribers WHERE email = normalized_email FOR UPDATE;
    IF FOUND AND (subscriber.status = 'active' OR subscriber.city_fips <> '0660620') THEN
        RETURN jsonb_build_object('activated', false);
    END IF;
    IF subscriber.id IS NULL THEN
        INSERT INTO public.email_subscribers(email,name,city_fips,source,subscribed_at,
          current_activation_id,current_activation_at,current_activation_surface,receive_council_updates)
        VALUES(normalized_email,NULLIF(trim(p_name),''),'0660620','website',activation_at,
          activation_id,activation_at,p_surface,p_subject IS NULL)
        ON CONFLICT(email) DO NOTHING RETURNING * INTO subscriber;
        -- A pre-v150 writer may win a concurrent signup. It cannot be amended
        -- using just the public email address.
        IF subscriber.id IS NULL THEN RETURN jsonb_build_object('activated', false); END IF;
    ELSE
        UPDATE public.email_subscribers SET status = 'active', name = COALESCE(NULLIF(trim(p_name),''),name),
          subscribed_at = activation_at, unsubscribed_at = NULL, unsubscribe_token = gen_random_uuid(),
          current_activation_id = activation_id, current_activation_at = activation_at,
          current_activation_surface = p_surface, last_orientation_meeting_id = NULL,
          receive_council_updates = p_subject IS NULL
        WHERE id = subscriber.id AND status = 'unsubscribed' RETURNING * INTO subscriber;
        IF subscriber.id IS NULL THEN RETURN jsonb_build_object('activated', false); END IF;
    END IF;
    IF p_subject IS NOT NULL THEN
        -- A follow-only reactivation is a fresh, explicit selection.
        DELETE FROM public.email_preferences WHERE subscriber_id = subscriber.id;
        INSERT INTO public.email_preferences(subscriber_id,preference_type,preference_value,city_fips)
        VALUES(subscriber.id,'subject',p_subject,'0660620');
    END IF;
    RETURN jsonb_build_object('activated',true,'subscriber_id',subscriber.id,'subscriber_name',subscriber.name,
      'unsubscribe_token',subscriber.unsubscribe_token,'activation_id',activation_id,
      'receive_council_updates',subscriber.receive_council_updates);
END;
$$;

REVOKE ALL ON FUNCTION public.replace_email_preferences(uuid,text[],text[],text[]) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.replace_email_preferences_v2(uuid,uuid,text[],text[],text[],text[],boolean) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.activate_email_subscription_v2(text,text,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.replace_email_preferences(uuid,text[],text[],text[]) TO service_role;
GRANT EXECUTE ON FUNCTION public.replace_email_preferences_v2(uuid,uuid,text[],text[],text[],text[],boolean) TO service_role;
GRANT EXECUTE ON FUNCTION public.activate_email_subscription_v2(text,text,text,text) TO service_role;

-- Preserve old RPC signatures across a frontend rollback while enforcing new
-- consent. Only the guarded wrappers may invoke the unchanged v141 mechanics.
DO $$ BEGIN
    IF to_regprocedure('public.claim_email_delivery_v141(uuid,character varying,character varying,character varying,integer,integer)') IS NULL THEN
        ALTER FUNCTION public.claim_email_delivery(uuid,varchar,varchar,varchar,integer,integer) RENAME TO claim_email_delivery_v141;
    END IF;
END $$;
CREATE OR REPLACE FUNCTION public.claim_email_delivery(
    p_subscriber_id uuid, p_delivery_kind varchar, p_content_key varchar, p_payload_sha256 varchar,
    p_lease_minutes integer DEFAULT 15, p_max_attempts integer DEFAULT 3
) RETURNS TABLE(delivery_id uuid, delivery_claim_token uuid, delivery_attempt integer, delivery_disposition varchar)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE council_consent boolean;
BEGIN
    SELECT receive_council_updates INTO council_consent FROM public.email_subscribers
      WHERE id = p_subscriber_id AND status = 'active' AND city_fips = '0660620' FOR SHARE;
    IF NOT FOUND OR (p_delivery_kind IN ('orientation','recap','digest') AND NOT council_consent) THEN
        RAISE EXCEPTION 'Subscription does not authorize this council email' USING ERRCODE = '42501';
    END IF;
    RETURN QUERY SELECT * FROM public.claim_email_delivery_v141(p_subscriber_id,p_delivery_kind,
      p_content_key,p_payload_sha256,p_lease_minutes,p_max_attempts);
END;
$$;
REVOKE ALL ON FUNCTION public.claim_email_delivery_v141(uuid,varchar,varchar,varchar,integer,integer) FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.claim_email_delivery(uuid,varchar,varchar,varchar,integer,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_email_delivery(uuid,varchar,varchar,varchar,integer,integer) TO service_role;

-- Recheck consent and exact approved versions in the same transaction as the
-- existing durable claim. Its immutable payload hash and provider key still
-- govern retries; this does not create a second sender or retry ledger.
CREATE OR REPLACE FUNCTION public.claim_consented_email_delivery(
    p_subscriber_id uuid, p_delivery_kind varchar, p_content_key varchar,
    p_payload_sha256 varchar, p_brief_versions jsonb DEFAULT '[]'::jsonb,
    p_contains_council_content boolean DEFAULT true,
    p_lease_minutes integer DEFAULT 15, p_max_attempts integer DEFAULT 3
) RETURNS TABLE(delivery_id uuid, delivery_claim_token uuid, delivery_attempt integer, delivery_disposition varchar)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE council_consent boolean; brief_ref jsonb;
BEGIN
    SELECT receive_council_updates INTO council_consent FROM public.email_subscribers
      WHERE id = p_subscriber_id AND status = 'active' AND city_fips = '0660620' FOR SHARE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Subscription is not active' USING ERRCODE = '42501'; END IF;
    IF p_brief_versions IS NULL OR jsonb_typeof(p_brief_versions) <> 'array'
      OR jsonb_array_length(p_brief_versions) > 40
      OR (p_delivery_kind <> 'digest' AND p_brief_versions <> '[]'::jsonb) THEN
        RAISE EXCEPTION 'Invalid brief version references' USING ERRCODE = '22023';
    END IF;
    IF (p_delivery_kind IN ('orientation','recap') AND NOT council_consent)
      OR (p_delivery_kind = 'digest' AND NOT council_consent
        AND (COALESCE(p_contains_council_content,true) OR jsonb_array_length(p_brief_versions) = 0)) THEN
        RAISE EXCEPTION 'Council email consent is off' USING ERRCODE = '42501';
    END IF;
    FOR brief_ref IN SELECT value FROM jsonb_array_elements(p_brief_versions) LOOP
        PERFORM 1 FROM public.civic_brief_candidates b WHERE b.id = (brief_ref->>'id')::uuid
          AND b.content_version = (brief_ref->>'content_version')::bigint AND b.status = 'published'
          AND b.published_at = (brief_ref->>'published_at')::timestamptz
          AND EXISTS (SELECT 1 FROM public.email_preferences p WHERE p.subscriber_id = p_subscriber_id
            AND p.preference_type = 'subject' AND p.preference_value = b.subject_key)
          FOR SHARE OF b;
        IF NOT FOUND THEN RAISE EXCEPTION 'Brief version is withdrawn, changed, or no longer followed' USING ERRCODE = '42501'; END IF;
    END LOOP;
    RETURN QUERY SELECT * FROM public.claim_email_delivery_v141(p_subscriber_id,p_delivery_kind,
      p_content_key,p_payload_sha256,p_lease_minutes,p_max_attempts);
END;
$$;
REVOKE ALL ON FUNCTION public.claim_consented_email_delivery(uuid,varchar,varchar,varchar,jsonb,boolean,integer,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_consented_email_delivery(uuid,varchar,varchar,varchar,jsonb,boolean,integer,integer) TO service_role;
