-- Migration 080: Email subscription preferences (topics, districts, candidates)
-- Extends S21.5.5 email_subscribers with per-subscriber follow preferences.
-- Separate table (not JSONB) for efficient batch digest queries in S23.

CREATE TABLE IF NOT EXISTS email_preferences (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  subscriber_id UUID NOT NULL
    REFERENCES email_subscribers(id) ON DELETE CASCADE,
  preference_type VARCHAR(20) NOT NULL
    CHECK (preference_type IN ('topic', 'district', 'candidate')),
  preference_value VARCHAR(100) NOT NULL,
  city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT email_preferences_unique
    UNIQUE (subscriber_id, preference_type, preference_value)
);

-- Batch digest: "all subscribers who follow topic X"
CREATE INDEX IF NOT EXISTS idx_email_preferences_type_value
  ON email_preferences (preference_type, preference_value);

-- Load one subscriber's preferences
CREATE INDEX IF NOT EXISTS idx_email_preferences_subscriber
  ON email_preferences (subscriber_id);

-- FIPS convention
CREATE INDEX IF NOT EXISTS idx_email_preferences_fips
  ON email_preferences (city_fips);

-- RLS: service-role only (subscriber PII adjacent)
ALTER TABLE email_preferences ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Service role full access on email_preferences" ON email_preferences;
CREATE POLICY "Service role full access on email_preferences"
  ON email_preferences
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
