-- Migration 141: durable, per-recipient delivery state for subscriber email.
--
-- Meeting-level *_emailed_at columns cannot distinguish successful recipients
-- from partial failures. This private ledger is the idempotency authority for
-- welcome, orientation, recap, and weekly-digest delivery. A separate private
-- activation ledger preserves first-subscription/reactivation history without
-- duplicating subscriber PII.
--
-- Cutover rule: do not backfill this table or rewrite legacy delivery markers.
-- meetings.orientation_emailed_at, meetings.recap_emailed_at,
-- meetings.transcript_recap_emailed_at, and
-- email_subscribers.last_orientation_meeting_id remain authoritative for sends
-- completed before this ledger existed. Application discovery honors them.

-- These nullable marker columns deliberately have no defaults. Old application
-- code never writes them, so applying this migration before the new route (or
-- rolling the route back) cannot manufacture an activation or welcome intent.
ALTER TABLE email_subscribers
    ADD COLUMN IF NOT EXISTS current_activation_id UUID,
    ADD COLUMN IF NOT EXISTS current_activation_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS current_activation_surface VARCHAR(32);

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_subscribers_current_activation
    ON email_subscribers (current_activation_id)
    WHERE current_activation_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS email_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscriber_id UUID NOT NULL
        REFERENCES email_subscribers(id) ON DELETE CASCADE,
    city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
    delivery_kind VARCHAR(20) NOT NULL,
    content_key VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    -- Welcome intents are inserted atomically with activation and bind their
    -- immutable payload fingerprint on the first delivery claim.
    payload_sha256 VARCHAR(64),
    claim_token UUID,
    lease_expires_at TIMESTAMPTZ,
    first_attempt_at TIMESTAMPTZ,
    next_attempt_at TIMESTAMPTZ,
    provider_message_id VARCHAR(255),
    failure_kind VARCHAR(32),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    CONSTRAINT email_deliveries_recipient_content_unique
        UNIQUE (subscriber_id, delivery_kind, content_key)
);

-- Keep the migration restart-safe if an earlier preview applied only the
-- original table definition.
ALTER TABLE email_deliveries
    ADD COLUMN IF NOT EXISTS payload_sha256 VARCHAR(64),
    ADD COLUMN IF NOT EXISTS first_attempt_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS failure_kind VARCHAR(32);

ALTER TABLE email_deliveries
    ALTER COLUMN failure_kind TYPE VARCHAR(32);

ALTER TABLE email_deliveries
    ALTER COLUMN payload_sha256 DROP NOT NULL;

-- Replace the checks whose v141 policy is stricter/different than the
-- original draft, including on a partially provisioned preview database.
ALTER TABLE email_deliveries
    DROP CONSTRAINT IF EXISTS email_deliveries_status_check,
    DROP CONSTRAINT IF EXISTS email_deliveries_attempt_count_check,
    DROP CONSTRAINT IF EXISTS email_deliveries_failure_kind_check;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'email_deliveries'::regclass
          AND conname = 'email_deliveries_delivery_kind_check'
    ) THEN
        ALTER TABLE email_deliveries
            ADD CONSTRAINT email_deliveries_delivery_kind_check
            CHECK (delivery_kind IN ('welcome', 'orientation', 'recap', 'digest'))
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'email_deliveries'::regclass
          AND conname = 'email_deliveries_status_check'
    ) THEN
        ALTER TABLE email_deliveries
            ADD CONSTRAINT email_deliveries_status_check
            CHECK (status IN ('pending', 'sending', 'sent', 'retry_wait', 'manual_review', 'cancelled'))
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'email_deliveries'::regclass
          AND conname = 'email_deliveries_attempt_count_check'
    ) THEN
        ALTER TABLE email_deliveries
            ADD CONSTRAINT email_deliveries_attempt_count_check
            CHECK (attempt_count BETWEEN 0 AND 3)
            NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'email_deliveries'::regclass
          AND conname = 'email_deliveries_failure_kind_check'
    ) THEN
        ALTER TABLE email_deliveries
            ADD CONSTRAINT email_deliveries_failure_kind_check
            CHECK (failure_kind IS NULL OR failure_kind IN (
                'provider_rejected', 'provider_ambiguous', 'payload_changed',
                'retry_window_expired', 'attempts_exhausted',
                'subscription_cycle_ended', 'invalid_content_key',
                'recipient_inactive', 'source_unavailable',
                'legacy_superseded'
            ))
            NOT VALID;
    END IF;
