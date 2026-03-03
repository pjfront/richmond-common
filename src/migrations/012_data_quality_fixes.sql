-- Migration 012: Data quality fixes
-- Fixes: Eduardo Martinez duplicate official, Lee stale is_current flag
-- Run in: Supabase SQL Editor (https://supabase.com/dashboard/project/ahrwvmizzykyyfavdvfv/sql/)
-- Idempotent: safe to run multiple times

-- ============================================================
-- 1. INVESTIGATE: Eduardo Martinez duplicate
-- Two records exist:
--   "Eduardo Martinez" (mayor) — canonical record
--   "Martinez, Eduardo" (City/Town Council Member) — duplicate from CivicPlus scraper
-- ============================================================

-- First, inspect both records (run this SELECT to confirm before proceeding):
-- SELECT id, name, normalized_name, role, is_current
-- FROM officials
-- WHERE city_fips = '0660620'
--   AND normalized_name IN ('eduardo martinez', 'martinez, eduardo');

-- Find the keeper (Mayor) and duplicate
DO $$
DECLARE
  v_keeper_id uuid;
  v_dupe_id uuid;
  v_rows_updated int := 0;
BEGIN
  -- Identify keeper: the "Eduardo Martinez" (mayor) record
  SELECT id INTO v_keeper_id
  FROM officials
  WHERE city_fips = '0660620'
    AND name = 'Eduardo Martinez'
    AND role = 'mayor'
  LIMIT 1;

  -- Identify duplicate: the "Martinez, Eduardo" record
  SELECT id INTO v_dupe_id
  FROM officials
  WHERE city_fips = '0660620'
    AND name ILIKE 'Martinez, Eduardo%'
    AND id != COALESCE(v_keeper_id, '00000000-0000-0000-0000-000000000000')
  LIMIT 1;

  IF v_keeper_id IS NULL THEN
    RAISE NOTICE 'No Eduardo Martinez (mayor) record found. Skipping merge.';
    RETURN;
  END IF;

  IF v_dupe_id IS NULL THEN
    RAISE NOTICE 'No duplicate Martinez, Eduardo record found. Already clean.';
    RETURN;
  END IF;

  RAISE NOTICE 'Merging duplicate % into keeper %', v_dupe_id, v_keeper_id;

  -- Re-wire foreign keys from duplicate to keeper
  UPDATE votes SET official_id = v_keeper_id WHERE official_id = v_dupe_id;
  GET DIAGNOSTICS v_rows_updated = ROW_COUNT;
  RAISE NOTICE 'votes: % rows updated', v_rows_updated;

  UPDATE meeting_attendance SET official_id = v_keeper_id WHERE official_id = v_dupe_id;
  GET DIAGNOSTICS v_rows_updated = ROW_COUNT;
  RAISE NOTICE 'meeting_attendance: % rows updated', v_rows_updated;

  UPDATE committees SET official_id = v_keeper_id WHERE official_id = v_dupe_id;
  GET DIAGNOSTICS v_rows_updated = ROW_COUNT;
  RAISE NOTICE 'committees: % rows updated', v_rows_updated;

  UPDATE form700_filings SET official_id = v_keeper_id WHERE official_id = v_dupe_id;
  GET DIAGNOSTICS v_rows_updated = ROW_COUNT;
  RAISE NOTICE 'form700_filings: % rows updated', v_rows_updated;

  UPDATE commission_members SET official_id = v_keeper_id WHERE official_id = v_dupe_id;
  GET DIAGNOSTICS v_rows_updated = ROW_COUNT;
  RAISE NOTICE 'commission_members: % rows updated', v_rows_updated;

  -- Delete the duplicate record
  DELETE FROM officials WHERE id = v_dupe_id;
  RAISE NOTICE 'Deleted duplicate official record %', v_dupe_id;
END $$;

-- ============================================================
-- 2. FIX: Lee (Nat Bates / former member) stale is_current flag
-- Context: A former council member with "Lee" in their name has
-- is_current=true in the DB but is no longer serving.
-- ============================================================

-- Inspect first:
-- SELECT id, name, role, is_current FROM officials
-- WHERE city_fips = '0660620' AND name ILIKE '%Lee%';

-- Known former members who should not be marked current:
UPDATE officials
SET is_current = false
WHERE city_fips = '0660620'
  AND is_current = true
  AND name ILIKE '%Lee%'
  AND role IN ('councilmember', 'council_member', 'City/Town Council Member');

-- ============================================================
-- 3. INVESTIGATE: "City of Richmond" as a campaign donor
-- Government entities sometimes appear in NetFile data.
-- These are typically inter-fund transfers, not campaign donations.
-- The frontend now filters these out, but inspect the source data:
-- ============================================================

-- Inspect "City of Richmond" contributions:
-- SELECT d.name as donor_name, d.employer, c.amount, c.contribution_date,
--        c.source, cm.name as committee_name
-- FROM contributions c
-- JOIN donors d ON c.donor_id = d.id
-- JOIN committees cm ON c.committee_id = cm.id
-- WHERE d.city_fips = '0660620'
--   AND d.name ILIKE '%City of Richmond%'
-- ORDER BY c.amount DESC;
