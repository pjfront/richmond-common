-- Migration 021: Former member cleanup based on historical research
-- Prerequisite: migration 020 (merge_official_pair function must exist in database)
-- Problem: After migration 020 fixed current council and merged known aliases,
--   ~95 former member entries remain with extraction artifacts:
--   - Last-name-only entries ("Bates", "Butt") from roll call parsing
--   - Compound title prefixes ("Councilmember/Boardmember Bates")
--   - Cross-contaminated names ("Jim Butt" = Jim Rogers first + Tom Butt last)
--   - Combined entries ("Beckles, Myrick, and Rogers")
--   - People who never served on council (candidates who lost elections)
-- Solution: Programmatic cleanup using structural signals + confirmed research.
--   Conservative approach: only clean entries with clear structural markers.
--   Ambiguous entries are left for manual investigation.
-- Run in: Supabase SQL Editor (https://supabase.com/dashboard/project/ahrwvmizzykyyfavdvfv/sql/)
-- Idempotent: safe to run multiple times

-- ============================================================
-- STEP 0: AUDIT QUERY (run first to see current state)
-- ============================================================

-- SELECT name, normalized_name, role, is_current,
--   (SELECT COUNT(*) FROM votes WHERE official_id = o.id) AS vote_count,
--   (SELECT COUNT(*) FROM meeting_attendance WHERE official_id = o.id) AS attendance_count,
--   LENGTH(normalized_name) - LENGTH(REPLACE(normalized_name, ' ', '')) AS word_count
-- FROM officials o
-- WHERE city_fips = '0660620' AND is_current = false
-- ORDER BY word_count, normalized_name;

-- ============================================================
-- STEP 1: Compound title prefix cleanup
-- Migration 020's Step 3 handled simple prefixes (mayor, vice mayor, etc.)
-- but missed compound variants like "Councilmember/Boardmember".
-- ============================================================

DO $$
DECLARE
  v_dupe record;
  v_stripped text;
  v_canonical_id uuid;
BEGIN
  FOR v_dupe IN
    SELECT id, name, normalized_name FROM officials
    WHERE city_fips = '0660620'
      AND (
        normalized_name LIKE 'councilmember/boardmember %'
        OR normalized_name LIKE 'mayor/chairperson %'
        OR normalized_name LIKE 'vice mayor/vice chairperson %'
        OR normalized_name LIKE 'chair %'
        OR normalized_name LIKE 'chairperson %'
      )
  LOOP
    -- Strip the compound title prefix
    v_stripped := regexp_replace(v_dupe.normalized_name,
      '^(councilmember/boardmember|mayor/chairperson|vice mayor/vice chairperson|chairperson|chair)\s+', '');

    -- Find a matching official without the prefix
    SELECT id INTO v_canonical_id FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name = v_stripped
      AND id != v_dupe.id
    LIMIT 1;

    IF v_canonical_id IS NOT NULL THEN
      PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
    ELSE
      RAISE NOTICE 'No match for compound-title entry "%". Left as-is.', v_dupe.name;
    END IF;
  END LOOP;

  RAISE NOTICE 'Step 1 (compound title cleanup) complete.';
END $$;

-- ============================================================
-- STEP 2: Last-name-only merges
-- Entries like "Bates", "Butt" etc. are extraction artifacts where
-- the minutes parser captured only the last name from roll call text.
-- Merge into the matching full-name official.
-- Safety: only merge single-word entries (no spaces in normalized_name).
-- ============================================================

DO $$
DECLARE
  v_dupe record;
  v_canonical_id uuid;
  v_match_count int;
BEGIN
  FOR v_dupe IN
    SELECT id, name, normalized_name FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name NOT LIKE '% %'  -- single-word names only
      AND normalized_name != ''
  LOOP
    -- Find officials whose last name matches this single-word entry
    -- Uses SPLIT_PART to get the last word of multi-word names
    SELECT COUNT(*) INTO v_match_count FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name LIKE '% %'  -- must be multi-word (full name)
      AND SPLIT_PART(normalized_name, ' ', -1) = v_dupe.normalized_name
      AND id != v_dupe.id;

    IF v_match_count = 1 THEN
      -- Exactly one full-name official matches: safe to merge
      SELECT id INTO v_canonical_id FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name LIKE '% %'
        AND SPLIT_PART(normalized_name, ' ', -1) = v_dupe.normalized_name
        AND id != v_dupe.id
      LIMIT 1;

      PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
    ELSIF v_match_count = 0 THEN
      RAISE NOTICE 'No full-name match for last-name-only "%". Left as-is.', v_dupe.name;
    ELSE
      RAISE NOTICE 'Multiple matches (%) for last-name-only "%". Left as-is (ambiguous).', v_match_count, v_dupe.name;
    END IF;
  END LOOP;

  RAISE NOTICE 'Step 2 (last-name-only merges) complete.';
END $$;

-- ============================================================
-- STEP 3: Cross-contaminated name cleanup
-- Extraction errors created entries like "Jim Butt" (Jim Rogers'
-- first name + Tom Butt's last name). These are structurally
-- impossible: no real person has this combination.
-- Strategy: build list of known council member first/last names,
-- then find entries where first name matches one member and last
-- name matches a DIFFERENT member. Merge into the last-name match
-- (the last name is the more reliable signal from roll call parsing).
-- ============================================================

DO $$
DECLARE
  v_known_members text[][] := ARRAY[
    -- [first_name_part, last_name_part, full_normalized_name]
    -- Current council
    ARRAY['eduardo', 'martinez', 'eduardo martinez'],
    ARRAY['cesar', 'zepeda', 'cesar zepeda'],
    ARRAY['jamelia', 'brown', 'jamelia brown'],
    ARRAY['doria', 'robinson', 'doria robinson'],
    ARRAY['soheila', 'bana', 'soheila bana'],
    ARRAY['sue', 'wilson', 'sue wilson'],
    ARRAY['claudia', 'jimenez', 'claudia jimenez'],
    -- Former council (confirmed by Tier 1-2 research)
    ARRAY['tom', 'butt', 'tom butt'],
    ARRAY['nat', 'bates', 'nat bates'],
    ARRAY['gayle', 'mclaughlin', 'gayle mclaughlin'],
    ARRAY['irma', 'anderson', 'irma anderson'],
    ARRAY['jovanka', 'beckles', 'jovanka beckles'],
    ARRAY['jael', 'myrick', 'jael myrick'],
    ARRAY['melvin', 'willis', 'melvin willis'],
    ARRAY['ben', 'choi', 'ben choi'],
    ARRAY['demnlus', 'johnson', 'demnlus johnson iii'],
    ARRAY['vinay', 'pimple', 'vinay pimple'],
    ARRAY['corky', 'booze', 'corky booze'],
    ARRAY['jim', 'rogers', 'jim rogers'],
    ARRAY['jeff', 'ritterman', 'jeff ritterman'],
    ARRAY['harpreet', 'sandhu', 'harpreet sandhu'],
    ARRAY['ludmyrna', 'lopez', 'ludmyrna lopez'],
    ARRAY['maria', 'viramontes', 'maria viramontes'],
    ARRAY['mindell', 'penn', 'mindell penn'],
    ARRAY['richard', 'griffin', 'richard griffin'],
    ARRAY['john', 'marquez', 'john marquez'],
    ARRAY['gary', 'bell', 'gary bell']
  ];
  v_known_firsts text[];
  v_known_lasts text[];
  v_member text[];
  v_dupe record;
  v_first text;
  v_last text;
  v_first_match bool;
  v_last_match bool;
  v_is_real_combo bool;
  v_canonical_id uuid;
  v_last_name_official text;
BEGIN
  -- Build arrays of known first and last names
  v_known_firsts := ARRAY[]::text[];
  v_known_lasts := ARRAY[]::text[];
  FOREACH v_member SLICE 1 IN ARRAY v_known_members LOOP
    v_known_firsts := array_append(v_known_firsts, v_member[1]);
    v_known_lasts := array_append(v_known_lasts, v_member[2]);
  END LOOP;

  -- Find two-word entries where first matches one member, last matches another
  FOR v_dupe IN
    SELECT id, name, normalized_name FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name LIKE '% %'
      AND normalized_name NOT LIKE '% % %'  -- exactly two words
      AND is_current = false
  LOOP
    v_first := SPLIT_PART(v_dupe.normalized_name, ' ', 1);
    v_last := SPLIT_PART(v_dupe.normalized_name, ' ', 2);

    v_first_match := v_first = ANY(v_known_firsts);
    v_last_match := v_last = ANY(v_known_lasts);

    IF v_first_match AND v_last_match THEN
      -- Both parts match known members. Check if this is a REAL combination.
      v_is_real_combo := false;
      FOREACH v_member SLICE 1 IN ARRAY v_known_members LOOP
        IF v_member[1] = v_first AND v_member[2] = v_last THEN
          v_is_real_combo := true;
          EXIT;
        END IF;
      END LOOP;

      IF NOT v_is_real_combo THEN
        -- Cross-contaminated: first name from person A, last name from person B
        -- Merge into the official matching the last name
        v_last_name_official := NULL;
        FOREACH v_member SLICE 1 IN ARRAY v_known_members LOOP
          IF v_member[2] = v_last THEN
            v_last_name_official := v_member[3];
            EXIT;
          END IF;
        END LOOP;

        IF v_last_name_official IS NOT NULL THEN
          SELECT id INTO v_canonical_id FROM officials
          WHERE city_fips = '0660620'
            AND normalized_name = v_last_name_official
          LIMIT 1;

          IF v_canonical_id IS NOT NULL THEN
            RAISE NOTICE 'Cross-contaminated: "%" (% first + % last) -> merging into "%"',
              v_dupe.name, v_first, v_last, v_last_name_official;
            PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
          END IF;
        END IF;
      END IF;
    END IF;
  END LOOP;

  RAISE NOTICE 'Step 3 (cross-contaminated name cleanup) complete.';
END $$;

-- ============================================================
-- STEP 4: Combined entry cleanup
-- Entries like "Beckles, Myrick, and Rogers" are extraction errors
-- where multiple names were parsed as a single official.
-- These are clearly not real people. Delete after removing FK refs.
-- ============================================================

DO $$
DECLARE
  v_dupe record;
BEGIN
  FOR v_dupe IN
    SELECT id, name, normalized_name FROM officials
    WHERE city_fips = '0660620'
      AND (
        normalized_name LIKE '%, % and %'   -- "Beckles, Myrick, and Rogers"
        OR normalized_name LIKE '% and %'    -- "Myrick and Rogers"
        OR normalized_name LIKE '%, %, %'    -- "A, B, C" pattern
      )
  LOOP
    RAISE NOTICE 'Deleting combined entry "%"', v_dupe.name;
    -- Delete FK references (no good merge target for these)
    DELETE FROM votes WHERE official_id = v_dupe.id;
    DELETE FROM meeting_attendance WHERE official_id = v_dupe.id;
    DELETE FROM committees WHERE official_id = v_dupe.id;
    DELETE FROM form700_filings WHERE official_id = v_dupe.id;
    DELETE FROM economic_interests WHERE official_id = v_dupe.id;
    DELETE FROM conflict_flags WHERE official_id = v_dupe.id;
    UPDATE commission_members SET appointed_by_official_id = NULL
      WHERE appointed_by_official_id = v_dupe.id;
    DELETE FROM officials WHERE id = v_dupe.id;
  END LOOP;

  RAISE NOTICE 'Step 4 (combined entry cleanup) complete.';
END $$;

-- ============================================================
-- STEP 5: Newly confirmed former member alias merges
-- Research identified additional name variants not in migration 020.
-- Merge these into the canonical official record.
-- ============================================================

DO $$
DECLARE
  v_canonical_id uuid;
  v_dupe record;
  v_alias text;
  v_aliases text[];
  v_canonical_name text;
BEGIN
  -- ── Corky Booze additional aliases ──
  -- "Courtland" is the legal first name
  v_canonical_name := 'corky booze';
  v_aliases := ARRAY['courtland booze', 'courtland boozé', 'nathaniel boozé'];
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
  END IF;

  -- ── Nat Bates additional aliases ──
  v_canonical_name := 'nat bates';
  v_aliases := ARRAY['nathanial bates'];  -- common misspelling
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
  END IF;

  -- ── Irma Anderson ──
  v_canonical_name := 'irma anderson';
  v_aliases := ARRAY['irma l. anderson', 'irma l anderson', 'irma louise anderson'];
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
    -- Try the reverse: canonical might be under a variant
    SELECT id INTO v_canonical_id FROM officials
    WHERE city_fips = '0660620' AND normalized_name = 'irma l. anderson' LIMIT 1;
    IF v_canonical_id IS NOT NULL THEN
      UPDATE officials SET name = 'Irma Anderson', normalized_name = 'irma anderson'
      WHERE id = v_canonical_id;
      RAISE NOTICE 'Renamed "Irma L. Anderson" to "Irma Anderson"';
    END IF;
  END IF;

  -- ── Harpreet Sandhu ──
  v_canonical_name := 'harpreet sandhu';
  v_aliases := ARRAY['harpreet singh sandhu', 'harpreet s. sandhu', 'harpreet s sandhu',
                      'harpreet sandhu rogers'];  -- cross-contamination variant
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
    SELECT id INTO v_canonical_id FROM officials
    WHERE city_fips = '0660620' AND normalized_name = 'harpreet singh sandhu' LIMIT 1;
    IF v_canonical_id IS NOT NULL THEN
      UPDATE officials SET name = 'Harpreet Sandhu', normalized_name = 'harpreet sandhu'
      WHERE id = v_canonical_id;
      RAISE NOTICE 'Renamed "Harpreet Singh Sandhu" to "Harpreet Sandhu"';
    END IF;
  END IF;

  -- ── Ludmyrna Lopez ──
  v_canonical_name := 'ludmyrna lopez';
  v_aliases := ARRAY['myrna lopez'];
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
  END IF;

  -- ── Maria Viramontes ──
  v_canonical_name := 'maria viramontes';
  v_aliases := ARRAY['maria theresa viramontes', 'maria t. viramontes', 'maria t viramontes'];
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
  END IF;

  -- ── Mindell Penn ──
  v_canonical_name := 'mindell penn';
  v_aliases := ARRAY['mindell lewis penn', 'mindell l. penn', 'mindell l penn'];
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
  END IF;

  -- ── Richard Griffin ──
  v_canonical_name := 'richard griffin';
  v_aliases := ARRAY['richard l. griffin', 'richard l griffin', 'richard lee griffin'];
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
  END IF;

  -- ── John Marquez ──
  v_canonical_name := 'john marquez';
  v_aliases := ARRAY['john e. marquez', 'john e marquez'];
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
  END IF;

  -- ── Demnlus Johnson III ──
  v_canonical_name := 'demnlus johnson iii';
  v_aliases := ARRAY['demnlus johnson'];
  SELECT id INTO v_canonical_id FROM officials
  WHERE city_fips = '0660620' AND normalized_name = v_canonical_name LIMIT 1;
  IF v_canonical_id IS NULL THEN
    SELECT id INTO v_canonical_id FROM officials
    WHERE city_fips = '0660620' AND normalized_name = 'demnlus johnson' LIMIT 1;
    IF v_canonical_id IS NOT NULL THEN
      UPDATE officials SET name = 'Demnlus Johnson III', normalized_name = 'demnlus johnson iii'
      WHERE id = v_canonical_id;
      RAISE NOTICE 'Renamed "Demnlus Johnson" to "Demnlus Johnson III"';
    END IF;
  ELSE
    FOREACH v_alias IN ARRAY v_aliases LOOP
      FOR v_dupe IN
        SELECT id FROM officials
        WHERE city_fips = '0660620' AND normalized_name = v_alias AND id != v_canonical_id
      LOOP
        PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
      END LOOP;
    END LOOP;
  END IF;

  -- ── Melvin Willis ──
  v_canonical_name := 'melvin willis';
  v_aliases := ARRAY['melvin lee willis jr.', 'melvin lee willis jr', 'melvin lee willis'];
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
  END IF;

  RAISE NOTICE 'Step 5 (additional alias merges) complete.';
END $$;

-- ============================================================
-- STEP 6: Remaining title prefix cleanup (second pass)
-- Catch any title-prefixed entries that survived migration 020.
-- Run AFTER alias merges so we have more canonical entries to match against.
-- ============================================================

DO $$
DECLARE
  v_dupe record;
  v_stripped text;
  v_canonical_id uuid;
BEGIN
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
    v_stripped := regexp_replace(v_dupe.normalized_name,
      '^(mayor|vice mayor|councilmember|council member|president|vice president)\s+', '');

    SELECT id INTO v_canonical_id FROM officials
    WHERE city_fips = '0660620'
      AND normalized_name = v_stripped
      AND id != v_dupe.id
    LIMIT 1;

    IF v_canonical_id IS NOT NULL THEN
      PERFORM merge_official_pair(v_canonical_id, v_dupe.id);
    ELSE
      RAISE NOTICE 'No match for title-prefixed "%". Left as-is.', v_dupe.name;
    END IF;
  END LOOP;

  RAISE NOTICE 'Step 6 (second-pass title prefix cleanup) complete.';
END $$;

-- ============================================================
-- STEP 7: Non-council-member removal
-- Research confirmed these people never served on Richmond council.
-- If they exist as council members in the database, remove them.
-- Note: they might legitimately exist in other contexts (commissioners,
-- donors), so we only remove records with council-like roles.
-- ============================================================

DO $$
DECLARE
  v_dupe record;
  v_name text;
  v_names text[] := ARRAY['ahmad anderson', 'oscar garcia', 'shawn dunning'];
BEGIN
  FOREACH v_name IN ARRAY v_names LOOP
    FOR v_dupe IN
      SELECT id, name, role FROM officials
      WHERE city_fips = '0660620'
        AND normalized_name = v_name
        AND role IN ('councilmember', 'council_member', 'City/Town Council Member',
                     'mayor', 'vice_mayor')
    LOOP
      RAISE NOTICE 'Removing non-council-member "%" (role: %). Never served on Richmond council.', v_dupe.name, v_dupe.role;
      -- Delete FK references
      DELETE FROM votes WHERE official_id = v_dupe.id;
      DELETE FROM meeting_attendance WHERE official_id = v_dupe.id;
      DELETE FROM committees WHERE official_id = v_dupe.id;
      DELETE FROM form700_filings WHERE official_id = v_dupe.id;
      DELETE FROM economic_interests WHERE official_id = v_dupe.id;
      DELETE FROM conflict_flags WHERE official_id = v_dupe.id;
      UPDATE commission_members SET appointed_by_official_id = NULL
        WHERE appointed_by_official_id = v_dupe.id;
      DELETE FROM officials WHERE id = v_dupe.id;
    END LOOP;
  END LOOP;

  RAISE NOTICE 'Step 7 (non-council-member removal) complete.';
END $$;

-- ============================================================
-- STEP 8: Verification queries (run to confirm results)
-- ============================================================

-- Current officials should still be exactly 7 council + leadership:
-- SELECT name, role, is_current FROM officials
-- WHERE city_fips = '0660620' AND is_current = true
-- ORDER BY role, name;

-- Former members should be much cleaner now:
-- SELECT name, role, is_current,
--   (SELECT COUNT(*) FROM votes WHERE official_id = o.id) AS votes,
--   (SELECT COUNT(*) FROM meeting_attendance WHERE official_id = o.id) AS attendance
-- FROM officials o
-- WHERE city_fips = '0660620' AND is_current = false
-- ORDER BY name;

-- Check remaining potential issues:
-- SELECT name, normalized_name, role,
--   (SELECT COUNT(*) FROM votes WHERE official_id = o.id) AS votes,
--   LENGTH(normalized_name) - LENGTH(REPLACE(normalized_name, ' ', '')) + 1 AS word_count
-- FROM officials o
-- WHERE city_fips = '0660620' AND is_current = false
--   AND (
--     -- Still single-word? (no match was found)
--     normalized_name NOT LIKE '% %'
--     -- Still has title prefix?
--     OR normalized_name LIKE 'councilmember %'
--     OR normalized_name LIKE 'mayor %'
--     OR normalized_name LIKE 'vice mayor %'
--   )
-- ORDER BY votes DESC, name;
