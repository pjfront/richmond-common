-- Re-link 2026 candidacies whose committee_id still points at a prior-cycle
-- committee. Caught by the candidacy_committee_cycle_matches liveness check
-- on 2026-04-29 — Bana's June and November 2026 candidacies still pointed at
-- her 2022 committee, and Martinez's November 2026 General row still pointed
-- at his 2018 council committee. Without this fix the candidate page would
-- pull the wrong cycle's contribution data (Bana would display $60K from her
-- 2022 council bid attributed to her 2026 campaign; Martinez's November row
-- would display $0 from a defunct 2018 committee).
--
-- This is the same hand-curated UPDATE pattern as migration 089. The
-- broader fix — making the discovery script reuse 089's logic for newly-
-- recognized 2026 paper filers — is tracked separately.
--
-- Idempotent: each UPDATE is bounded by candidate name + election + city,
-- and rerunning is a no-op once committee_id already matches.

DO $$
DECLARE
  v_june_2026_id UUID;
  v_nov_2026_id  UUID;
  v_committee_id UUID;
BEGIN
  SELECT id INTO v_june_2026_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-06-02';

  SELECT id INTO v_nov_2026_id
  FROM elections
  WHERE city_fips = '0660620' AND election_date = '2026-11-03';

  -- Soheila Bana for Council 2026 → Bana's June + November 2026 candidacies
  SELECT id INTO v_committee_id
  FROM committees
  WHERE city_fips = '0660620' AND name = 'Soheila Bana for Council 2026';

  IF v_committee_id IS NOT NULL THEN
    IF v_june_2026_id IS NOT NULL THEN
      UPDATE election_candidates
      SET committee_id = v_committee_id, updated_at = NOW()
      WHERE city_fips = '0660620'
        AND election_id = v_june_2026_id
        AND normalized_name = 'soheila bana';
    END IF;

    IF v_nov_2026_id IS NOT NULL THEN
      UPDATE election_candidates
      SET committee_id = v_committee_id, updated_at = NOW()
      WHERE city_fips = '0660620'
        AND election_id = v_nov_2026_id
        AND normalized_name = 'soheila bana';
    END IF;
  END IF;

  -- Eduardo Martinez for Mayor 2026 → Martinez's November 2026 General row
  -- (June primary was already fixed in migration 089)
  SELECT id INTO v_committee_id
  FROM committees
  WHERE city_fips = '0660620' AND name = 'Eduardo Martinez for Mayor 2026';

  IF v_committee_id IS NOT NULL AND v_nov_2026_id IS NOT NULL THEN
    UPDATE election_candidates
    SET committee_id = v_committee_id, updated_at = NOW()
    WHERE city_fips = '0660620'
      AND election_id = v_nov_2026_id
      AND normalized_name = 'eduardo martinez';
  END IF;

END $$;
