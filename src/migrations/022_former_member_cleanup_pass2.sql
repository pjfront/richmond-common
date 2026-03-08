-- Migration 022: Former member cleanup pass 2
-- Prerequisite: migration 021 (former_member_cleanup) must have been run
-- Problem: Migration 021 reduced former members from ~95 to ~54, but missed:
--   - Tony Thurmond cross-contaminations (he wasn't in ground truth yet)
--   - "Tony [X]" entries (Tony from Thurmond crossed with other last names)
--   - Last-name-only entries that were ambiguous due to cross-contamination
--   - Accent-variant entries (Boozé, Pimplé) that didn't match normalized forms
--   - Ada Recinos (real member, not yet in ground truth)
-- Solution: Delete cross-contaminations first, then re-run last-name merges.
--   Sequential approach: each step reduces ambiguity for the next.
-- Run in: Supabase SQL Editor (https://supabase.com/dashboard/project/ahrwvmizzykyyfavdvfv/sql/)
-- Idempotent: safe to run multiple times

-- ============================================================
-- HELPER: delete_official_and_refs
-- Deletes an official and all FK references. Used for entries
-- that have no valid merge target (artifacts, non-members).
-- ============================================================

CREATE OR REPLACE FUNCTION delete_official_and_refs(p_official_id uuid)
RETURNS void AS $$
BEGIN
  DELETE FROM votes WHERE official_id = p_official_id;
  DELETE FROM meeting_attendance WHERE official_id = p_official_id;
  DELETE FROM committee_memberships WHERE official_id = p_official_id;
  DELETE FROM form700_filings WHERE official_id = p_official_id;
  DELETE FROM economic_interests WHERE official_id = p_official_id;
  DELETE FROM conflict_flags WHERE official_id = p_official_id;
  DELETE FROM commission_members WHERE official_id = p_official_id;
  DELETE FROM officials WHERE id = p_official_id;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- STEP 1: Tony Thurmond cross-contamination cleanup
-- Tony Thurmond served on council 2005-2008 (real member).
-- His name got cross-contaminated with other members' first names
-- ("[X] Thurmond") and his first name got crossed with other
-- members' last names ("Tony [X]").
-- ============================================================

DO $$
DECLARE
  v_thurmond_id uuid;
  v_dupe record;
  v_deleted int := 0;
BEGIN
  -- Ensure Tony Thurmond exists as a proper entry
  SELECT id INTO v_thurmond_id FROM officials
  WHERE city_fips = '0660620'
    AND normalized_name = 'tony thurmond'
  LIMIT 1;

  IF v_thurmond_id IS NULL THEN
    RAISE NOTICE 'Tony Thurmond not found in officials. Skipping Thurmond cleanup.';
  ELSE
    -- Delete "[X] Thurmond" entries where X is NOT "Tony"
    -- These are cross-contaminations: first name from another member + Thurmond last name
    FOR v_dupe IN
      SELECT id, name, normalized_name FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name LIKE '% thurmond'
        AND normalized_name != 'tony thurmond'
        AND id != v_thurmond_id
    LOOP
      RAISE NOTICE 'Deleting cross-contaminated entry: "%" (not a real person)', v_dupe.name;
      PERFORM delete_official_and_refs(v_dupe.id);
      v_deleted := v_deleted + 1;
    END LOOP;

    -- Merge "Thurmond" (last-name-only) into Tony Thurmond
    FOR v_dupe IN
      SELECT id FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name = 'thurmond'
        AND id != v_thurmond_id
    LOOP
      PERFORM merge_official_pair(v_thurmond_id, v_dupe.id);
      v_deleted := v_deleted + 1;
    END LOOP;
  END IF;

  -- Delete "Tony [X]" entries where X is NOT "Thurmond"
  -- These are cross-contaminations: Tony first name + another member's last name
  FOR v_dupe IN
    SELECT id, name, normalized_name FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name LIKE 'tony %'
      AND normalized_name NOT IN ('tony thurmond')
      AND is_current = false
  LOOP
    RAISE NOTICE 'Deleting cross-contaminated entry: "%" (Tony Thurmond first + other last)', v_dupe.name;
    PERFORM delete_official_and_refs(v_dupe.id);
    v_deleted := v_deleted + 1;
  END LOOP;

  RAISE NOTICE 'Step 1 complete: deleted/merged % Thurmond cross-contaminations.', v_deleted;
END $$;

-- ============================================================
-- STEP 2: Other cross-contamination and artifact cleanup
-- Entries where first name matches one known member and last name
-- matches a different known member, but the combination never
-- existed. Also combined/unknown entries.
-- ============================================================

DO $$
DECLARE
  v_dupe record;
  v_deleted int := 0;
  -- Specific entries to delete (confirmed artifacts via research)
  v_artifacts text[] := ARRAY[
    'nathaniel boozé',    -- Nathaniel (Bates) × Boozé (Corky Booze)
    'nathaniel booze',    -- Same without accent
    'maria t. lopez',     -- Maria T. (Viramontes) × Lopez
    'maria t lopez',      -- Same without period
    'andres marquez',     -- Not a Richmond council member (Cloverdale, CA)
    'rosemary corral lopez',  -- Combined entry artifact
    'lito viramontes',    -- No evidence of council service
    'lark thurmond'       -- Unknown "Lark" × Thurmond (may have been caught by Step 1)
  ];
  v_artifact text;
BEGIN
  FOREACH v_artifact IN ARRAY v_artifacts LOOP
    FOR v_dupe IN
      SELECT id, name, normalized_name FROM officials
      WHERE city_fips = '0660620'
        AND (normalized_name = v_artifact
             OR LOWER(REPLACE(name, '.', '')) = REPLACE(v_artifact, '.', ''))
    LOOP
      RAISE NOTICE 'Deleting artifact entry: "%"', v_dupe.name;
      PERFORM delete_official_and_refs(v_dupe.id);
      v_deleted := v_deleted + 1;
    END LOOP;
  END LOOP;

  RAISE NOTICE 'Step 2 complete: deleted % artifact entries.', v_deleted;
END $$;

-- ============================================================
-- STEP 3: Unknown/unverified entries cleanup
-- Entries with no evidence of council service from Tier 1-2 sources.
-- ============================================================

DO $$
DECLARE
  v_dupe record;
  v_deleted int := 0;
  v_unknowns text[] := ARRAY[
    'belcher'   -- No evidence of any Richmond council member named Belcher
  ];
  v_unknown text;
BEGIN
  FOREACH v_unknown IN ARRAY v_unknowns LOOP
    FOR v_dupe IN
      SELECT id, name FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name = v_unknown
    LOOP
      RAISE NOTICE 'Deleting unverified entry: "%" (no Tier 1-2 evidence of council service)', v_dupe.name;
      PERFORM delete_official_and_refs(v_dupe.id);
      v_deleted := v_deleted + 1;
    END LOOP;
  END LOOP;

  RAISE NOTICE 'Step 3 complete: deleted % unverified entries.', v_deleted;
END $$;

-- ============================================================
-- STEP 4: Accent-variant and alias merges
-- Handle entries with diacritical marks that didn't match
-- normalized forms in previous migrations.
-- ============================================================

DO $$
DECLARE
  v_keeper_id uuid;
  v_dupe_id uuid;
  v_merged int := 0;
BEGIN
  -- Courtland Boozé → merge into Corky Booze or Corky Boozé
  v_keeper_id := NULL;
  SELECT id INTO v_keeper_id FROM officials
  WHERE city_fips = '0660620'
    AND normalized_name IN ('corky booze', 'corky boozé', 'corky booz')
  LIMIT 1;

  IF v_keeper_id IS NOT NULL THEN
    FOR v_dupe_id IN
      SELECT id FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name IN ('courtland boozé', 'courtland booze', 'courtland boozã©')
        AND id != v_keeper_id
    LOOP
      PERFORM merge_official_pair(v_keeper_id, v_dupe_id);
      v_merged := v_merged + 1;
    END LOOP;
  END IF;

  -- Merge "Booze" and "Boozé" last-name-only into Corky
  IF v_keeper_id IS NOT NULL THEN
    FOR v_dupe_id IN
      SELECT id FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name IN ('booze', 'boozé', 'boozã©')
        AND id != v_keeper_id
    LOOP
      PERFORM merge_official_pair(v_keeper_id, v_dupe_id);
      v_merged := v_merged + 1;
    END LOOP;
  END IF;

  -- Vinay Pimplé → merge into Vinay Pimple
  v_keeper_id := NULL;
  SELECT id INTO v_keeper_id FROM officials
  WHERE city_fips = '0660620'
    AND normalized_name IN ('vinay pimple')
  LIMIT 1;

  IF v_keeper_id IS NOT NULL THEN
    FOR v_dupe_id IN
      SELECT id FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name IN ('vinay pimplé', 'vinay pimplã©')
        AND id != v_keeper_id
    LOOP
      PERFORM merge_official_pair(v_keeper_id, v_dupe_id);
      v_merged := v_merged + 1;
    END LOOP;
  ELSE
    -- If Vinay Pimple doesn't exist but Pimplé does, rename
    SELECT id INTO v_keeper_id FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name IN ('vinay pimplé', 'vinay pimplã©')
    LIMIT 1;
    IF v_keeper_id IS NOT NULL THEN
      UPDATE officials SET
        name = 'Vinay Pimple',
        normalized_name = 'vinay pimple'
      WHERE id = v_keeper_id;
      RAISE NOTICE 'Renamed Vinay Pimplé → Vinay Pimple';
      v_merged := v_merged + 1;
    END IF;
  END IF;

  RAISE NOTICE 'Step 4 complete: merged/renamed % accent-variant entries.', v_merged;
END $$;

-- ============================================================
-- STEP 5: Fragment merges
-- Multi-word fragments that should merge into full entries.
-- ============================================================

DO $$
DECLARE
  v_keeper_id uuid;
  v_dupe_id uuid;
  v_merged int := 0;
BEGIN
  -- "Johnson III" → merge into "Demnlus Johnson III"
  SELECT id INTO v_keeper_id FROM officials
  WHERE city_fips = '0660620'
    AND normalized_name = 'demnlus johnson iii'
  LIMIT 1;

  IF v_keeper_id IS NOT NULL THEN
    FOR v_dupe_id IN
      SELECT id FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name = 'johnson iii'
        AND id != v_keeper_id
    LOOP
      PERFORM merge_official_pair(v_keeper_id, v_dupe_id);
      v_merged := v_merged + 1;
    END LOOP;
  END IF;

  RAISE NOTICE 'Step 5 complete: merged % fragment entries.', v_merged;
END $$;

-- ============================================================
-- STEP 6: Re-run last-name-only merges
-- Now that cross-contaminated entries are removed, ambiguities
-- should resolve. Same logic as migration 021 Step 2.
-- ============================================================

DO $$
DECLARE
  v_dupe record;
  v_canonical_id uuid;
  v_match_count int;
  v_merged int := 0;
  v_skipped int := 0;
BEGIN
  FOR v_dupe IN
    SELECT id, name, normalized_name FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name NOT LIKE '% %'  -- single-word names only
      AND normalized_name != ''
  LOOP
    -- Find officials whose last name matches this single-word entry
    SELECT COUNT(*) INTO v_match_count FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name LIKE '% %'  -- must be multi-word (full name)
      AND SPLIT_PART(normalized_name, ' ', -1) = v_dupe.normalized_name
      AND id != v_dupe.id;

    IF v_match_count = 1 THEN
      SELECT id INTO v_canonical_id FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name LIKE '% %'
        AND SPLIT_PART(normalized_name, ' ', -1) = v_dupe.normalized_name
        AND id != v_dupe.id
      LIMIT 1;

      PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      v_merged := v_merged + 1;
    ELSIF v_match_count = 0 THEN
      RAISE NOTICE 'No full-name match for last-name-only "%". Left as-is.', v_dupe.name;
      v_skipped := v_skipped + 1;
    ELSE
      RAISE NOTICE 'Multiple matches (%) for last-name-only "%". Left as-is.', v_match_count, v_dupe.name;
      v_skipped := v_skipped + 1;
    END IF;
  END LOOP;

  RAISE NOTICE 'Step 6 complete: merged %, skipped % (no match or ambiguous).', v_merged, v_skipped;
END $$;

-- ============================================================
-- STEP 7: Ensure Gary Bell has full name
-- Gary Bell may only exist as "Bell" (last-name-only) if his
-- full name was never parsed from minutes. If so, rename.
-- ============================================================

DO $$
DECLARE
  v_full_id uuid;
  v_last_only_id uuid;
BEGIN
  -- Check if "Gary Bell" exists
  SELECT id INTO v_full_id FROM officials
  WHERE city_fips = '0660620'
    AND normalized_name = 'gary bell'
  LIMIT 1;

  -- Check if "Bell" (last-name-only) still exists
  SELECT id INTO v_last_only_id FROM officials
  WHERE city_fips = '0660620'
    AND normalized_name = 'bell'
  LIMIT 1;

  IF v_full_id IS NOT NULL AND v_last_only_id IS NOT NULL THEN
    -- Both exist: merge Bell into Gary Bell
    PERFORM merge_official_pair(v_full_id, v_last_only_id);
    RAISE NOTICE 'Merged "Bell" into "Gary Bell"';
  ELSIF v_full_id IS NULL AND v_last_only_id IS NOT NULL THEN
    -- Only "Bell" exists: rename to Gary Bell
    UPDATE officials SET
      name = 'Gary Bell',
      normalized_name = 'gary bell'
    WHERE id = v_last_only_id;
    RAISE NOTICE 'Renamed "Bell" → "Gary Bell"';
  ELSE
    RAISE NOTICE 'Gary Bell already resolved (full name exists, no orphan "Bell" entry).';
  END IF;
END $$;

-- ============================================================
-- STEP 8: Cleanup helper function
-- Drop the helper function created in this migration.
-- merge_official_pair from migration 020 is kept.
-- ============================================================

DROP FUNCTION IF EXISTS delete_official_and_refs(uuid);

-- ============================================================
-- STEP 9: VERIFICATION QUERIES (run after migration)
-- ============================================================

-- Remaining former members (should be ~22):
-- SELECT name, normalized_name,
--   (SELECT COUNT(*) FROM votes WHERE official_id = o.id) AS vote_count,
--   (SELECT COUNT(*) FROM meeting_attendance WHERE official_id = o.id) AS attendance_count
-- FROM officials o
-- WHERE city_fips = '0660620' AND is_current = false
-- ORDER BY name;

-- Current council (should still be 7):
-- SELECT name, role, district FROM officials
-- WHERE city_fips = '0660620' AND is_current = true
-- ORDER BY name;

-- Any remaining single-word entries?
-- SELECT name, normalized_name FROM officials
-- WHERE city_fips = '0660620'
--   AND normalized_name NOT LIKE '% %'
--   AND normalized_name != '';

-- Any remaining accent variants?
-- SELECT name, normalized_name FROM officials
-- WHERE city_fips = '0660620'
--   AND (name LIKE '%é%' OR name LIKE '%ã%' OR name LIKE '%ñ%');
