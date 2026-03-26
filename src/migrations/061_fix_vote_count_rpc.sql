-- Migration 061: Fix vote count in get_meeting_counts RPC
-- Previously counted individual vote records (one per councilmember per motion),
-- inflating the count (e.g., 322 instead of ~46). Now counts distinct motions
-- that have at least one vote record.

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
    SELECT ai.meeting_id, COUNT(DISTINCT mo.id) AS cnt
    FROM motions mo
    JOIN agenda_items ai ON ai.id = mo.agenda_item_id
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
      AND EXISTS (SELECT 1 FROM votes v WHERE v.motion_id = mo.id)
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
