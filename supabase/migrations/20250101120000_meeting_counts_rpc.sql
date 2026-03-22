-- Migration 013: Server-side meeting counts RPC
-- Replaces client-side row-fetching-to-count pattern in getMeetingsWithCounts
-- with a single database function that aggregates server-side.
-- Eliminates dependency on Supabase max_rows setting for correct counts.

CREATE OR REPLACE FUNCTION get_meeting_counts(p_city_fips TEXT)
RETURNS TABLE (
  meeting_id UUID,
  agenda_item_count BIGINT,
  vote_count BIGINT,
  categories JSONB
) AS $$
BEGIN
  RETURN QUERY
  WITH item_counts AS (
    SELECT ai.meeting_id, COUNT(*) AS cnt
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
    GROUP BY ai.meeting_id
  ),
  category_counts AS (
    SELECT ai.meeting_id, ai.category, COUNT(*) AS cnt
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips AND ai.category IS NOT NULL
    GROUP BY ai.meeting_id, ai.category
  ),
  categories_agg AS (
    SELECT cc.meeting_id,
           jsonb_agg(
             jsonb_build_object('category', cc.category, 'count', cc.cnt)
             ORDER BY cc.cnt DESC
           ) AS categories
    FROM category_counts cc
    GROUP BY cc.meeting_id
  ),
  vote_counts AS (
    SELECT ai.meeting_id, COUNT(DISTINCT v.id) AS cnt
    FROM votes v
    JOIN motions mo ON mo.id = v.motion_id
    JOIN agenda_items ai ON ai.id = mo.agenda_item_id
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
    GROUP BY ai.meeting_id
  )
  SELECT
    m.id AS meeting_id,
    COALESCE(ic.cnt, 0)::BIGINT AS agenda_item_count,
    COALESCE(vc.cnt, 0)::BIGINT AS vote_count,
    COALESCE(ca.categories, '[]'::jsonb) AS categories
  FROM meetings m
  LEFT JOIN item_counts ic ON ic.meeting_id = m.id
  LEFT JOIN vote_counts vc ON vc.meeting_id = m.id
  LEFT JOIN categories_agg ca ON ca.meeting_id = m.id
  WHERE m.city_fips = p_city_fips;
END;
$$ LANGUAGE plpgsql STABLE;
