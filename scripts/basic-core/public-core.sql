-- Candidate bootstrap for a NEW EMPTY PostgreSQL database. Not a live migration.
-- No extensions, vectors, auth/operator/log tables, provider services or paid API.
-- Existing read-only PostgREST relation names and FK embeds are preserved.
BEGIN;

CREATE TABLE public.bodies (
  id uuid PRIMARY KEY, city_fips text NOT NULL CHECK (city_fips = '0660620'),
  name text NOT NULL, body_type text NOT NULL, short_name text,
  parent_body_id uuid REFERENCES public.bodies DEFERRABLE INITIALLY DEFERRED,
  is_elected boolean NOT NULL, num_seats smallint, meeting_schedule text,
  is_active boolean NOT NULL, created_at timestamptz NOT NULL
);
CREATE TABLE public.officials (
  id uuid PRIMARY KEY, city_fips text NOT NULL CHECK (city_fips = '0660620'),
  name text NOT NULL, normalized_name text NOT NULL, role text NOT NULL, seat text,
  party_affiliation text, term_start date, term_end date,
  is_current boolean NOT NULL, created_at timestamptz NOT NULL
);
CREATE TABLE public.meetings (
  id uuid PRIMARY KEY, city_fips text NOT NULL CHECK (city_fips = '0660620'),
  document_id uuid, -- source identity only; the raw document lake is not copied
  body_id uuid NOT NULL REFERENCES public.bodies,
  meeting_date date NOT NULL, meeting_type text NOT NULL,
  call_to_order_time text, adjournment_time text, presiding_officer text,
  minutes_url text, agenda_url text, video_url text, adjourned_in_memory_of text,
  next_meeting_date text, source_cancelled_at timestamptz,
  source_meeting_guid text, created_at timestamptz NOT NULL,
  -- Nullable compatibility extras; no generated content or email metadata imported.
  meeting_summary text CHECK (meeting_summary IS NULL),
  meeting_recap text CHECK (meeting_recap IS NULL),
  orientation_preview text CHECK (orientation_preview IS NULL),
  transcript_recap text CHECK (transcript_recap IS NULL),
  meeting_summary_provenance jsonb CHECK (meeting_summary_provenance IS NULL),
  meeting_recap_provenance jsonb CHECK (meeting_recap_provenance IS NULL),
  orientation_preview_provenance jsonb CHECK (orientation_preview_provenance IS NULL),
  transcript_recap_provenance jsonb CHECK (transcript_recap_provenance IS NULL),
  metadata jsonb NOT NULL DEFAULT '{}' CHECK (metadata = '{}'::jsonb),
  agenda_item_count integer NOT NULL DEFAULT 0 CHECK (agenda_item_count >= 0)
);
CREATE TABLE public.agenda_items (
  id uuid PRIMARY KEY, meeting_id uuid NOT NULL REFERENCES public.meetings,
  item_number text NOT NULL, title text NOT NULL, description text, department text,
  category text, is_consent_calendar boolean NOT NULL,
  was_pulled_from_consent boolean NOT NULL, resolution_number text, financial_amount text,
  continued_from text, continued_to text, topic_label text, proceeding_type text,
  agenda_source_authority text NOT NULL, agenda_source_revision_sha256 text,
  agenda_source_retired_at timestamptz,
  created_at timestamptz NOT NULL,
  -- Empty extras satisfy basic meeting/item readers without copying generated claims.
  summary_headline text CHECK (summary_headline IS NULL),
  plain_language_summary text CHECK (plain_language_summary IS NULL),
  plain_language_generated_at timestamptz CHECK (plain_language_generated_at IS NULL),
  plain_language_model text CHECK (plain_language_model IS NULL),
  plain_language_summary_provenance jsonb CHECK (plain_language_summary_provenance IS NULL),
  ai_comment_summary text CHECK (ai_comment_summary IS NULL),
  public_comment_count integer CHECK (public_comment_count IS NULL),
  discussion_duration_minutes integer CHECK (discussion_duration_minutes IS NULL),
  legal_framework text CHECK (legal_framework IS NULL),
  legal_framework_source text CHECK (legal_framework_source IS NULL),
  legal_framework_classified_at timestamptz CHECK (legal_framework_classified_at IS NULL),
  party_entities jsonb CHECK (party_entities IS NULL),
  CHECK (id <> '9cf375c8-edc1-413c-8ee0-6485348fbc6f'::uuid OR
    (meeting_id = '5f560013-daea-499a-8ecd-ca1a089c8a0c'::uuid AND lower(item_number) = 'j-2'))
);
CREATE TABLE public.motions (
  id uuid PRIMARY KEY, agenda_item_id uuid NOT NULL REFERENCES public.agenda_items,
  motion_type text NOT NULL, motion_text text NOT NULL, moved_by text, seconded_by text,
  result text NOT NULL, vote_tally text, resolution_number text,
  sequence_number smallint NOT NULL, source text, created_at timestamptz NOT NULL,
  vote_explainer text CHECK (vote_explainer IS NULL),
  vote_explainer_generated_at timestamptz CHECK (vote_explainer_generated_at IS NULL),
  vote_explainer_model text CHECK (vote_explainer_model IS NULL),
  CHECK (agenda_item_id <> '9cf375c8-edc1-413c-8ee0-6485348fbc6f'::uuid)
);
CREATE TABLE public.votes (
  id uuid PRIMARY KEY, motion_id uuid NOT NULL REFERENCES public.motions,
  official_id uuid REFERENCES public.officials, official_name text NOT NULL,
  official_role text, vote_choice text NOT NULL, source text
);
CREATE TABLE public.meeting_attendance (
  id uuid PRIMARY KEY, meeting_id uuid NOT NULL REFERENCES public.meetings,
  official_id uuid NOT NULL REFERENCES public.officials,
  body_id uuid REFERENCES public.bodies, status text NOT NULL, notes text
);
CREATE TABLE public.topics (
  id uuid PRIMARY KEY, city_fips text NOT NULL CHECK (city_fips = '0660620'),
  slug text NOT NULL, name text NOT NULL, description text, primary_category text,
  status text NOT NULL, merged_into_id uuid REFERENCES public.topics DEFERRABLE INITIALLY DEFERRED,
  color_classes text, keywords text[] NOT NULL, created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL
);
CREATE TABLE public.item_topics (
  id uuid PRIMARY KEY, agenda_item_id uuid NOT NULL REFERENCES public.agenda_items,
  topic_id uuid NOT NULL REFERENCES public.topics,
  confidence real NOT NULL, source text NOT NULL, created_at timestamptz NOT NULL
);
CREATE TABLE public.closed_session_items (
  id uuid PRIMARY KEY, meeting_id uuid NOT NULL REFERENCES public.meetings,
  item_number text NOT NULL, legal_authority text NOT NULL, description text NOT NULL,
  parties text[], reportable_action text
);
CREATE TABLE public.public_comments (
  id uuid PRIMARY KEY, meeting_id uuid NOT NULL REFERENCES public.meetings,
  agenda_item_id uuid REFERENCES public.agenda_items, speaker_name text NOT NULL,
  method text NOT NULL, comment_type text NOT NULL, source text,
  confidence real, name_confidence text, extracted_at timestamptz,
  created_at timestamptz NOT NULL, city_fips text CHECK (city_fips = '0660620'),
  summary text CHECK (summary IS NULL),
  submitted_by_system boolean NOT NULL DEFAULT false CHECK (NOT submitted_by_system)
);
CREATE TABLE public.finance_public_events (
  event_key text PRIMARY KEY, scope_key text NOT NULL CHECK (scope_key = '0660620:calendar-2026'),
  event_kind text NOT NULL CHECK (event_kind IN
    ('receipt','transfer','independent_expenditure','refund','loan','noncash')),
  donor_name text, donor_fppc_id text, recipient_name text, recipient_fppc_id text,
  reporting_filer_name text, reporting_filer_fppc_id text,
  amount numeric NOT NULL, amount_kind text NOT NULL,
  activity_date date NOT NULL CHECK (activity_date BETWEEN DATE '2026-01-01' AND DATE '2026-11-03'),
  support_oppose text CHECK (support_oppose IN ('S','O')), candidate_name text,
  measure_name text, election_date date, filing_ids text[] NOT NULL,
  source_urls text[] NOT NULL, source_url text NOT NULL CHECK (btrim(source_url) <> ''),
  extracted_at timestamptz NOT NULL, source_tier smallint NOT NULL CHECK (source_tier BETWEEN 1 AND 4),
  confidence_score numeric NOT NULL CHECK (confidence_score BETWEEN 0.90 AND 1.00),
  reconciliation_status text NOT NULL CHECK (reconciliation_status IN ('source_reported','matched_exact'))
);
CREATE TABLE public.finance_public_coverage (
  source text NOT NULL, form_type text NOT NULL,
  scope_key text NOT NULL CHECK (scope_key = '0660620:calendar-2026'),
  status text NOT NULL CHECK (status IN ('complete','partial','unavailable','pending_review')),
  checked_at timestamptz NOT NULL, activity_from date, activity_through date,
  filing_count integer NOT NULL, assertion_count integer NOT NULL, pending_count integer NOT NULL,
  limitations text[] NOT NULL, source_url text NOT NULL CHECK (btrim(source_url) <> ''),
  extracted_at timestamptz NOT NULL, source_tier smallint NOT NULL,
  confidence_score numeric NOT NULL,
  PRIMARY KEY (source, form_type, scope_key)
);
-- Explicit public availability metadata; these are projection decisions, not source facts.
CREATE TABLE public.core_projection_status (
  feature text PRIMARY KEY, status text NOT NULL, detail text NOT NULL,
  checked_at timestamptz, source_url text, revision_sha256 text,
  source_scope text, updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO public.core_projection_status (feature,status,detail) VALUES
  ('generated_content','withheld','Basic core contains no generated summaries, recaps, biographies or vote explanations.'),
  ('public_comments','not_indexed','Comment projection is off by default. Missing records do not establish that no comments occurred.'),
  ('conflict_flags','not_indexed','Conflict and influence analysis is unavailable in the basic tier.'),
  ('finance','partial','Published 2026 index only: 2026-01-01 through 2026-11-03. Preserve individual source coverage limitations.'),
  ('point_molate_2010_j2','held','J-2 of meeting 5f560013-daea-499a-8ecd-ca1a089c8a0c is retained; disputed motions/votes are withheld. Source: https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809; reviewed 2026-10-03.');
-- An empty compatibility relation, protected against later accidental population.
CREATE TABLE public.conflict_flags (
  id uuid PRIMARY KEY, city_fips text, agenda_item_id uuid REFERENCES public.agenda_items,
  meeting_id uuid REFERENCES public.meetings, official_id uuid REFERENCES public.officials,
  flag_type text, description text, evidence jsonb, confidence numeric,
  legal_reference text, reviewed boolean, reviewed_at timestamptz, reviewed_by text,
  false_positive boolean, is_current boolean, created_at timestamptz,
  CONSTRAINT basic_core_conflict_flags_empty CHECK (false)
);

CREATE INDEX ON public.meetings (meeting_date DESC, id);
CREATE INDEX ON public.meetings (body_id, meeting_date DESC);
CREATE UNIQUE INDEX core_meeting_source_guid ON public.meetings (source_meeting_guid)
  WHERE source_meeting_guid IS NOT NULL;
CREATE INDEX ON public.agenda_items (meeting_id, item_number, id);
CREATE INDEX ON public.agenda_items (topic_label, id);
CREATE INDEX ON public.motions (agenda_item_id, sequence_number, id);
CREATE INDEX ON public.votes (motion_id, id);
CREATE INDEX ON public.votes (official_id);
CREATE INDEX ON public.meeting_attendance (meeting_id, id);
CREATE INDEX ON public.item_topics (agenda_item_id, topic_id);
CREATE INDEX ON public.closed_session_items (meeting_id, id);
CREATE INDEX ON public.public_comments (meeting_id, id);
CREATE INDEX ON public.public_comments (agenda_item_id, created_at, id);
CREATE INDEX ON public.finance_public_events (activity_date DESC, event_key);
CREATE INDEX core_agenda_fts ON public.agenda_items USING gin
  (to_tsvector('english', coalesce(title,'') || ' ' || coalesce(description,'') || ' ' ||
    coalesce(category,'') || ' ' || coalesce(topic_label,'')));
CREATE INDEX core_motion_fts ON public.motions USING gin (to_tsvector('english', motion_text));

-- Same named arguments/result shape as the existing read-only search RPC.
-- vote_explainer is a legacy result-kind alias here: search SOURCE motion_text.
CREATE FUNCTION public.search_site(p_query text, p_city_fips text DEFAULT '0660620',
  p_result_type text DEFAULT NULL, p_limit integer DEFAULT 20, p_offset integer DEFAULT 0)
RETURNS TABLE(id uuid, result_type text, title text, snippet text, url_path text,
  relevance_score real, metadata jsonb)
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $fn$
  WITH parameters AS (
    SELECT plainto_tsquery('english', left(btrim(coalesce(p_query,'')),200)) AS q
  ), matches AS (
    SELECT ai.id, 'agenda_item'::text AS result_type, ai.title,
      ts_headline('english', coalesce(ai.description,ai.title), p.q,
        'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20') AS snippet,
      '/meetings/' || ai.meeting_id::text || '/items/' || lower(ai.item_number) AS url_path,
      ts_rank(to_tsvector('english', coalesce(ai.title,'') || ' ' || coalesce(ai.description,'') || ' ' ||
        coalesce(ai.category,'') || ' ' || coalesce(ai.topic_label,'')), p.q)::real AS relevance_score,
      jsonb_build_object('meeting_date',mt.meeting_date,'category',ai.category,
        'item_number',ai.item_number,'topic_label',ai.topic_label,'text_source','source_agenda') AS metadata
    FROM public.agenda_items ai JOIN public.meetings mt ON mt.id=ai.meeting_id CROSS JOIN parameters p
    WHERE p_city_fips='0660620' AND mt.city_fips=p_city_fips
      AND mt.source_cancelled_at IS NULL AND ai.agenda_source_retired_at IS NULL
      AND (p_result_type IS NULL OR p_result_type='agenda_item')
      AND to_tsvector('english',coalesce(ai.title,'') || ' ' || coalesce(ai.description,'') || ' ' ||
        coalesce(ai.category,'') || ' ' || coalesce(ai.topic_label,'')) @@ p.q
    UNION ALL
    SELECT mo.id, 'vote_explainer'::text, ai.title,
      ts_headline('english',mo.motion_text,p.q,'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'),
      '/meetings/' || ai.meeting_id::text || '/items/' || lower(ai.item_number),
      ts_rank(to_tsvector('english',mo.motion_text),p.q)::real,
      jsonb_build_object('meeting_date',mt.meeting_date,'agenda_item_title',ai.title,'text_source','source_motion')
    FROM public.motions mo JOIN public.agenda_items ai ON ai.id=mo.agenda_item_id
      JOIN public.meetings mt ON mt.id=ai.meeting_id CROSS JOIN parameters p
    WHERE p_city_fips='0660620' AND mt.city_fips=p_city_fips
      AND mt.source_cancelled_at IS NULL AND ai.agenda_source_retired_at IS NULL
      AND (p_result_type IS NULL OR p_result_type='vote_explainer')
      AND to_tsvector('english',mo.motion_text) @@ p.q
  ) SELECT * FROM matches ORDER BY relevance_score DESC, result_type, id
    LIMIT least(greatest(coalesce(p_limit,20),1),50)
    OFFSET least(greatest(coalesce(p_offset,0),0),200);
$fn$;
REVOKE ALL ON FUNCTION public.search_site(text,text,text,integer,integer) FROM PUBLIC;

-- PostgreSQL itself stays provider-independent. Existing Supabase read roles,
-- if present, receive SELECT/EXECUTE only. An optional basic_core_reader role
-- can be provisioned separately for a local PostgREST instance.
DO $permissions$
DECLARE relation_name text; role_name text;
BEGIN
  FOR relation_name IN SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',relation_name);
    EXECUTE format('REVOKE ALL ON TABLE public.%I FROM PUBLIC',relation_name);
    EXECUTE format('CREATE POLICY core_public_read ON public.%I FOR SELECT USING (true)',relation_name);
    FOREACH role_name IN ARRAY ARRAY['anon','authenticated','service_role','basic_core_reader'] LOOP
      IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=role_name) THEN
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM %I',relation_name,role_name);
        IF role_name <> 'service_role' THEN
          EXECUTE format('GRANT SELECT ON TABLE public.%I TO %I',relation_name,role_name);
        END IF;
      END IF;
    END LOOP;
  END LOOP;
  FOREACH role_name IN ARRAY ARRAY['anon','authenticated','basic_core_reader'] LOOP
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=role_name) THEN
      EXECUTE format('GRANT USAGE ON SCHEMA public TO %I',role_name);
      EXECUTE format('GRANT EXECUTE ON FUNCTION public.search_site(text,text,text,integer,integer) TO %I',role_name);
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='service_role') THEN
    REVOKE ALL ON FUNCTION public.search_site(text,text,text,integer,integer) FROM service_role;
  END IF;
END;
$permissions$;
COMMIT;
