-- Migration 114: DB-backed form summary cache for paper-filing reconciliation
--
-- Background (T0.3 of plans/steady-crafting-island.md, audit diagnosis
-- 2026-05-16): paper_filing_reconciliation has been silently producing
-- `records_fetched: 0` since 2026-05-16 ~07:00 UTC. ZERO UNI synthetic
-- rows exist in prod for ANY paper filer. Public donor totals are
-- silently $1,030 (Anderson) and other amounts low across ~10 candidates.
--
-- Root cause: the form summary cache lived in `src/data/form_summaries.json`,
-- which is gitignored AND on ephemeral GitHub Actions runners. Each cloud
-- pipeline run started with an EMPTY cache. To rebuild the cache,
-- `discover_and_extract_all_form460_summaries` walks the NetFile RSS feed
-- — but the RSS has a rolling 15-day window. The April 30 semi-annual
-- filing deadline was ~16 days ago, so ALL Form 460s have aged out of
-- RSS. Verified by direct fetch: 49 items in RSS, ZERO 460s.
--
-- Effect: extraction returns nothing → cache stays empty → reconciliation
-- loop iterates over zero filings → records_fetched=0 every run.
-- Idempotent DELETE of UNI rows still runs at the start of reconciliation,
-- so even previously-synthesized UNI rows got wiped and never replaced.
--
-- This migration moves the cache to Postgres. Once populated (via the
-- backfill below + future RSS-discovered additions), it survives across
-- runs and across the RSS window expiry. Loader changes in
-- src/load_paper_filings.py read/write to this table instead of the file.
--
-- The local file remains in place as a debugging artifact (operator's
-- machine had 24 cached summaries that we backfill here), but it is no
-- longer the source of truth.

CREATE TABLE IF NOT EXISTS form_summary_cache (
  filing_id     VARCHAR PRIMARY KEY,
  committee     VARCHAR NOT NULL,
  city_fips     VARCHAR NOT NULL DEFAULT '0660620',
  summary       JSONB   NOT NULL,
  extracted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lookup by committee name (used by reconciliation to map cached
-- entries back to a committee row via name match).
CREATE INDEX IF NOT EXISTS idx_form_summary_cache_committee
  ON form_summary_cache(committee);

-- Lookup by city_fips for any future multi-city introspection.
CREATE INDEX IF NOT EXISTS idx_form_summary_cache_city
  ON form_summary_cache(city_fips);

COMMENT ON TABLE form_summary_cache IS
  'Cached Form 460 cover-page summaries extracted by Anthropic Vision API. '
  'Source of truth for paper_filing_reconciliation. Replaces the file-based '
  'cache at src/data/form_summaries.json which was lost between cloud runs.';

COMMENT ON COLUMN form_summary_cache.summary IS
  'Full JSONB blob from parse_form460_summary_with_vision: '
  'monetary_this_period, loans_this_period, unitemized_this_period, '
  'period_start, period_end, total_cycle_to_date, etc. '
  'Reconciliation reads monetary_this_period and period dates.';

-- RLS: anon role has no business reading these (operator-only).
ALTER TABLE form_summary_cache ENABLE ROW LEVEL SECURITY;

-- Operator/service-role can do everything. No anon policies — RLS denies
-- by default with no matching policies.
DROP POLICY IF EXISTS form_summary_cache_service_all ON form_summary_cache;
CREATE POLICY form_summary_cache_service_all
  ON form_summary_cache
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