END;
$$;

-- Immutable, private activation history for the November demand test. It stores
-- only a subscriber FK plus coarse, allow-listed acquisition facts: never an
-- email address, name, unsubscribe token, raw URL, or referrer.
CREATE TABLE IF NOT EXISTS subscription_activations (
    id UUID PRIMARY KEY,
    subscriber_id UUID NOT NULL
        REFERENCES email_subscribers(id) ON DELETE CASCADE,
    activation_kind VARCHAR(20) NOT NULL
        CHECK (activation_kind IN ('initial', 'reactivation')),
    activation_at TIMESTAMPTZ NOT NULL,
    acquisition_surface VARCHAR(32) NOT NULL
        CHECK (acquisition_surface IN (
            'homepage', 'nav', 'footer', 'meeting',
            'subscribe_page', 'november_election'
        )),
    city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE email_deliveries
    ADD COLUMN IF NOT EXISTS subscription_activation_id UUID
        REFERENCES subscription_activations(id) ON DELETE CASCADE;

CREATE UNIQUE INDEX IF NOT EXISTS idx_email_deliveries_subscription_activation
    ON email_deliveries (subscription_activation_id)
    WHERE subscription_activation_id IS NOT NULL;

-- NULL is reserved for an unattempted activation-backed welcome intent (or
-- that same never-attempted intent after it is cancelled). Every other row has
-- an immutable lowercase SHA-256 payload fingerprint.
ALTER TABLE email_deliveries
    DROP CONSTRAINT IF EXISTS email_deliveries_payload_sha256_check,
    DROP CONSTRAINT IF EXISTS email_deliveries_activation_welcome_check;
ALTER TABLE email_deliveries
    ADD CONSTRAINT email_deliveries_payload_sha256_check
        CHECK (
            COALESCE(payload_sha256 ~ '^[0-9a-f]{64}$', FALSE)
            OR (
                payload_sha256 IS NULL
                AND subscription_activation_id IS NOT NULL
                AND delivery_kind = 'welcome'
                AND attempt_count = 0
                AND status IN ('pending', 'cancelled')
                AND first_attempt_at IS NULL
                AND next_attempt_at IS NULL
                AND claim_token IS NULL
                AND lease_expires_at IS NULL
                AND provider_message_id IS NULL
                AND sent_at IS NULL
            )
        ) NOT VALID,
    ADD CONSTRAINT email_deliveries_activation_welcome_check
        CHECK (
            subscription_activation_id IS NULL
            OR (
                delivery_kind = 'welcome'
                AND content_key = 'welcome:' || subscription_activation_id::TEXT
            )
        ) NOT VALID;

CREATE INDEX IF NOT EXISTS idx_subscription_activations_window
    ON subscription_activations (activation_at, activation_kind, acquisition_surface);

ALTER TABLE subscription_activations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role reads subscription activations"
    ON subscription_activations;
CREATE POLICY "Service role reads subscription activations"
    ON subscription_activations FOR SELECT TO service_role
    USING (true);
REVOKE ALL ON TABLE subscription_activations FROM anon, authenticated, service_role;
GRANT SELECT ON TABLE subscription_activations TO service_role;

-- Per-cycle activation rows are retained for at most 90 days plus the bounded
-- scheduler interval. Linked activation-backed welcome intents are deleted by
-- their ON DELETE CASCADE foreign key. Subscriber rows and current activation
-- markers are never selected or modified by this function.
CREATE OR REPLACE FUNCTION prune_subscription_activations()
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    WITH deleted AS (
        DELETE FROM public.subscription_activations
        WHERE activation_at < NOW() - INTERVAL '90 days'
        RETURNING 1
    )
    SELECT COUNT(*)::INTEGER INTO deleted_count FROM deleted;

    RETURN deleted_count;
END;
$$;

-- Marker coherence is enforced only for future writes. The two legacy
-- subscriber rows remain NULL/NULL/NULL and are intentionally not backfilled.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'email_subscribers'::regclass
          AND conname = 'email_subscribers_activation_marker_check'
    ) THEN
        ALTER TABLE email_subscribers
            ADD CONSTRAINT email_subscribers_activation_marker_check
            CHECK (
                (current_activation_id IS NULL
                    AND current_activation_at IS NULL
                    AND current_activation_surface IS NULL)
                OR
                (current_activation_id IS NOT NULL
                    AND current_activation_at IS NOT NULL
                    AND current_activation_surface IN (
                        'homepage', 'nav', 'footer', 'meeting',
                        'subscribe_page', 'november_election'
                    ))
            ) NOT VALID;
    END IF;
