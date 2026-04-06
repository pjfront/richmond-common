-- Fix find_similar_items: motions.result not motions.passed
SET search_path TO public, extensions;

CREATE OR REPLACE FUNCTION find_similar_items(
  p_item_id UUID,
  p_city_fips TEXT DEFAULT '0660620',
  p_limit INT DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  title TEXT,
  summary_headline TEXT,
  meeting_id UUID,
  meeting_date DATE,
  item_number TEXT,
  similarity REAL,
  vote_outcome TEXT,
  public_comment_count INTEGER,
  financial_amount TEXT,
  category TEXT,
  topic_label TEXT
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  source_embedding vector(1536);
BEGIN
  SELECT ai.embedding INTO source_embedding
  FROM agenda_items ai
  WHERE ai.id = p_item_id;

  IF source_embedding IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    ai.id,
    ai.title,
    ai.summary_headline,
    ai.meeting_id,
    m.meeting_date,
    ai.item_number::TEXT,
    (1 - (ai.embedding <=> source_embedding))::REAL AS similarity,
    CASE
      WHEN m.meeting_date > CURRENT_DATE THEN 'upcoming'
      WHEN mo.id IS NULL AND m.minutes_url IS NULL THEN 'minutes pending'
      WHEN mo.id IS NULL THEN 'no vote'
      WHEN lower(mo.motion_result) LIKE '%pass%' OR lower(mo.motion_result) LIKE '%approv%' OR lower(mo.motion_result) LIKE '%adopt%' THEN 'passed'
      ELSE 'failed'
    END AS vote_outcome,
    ai.public_comment_count,
    ai.financial_amount::TEXT,
    ai.category::TEXT,
    ai.topic_label::TEXT
  FROM agenda_items ai
  JOIN meetings m ON m.id = ai.meeting_id
  LEFT JOIN LATERAL (
    SELECT mo2.id, mo2.result AS motion_result
    FROM motions mo2
    WHERE mo2.agenda_item_id = ai.id
    ORDER BY mo2.id
    LIMIT 1
  ) mo ON true
  WHERE ai.id != p_item_id
    AND ai.embedding IS NOT NULL
    AND m.city_fips = p_city_fips
    AND (1 - (ai.embedding <=> source_embedding)) > 0.3
  ORDER BY ai.embedding <=> source_embedding
  LIMIT p_limit;
END;
$$;
