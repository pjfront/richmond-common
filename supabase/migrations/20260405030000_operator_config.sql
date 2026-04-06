-- Migration 074: Operator configuration table
-- Stores per-city AI parameter settings tunable via the operator dashboard.
-- Defaults exactly mirror current hardcoded constants — zero behavioral change on deploy.

CREATE TABLE IF NOT EXISTS operator_config (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  city_fips   VARCHAR(7) NOT NULL UNIQUE,

  -- Section 1: What gets published? (tier thresholds + language controls)
  publication JSONB NOT NULL DEFAULT '{
    "tier_high": 0.85,
    "tier_medium": 0.70,
    "tier_low": 0.50,
    "hedge_enabled": true,
    "hedge_text": "Other explanations may exist.",
    "blocklist": [
      "corruption", "corrupt",
      "illegal", "illegally",
      "bribery", "bribe", "kickback",
      "scandal", "scandalous",
      "suspicious", "suspiciously"
    ]
  }',

  -- Section 2: How is evidence weighted? (confidence weights + multipliers)
  evidence    JSONB NOT NULL DEFAULT '{
    "match_strength": 0.35,
    "temporal_factor": 0.25,
    "financial_factor": 0.20,
    "anomaly_factor": 0.20,
    "sitting_mult": 1.0,
    "non_sitting_mult": 0.6,
    "corroboration_2": 1.15,
    "corroboration_3plus": 1.30
  }',

  -- Section 3: Temporal signal bands
  temporal    JSONB NOT NULL DEFAULT '{
    "bands": [
      {"days": 90,  "factor": 1.0},
      {"days": 180, "factor": 0.8},
      {"days": 365, "factor": 0.6},
      {"days": 730, "factor": 0.4}
    ],
    "beyond_factor": 0.2,
    "post_vote_penalty": 0.70,
    "anomaly_boost_days": 30,
    "anomaly_boost_amount": 0.10
  }',

  -- Section 4: Financial materiality bands (ordered highest-min first)
  financial   JSONB NOT NULL DEFAULT '[
    {"min": 5000, "factor": 1.0},
    {"min": 1000, "factor": 0.7},
    {"min": 500,  "factor": 0.5},
    {"min": 100,  "factor": 0.3},
    {"min": 0,    "factor": 0.1}
  ]',

  -- Section 5: Data completeness weights + anomaly detection
  quality     JSONB NOT NULL DEFAULT '{
    "weight_items": 30,
    "weight_votes": 30,
    "weight_attendance": 20,
    "weight_urls": 20,
    "anomaly_stddev": 2.0,
    "min_baselines": 50,
    "default_anomaly": 0.5
  }',

  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by  TEXT NOT NULL DEFAULT 'operator'
);

CREATE INDEX IF NOT EXISTS idx_operator_config_fips ON operator_config(city_fips);

ALTER TABLE operator_config ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS operator_config_service_all ON operator_config;
CREATE POLICY operator_config_service_all
  ON operator_config FOR ALL TO service_role USING (true);

-- Anon read/write for operator dashboard (OperatorGate protects frontend)
DROP POLICY IF EXISTS operator_config_anon_read ON operator_config;
CREATE POLICY operator_config_anon_read
  ON operator_config FOR SELECT TO anon USING (true);

DROP POLICY IF EXISTS operator_config_anon_write ON operator_config;
CREATE POLICY operator_config_anon_write
  ON operator_config FOR UPDATE TO anon USING (true);

-- Seed Richmond with defaults on deploy
INSERT INTO operator_config (city_fips)
VALUES ('0660620')
ON CONFLICT (city_fips) DO NOTHING;
