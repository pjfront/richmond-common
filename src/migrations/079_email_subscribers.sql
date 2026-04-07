-- Migration 079: Email subscriber list for weekly digest
-- Publication tier: Public (email capture form is public-facing)

CREATE TABLE IF NOT EXISTS email_subscribers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) NOT NULL,
  name VARCHAR(200),
  status VARCHAR(20) NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'unsubscribed')),
  subscribed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  unsubscribed_at TIMESTAMPTZ,
  city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
  source VARCHAR(50) NOT NULL DEFAULT 'website'
    CHECK (source IN ('website', 'manual')),
  metadata JSONB DEFAULT '{}',
  unsubscribe_token UUID NOT NULL DEFAULT gen_random_uuid(),
  CONSTRAINT email_subscribers_email_unique UNIQUE (email)
);

-- Index for lookup by email (upsert) and unsubscribe token
CREATE INDEX IF NOT EXISTS idx_email_subscribers_email
  ON email_subscribers (email);
CREATE INDEX IF NOT EXISTS idx_email_subscribers_token
  ON email_subscribers (unsubscribe_token);
CREATE INDEX IF NOT EXISTS idx_email_subscribers_status
  ON email_subscribers (status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_email_subscribers_fips
  ON email_subscribers (city_fips);

-- RLS: service-role only (no anon access — subscriber PII)
ALTER TABLE email_subscribers ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access on email_subscribers" ON email_subscribers;
CREATE POLICY "Service role full access on email_subscribers"
  ON email_subscribers
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
