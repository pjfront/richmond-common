-- Migration 048: Contributor Type Classification
-- Adds contributor_type enum and entity_code to contributions table.
-- Enables filtering contributions by Corporate/Union/Individual/PAC/Other.
-- Part of S14-P: Pipeline Prep for topic navigation + financial overlay.

-- 1. Add columns
ALTER TABLE contributions
  ADD COLUMN IF NOT EXISTS contributor_type VARCHAR(20),
  ADD COLUMN IF NOT EXISTS contributor_type_source VARCHAR(20),
  ADD COLUMN IF NOT EXISTS entity_code VARCHAR(10);

-- contributor_type: 'corporate', 'union', 'individual', 'pac_ie', 'other'
-- contributor_type_source: 'entity_cd' (authoritative from CAL-ACCESS),
--   'inferred' (name-pattern heuristic from NetFile), 'manual' (operator override)
-- entity_code: raw ENTITY_CD value from CAL-ACCESS (IND, COM, OTH, PTY, SCC)

COMMENT ON COLUMN contributions.contributor_type IS
  'Contributor classification: corporate, union, individual, pac_ie, other';
COMMENT ON COLUMN contributions.contributor_type_source IS
  'How contributor_type was determined: entity_cd, inferred, manual';
COMMENT ON COLUMN contributions.entity_code IS
  'Raw FPPC entity code from CAL-ACCESS ENTITY_CD field';

-- 2. Index for filtering by contributor type
CREATE INDEX IF NOT EXISTS idx_contributions_contributor_type
  ON contributions (contributor_type)
  WHERE contributor_type IS NOT NULL;

-- 3. Backfill: classify existing contributions by donor name patterns
-- Corporate patterns
UPDATE contributions c
SET contributor_type = 'corporate',
    contributor_type_source = 'inferred'
FROM donors d
WHERE c.donor_id = d.id
  AND c.contributor_type IS NULL
  AND d.name ~* '\m(inc|corp|llc|ltd|co\.|company|enterprises|holdings|group|partners|associates|investments|properties|construction|consulting|services|solutions|technologies|industries|ventures|management|development|realty|builders|contracting)\M';

-- Union patterns
UPDATE contributions c
SET contributor_type = 'union',
    contributor_type_source = 'inferred'
FROM donors d
WHERE c.donor_id = d.id
  AND c.contributor_type IS NULL
  AND d.name ~* '\m(union|local\s+\d|seiu|ibew|ufcw|afscme|aft|iatse|unite here|teamsters|laborers|plumbers|carpenters|firefighters|nurses|teachers|workers|trades council|labor council|building trades|police officers|officers assoc)\M';

-- PAC/IE Committee patterns
UPDATE contributions c
SET contributor_type = 'pac_ie',
    contributor_type_source = 'inferred'
FROM donors d
WHERE c.donor_id = d.id
  AND c.contributor_type IS NULL
  AND d.name ~* '\m(pac$|political action|independent expenditure|ballot measure|committee|for council|for mayor|for supervisor|for assembly|for senate|for governor)\M';

-- Remaining unclassified → individual (most common for city-level contributions)
UPDATE contributions c
SET contributor_type = 'individual',
    contributor_type_source = 'inferred'
WHERE c.contributor_type IS NULL;
