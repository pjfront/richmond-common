-- Migration 064: Restore topic_labels in get_meeting_counts RPC
-- Migration 061 (fix_vote_count_rpc) accidentally dropped the topic_labels
-- column added by migration 056. This restores it while keeping the
-- corrected vote counting logic from 061.

DROP FUNCTION IF EXISTS get_meeting_counts(TEXT);

CREATE OR REPLACE FUNCTION get_meeting_counts(p_city_fips TEXT)
RETURNS TABLE (
  meeting_id UUID,
  agenda_item_count BIGINT,
  vote_count BIGINT,
  categories JSONB,
  topic_labels JSONB
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
  topic_label_counts AS (
    SELECT ai.meeting_id, ai.topic_label, COUNT(*) AS cnt
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
      AND ai.topic_label IS NOT NULL
      AND ai.category != 'procedural'
    GROUP BY ai.meeting_id, ai.topic_label
  ),
  topic_labels_agg AS (
    SELECT tlc.meeting_id,
           jsonb_agg(
             jsonb_build_object('label', tlc.topic_label, 'count', tlc.cnt)
             ORDER BY tlc.cnt DESC
           ) AS topic_labels
    FROM topic_label_counts tlc
    GROUP BY tlc.meeting_id
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
    COALESCE(ca.categories, '[]'::jsonb) AS categories,
    COALESCE(tla.topic_labels, '[]'::jsonb) AS topic_labels
  FROM meetings m
  LEFT JOIN item_counts ic ON ic.meeting_id = m.id
  LEFT JOIN vote_counts vc ON vc.meeting_id = m.id
  LEFT JOIN categories_agg ca ON ca.meeting_id = m.id
  LEFT JOIN topic_labels_agg tla ON tla.meeting_id = m.id
  WHERE m.city_fips = p_city_fips;
END;
$$ LANGUAGE plpgsql STABLE;
