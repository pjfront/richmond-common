-- Migration 067: Permanently fix is_current on officials
--
-- Root cause: schema default was TRUE + ensure_official() never set
-- is_current explicitly. Every official extracted from historical
-- meetings got is_current=TRUE. Migration 020 fixed values once
-- but pipeline re-created stale officials immediately.
--
-- Permanent fix:
-- 1. Change schema default to FALSE (new officials aren't current)
-- 2. Set ALL officials to is_current=FALSE
-- 3. Set only the 7 actual current council members to TRUE
--    (matched by normalized name for robustness)

-- Step 1: Change default so new officials aren't marked current
ALTER TABLE officials ALTER COLUMN is_current SET DEFAULT FALSE;

-- Step 2: Reset all to false
UPDATE officials SET is_current = FALSE WHERE city_fips = '0660620';

-- Step 3: Set actual current council members (as of March 2026)
UPDATE officials
SET is_current = TRUE
WHERE city_fips = '0660620'
  AND lower(trim(name)) IN (
    'claudia jimenez',
    'eduardo martinez',
    'soheila bana',
    'doria robinson',
    'sue wilson',
    'cesar zepeda',
    'jamelia brown'
  );
