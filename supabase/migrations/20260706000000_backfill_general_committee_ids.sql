-- Migration 121: Backfill committee_id for general election candidates
-- from their primary election counterparts.
--
-- General election candidates seeded by migration 120 lack committee_id
-- because the INSERT statement doesn't include it, and
-- build_candidates_from_committees() only targets primary elections.
-- Primary rows for the same candidates (same normalized_name, same
-- office_sought, same election year) already have committee_id from the
-- committee-scanning pipeline or hand-curated linkage migrations.
--
-- Also backfills official_id for candidates where it's still NULL
-- (e.g., Ahmad J. Anderson's general row has neither committee_id nor
-- official_id). Migration 073's pattern requires official_id to link
-- committees, but the primary→general match works without it.
--
-- Idempotent: the WHERE clause only touches rows WHERE committee_id IS
-- NULL. On re-run, those rows already have committee_id so the UPDATE
-- finds nothing. Same for official_id IS NULL in Part B.

-- Part A: Propagate committee_id from primary → general candidates
-- matching on (normalized_name, office_sought) within the same election
-- year. This works even when the general candidate lacks official_id.
UPDATE election_candidates
SET committee_id = pri.committee_id,
    updated_at = NOW()
FROM election_candidates pri
JOIN elections e_pri ON e_pri.id = pri.election_id
WHERE election_candidates.committee_id IS NULL
  AND election_candidates.city_fips = pri.city_fips
  AND election_candidates.normalized_name = pri.normalized_name
  AND election_candidates.office_sought = pri.office_sought
  AND e_pri.election_type = 'primary'
  AND pri.committee_id IS NOT NULL
  AND election_candidates.election_id IN (
    SELECT id FROM elections
    WHERE election_type = 'general'
      AND EXTRACT(YEAR FROM election_date) =
          EXTRACT(YEAR FROM e_pri.election_date)
  );

-- Part B: Backfill official_id from current officials (migration 073
-- pattern). Catches candidates like Anderson who were seeded without an
-- official link — needed for council-page candidacy badges.
UPDATE election_candidates ec
SET official_id = o.id,
    updated_at = NOW()
FROM officials o
WHERE ec.official_id IS NULL
  AND ec.city_fips = o.city_fips
  AND ec.normalized_name = o.normalized_name
  AND o.is_current = TRUE;