END;
$$;

-- A fresh marker creates activation history and the pending welcome intent in
-- the same transaction as the subscriber insert/reactivation. UPDATE triggers
-- only when new code explicitly includes current_activation_id; old code and a
-- rollback leave the marker unchanged and cannot create duplicate welcomes.
CREATE OR REPLACE FUNCTION record_subscription_activation_intent()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    activation_kind_value VARCHAR(20);
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.current_activation_id IS NULL THEN
            RETURN NEW;
        END IF;
        activation_kind_value := 'initial';
    ELSE
        IF NEW.current_activation_id IS NOT DISTINCT FROM OLD.current_activation_id THEN
            IF OLD.status = 'unsubscribed' AND NEW.status = 'active' THEN
                RAISE EXCEPTION 'Reactivation requires a fresh activation marker';
            END IF;
            IF NEW.current_activation_at IS DISTINCT FROM OLD.current_activation_at
               OR NEW.current_activation_surface IS DISTINCT FROM OLD.current_activation_surface THEN
                RAISE EXCEPTION 'Activation time and surface are immutable for the current marker';
            END IF;
            RETURN NEW;
        END IF;
        IF OLD.status <> 'unsubscribed' OR NEW.status <> 'active' THEN
            RAISE EXCEPTION 'A new activation marker requires an unsubscribed-to-active transition';
        END IF;
        activation_kind_value := 'reactivation';
    END IF;

    IF NEW.status <> 'active'
       OR NEW.current_activation_id IS NULL
       OR NEW.current_activation_at IS NULL
       OR NEW.current_activation_surface IS NULL THEN
        RAISE EXCEPTION 'A complete activation marker is required for an active subscription';
    END IF;

    IF NEW.subscribed_at IS DISTINCT FROM NEW.current_activation_at THEN
        RAISE EXCEPTION 'subscribed_at must match the explicit activation time';
    END IF;

    IF NEW.current_activation_at < NOW() - INTERVAL '5 minutes'
       OR NEW.current_activation_at > NOW() + INTERVAL '5 minutes' THEN
        RAISE EXCEPTION 'Activation marker is not fresh';
    END IF;

    INSERT INTO subscription_activations (
        id, subscriber_id, activation_kind, activation_at,
        acquisition_surface, city_fips
    ) VALUES (
        NEW.current_activation_id, NEW.id, activation_kind_value,
        NEW.current_activation_at, NEW.current_activation_surface, NEW.city_fips
    );

    INSERT INTO email_deliveries (
        subscriber_id, city_fips, delivery_kind, content_key,
        subscription_activation_id, status, attempt_count, payload_sha256,
        created_at, updated_at
    ) VALUES (
        NEW.id, NEW.city_fips, 'welcome',
        'welcome:' || NEW.current_activation_id::TEXT,
        NEW.current_activation_id, 'pending', 0, NULL,
        NEW.current_activation_at, NEW.current_activation_at
    );

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS record_subscription_activation_intent_trigger
    ON email_subscribers;
