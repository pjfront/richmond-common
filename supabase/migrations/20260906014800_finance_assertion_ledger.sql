-- Preserve reports separately from economic events. No historical rows are rewritten.
CREATE TABLE IF NOT EXISTS public.finance_assertions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source text NOT NULL,
    scope_key text NOT NULL,
    record_key text NOT NULL,
    content_hash text NOT NULL CHECK (length(content_hash) = 64),
    filing_id text NOT NULL,
    transaction_id text NOT NULL,
    form_type text NOT NULL,
    transaction_type integer,
    reporting_filer_name text NOT NULL,
    reporting_filer_fppc_id text,
    donor_name text,
    donor_fppc_id text,
    recipient_name text,
    recipient_fppc_id text,
    event_kind text NOT NULL CHECK (event_kind IN ('receipt','transfer','independent_expenditure','refund','loan','noncash','unclassified')),
    amount numeric(16,2),
    amount_kind text NOT NULL,
    activity_date date,
    support_oppose text CHECK (support_oppose IN ('S','O')),
    candidate_name text,
    measure_name text,
    election_date date,
    report_number text,
    amends_filing_id text,
    amended_by_filing_id text,
    amendment_sequence integer NOT NULL DEFAULT 0,
    document_id uuid REFERENCES public.documents(id),
    raw_payload jsonb NOT NULL,
    source_url text NOT NULL CHECK (btrim(source_url) <> ''),
    extracted_at timestamptz NOT NULL DEFAULT now(),
    source_tier smallint NOT NULL DEFAULT 1 CHECK (source_tier BETWEEN 1 AND 4),
    confidence_score numeric(3,2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    -- Derived selection state can change; source evidence cannot.
    is_current boolean NOT NULL DEFAULT true,
    reconciliation_status text NOT NULL DEFAULT 'pending_review',
    canonical_event_key text,
    review_reason text,
    UNIQUE(source, record_key, content_hash)
);
CREATE INDEX IF NOT EXISTS finance_assertions_scope_current
    ON public.finance_assertions(source,scope_key) WHERE is_current;
CREATE INDEX IF NOT EXISTS finance_assertions_filing ON public.finance_assertions(source,filing_id);

CREATE OR REPLACE FUNCTION public.protect_finance_evidence() RETURNS trigger
LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Finance source assertions cannot be deleted';
    END IF;
    IF (to_jsonb(NEW) - ARRAY['is_current','reconciliation_status','canonical_event_key','review_reason'])
       IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['is_current','reconciliation_status','canonical_event_key','review_reason']) THEN
        RAISE EXCEPTION 'Finance source evidence is immutable; insert a new content version';
    END IF;
    RETURN NEW;
END; $$;
DROP TRIGGER IF EXISTS protect_finance_evidence ON public.finance_assertions;
CREATE TRIGGER protect_finance_evidence BEFORE UPDATE OR DELETE ON public.finance_assertions
    FOR EACH ROW EXECUTE FUNCTION public.protect_finance_evidence();

CREATE TABLE IF NOT EXISTS public.finance_events (
    event_key text PRIMARY KEY,
    source text NOT NULL,
    scope_key text NOT NULL,
    event_kind text NOT NULL CHECK (event_kind IN ('receipt','transfer','independent_expenditure','refund','loan','noncash')),
    reporting_filer_name text NOT NULL,
    reporting_filer_fppc_id text,
    donor_name text,
    donor_fppc_id text,
    recipient_name text,
    recipient_fppc_id text,
    amount numeric(16,2) NOT NULL,
    amount_kind text NOT NULL,
    activity_date date NOT NULL,
    support_oppose text CHECK (support_oppose IN ('S','O')),
    candidate_name text,
    measure_name text,
    election_date date,
    description text,
    filing_ids text[] NOT NULL,
    source_urls text[] NOT NULL,
    assertion_ids uuid[] NOT NULL,
    reconciliation_status text NOT NULL CHECK (reconciliation_status IN ('source_reported','matched_exact','pending_review')),
    is_current boolean NOT NULL DEFAULT true,
    source_url text NOT NULL CHECK (btrim(source_url) <> ''),
    extracted_at timestamptz NOT NULL,
    source_tier smallint NOT NULL CHECK (source_tier BETWEEN 1 AND 4),
    confidence_score numeric(3,2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1)
);
CREATE INDEX IF NOT EXISTS finance_events_recipient_date ON public.finance_events(recipient_fppc_id,activity_date) WHERE is_current;
CREATE INDEX IF NOT EXISTS finance_events_candidate_date ON public.finance_events(candidate_name,activity_date) WHERE is_current;

