-- Migration 122: S28.1 — repair Form 700 filer→official matching + D1 quartet.
--
-- Context: docs/specs/interest-profiles-spec.md (S28.1). The NetFile SEI portal
-- lists filers as "Last, First"; load_form700_to_db passed that form straight to
-- ensure_official(), which missed every canonical official and auto-created a
-- duplicate officials row per filer (101 filings attached to comma-name
-- duplicates as of 2026-07-05). The code fix flips the name before matching
-- (src/db/form700.py::_flip_comma_name); this migration repairs existing rows:
--
--   A. Re-point filings (and their interests) to an existing canonical official
--      when the flipped filer name matches one exactly.
--   B. Rename the remaining auto-created comma-form officials rows in place
--      ("Chak, Chung Ho" → "Chung Ho Chak") so future syncs and public surfaces
--      (e.g. search) see display-order names. Guarded: only is_current = FALSE
--      rows with exactly one comma, and only when no other official already has
--      the flipped normalized name (those stay as-is; re-point in A covers their
--      filings, and the now-orphaned duplicates are noted in AI-PARKING-LOT).
--   C. Add the D1 provenance quartet to form700_filings (source_tier,
--      confidence_score, extracted_at + source_url NOT NULL). Required because
--      S28.1 adds the first direct web query against this table and new
--      d1-provenance-manifest entries must ship compliant. confidence_score
--      backfills from metadata->>'extraction_confidence'; 0/unreported becomes
--      0.5 ("extractor did not report") — both sit below the D2 0.90
--      summary-display threshold, so display behavior is identical.
--
-- Idempotent: re-running matches no rows / no-ops on existing columns.

SET search_path TO public, extensions;

-- ── A. Re-point filings + interests to canonical officials ─────────────────

DO $$
DECLARE n BIGINT;
BEGIN
  UPDATE form700_filings f
  SET official_id = o2.id
  FROM officials dup, officials o2
  WHERE f.official_id = dup.id
    AND dup.id != o2.id
    AND dup.name LIKE '%,%'
    AND o2.city_fips = f.city_fips
    AND o2.name NOT LIKE '%,%'
    AND o2.normalized_name = lower(trim(regexp_replace(
          regexp_replace(f.filer_name, '^\s*([^,]+)\s*,\s*(.+)$', '\2 \1'),
          '\s+', ' ', 'g')));
  GET DIAGNOSTICS n = ROW_COUNT;
  RAISE NOTICE 'S28.1-A: re-pointed % filings to canonical officials', n;

  UPDATE economic_interests ei
  SET official_id = f.official_id
  FROM form700_filings f
  WHERE ei.filing_id = f.id
    AND ei.official_id IS DISTINCT FROM f.official_id;
  GET DIAGNOSTICS n = ROW_COUNT;
  RAISE NOTICE 'S28.1-A: re-pointed % economic_interests rows', n;
END $$;

-- ── B. Rename remaining comma-form auto-created officials ──────────────────

DO $$
DECLARE n BIGINT;
BEGIN
  UPDATE officials o
  SET name = trim(regexp_replace(o.name, '^\s*([^,]+)\s*,\s*(.+)$', '\2 \1')),
      normalized_name = lower(trim(regexp_replace(
        regexp_replace(o.name, '^\s*([^,]+)\s*,\s*(.+)$', '\2 \1'),
        '\s+', ' ', 'g')))
  WHERE o.name ~ '^[^,]+,[^,]+$'
    AND o.is_current = FALSE
    AND NOT EXISTS (
      SELECT 1 FROM officials t
      WHERE t.city_fips = o.city_fips
        AND t.id != o.id
        AND t.normalized_name = lower(trim(regexp_replace(
              regexp_replace(o.name, '^\s*([^,]+)\s*,\s*(.+)$', '\2 \1'),
              '\s+', ' ', 'g')))
    );
  GET DIAGNOSTICS n = ROW_COUNT;
  RAISE NOTICE 'S28.1-B: renamed % comma-form officials rows to display order', n;
END $$;

-- ── C. D1 provenance quartet on form700_filings ─────────────────────────────

ALTER TABLE form700_filings ADD COLUMN IF NOT EXISTS source_tier SMALLINT NOT NULL DEFAULT 1;
ALTER TABLE form700_filings ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(3,2);
ALTER TABLE form700_filings ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ;

UPDATE form700_filings
SET confidence_score = CASE
      WHEN COALESCE(NULLIF(metadata->>'extraction_confidence', ''), '0')::numeric > 0
        THEN LEAST(1.0, (metadata->>'extraction_confidence')::numeric)
      ELSE 0.5
    END
WHERE confidence_score IS NULL;

UPDATE form700_filings SET extracted_at = created_at WHERE extracted_at IS NULL;

UPDATE form700_filings
SET source_url = 'https://public.netfile.com/pub/?AID=RICH'
WHERE source_url IS NULL OR source_url = '';

ALTER TABLE form700_filings ALTER COLUMN confidence_score SET NOT NULL;
ALTER TABLE form700_filings ALTER COLUMN confidence_score SET DEFAULT 0.5;
ALTER TABLE form700_filings ALTER COLUMN extracted_at SET NOT NULL;
ALTER TABLE form700_filings ALTER COLUMN extracted_at SET DEFAULT NOW();
ALTER TABLE form700_filings ALTER COLUMN source_url SET NOT NULL;
