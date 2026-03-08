-- Migration 020: Official deduplication and is_current correction
-- Problem: Historical data loaded many name variants as separate officials
--   (e.g., "Tom Butt", "Thomas K. Butt", "Mayor Tom Butt" are all separate records)
--   and all officials have is_current=TRUE regardless of when they served.
-- Solution:
--   1. Create reusable merge function
--   2. Merge known duplicate clusters based on name patterns
--   3. Set is_current=FALSE for all non-current council members
-- Run in: Supabase SQL Editor (https://supabase.com/dashboard/project/ahrwvmizzykyyfavdvfv/sql/)
-- Idempotent: safe to run multiple times

-- ============================================================
-- STEP 0: AUDIT QUERY (run this first to see the mess)
-- Uncomment and run to inspect before applying fixes.
-- ============================================================

-- SELECT name, normalized_name, role, is_current, id,
--   (SELECT COUNT(*) FROM votes WHERE official_id = o.id) AS vote_count,
--   (SELECT COUNT(*) FROM meeting_attendance WHERE official_id = o.id) AS attendance_count
-- FROM officials o
-- WHERE city_fips = '0660620'
-- ORDER BY normalized_name, name;

-- ============================================================
-- STEP 1: Reusable merge function
-- Moves all FK references from dupe to keeper, handles unique
-- constraint conflicts, then deletes the dupe.
-- ============================================================

CREATE OR REPLACE FUNCTION merge_official_pair(
  p_keeper_id uuid,
  p_dupe_id uuid
) RETURNS void AS $$
DECLARE
  v_rows int;
  v_keeper_name text;
  v_dupe_name text;
BEGIN
  -- Look up names for logging
  SELECT name INTO v_keeper_name FROM officials WHERE id = p_keeper_id;
  SELECT name INTO v_dupe_name FROM officials WHERE id = p_dupe_id;

  IF v_keeper_name IS NULL OR v_dupe_name IS NULL THEN
    RAISE NOTICE 'merge_official_pair: one or both IDs not found (keeper=%, dupe=%). Skipping.', p_keeper_id, p_dupe_id;
    RETURN;
  END IF;

  RAISE NOTICE 'Merging "%" (%) into "%" (%)', v_dupe_name, p_dupe_id, v_keeper_name, p_keeper_id;

  -- votes: no unique constraint on (motion_id, official_id), safe to update all
  UPDATE votes SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  votes: % rows rewired', v_rows; END IF;

  -- meeting_attendance: has UNIQUE (meeting_id, official_id)
  -- Delete dupe attendance where keeper already has a record for that meeting
  DELETE FROM meeting_attendance
  WHERE official_id = p_dupe_id
    AND meeting_id IN (
      SELECT meeting_id FROM meeting_attendance WHERE official_id = p_keeper_id
    );
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  meeting_attendance: % duplicate records removed', v_rows; END IF;

  -- Update remaining (non-conflicting) attendance records
  UPDATE meeting_attendance SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  meeting_attendance: % rows rewired', v_rows; END IF;

  -- committees
  UPDATE committees SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  committees: % rows rewired', v_rows; END IF;

  -- form700_filings
  UPDATE form700_filings SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  form700_filings: % rows rewired', v_rows; END IF;

  -- economic_interests
  UPDATE economic_interests SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  economic_interests: % rows rewired', v_rows; END IF;

  -- conflict_flags
  UPDATE conflict_flags SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  conflict_flags: % rows rewired', v_rows; END IF;

  -- commission_members (appointed_by_official_id)
  UPDATE commission_members SET appointed_by_official_id = p_keeper_id
  WHERE appointed_by_official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  commission_members: % rows rewired', v_rows; END IF;

  -- Delete the duplicate official record
  DELETE FROM officials WHERE id = p_dupe_id;
  RAISE NOTICE '  Deleted duplicate official "%"', v_dupe_name;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- STEP 2: Merge known duplicate clusters
-- For each alias group, find the canonical record and merge
-- all variants into it. Uses normalized_name for matching.
-- ============================================================

DO $$
DECLARE
  v_canonical_id uuid;
  v_dupe record;
  v_alias text;
  v_aliases text[];
  v_canonical_name text;
BEGIN
  -- ── Tom Butt ──
  -- Legal name: Thomas K. Butt. Goes by Tom Butt publicly.
  v_canonical_name := 'tom butt';
  v_aliases := ARRAY['thomas k. butt', 'thomas butt', 'thomas k butt',
                      'mayor butt', 'mayor tom butt', 't. butt', 't butt',
                      't. k. butt', 't k butt'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;

  IF v_canonical_id IS NOT NULL THEN
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END LOOP;
  ELSE
    -- If "Tom Butt" doesn't exist but "Thomas K. Butt" does, use that as canonical
    SELECT id INTO v_canonical_id FROM officials
    WHERE city_fips = '0660620' AND normalized_name = 'thomas k. butt' LIMIT 1;
    IF v_canonical_id IS NOT NULL THEN
      -- Rename to canonical display name
      UPDATE officials SET name = 'Tom Butt', normalized_name = 'tom butt'
      WHERE id = v_canonical_id;
      FOREACH v_alias IN ARRAY v_aliases LOOP
        IF v_alias != 'thomas k. butt' THEN
          FOR v_dupe IN
            SELECT id FROM officials
            WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
          LOOP
            PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
          END LOOP;
        END IF;
      END LOOP;
    END IF;
  END IF;

  -- ── Nat Bates ──
  v_canonical_name := 'nat bates';
  v_aliases := ARRAY['nathaniel bates', 'nathaniel s. bates', 'nathaniel s bates'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;
  IF v_canonical_id IS NOT NULL THEN
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END FOREACH;
  END IF;

  -- ── Gayle McLaughlin ──
  v_canonical_name := 'gayle mclaughlin';
  v_aliases := ARRAY['mayor mclaughlin', 'mayor gayle mclaughlin',
                      'gayle s. mclaughlin', 'gayle s mclaughlin'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;
  IF v_canonical_id IS NOT NULL THEN
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END FOREACH;
  END IF;

  -- ── Eduardo Martinez ──
  v_canonical_name := 'eduardo martinez';
  v_aliases := ARRAY['martinez, eduardo', 'mayor martinez', 'mayor eduardo martinez'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;
  IF v_canonical_id IS NOT NULL THEN
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END FOREACH;
  END IF;

  -- ── Jovanka Beckles ──
  v_canonical_name := 'jovanka beckles';
  v_aliases := ARRAY['jovanka beckles-rivera'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;
  IF v_canonical_id IS NOT NULL THEN
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END FOREACH;
  END IF;

  -- ── Jim Rogers ──
  v_canonical_name := 'jim rogers';
  v_aliases := ARRAY['james rogers', 'james f. rogers', 'james f rogers'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;
  IF v_canonical_id IS NOT NULL THEN
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END FOREACH;
  END IF;

  -- ── Ben Choi ──
  v_canonical_name := 'ben choi';
  v_aliases := ARRAY['benjamin choi'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;
  IF v_canonical_id IS NOT NULL THEN
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END FOREACH;
  END IF;

  -- ── Corky Booze ──
  v_canonical_name := 'corky booze';
  v_aliases := ARRAY['corky boozé'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;
  IF v_canonical_id IS NOT NULL THEN
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END FOREACH;
  END IF;

  -- ── Jamelia Brown ──
  v_canonical_name := 'jamelia brown';
  v_aliases := ARRAY['jameila brown', 'jamalia brown'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;
  IF v_canonical_id IS NOT NULL THEN
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END FOREACH;
  END IF;

  RAISE NOTICE 'Alias-based merges complete.';
END $$;

-- ============================================================
-- STEP 3: Catch remaining title-prefixed duplicates
-- Handles "Vice Mayor Zepeda" -> "Cesar Zepeda" etc. by
-- stripping common title prefixes and matching against known officials.
-- ============================================================

DO $$
DECLARE
  v_dupe record;
  v_stripped text;
  v_canonical_id uuid;
BEGIN
  -- Find officials whose name starts with a title prefix
  FOR v_dupe IN
    SELECT id, name, normalized_name FROM officials
    WHERE city_fips = '0660620'
      AND (
        normalized_name LIKE 'mayor %'
        OR normalized_name LIKE 'vice mayor %'
        OR normalized_name LIKE 'councilmember %'
        OR normalized_name LIKE 'council member %'
        OR normalized_name LIKE 'president %'
        OR normalized_name LIKE 'vice president %'
      )
  LOOP
    -- Strip the title prefix
    v_stripped := regexp_replace(v_dupe.normalized_name,
      '^(mayor|vice mayor|councilmember|council member|president|vice president)\s+', '');

    -- Find a matching canonical official (without title prefix)
    SELECT id INTO v_canonical_id FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name = v_stripped
      AND id != v_dupe.id
    LIMIT 1;

    IF v_canonical_id IS NOT NULL THEN
      PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
    END IF;
  END LOOP;

  RAISE NOTICE 'Title-prefix dedup complete.';
END $$;

-- ============================================================
-- STEP 4: Set is_current = FALSE for non-current members
-- Uses ground truth: the 7 current council members are the ONLY
-- officials who should be is_current = TRUE.
-- ============================================================

-- First, set ALL officials to is_current = FALSE
UPDATE officials
SET is_current = false
WHERE city_fips = '0660620'
  AND is_current = true;

-- Then set only the 7 current council members back to TRUE
UPDATE officials
SET is_current = true
WHERE city_fips = '0660620'
  AND normalized_name IN (
    'eduardo martinez',
    'cesar zepeda',
    'jamelia brown',
    'doria robinson',
    'soheila bana',
    'sue wilson',
    'claudia jimenez'
  );

-- Also mark current city leadership as current
UPDATE officials
SET is_current = true
WHERE city_fips = '0660620'
  AND normalized_name IN (
    'shasa curl',
    'shannon moore',
    'pamela christian'
  );

-- ============================================================
-- STEP 5: Update roles for current officials to best-known role
-- Some may have been created as 'councilmember' when they're
-- actually mayor or vice mayor.
-- ============================================================

UPDATE officials SET role = 'mayor'
WHERE city_fips = '0660620' AND normalized_name = 'eduardo martinez' AND is_current = true;

UPDATE officials SET role = 'vice_mayor'
WHERE city_fips = '0660620' AND normalized_name = 'cesar zepeda' AND is_current = true;

UPDATE officials SET role = 'councilmember'
WHERE city_fips = '0660620'
  AND normalized_name IN ('jamelia brown', 'doria robinson', 'soheila bana', 'sue wilson', 'claudia jimenez')
  AND is_current = true;

-- ============================================================
-- STEP 6: Verification queries (run to confirm results)
-- ============================================================

-- Current officials (should be exactly 7 council + a few leadership):
-- SELECT name, role, is_current FROM officials
-- WHERE city_fips = '0660620' AND is_current = true
-- ORDER BY role, name;

-- Former officials (should be clean, no duplicates):
-- SELECT name, role, is_current,
--   (SELECT COUNT(*) FROM votes WHERE official_id = o.id) AS votes,
--   (SELECT COUNT(*) FROM meeting_attendance WHERE official_id = o.id) AS attendance
-- FROM officials o
-- WHERE city_fips = '0660620' AND is_current = false
-- ORDER BY name;

-- Check for any remaining potential duplicates (last-name-only check):
-- SELECT SPLIT_PART(normalized_name, ' ', -1) AS last_name,
--   ARRAY_AGG(name ORDER BY name) AS names,
--   COUNT(*) AS count
-- FROM officials
-- WHERE city_fips = '0660620'
-- GROUP BY SPLIT_PART(normalized_name, ' ', -1)
-- HAVING COUNT(*) > 1
-- ORDER BY count DESC;

-- Clean up the merge function (optional, keep if you want to merge more later)
-- DROP FUNCTION IF EXISTS merge_official_pair(uuid, uuid);
