-- Atomic cross-process LLM budget reservations.
--
-- The API-cost journal is an audit ledger, but a read-then-call cap check can
-- race when multiple GitHub Actions runners start together.  Each paid request
-- now reserves its conservative maximum cost while holding a PostgreSQL
-- advisory transaction lock.  Settled rows retain actual cost; an ambiguous
-- or crashed request retains its full reservation through the month so the
-- safety boundary fails closed.

CREATE TABLE IF NOT EXISTS llm_cost_reservations (
  id                UUID PRIMARY KEY,
  city_fips         VARCHAR NOT NULL DEFAULT '0660620',
  model             TEXT NOT NULL,
  caller            TEXT NOT NULL,
  event_type        TEXT,
  projected_cost    NUMERIC(14, 8) NOT NULL CHECK (projected_cost >= 0),
  actual_cost       NUMERIC(14, 8) CHECK (actual_cost >= 0),
  status            TEXT NOT NULL DEFAULT 'reserved'
                    CHECK (status IN ('reserved', 'settled')),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  settled_at        TIMESTAMPTZ,
  metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT llm_cost_reservations_settlement_shape CHECK (
    (status = 'reserved' AND actual_cost IS NULL AND settled_at IS NULL)
    OR
    (status = 'settled' AND actual_cost IS NOT NULL AND settled_at IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_llm_cost_reservations_month
  ON llm_cost_reservations (created_at);

CREATE INDEX IF NOT EXISTS idx_llm_cost_reservations_open
  ON llm_cost_reservations (created_at)
  WHERE status = 'reserved';

COMMENT ON TABLE llm_cost_reservations IS
  'Service-only atomic monthly LLM spend reservations. Reserved rows count at '
  'their conservative ceiling; settled rows count at provider-reported cost.';

COMMENT ON COLUMN llm_cost_reservations.status IS
  'reserved remains fail-closed after ambiguous/crashed requests; settled has actual_cost.';

ALTER TABLE llm_cost_reservations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS llm_cost_reservations_service_all
  ON llm_cost_reservations;
CREATE POLICY llm_cost_reservations_service_all
  ON llm_cost_reservations
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Web routes cannot safely reproduce the direct-Postgres transaction used by
-- llm_budget_lock.py.  These SECURITY DEFINER functions expose only the two
-- operations they need through the service-role client: reserve under the
-- same monthly advisory lock, then atomically settle + append the cost journal.
-- Neither function is callable by anon/authenticated roles.

CREATE OR REPLACE FUNCTION reserve_llm_cost(
  p_reservation_id UUID,
  p_city_fips VARCHAR,
  p_model TEXT,
  p_caller TEXT,
  p_projected_cost NUMERIC,
  p_monthly_cap NUMERIC,
  p_event_type TEXT DEFAULT NULL,
  p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS TABLE (
  reserved BOOLEAN,
  committed_cost NUMERIC,
  reason TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_committed NUMERIC;
BEGIN
  IF p_reservation_id IS NULL
     OR NULLIF(BTRIM(p_city_fips), '') IS NULL
     OR NULLIF(BTRIM(p_model), '') IS NULL
     OR NULLIF(BTRIM(p_caller), '') IS NULL
     OR p_projected_cost IS NULL
     OR p_monthly_cap IS NULL
     OR p_projected_cost < 0
     OR p_monthly_cap < 0
     OR p_projected_cost = 'NaN'::numeric
     OR p_monthly_cap = 'NaN'::numeric
     OR p_projected_cost = 'Infinity'::numeric
     OR p_monthly_cap = 'Infinity'::numeric
     OR jsonb_typeof(COALESCE(p_metadata, '{}'::jsonb)) <> 'object' THEN
    RAISE EXCEPTION 'invalid LLM cost reservation parameters';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtext('richmond-commons-llm-budget'),
    hashtext(to_char(NOW(), 'YYYY-MM'))
  );

  SELECT
    COALESCE((
      SELECT SUM((metrics->>'approx_cost')::numeric)
      FROM pipeline_journal
      WHERE entry_type = 'api_cost'
        AND NULLIF(metrics->>'reservation_id', '') IS NULL
        AND date_trunc('month', created_at) = date_trunc('month', NOW())
    ), 0)
    +
    COALESCE((
      SELECT SUM(
        CASE WHEN status = 'settled' THEN actual_cost ELSE projected_cost END
      )
      FROM llm_cost_reservations
      WHERE date_trunc('month', created_at) = date_trunc('month', NOW())
    ), 0)
  INTO v_committed;

  IF v_committed >= p_monthly_cap
     OR v_committed + p_projected_cost > p_monthly_cap THEN
    RETURN QUERY SELECT FALSE, v_committed, 'monthly_cap_exceeded'::TEXT;
    RETURN;
  END IF;

  INSERT INTO llm_cost_reservations
    (id, city_fips, model, caller, event_type, projected_cost, status, metadata)
  VALUES
    (p_reservation_id, p_city_fips, p_model, p_caller, p_event_type,
     p_projected_cost, 'reserved', COALESCE(p_metadata, '{}'::jsonb));

  RETURN QUERY SELECT TRUE, v_committed + p_projected_cost, 'reserved'::TEXT;
END;
$$;

REVOKE ALL ON FUNCTION reserve_llm_cost(
  UUID, VARCHAR, TEXT, TEXT, NUMERIC, NUMERIC, TEXT, JSONB
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION reserve_llm_cost(
  UUID, VARCHAR, TEXT, TEXT, NUMERIC, NUMERIC, TEXT, JSONB
) TO service_role;


CREATE OR REPLACE FUNCTION settle_llm_cost_reservation(
  p_reservation_id UUID,
  p_actual_cost NUMERIC,
  p_input_tokens INTEGER,
  p_output_tokens INTEGER DEFAULT 0,
  p_metadata JSONB DEFAULT '{}'::jsonb
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_city_fips VARCHAR;
  v_model TEXT;
  v_caller TEXT;
  v_event_type TEXT;
  v_metrics JSONB;
BEGIN
  IF p_reservation_id IS NULL
     OR p_actual_cost IS NULL
     OR p_actual_cost < 0
     OR p_actual_cost = 'NaN'::numeric
     OR p_actual_cost = 'Infinity'::numeric
     OR p_input_tokens IS NULL
     OR p_input_tokens < 0
     OR p_output_tokens IS NULL
     OR p_output_tokens < 0
     OR jsonb_typeof(COALESCE(p_metadata, '{}'::jsonb)) <> 'object' THEN
    RAISE EXCEPTION 'invalid LLM cost settlement parameters';
  END IF;

  UPDATE llm_cost_reservations
  SET status = 'settled',
      actual_cost = p_actual_cost,
      settled_at = NOW(),
      metadata = metadata || COALESCE(p_metadata, '{}'::jsonb)
  WHERE id = p_reservation_id
    AND status = 'reserved'
  RETURNING city_fips, model, caller, event_type
  INTO v_city_fips, v_model, v_caller, v_event_type;

  IF NOT FOUND THEN
    RETURN FALSE;
  END IF;

  v_metrics := COALESCE(p_metadata, '{}'::jsonb) || jsonb_build_object(
    'model', v_model,
    'input_tokens', p_input_tokens,
    'output_tokens', p_output_tokens,
    'approx_cost', p_actual_cost,
    'event_type', v_event_type,
    'reservation_id', p_reservation_id::TEXT
  );

  INSERT INTO pipeline_journal
    (id, city_fips, session_id, entry_type, zone,
     target_artifact, description, metrics)
  VALUES
    (gen_random_uuid(), v_city_fips, p_reservation_id, 'api_cost',
     'observation', v_caller,
     v_caller || ': $' || to_char(p_actual_cost, 'FM999999990.00000000'),
     v_metrics);

  RETURN TRUE;
END;
$$;

REVOKE ALL ON FUNCTION settle_llm_cost_reservation(
  UUID, NUMERIC, INTEGER, INTEGER, JSONB
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION settle_llm_cost_reservation(
  UUID, NUMERIC, INTEGER, INTEGER, JSONB
) TO service_role;
