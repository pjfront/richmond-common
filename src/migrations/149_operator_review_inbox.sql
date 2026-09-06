-- Migration 149: Versioned operator decisions and source-backed publication.
-- Review state and its audit event commit atomically through one service-only RPC.
-- Evidence is data: no SQL, code, URL fetch, or arbitrary action is executed from it.

CREATE TABLE IF NOT EXISTS public.civic_brief_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    kind text NOT NULL CHECK (kind IN ('story_update', 'meeting_brief', 'finance_brief')),
    subject_key text NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    sources jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(sources) = 'array'),
    input_fingerprint text NOT NULL,
    content_version bigint NOT NULL DEFAULT 1 CHECK (content_version > 0),
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'rejected')),
    published_at timestamptz,
    published_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS civic_briefs_published_subject
    ON public.civic_brief_candidates (subject_key, published_at DESC) WHERE status = 'published';
ALTER TABLE public.civic_brief_candidates ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS civic_briefs_public_read ON public.civic_brief_candidates;
CREATE POLICY civic_briefs_public_read ON public.civic_brief_candidates
    FOR SELECT TO anon, authenticated USING (status = 'published');
DROP POLICY IF EXISTS civic_briefs_service_all ON public.civic_brief_candidates;
CREATE POLICY civic_briefs_service_all ON public.civic_brief_candidates
    FOR ALL TO service_role USING (true) WITH CHECK (true);
REVOKE ALL PRIVILEGES ON TABLE public.civic_brief_candidates FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.civic_brief_candidates TO anon, authenticated;
GRANT SELECT ON TABLE public.civic_brief_candidates TO service_role;
-- Content producers can prepare drafts. Only the review RPC can change the
-- publication status or its attribution; a generic service PATCH cannot.
GRANT INSERT (id, kind, subject_key, title, body, sources, input_fingerprint)
    ON TABLE public.civic_brief_candidates TO service_role;
GRANT UPDATE (kind, subject_key, title, body, sources, input_fingerprint)
    ON TABLE public.civic_brief_candidates TO service_role;

ALTER TABLE public.pending_decisions ADD COLUMN IF NOT EXISTS review_version bigint NOT NULL DEFAULT 1;
ALTER TABLE public.pending_decisions ADD COLUMN IF NOT EXISTS review_class text NOT NULL DEFAULT 'engineering';
ALTER TABLE public.pending_decisions ADD COLUMN IF NOT EXISTS action_kind text NOT NULL DEFAULT 'resolve_only';
ALTER TABLE public.pending_decisions ADD COLUMN IF NOT EXISTS target_brief_id uuid REFERENCES public.civic_brief_candidates(id);
ALTER TABLE public.pending_decisions ADD COLUMN IF NOT EXISTS target_content_version bigint;
ALTER TABLE public.pending_decisions DROP CONSTRAINT IF EXISTS pending_decisions_review_contract;
ALTER TABLE public.pending_decisions ADD CONSTRAINT pending_decisions_review_contract CHECK (
    review_version > 0 AND review_class IN ('engineering', 'editorial') AND (
      (action_kind = 'resolve_only' AND target_brief_id IS NULL AND target_content_version IS NULL)
      OR (action_kind = 'publish_brief' AND review_class = 'editorial'
          AND target_brief_id IS NOT NULL AND target_content_version > 0)
    )
);
-- A deferred judgment stays in the open queue and must still deduplicate.
-- Existing databases may have historical deferred duplicates; do not rewrite
-- their rows or replace the existing partial unique index in this migration.

CREATE OR REPLACE FUNCTION public.bump_operator_review_version()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    NEW.review_version := OLD.review_version + 1;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS pending_decisions_review_version ON public.pending_decisions;
CREATE TRIGGER pending_decisions_review_version BEFORE UPDATE ON public.pending_decisions
    FOR EACH ROW EXECUTE FUNCTION public.bump_operator_review_version();

CREATE OR REPLACE FUNCTION public.version_civic_brief_content()
RETURNS trigger LANGUAGE plpgsql SET search_path = pg_catalog, public AS $$
BEGIN
    IF ROW(NEW.kind, NEW.subject_key, NEW.title, NEW.body, NEW.sources, NEW.input_fingerprint)
       IS DISTINCT FROM ROW(OLD.kind, OLD.subject_key, OLD.title, OLD.body, OLD.sources, OLD.input_fingerprint) THEN
        IF OLD.status = 'published' THEN
            RAISE EXCEPTION 'Published content is immutable; create a new candidate or withdraw it first' USING ERRCODE = '23514';
        END IF;
        NEW.content_version := OLD.content_version + 1;
    ELSE
        NEW.content_version := OLD.content_version;
    END IF;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS civic_brief_content_version ON public.civic_brief_candidates;
