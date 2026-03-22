-- Migration 037: Replace legacy meeting uniqueness constraint with body-aware version
--
-- The original uq_meetings_date_type constraint on (city_fips, meeting_date, meeting_type)
-- prevents commission meetings on the same date as council meetings.
-- Migration 035 added a partial index uq_meetings_date_type_body but kept the old one
-- as a "fallback." Now that commission extraction is live, the old constraint must go.
--
-- Strategy:
-- 1. Drop the old constraint
-- 2. Backfill body_id on existing meetings (City Council)
-- 3. Make body_id NOT NULL (every meeting belongs to a body)
-- 4. Replace partial index with proper unique constraint on all 4 columns

-- Step 1: Drop old constraint that blocks multi-body same-date meetings
ALTER TABLE meetings DROP CONSTRAINT IF EXISTS uq_meetings_date_type;

-- Step 2: Backfill body_id for existing meetings (all are City Council)
UPDATE meetings m
SET body_id = b.id
FROM bodies b
WHERE b.city_fips = m.city_fips
  AND b.name = 'City Council'
  AND b.body_type = 'city_council'
  AND m.body_id IS NULL;

-- Step 3: Make body_id NOT NULL now that all rows have a value
-- (Uses a subquery default for any stragglers — defensive)
DO $$
DECLARE
  cc_body_id UUID;
BEGIN
  SELECT id INTO cc_body_id FROM bodies
  WHERE name = 'City Council' AND body_type = 'city_council' LIMIT 1;

  IF cc_body_id IS NOT NULL THEN
    UPDATE meetings SET body_id = cc_body_id WHERE body_id IS NULL;
  END IF;
END $$;

ALTER TABLE meetings ALTER COLUMN body_id SET NOT NULL;

-- Step 4: Drop the partial index/constraint from migration 035 and create proper constraint
ALTER TABLE meetings DROP CONSTRAINT IF EXISTS uq_meetings_date_type_body;
DROP INDEX IF EXISTS uq_meetings_date_type_body;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'uq_meetings_date_type_body'
  ) THEN
    ALTER TABLE meetings ADD CONSTRAINT uq_meetings_date_type_body
      UNIQUE (city_fips, meeting_date, meeting_type, body_id);
  END IF;
END $$;
