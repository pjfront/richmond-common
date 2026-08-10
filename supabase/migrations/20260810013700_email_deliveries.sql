-- Durable, per-recipient delivery state for subscriber email.
--
-- Meeting-level *_emailed_at columns cannot distinguish successful recipients
-- from partial failures. This private ledger is the idempotency authority for
-- welcome, orientation, recap, and weekly-digest delivery.

CREATE TABLE IF NOT EXISTS email_deliveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subscriber_id UUID NOT NULL
        REFERENCES email_subscribers(id) ON DELETE CASCADE,
    city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
    delivery_kind VARCHAR(20) NOT NULL
        CHECK (delivery_kind IN ('welcome', 'orientation', 'recap', 'digest')),
    content_key VARCHAR(160) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sending', 'sent', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    claim_token UUID,
    lease_expires_at TIMESTAMPTZ,
    provider_message_id VARCHAR(255),
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    CONSTRAINT email_deliveries_recipient_content_unique
        UNIQUE (subscriber_id, delivery_kind, content_key)
);

CREATE INDEX IF NOT EXISTS idx_email_deliveries_retryable
    ON email_deliveries (status, lease_expires_at, updated_at)
    WHERE status IN ('pending', 'sending', 'failed');

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

-- Create the unique row if needed, then atomically lease it. A concurrent
-- caller cannot obtain the same row while its lease is live. Expired leases
-- are retryable with the same provider idempotency key.
CREATE OR REPLACE FUNCTION claim_email_delivery(
    p_subscriber_id UUID,
    p_delivery_kind VARCHAR,
    p_content_key VARCHAR,
    p_lease_minutes INTEGER DEFAULT 15
)
RETURNS TABLE(delivery_id UUID, delivery_claim_token UUID, delivery_attempt INTEGER)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO email_deliveries (
        subscriber_id, delivery_kind, content_key
    ) VALUES (
        p_subscriber_id, p_delivery_kind, p_content_key
    )
    ON CONFLICT (subscriber_id, delivery_kind, content_key) DO NOTHING;

    RETURN QUERY
    UPDATE email_deliveries AS d
    SET status = 'sending',
        attempt_count = d.attempt_count + 1,
        claim_token = gen_random_uuid(),
        lease_expires_at = NOW()
            + make_interval(mins => GREATEST(1, LEAST(p_lease_minutes, 60))),
        last_error = NULL,
        updated_at = NOW()
    WHERE d.subscriber_id = p_subscriber_id
      AND d.delivery_kind = p_delivery_kind
      AND d.content_key = p_content_key
      AND (
          d.status IN ('pending', 'failed')
          OR (d.status = 'sending' AND d.lease_expires_at <= NOW())
      )
    RETURNING d.id, d.claim_token, d.attempt_count;
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
            claim_token = NULL,
            last_error = NULL,
            updated_at = NOW()
        WHERE id = p_delivery_id
          AND status = 'sending'
          AND claim_token = p_claim_token
        RETURNING 1
    )
    SELECT EXISTS (SELECT 1 FROM completed);
$$;

CREATE OR REPLACE FUNCTION fail_email_delivery(
    p_delivery_id UUID,
    p_claim_token UUID,
    p_error TEXT
)
RETURNS BOOLEAN
LANGUAGE sql
SECURITY DEFINER
SET search_path = public
AS $$
    WITH failed AS (
        UPDATE email_deliveries
        SET status = 'failed',
            lease_expires_at = NULL,
            claim_token = NULL,
            last_error = LEFT(COALESCE(p_error, 'Unknown email delivery failure'), 2000),
            updated_at = NOW()
        WHERE id = p_delivery_id
          AND status = 'sending'
          AND claim_token = p_claim_token
        RETURNING 1
    )
    SELECT EXISTS (SELECT 1 FROM failed);
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

REVOKE ALL ON FUNCTION claim_email_delivery(UUID, VARCHAR, VARCHAR, INTEGER)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION complete_email_delivery(UUID, UUID, VARCHAR)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION fail_email_delivery(UUID, UUID, TEXT)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION replace_email_preferences(UUID, TEXT[], TEXT[], TEXT[])
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION claim_email_delivery(UUID, VARCHAR, VARCHAR, INTEGER)
    TO service_role;
GRANT EXECUTE ON FUNCTION complete_email_delivery(UUID, UUID, VARCHAR)
    TO service_role;
GRANT EXECUTE ON FUNCTION fail_email_delivery(UUID, UUID, TEXT)
    TO service_role;
GRANT EXECUTE ON FUNCTION replace_email_preferences(UUID, TEXT[], TEXT[], TEXT[])
    TO service_role;