CREATE TRIGGER civic_brief_content_version BEFORE UPDATE ON public.civic_brief_candidates
    FOR EACH ROW EXECUTE FUNCTION public.version_civic_brief_content();

CREATE TABLE IF NOT EXISTS public.operator_decision_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id uuid NOT NULL REFERENCES public.pending_decisions(id),
    idempotency_key uuid NOT NULL UNIQUE,
    action text NOT NULL CHECK (action IN ('approve', 'reject', 'defer', 'reopen', 'edit_note', 'withdraw')),
    actor text NOT NULL,
    expected_version bigint NOT NULL,
    note text,
    before_state jsonb NOT NULL,
    after_state jsonb NOT NULL,
    result jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS operator_decision_events_by_decision
    ON public.operator_decision_events(decision_id, created_at DESC);
ALTER TABLE public.operator_decision_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS operator_decision_events_service_read ON public.operator_decision_events;
CREATE POLICY operator_decision_events_service_read ON public.operator_decision_events
    FOR SELECT TO service_role USING (true);
REVOKE ALL PRIVILEGES ON TABLE public.operator_decision_events FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT ON TABLE public.operator_decision_events TO service_role;

CREATE OR REPLACE FUNCTION public.review_decision(
    p_decision_id uuid, p_action text, p_expected_version bigint,
    p_idempotency_key uuid, p_note text DEFAULT NULL, p_actor text DEFAULT 'operator'
) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE
    decision public.pending_decisions%ROWTYPE;
    brief public.civic_brief_candidates%ROWTYPE;
    previous_event public.operator_decision_events%ROWTYPE;
    before_state jsonb;
    after_state jsonb;
    result jsonb;
    next_status text;
    source jsonb;
    host text;
    effect text := 'decision_recorded';