CREATE TABLE IF NOT EXISTS public.finance_source_coverage (
    source text NOT NULL,
    form_type text NOT NULL,
    scope_key text NOT NULL,
    status text NOT NULL CHECK (status IN ('complete','partial','unavailable','pending_review')),
    checked_at timestamptz NOT NULL,
    activity_from date,
    activity_through date,
    filing_count integer NOT NULL DEFAULT 0,
    assertion_count integer NOT NULL DEFAULT 0,
    pending_count integer NOT NULL DEFAULT 0,
    limitations text[] NOT NULL DEFAULT '{}',
    source_url text NOT NULL CHECK (btrim(source_url) <> ''),
    extracted_at timestamptz NOT NULL,
    source_tier smallint NOT NULL DEFAULT 1 CHECK (source_tier BETWEEN 1 AND 4),
    confidence_score numeric(3,2) NOT NULL CHECK (confidence_score BETWEEN 0 AND 1),
    PRIMARY KEY(source,form_type,scope_key)
);
COMMENT ON TABLE public.finance_source_coverage IS
    'Coverage of the precisely described source/window, never a claim that all political activity is known.';

ALTER TABLE public.finance_assertions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finance_source_coverage ENABLE ROW LEVEL SECURITY;
-- Default privileges may grant TRUNCATE, which bypasses row policies. RLS is
-- not a substitute for revoking table privileges on newly created relations.
REVOKE ALL ON public.finance_assertions,public.finance_events,public.finance_source_coverage
    FROM PUBLIC,anon,authenticated;
REVOKE ALL ON public.finance_assertions FROM service_role;
GRANT SELECT, INSERT, UPDATE ON public.finance_assertions TO service_role;
DROP POLICY IF EXISTS finance_assertions_service ON public.finance_assertions;
CREATE POLICY finance_assertions_service ON public.finance_assertions FOR ALL TO service_role USING(true) WITH CHECK(true);
GRANT ALL ON public.finance_events,public.finance_source_coverage TO service_role;
GRANT SELECT ON public.finance_events,public.finance_source_coverage TO anon,authenticated;
DROP POLICY IF EXISTS finance_events_service ON public.finance_events;
CREATE POLICY finance_events_service ON public.finance_events FOR ALL TO service_role USING(true) WITH CHECK(true);
DROP POLICY IF EXISTS finance_events_public ON public.finance_events;
CREATE POLICY finance_events_public ON public.finance_events FOR SELECT TO anon,authenticated
    USING(is_current AND confidence_score >= 0.90 AND reconciliation_status IN ('source_reported','matched_exact'));
DROP POLICY IF EXISTS finance_coverage_service ON public.finance_source_coverage;
CREATE POLICY finance_coverage_service ON public.finance_source_coverage FOR ALL TO service_role USING(true) WITH CHECK(true);
DROP POLICY IF EXISTS finance_coverage_public ON public.finance_source_coverage;
CREATE POLICY finance_coverage_public ON public.finance_source_coverage FOR SELECT TO anon,authenticated USING(true);

CREATE OR REPLACE VIEW public.finance_public_events WITH (security_invoker=true) AS
SELECT event_key,source,scope_key,event_kind,reporting_filer_name,reporting_filer_fppc_id,
       donor_name,donor_fppc_id,recipient_name,recipient_fppc_id,
       amount,amount_kind,activity_date,support_oppose,candidate_name,measure_name,election_date,
       description,filing_ids,source_urls,reconciliation_status,
       source_url,extracted_at,source_tier,confidence_score
FROM public.finance_events
WHERE is_current AND confidence_score >= 0.90 AND reconciliation_status IN ('source_reported','matched_exact');
GRANT SELECT ON public.finance_public_events TO anon,authenticated,service_role;

CREATE OR REPLACE VIEW public.finance_public_coverage WITH (security_invoker=true) AS
SELECT source,form_type,scope_key,status,checked_at,activity_from,activity_through,
       filing_count,assertion_count,pending_count,limitations,
       source_url,extracted_at,source_tier,confidence_score
FROM public.finance_source_coverage;
GRANT SELECT ON public.finance_public_coverage TO anon,authenticated,service_role;

-- A public source link is sufficient; do not expose raw address fields through
-- the otherwise publicly readable document lake as a side channel.
DROP POLICY IF EXISTS finance_raw_documents_private ON public.documents;
CREATE POLICY finance_raw_documents_private ON public.documents AS RESTRICTIVE
    FOR SELECT TO anon,authenticated
    USING (source_type NOT IN ('netfile_496','netfile_transaction'));

COMMENT ON COLUMN public.finance_events.confidence_score IS
    'Confidence in transcription and reconciliation, not truth of a filer claim or economic completeness.';