CREATE TRIGGER record_subscription_activation_intent_trigger
AFTER INSERT OR UPDATE OF current_activation_id, current_activation_at,
    current_activation_surface ON email_subscribers
FOR EACH ROW EXECUTE FUNCTION record_subscription_activation_intent();

DROP INDEX IF EXISTS idx_email_deliveries_retryable;
CREATE INDEX idx_email_deliveries_retryable
    ON email_deliveries (status, next_attempt_at, lease_expires_at)
    WHERE status IN ('pending', 'sending', 'retry_wait');

CREATE INDEX IF NOT EXISTS idx_email_deliveries_content_status
    ON email_deliveries (delivery_kind, content_key, status);

ALTER TABLE email_deliveries ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access on email_deliveries"
    ON email_deliveries;
CREATE POLICY "Service role full access on email_deliveries"
    ON email_deliveries FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

REVOKE ALL ON TABLE email_deliveries FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE email_deliveries TO service_role;

-- Create the unique row if needed, then atomically lease it. A delivery gets
-- at most three attempts, all within a conservative 23-hour window inside
-- Resend's 24-hour idempotency guarantee. Payload changes and exhausted or
-- expired retries stop for manual review rather than risking a duplicate.
DROP FUNCTION IF EXISTS claim_email_delivery(UUID, VARCHAR, VARCHAR, INTEGER);
CREATE OR REPLACE FUNCTION claim_email_delivery(
    p_subscriber_id UUID,
    p_delivery_kind VARCHAR,
    p_content_key VARCHAR,
    p_payload_sha256 VARCHAR,
    p_lease_minutes INTEGER DEFAULT 15,
    p_max_attempts INTEGER DEFAULT 3
)
RETURNS TABLE(
    delivery_id UUID,
    delivery_claim_token UUID,
    delivery_attempt INTEGER,
    delivery_disposition VARCHAR
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    delivery email_deliveries%ROWTYPE;
    attempt_limit INTEGER := GREATEST(1, LEAST(COALESCE(p_max_attempts, 3), 3));
    current_activation UUID;
BEGIN
    IF p_payload_sha256 IS NULL OR p_payload_sha256 !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'A lowercase SHA-256 payload fingerprint is required';
    END IF;

    IF p_delivery_kind = 'welcome' THEN
        SELECT current_activation_id INTO current_activation
        FROM email_subscribers
        WHERE id = p_subscriber_id;

        IF current_activation IS NOT NULL
           AND p_content_key <> 'welcome:' || current_activation::TEXT THEN
            RAISE EXCEPTION 'Welcome content key does not match the current activation';
        END IF;
    END IF;

    -- A marked activation's trigger is the only authority allowed to create
    -- its welcome row. Other message kinds and legacy unmarked welcomes retain
    -- create-on-first-claim behavior.
    IF current_activation IS NULL THEN
        INSERT INTO email_deliveries (
            subscriber_id, delivery_kind, content_key, payload_sha256
        ) VALUES (
            p_subscriber_id, p_delivery_kind, p_content_key, p_payload_sha256
        )
        ON CONFLICT (subscriber_id, delivery_kind, content_key) DO NOTHING;
    END IF;

    SELECT * INTO delivery
    FROM email_deliveries
    WHERE subscriber_id = p_subscriber_id
      AND delivery_kind = p_delivery_kind
      AND content_key = p_content_key
    FOR UPDATE;

    IF delivery.id IS NULL THEN
        RAISE EXCEPTION 'Atomic welcome intent is missing for the current activation';
    END IF;

    IF current_activation IS NOT NULL
       AND delivery.subscription_activation_id IS DISTINCT FROM current_activation THEN
        RAISE EXCEPTION 'Welcome delivery is not linked to the current activation';
    END IF;

    IF delivery.status = 'sent' THEN
        RETURN QUERY SELECT delivery.id, NULL::UUID, delivery.attempt_count, 'already_sent'::VARCHAR;
        RETURN;
    END IF;

    IF delivery.status IN ('manual_review', 'cancelled') THEN
        RETURN QUERY SELECT delivery.id, NULL::UUID, delivery.attempt_count, 'manual_review'::VARCHAR;
        RETURN;
    END IF;

    -- Activation-triggered welcomes intentionally begin without a payload
    -- fingerprint. Bind it exactly once, before any provider attempt.
    IF delivery.payload_sha256 IS NULL THEN
        IF delivery.status <> 'pending' OR delivery.attempt_count <> 0 THEN
            UPDATE email_deliveries
            SET status = 'manual_review',
                failure_kind = 'payload_changed',
                next_attempt_at = NULL,
                lease_expires_at = NULL,
                claim_token = NULL,
                last_error = 'Missing email payload fingerprint after delivery attempts began',
                updated_at = NOW()
            WHERE id = delivery.id;
            RETURN QUERY SELECT delivery.id, NULL::UUID, delivery.attempt_count, 'manual_review'::VARCHAR;
            RETURN;
        END IF;

        UPDATE email_deliveries
        SET payload_sha256 = p_payload_sha256,
            updated_at = NOW()
        WHERE id = delivery.id;
        delivery.payload_sha256 := p_payload_sha256;
    END IF;

    IF delivery.payload_sha256 IS DISTINCT FROM p_payload_sha256 THEN
        UPDATE email_deliveries
        SET status = 'manual_review',
            failure_kind = 'payload_changed',
            next_attempt_at = NULL,
            lease_expires_at = NULL,
            claim_token = NULL,
            last_error = 'Email payload changed after the first delivery claim',
            updated_at = NOW()
        WHERE id = delivery.id
          AND status <> 'sent';
        RETURN QUERY SELECT delivery.id, NULL::UUID, delivery.attempt_count, 'manual_review'::VARCHAR;
        RETURN;
    END IF;

    IF delivery.status = 'sending'
       AND delivery.lease_expires_at IS NOT NULL
       AND delivery.lease_expires_at > NOW() THEN
        RETURN QUERY SELECT delivery.id, NULL::UUID, delivery.attempt_count, 'in_flight'::VARCHAR;
        RETURN;
    END IF;

    IF delivery.attempt_count >= attempt_limit THEN
        UPDATE email_deliveries
        SET status = 'manual_review',
            failure_kind = 'attempts_exhausted',
            next_attempt_at = NULL,
            lease_expires_at = NULL,
            claim_token = NULL,
            updated_at = NOW()
        WHERE id = delivery.id;
        RETURN QUERY SELECT delivery.id, NULL::UUID, delivery.attempt_count, 'manual_review'::VARCHAR;
        RETURN;
    END IF;

    IF delivery.first_attempt_at IS NOT NULL
       AND delivery.first_attempt_at <= NOW() - INTERVAL '23 hours' THEN
        UPDATE email_deliveries
        SET status = 'manual_review',
            failure_kind = 'retry_window_expired',
            next_attempt_at = NULL,
            lease_expires_at = NULL,
            claim_token = NULL,
            updated_at = NOW()
        WHERE id = delivery.id;
        RETURN QUERY SELECT delivery.id, NULL::UUID, delivery.attempt_count, 'manual_review'::VARCHAR;
        RETURN;
    END IF;

    IF delivery.status = 'retry_wait'
       AND delivery.next_attempt_at IS NOT NULL
       AND delivery.next_attempt_at > NOW() THEN
        RETURN QUERY SELECT delivery.id, NULL::UUID, delivery.attempt_count, 'backoff'::VARCHAR;
        RETURN;
    END IF;

    RETURN QUERY
    UPDATE email_deliveries AS d
    SET status = 'sending',
        attempt_count = d.attempt_count + 1,
        first_attempt_at = COALESCE(d.first_attempt_at, NOW()),
        claim_token = gen_random_uuid(),
        lease_expires_at = NOW()
            + make_interval(mins => GREATEST(1, LEAST(COALESCE(p_lease_minutes, 15), 60))),
        next_attempt_at = NULL,
        last_error = NULL,
        updated_at = NOW()
    WHERE d.id = delivery.id
    RETURNING d.id, d.claim_token, d.attempt_count, 'claimed'::VARCHAR;
END;
$$;

CREATE OR REPLACE FUNCTION complete_email_delivery(
    p_delivery_id UUID,
    p_claim_token UUID,
    p_provider_message_id VARCHAR DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    WITH completed AS (
        UPDATE email_deliveries
        SET status = 'sent',
            provider_message_id = p_provider_message_id,
            sent_at = NOW(),
            lease_expires_at = NULL,
            next_attempt_at = NULL,
            claim_token = NULL,
            failure_kind = NULL,
            last_error = NULL,
            updated_at = NOW()
        WHERE id = p_delivery_id
          AND status = 'sending'
          AND claim_token = p_claim_token
        RETURNING 1
    )
    SELECT EXISTS (SELECT 1 FROM completed);
$$;

DROP FUNCTION IF EXISTS fail_email_delivery(UUID, UUID, TEXT);
CREATE OR REPLACE FUNCTION fail_email_delivery(
    p_delivery_id UUID,
    p_claim_token UUID,
    p_error TEXT,
    p_is_ambiguous BOOLEAN DEFAULT FALSE
)
RETURNS VARCHAR
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    final_status VARCHAR;
BEGIN
    UPDATE email_deliveries
    SET status = CASE
            WHEN attempt_count >= 3
              OR first_attempt_at <= NOW() - INTERVAL '23 hours'
                THEN 'manual_review'
            ELSE 'retry_wait'
        END,
        next_attempt_at = CASE
            WHEN attempt_count >= 3
              OR first_attempt_at <= NOW() - INTERVAL '23 hours'
                THEN NULL
            WHEN attempt_count = 1 THEN NOW() + INTERVAL '5 minutes'
            ELSE NOW() + INTERVAL '30 minutes'
        END,
        lease_expires_at = NULL,
        claim_token = NULL,
        failure_kind = CASE
            WHEN attempt_count >= 3 THEN 'attempts_exhausted'
            WHEN first_attempt_at <= NOW() - INTERVAL '23 hours' THEN 'retry_window_expired'
            WHEN p_is_ambiguous THEN 'provider_ambiguous'
            ELSE 'provider_rejected'
        END,
        last_error = LEFT(COALESCE(p_error, 'Unknown email delivery failure'), 2000),
        updated_at = NOW()
    WHERE id = p_delivery_id
      AND status = 'sending'
      AND claim_token = p_claim_token
    RETURNING status INTO final_status;

    RETURN final_status;
END;
$$;

-- Terminalize a stale recovery row only if it is still due. The UPDATE's row
-- lock and predicate prevent a cleanup worker from overwriting a fresh lease
-- won concurrently by another delivery worker.
DROP FUNCTION IF EXISTS terminalize_retryable_email_delivery(UUID, VARCHAR, TEXT, BOOLEAN);
CREATE OR REPLACE FUNCTION terminalize_retryable_email_delivery(
    p_delivery_id UUID,
    p_failure_kind VARCHAR,
    p_reason TEXT,
    p_manual_review BOOLEAN DEFAULT FALSE
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    terminalized BOOLEAN;
BEGIN
    IF p_failure_kind IS NULL OR p_failure_kind NOT IN (
        'subscription_cycle_ended', 'invalid_content_key',
        'recipient_inactive', 'source_unavailable', 'legacy_superseded'
    ) THEN
        RAISE EXCEPTION 'Unsupported terminal email-delivery reason';
    END IF;

    UPDATE email_deliveries
    SET status = CASE WHEN p_manual_review THEN 'manual_review' ELSE 'cancelled' END,
        failure_kind = p_failure_kind,
        next_attempt_at = NULL,
        lease_expires_at = NULL,
        claim_token = NULL,
        last_error = LEFT(COALESCE(p_reason, 'Delivery is no longer retryable'), 2000),
        updated_at = NOW()
    WHERE id = p_delivery_id
      -- A NULL payload can only be an unattempted welcome intent, which may be
      -- cancelled but cannot be moved to manual_review by the payload check.
      AND (NOT p_manual_review OR payload_sha256 IS NOT NULL)
      AND (
          status = 'pending'
          OR (status = 'retry_wait'
              AND (next_attempt_at IS NULL OR next_attempt_at <= NOW()))
          OR (status = 'sending'
              AND (lease_expires_at IS NULL OR lease_expires_at <= NOW()))
      )
    RETURNING TRUE INTO terminalized;

    RETURN COALESCE(terminalized, FALSE);
END;
$$;

-- Preference replacement must be one transaction. The previous API deleted
-- first and inserted second, so an insert failure silently erased preferences.
CREATE OR REPLACE FUNCTION replace_email_preferences(
    p_subscriber_id UUID,
    p_topics TEXT[] DEFAULT ARRAY[]::TEXT[],
    p_districts TEXT[] DEFAULT ARRAY[]::TEXT[],
    p_candidates TEXT[] DEFAULT ARRAY[]::TEXT[]
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    DELETE FROM email_preferences WHERE subscriber_id = p_subscriber_id;

    INSERT INTO email_preferences (
        subscriber_id, preference_type, preference_value, city_fips
    )
    SELECT p_subscriber_id, preference_values.preference_type, preference_values.preference_value, '0660620'
    FROM (
        SELECT 'topic'::VARCHAR AS preference_type, unnest(p_topics) AS preference_value
        UNION ALL
        SELECT 'district'::VARCHAR, unnest(p_districts)
        UNION ALL
        SELECT 'candidate'::VARCHAR, unnest(p_candidates)
    ) AS preference_values
    WHERE preference_values.preference_value <> ''
    ON CONFLICT (subscriber_id, preference_type, preference_value) DO NOTHING;
END;
$$;

REVOKE ALL ON FUNCTION claim_email_delivery(UUID, VARCHAR, VARCHAR, VARCHAR, INTEGER, INTEGER)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION complete_email_delivery(UUID, UUID, VARCHAR)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION fail_email_delivery(UUID, UUID, TEXT, BOOLEAN)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION terminalize_retryable_email_delivery(UUID, VARCHAR, TEXT, BOOLEAN)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION replace_email_preferences(UUID, TEXT[], TEXT[], TEXT[])
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION record_subscription_activation_intent()
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION prune_subscription_activations()
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION claim_email_delivery(UUID, VARCHAR, VARCHAR, VARCHAR, INTEGER, INTEGER)
    TO service_role;
GRANT EXECUTE ON FUNCTION complete_email_delivery(UUID, UUID, VARCHAR)
    TO service_role;
GRANT EXECUTE ON FUNCTION fail_email_delivery(UUID, UUID, TEXT, BOOLEAN)
    TO service_role;
GRANT EXECUTE ON FUNCTION terminalize_retryable_email_delivery(UUID, VARCHAR, TEXT, BOOLEAN)
    TO service_role;
GRANT EXECUTE ON FUNCTION replace_email_preferences(UUID, TEXT[], TEXT[], TEXT[])
    TO service_role;
GRANT EXECUTE ON FUNCTION prune_subscription_activations()
    TO service_role;