BEGIN
    IF p_action IS NULL OR p_action NOT IN ('approve', 'reject', 'defer', 'reopen', 'edit_note', 'withdraw')
       OR p_expected_version IS NULL OR p_expected_version < 1 OR p_idempotency_key IS NULL
       OR p_actor IS NULL OR length(trim(p_actor)) = 0 OR length(p_actor) > 100
       OR length(p_note) > 4000 THEN
        RAISE EXCEPTION 'Invalid review action request' USING ERRCODE = '22023';
    END IF;
    -- Serialize reuse of a request key, including requests against different rows.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_idempotency_key::text, 0));
    SELECT * INTO previous_event FROM public.operator_decision_events WHERE idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF previous_event.decision_id IS DISTINCT FROM p_decision_id
           OR previous_event.action IS DISTINCT FROM p_action
           OR previous_event.expected_version IS DISTINCT FROM p_expected_version
           OR previous_event.note IS DISTINCT FROM p_note OR previous_event.actor IS DISTINCT FROM p_actor THEN
            RETURN jsonb_build_object('ok', false, 'code', 'idempotency_conflict');
        END IF;
        RETURN previous_event.result || jsonb_build_object('replayed', true);
    END IF;
    SELECT * INTO decision FROM public.pending_decisions WHERE id = p_decision_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('ok', false, 'code', 'not_found'); END IF;
    IF decision.review_version <> p_expected_version THEN
        RETURN jsonb_build_object('ok', false, 'code', 'stale_decision', 'current_version', decision.review_version);
    END IF;
    before_state := jsonb_build_object('decision', to_jsonb(decision));
    IF decision.action_kind = 'publish_brief' THEN
        SELECT * INTO brief FROM public.civic_brief_candidates WHERE id = decision.target_brief_id FOR UPDATE;
        IF NOT FOUND OR (p_action NOT IN ('edit_note', 'defer') AND brief.content_version IS DISTINCT FROM decision.target_content_version) THEN
            RETURN jsonb_build_object('ok', false, 'code', 'stale_content');
        END IF;
        before_state := before_state || jsonb_build_object('brief', to_jsonb(brief));
    ELSIF decision.action_kind <> 'resolve_only' THEN
        RETURN jsonb_build_object('ok', false, 'code', 'unsupported_action_kind');
    END IF;

    IF p_action IN ('approve', 'reject', 'defer') AND decision.status NOT IN ('pending', 'deferred') THEN
        RETURN jsonb_build_object('ok', false, 'code', 'already_resolved');
    END IF;
    IF p_action = 'reopen' AND decision.status = 'pending' THEN
        RETURN jsonb_build_object('ok', false, 'code', 'already_open');
    END IF;
    IF p_action IN ('reopen', 'approve', 'reject') AND decision.action_kind = 'publish_brief' AND brief.status = 'published' THEN
        RETURN jsonb_build_object('ok', false, 'code', 'withdraw_required');
    END IF;
    IF p_action = 'withdraw' AND (decision.action_kind <> 'publish_brief' OR brief.status <> 'published'
                                  OR p_note IS NULL OR length(trim(p_note)) = 0) THEN
        RETURN jsonb_build_object('ok', false, 'code', 'withdraw_requires_published_brief_and_note');
    END IF;

    IF p_action = 'approve' AND decision.action_kind = 'publish_brief' THEN
        IF length(trim(brief.title)) = 0 OR length(trim(brief.body)) = 0
           OR length(trim(brief.input_fingerprint)) = 0 OR brief.body ~ '<[^>]*>'
           OR jsonb_array_length(brief.sources) = 0 THEN
            RETURN jsonb_build_object('ok', false, 'code', 'invalid_publication');
        END IF;
        FOR source IN SELECT value FROM jsonb_array_elements(brief.sources) LOOP
            IF jsonb_typeof(source) <> 'object' OR COALESCE(source->>'source_tier', '') NOT IN ('1', '2')
               OR length(trim(COALESCE(source->>'title', ''))) = 0
               OR COALESCE(source->>'url', '') !~ '^https?://[A-Za-z0-9][A-Za-z0-9.-]*(:[0-9]{1,5})?([/?#][^[:space:]]*)?$' THEN
                RETURN jsonb_build_object('ok', false, 'code', 'invalid_source');
            END IF;
            host := lower(substring(source->>'url' from '^https?://([^/:?#]+)'));
            IF host !~ '[a-z]' OR host !~ '\.' OR host ~ '(^|\.)(localhost|local|internal|test|invalid)$' THEN
                RETURN jsonb_build_object('ok', false, 'code', 'invalid_source');
            END IF;
        END LOOP;
        UPDATE public.civic_brief_candidates SET status = 'published', published_at = clock_timestamp(), published_by = p_actor
            WHERE id = brief.id RETURNING * INTO brief;
        effect := 'brief_published';
    ELSIF p_action = 'reject' AND decision.action_kind = 'publish_brief' THEN
        UPDATE public.civic_brief_candidates SET status = 'rejected' WHERE id = brief.id RETURNING * INTO brief;
        effect := 'brief_rejected';
    ELSIF p_action IN ('reopen', 'withdraw') AND decision.action_kind = 'publish_brief' THEN
        UPDATE public.civic_brief_candidates SET status = 'draft', published_at = NULL, published_by = NULL
            WHERE id = brief.id RETURNING * INTO brief;
        effect := CASE WHEN p_action = 'withdraw' THEN 'brief_withdrawn' ELSE 'brief_reopened' END;
    END IF;

    next_status := CASE p_action WHEN 'approve' THEN 'approved' WHEN 'reject' THEN 'rejected'
      WHEN 'defer' THEN 'deferred' WHEN 'reopen' THEN 'pending' WHEN 'withdraw' THEN 'pending' ELSE decision.status END;
    -- A duplicate active decision can be created while this one was resolved.
    IF next_status = 'pending' AND decision.dedup_key IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.pending_decisions d WHERE d.dedup_key = decision.dedup_key
        AND d.id <> decision.id AND d.status = 'pending'
    ) THEN
        -- Raising rolls back any brief transition made earlier in this RPC.
        RAISE EXCEPTION 'A pending decision already exists for this evidence' USING ERRCODE = '23505';
    END IF;
    UPDATE public.pending_decisions SET status = next_status,
        resolution_note = p_note,
        resolved_by = CASE WHEN p_action = 'edit_note' THEN decision.resolved_by WHEN next_status = 'pending' THEN NULL ELSE p_actor END,
        resolved_at = CASE WHEN p_action = 'edit_note' THEN decision.resolved_at WHEN next_status = 'pending' THEN NULL ELSE clock_timestamp() END
        WHERE id = decision.id RETURNING * INTO decision;
    after_state := jsonb_build_object('decision', to_jsonb(decision));
    IF decision.action_kind = 'publish_brief' THEN after_state := after_state || jsonb_build_object('brief', to_jsonb(brief)); END IF;
    result := jsonb_build_object('ok', true, 'replayed', false, 'effect', effect,
        'decision_id', decision.id, 'status', decision.status, 'review_version', decision.review_version);
    INSERT INTO public.operator_decision_events (decision_id, idempotency_key, action, actor, expected_version,
        note, before_state, after_state, result)
    VALUES (decision.id, p_idempotency_key, p_action, p_actor, p_expected_version, p_note, before_state, after_state, result);
    RETURN result;
END;
$$;
REVOKE ALL ON FUNCTION public.review_decision(uuid, text, bigint, uuid, text, text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.review_decision(uuid, text, bigint, uuid, text, text) TO service_role;
REVOKE ALL ON FUNCTION public.bump_operator_review_version() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.version_civic_brief_content() FROM PUBLIC, anon, authenticated;
