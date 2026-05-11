-- Migration 082: Neighborhood councils
-- Richmond has 31 neighborhood councils and HOAs that serve as community-level
-- civic organizations. This table stores their registry data, meeting info,
-- and maps them to the neighborhoods GeoJSON via geojson_codes.

CREATE TABLE IF NOT EXISTS neighborhood_councils (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
  name TEXT NOT NULL,
  short_name TEXT,
  nc_type TEXT NOT NULL DEFAULT 'neighborhood_council',  -- 'neighborhood_council' or 'hoa'
  geojson_codes INTEGER[] NOT NULL DEFAULT '{}',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  meeting_schedule TEXT,        -- human-readable schedule (e.g., "4th Thursday of each month")
  meeting_time TEXT,            -- e.g., "7:00 PM"
  meeting_location TEXT,        -- address or "Via Zoom"
  city_page_url TEXT,
  city_page_id INTEGER,
  document_center_path TEXT,    -- e.g., "/DocumentCenter/Index/4485"
  contact_email TEXT DEFAULT 'neighborhoods@ci.richmond.ca.us',
  president TEXT,
  vice_president TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(city_fips, name)
);

CREATE INDEX IF NOT EXISTS idx_neighborhood_councils_city_fips
  ON neighborhood_councils(city_fips);
CREATE INDEX IF NOT EXISTS idx_neighborhood_councils_active
  ON neighborhood_councils(is_active);
CREATE INDEX IF NOT EXISTS idx_neighborhood_councils_geojson_codes
  ON neighborhood_councils USING GIN(geojson_codes);

-- RLS: public read access (same pattern as commissions)
ALTER TABLE neighborhood_councils ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS neighborhood_councils_public_read ON neighborhood_councils;
CREATE POLICY neighborhood_councils_public_read ON neighborhood_councils
  FOR SELECT USING (true);
DROP POLICY IF EXISTS neighborhood_councils_service_write ON neighborhood_councils;
CREATE POLICY neighborhood_councils_service_write ON neighborhood_councils
  FOR ALL USING (true) WITH CHECK (true);

COMMENT ON TABLE neighborhood_councils IS 'Registry of Richmond neighborhood councils and HOAs with meeting info and GeoJSON mapping';
COMMENT ON COLUMN neighborhood_councils.geojson_codes IS 'Array of code values from richmond-neighborhoods.geojson that map to this NC';
COMMENT ON COLUMN neighborhood_councils.nc_type IS 'neighborhood_council or hoa';
