-- Migration 121: OD-14 database diet — the reversible cuts.
--
-- Context: docs/plans/2026-07-03-self-sustaining-plan.md (free-tier addendum).
-- Both hosting tiers are now free; Supabase free tier allows 500 MB and the DB
-- measured 1,251 MB on 2026-07-05. Operator direction (2026-07-05): execute the
-- reversible cuts now; defer irreversible options (dropping embeddings, offloading
-- Document Lake raw text) to a follow-up decision.
--
-- What this does, and why each cut is reversible:
--   A. DELETE superseded conflict-flag history (is_current = FALSE; 85,270 rows,
--      82% of the table, none reviewed). Recoverable from the encrypted weekly
--      backup (.github/workflows/db-backup.yml — verified run 28744532419).
--      Current flags (is_current = TRUE) are untouched; liveness expectation
--      conflict_scanner_has_current_flags still holds.
--   B. TRIM city_permits to 2013+ (drops the 1991–1999 legacy block, ~30K rows).
--      Fully re-fetchable: socrata_permits sync_type=full fetches ALL rows
--      (src/pipelines/socrata.py). Rows with no dates are kept.
--   C. TRIM city_expenditures to FY2024+ (drops FY2022–2023, ~58K rows).
--      Re-fetchable today: sync_type=full covers current FY minus 0–4
--      (socrata.py) — FY2022 leaves that window when FY2027 starts; the
--      encrypted backup covers it beyond that.
--   D. DROP never-scanned single-purpose indexes on the Socrata mirrors
--      (0 idx_scan since DB creation; upsert keys and PKs kept) and the
--      single-column city_fips indexes sanctioned by .claude/rules/conventions.md
--      ("Phase 3 ... drops ~30 single-column (city_fips) indexes wholesale").
--      Trivially reversible: recreate DDL lives in the migrations cited inline.
--   E. CONVERT the four *_embeddings sidecars from vector(1536) to halfvec(1536)
--      (pgvector 0.8.0; fp16 halves ~335 MB of embedding storage+index).
--      Recall loss at 1536 dims is negligible for this corpus (~23K vectors).
--      Reversal = re-embed (src/embedding_generator.py) or backup restore.
--   F. REWRITE search_hybrid / find_similar_items for halfvec. Signatures are
--      unchanged (PostgREST callers in web/src/lib/queries/search.ts keep
--      working); the query embedding is cast to halfvec inside the bodies
--      because pgvector has no cross-type <=> operator.
--
-- NOT in this migration (must run outside a transaction, direct connection):
--   VACUUM FULL conflict_flags; VACUUM FULL city_permits; VACUUM FULL city_expenditures;
--   (The ALTER COLUMN TYPE in section E already rewrites the embedding tables.)
--
-- Idempotent: DELETEs re-match nothing, index drops/creates are IF (NOT) EXISTS,
-- the ALTERs are guarded on the column's current type.

SET search_path TO public, extensions;

-- Data-movement migration: the bulk DELETE and the ALTER COLUMN TYPE rewrites
-- exceed the default session statement_timeout (observed SQLSTATE 57014).
SET statement_timeout = 0;

-- ── A. Superseded conflict-flag history ────────────────────────────────────

-- The self-FK conflict_flags_superseded_by_fkey fires an RI check per deleted
-- row; without an index on superseded_by each check is a full seq scan
-- (85K deletes × 100K-row scans). The column is all-NULL today (no writer
-- populates it), so this partial index is empty — it exists to make the RI
-- triggers, and any future supersession lookups, indexed.
CREATE INDEX IF NOT EXISTS idx_conflict_flags_superseded_by
  ON conflict_flags (superseded_by)
  WHERE superseded_by IS NOT NULL;

DO $$
DECLARE
  n_deleted BIGINT;
  n_current BIGINT;
BEGIN
  DELETE FROM conflict_flags
  WHERE is_current = FALSE
    AND id NOT IN (
      SELECT superseded_by FROM conflict_flags WHERE superseded_by IS NOT NULL
    );
  GET DIAGNOSTICS n_deleted = ROW_COUNT;

  SELECT COUNT(*) INTO n_current FROM conflict_flags WHERE is_current = TRUE;

  RAISE NOTICE 'OD-14A: deleted % superseded conflict_flags rows (% current rows remain)',
    n_deleted, n_current;

  IF n_deleted > 95000 THEN
    RAISE EXCEPTION 'OD-14A sanity: deleted % rows, expected <= ~85K', n_deleted;
  END IF;
  IF n_current < 15000 THEN
    RAISE EXCEPTION 'OD-14A sanity: only % current flags remain, expected ~18K', n_current;
  END IF;
END $$;

-- ── B. city_permits: trim pre-2013, drop never-scanned indexes ─────────────
-- NULL-dated rows (25,869 as of 2026-07-05) are deliberately kept: COALESCE(...)
-- < DATE yields NULL for them, which does not match.

DO $$
DECLARE n_deleted BIGINT;
BEGIN
  DELETE FROM city_permits
  WHERE COALESCE(issued_date, applied_date) < DATE '2013-01-01';
  GET DIAGNOSTICS n_deleted = ROW_COUNT;
  RAISE NOTICE 'OD-14B: deleted % pre-2013 city_permits rows', n_deleted;
  IF n_deleted > 40000 THEN
    RAISE EXCEPTION 'OD-14B sanity: deleted % rows, expected ~30K', n_deleted;
  END IF;
END $$;

-- 0 idx_scan since DB creation (2026-02); scanner + quality checks read these
-- tables via seq scans. Recreate DDL: src/migrations/039_socrata_regulatory_datasets.sql.
DROP INDEX IF EXISTS idx_city_permits_job_value;
DROP INDEX IF EXISTS idx_city_permits_type;
DROP INDEX IF EXISTS idx_city_permits_applied_by;
DROP INDEX IF EXISTS idx_city_permits_status;
DROP INDEX IF EXISTS idx_city_permits_address;
DROP INDEX IF EXISTS idx_city_permits_applied;

-- ── C. city_expenditures: trim FY2022–2023, drop never-scanned index ───────

DO $$
DECLARE n_deleted BIGINT;
BEGIN
  DELETE FROM city_expenditures
  WHERE fiscal_year IN ('2022', '2023');
  GET DIAGNOSTICS n_deleted = ROW_COUNT;
  RAISE NOTICE 'OD-14C: deleted % FY2022–2023 city_expenditures rows', n_deleted;
  IF n_deleted > 70000 THEN
    RAISE EXCEPTION 'OD-14C sanity: deleted % rows, expected ~58K', n_deleted;
  END IF;
END $$;

-- Recreate DDL: src/migrations/023_city_expenditures.sql.
DROP INDEX IF EXISTS idx_city_expenditures_amount;

-- ── D. Single-column city_fips indexes (Phase 3 drop list) ─────────────────
-- The DB is single-tenant; these indexes have zero selectivity benefit and cost
-- write amplification. Sanctioned by .claude/rules/conventions.md "FIPS
-- Enforcement". Recreate DDL lives in the migration cited on each line.
-- Composite and partial (predicate-carrying) city_fips indexes are kept.

DROP INDEX IF EXISTS idx_scan_runs_city;                 -- 001
DROP INDEX IF EXISTS idx_sync_log_city;                  -- 001
DROP INDEX IF EXISTS idx_feedback_city;                  -- 002
DROP INDEX IF EXISTS idx_nextrequest_city;               -- 003
DROP INDEX IF EXISTS idx_city_employees_fips;            -- 004
DROP INDEX IF EXISTS idx_commissions_fips;               -- 005
DROP INDEX IF EXISTS idx_commission_members_fips;        -- 005
DROP INDEX IF EXISTS idx_city_expenditures_fips;         -- 023
DROP INDEX IF EXISTS idx_court_cases_city;               -- 024
DROP INDEX IF EXISTS idx_court_matches_city;             -- 024
DROP INDEX IF EXISTS idx_ie_city_fips;                   -- 029
DROP INDEX IF EXISTS idx_meetings_city_fips;             -- 034/038
DROP INDEX IF EXISTS idx_bodies_fips;                    -- 035
DROP INDEX IF EXISTS idx_city_permits_fips;              -- 039
DROP INDEX IF EXISTS idx_city_licenses_fips;             -- 039
DROP INDEX IF EXISTS idx_city_code_cases_fips;           -- 039
DROP INDEX IF EXISTS idx_city_service_requests_fips;     -- 039
DROP INDEX IF EXISTS idx_city_projects_fips;             -- 039
DROP INDEX IF EXISTS idx_organizations_fips;             -- 040
DROP INDEX IF EXISTS idx_entity_links_fips;              -- 040
DROP INDEX IF EXISTS idx_behested_fips;                  -- 044
DROP INDEX IF EXISTS idx_lobbyist_fips;                  -- 044
DROP INDEX IF EXISTS idx_topics_city_fips;               -- 049
DROP INDEX IF EXISTS idx_elections_city;                 -- 051
DROP INDEX IF EXISTS idx_ec_city;                        -- 051
DROP INDEX IF EXISTS idx_comments_city_fips;             -- 068
DROP INDEX IF EXISTS idx_operator_config_fips;           -- 074
DROP INDEX IF EXISTS idx_fpb_city;                       -- 099
DROP INDEX IF EXISTS idx_neighborhood_councils_city_fips; -- 109
DROP INDEX IF EXISTS idx_documents_city_fips;            -- schema.sql
DROP INDEX IF EXISTS idx_officials_city;                 -- schema.sql
DROP INDEX IF EXISTS idx_meetings_city;                  -- schema.sql (duplicate of idx_meetings_city_fips)
DROP INDEX IF EXISTS idx_donors_city;                    -- schema.sql
DROP INDEX IF EXISTS idx_committees_city;                -- schema.sql
DROP INDEX IF EXISTS idx_contributions_city;             -- schema.sql
DROP INDEX IF EXISTS idx_flags_city;                     -- schema.sql
DROP INDEX IF EXISTS idx_cpra_city;                      -- schema.sql

-- ── E. Embedding sidecars → halfvec(1536) ──────────────────────────────────
-- HNSW indexes must be dropped BEFORE the type change: ALTER COLUMN TYPE
-- rebuilds dependent indexes with their existing operator class, and
-- vector_cosine_ops cannot index a halfvec column.

DROP INDEX IF EXISTS idx_agenda_items_embeddings_hnsw;
DROP INDEX IF EXISTS idx_meetings_embeddings_hnsw;
DROP INDEX IF EXISTS idx_officials_embeddings_hnsw;
DROP INDEX IF EXISTS idx_motions_embeddings_hnsw;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'agenda_items_embeddings',
    'meetings_embeddings',
    'officials_embeddings',
    'motions_embeddings'
  ] LOOP
    IF EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = t
        AND column_name = 'embedding'
        AND udt_name = 'vector'
    ) THEN
      EXECUTE format(
        'ALTER TABLE %I ALTER COLUMN embedding TYPE halfvec(1536) USING embedding::halfvec(1536)',
        t
      );
      RAISE NOTICE 'OD-14E: % converted to halfvec(1536)', t;
    ELSE
      RAISE NOTICE 'OD-14E: % already halfvec, skipping', t;
    END IF;
  END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_agenda_items_embeddings_hnsw
  ON agenda_items_embeddings USING hnsw (embedding halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_meetings_embeddings_hnsw
  ON meetings_embeddings USING hnsw (embedding halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_officials_embeddings_hnsw
  ON officials_embeddings USING hnsw (embedding halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_motions_embeddings_hnsw
  ON motions_embeddings USING hnsw (embedding halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ── F. RPC rewrites for halfvec ────────────────────────────────────────────
-- Bodies are migration 111's definitions with exactly one kind of edit: every
-- comparison against p_query_embedding casts it to halfvec(1536), and
-- find_similar_items' local variable is declared halfvec(1536). Signatures are
-- unchanged so PostgREST callers (web/src/lib/queries/search.ts) need no change.

CREATE OR REPLACE FUNCTION search_hybrid(
  p_query TEXT,
  p_query_embedding vector(1536) DEFAULT NULL,
  p_city_fips TEXT DEFAULT '0660620',
  p_result_type TEXT DEFAULT NULL,
  p_limit INT DEFAULT 20,
  p_offset INT DEFAULT 0
)
RETURNS TABLE (
  id UUID,
  result_type TEXT,
  title TEXT,
  snippet TEXT,
  url_path TEXT,
  relevance_score REAL,
  match_type TEXT,
  metadata JSONB
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  tsq tsquery;
  k CONSTANT INT := 60;  -- RRF constant
BEGIN
  tsq := plainto_tsquery('english', p_query);

  RETURN QUERY
  WITH
  fts_results AS (
    SELECT * FROM search_site(p_query, p_city_fips, p_result_type, 50, 0)
  ),
  fts_ranked AS (
    SELECT
      f.id, f.result_type, f.title, f.snippet, f.url_path,
      f.relevance_score, f.metadata,
      ROW_NUMBER() OVER (ORDER BY f.relevance_score DESC) AS fts_rank
    FROM fts_results f
  ),

  vec_results AS (
    SELECT * FROM (
      SELECT
        ai.id,
        'agenda_item'::TEXT AS result_type,
        ai.title,
        left(coalesce(ai.plain_language_summary, ai.description, ''), 160) AS snippet,
        '/meetings/' || ai.meeting_id AS url_path,
        (1 - (aie.embedding <=> p_query_embedding::halfvec(1536)))::REAL AS sim_score,
        jsonb_build_object(
          'meeting_date', m.meeting_date,
          'category', ai.category,
          'item_number', ai.item_number,
          'topic_label', ai.topic_label
        ) AS metadata
      FROM agenda_items_embeddings aie
      JOIN agenda_items ai ON ai.id = aie.id
      JOIN meetings m ON m.id = ai.meeting_id
      WHERE p_query_embedding IS NOT NULL
        AND m.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'agenda_item')
      ORDER BY aie.embedding <=> p_query_embedding::halfvec(1536)
      LIMIT 50
    ) ai_sub

    UNION ALL

    SELECT * FROM (
      SELECT
        mo.id,
        'vote_explainer'::TEXT,
        coalesce(ai.title, 'Motion on item ' || ai.item_number),
        left(coalesce(mo.vote_explainer, ''), 160),
        '/meetings/' || m.id,
        (1 - (moe.embedding <=> p_query_embedding::halfvec(1536)))::REAL,
        jsonb_build_object(
          'meeting_date', m.meeting_date,
          'agenda_item_title', ai.title
        )
      FROM motions_embeddings moe
      JOIN motions mo ON mo.id = moe.id
      JOIN agenda_items ai ON ai.id = mo.agenda_item_id
      JOIN meetings m ON m.id = ai.meeting_id
      WHERE p_query_embedding IS NOT NULL
        AND m.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'vote_explainer')
      ORDER BY moe.embedding <=> p_query_embedding::halfvec(1536)
      LIMIT 50
    ) mo_sub

    UNION ALL

    SELECT * FROM (
      SELECT
        o.id,
        'official'::TEXT,
        o.name,
        left(coalesce(o.bio_summary, ''), 160),
        '/council/' || lower(regexp_replace(regexp_replace(o.name, '\s+', '-', 'g'), '[^a-z0-9-]', '', 'g')),
        (1 - (oe.embedding <=> p_query_embedding::halfvec(1536)))::REAL,
        jsonb_build_object('role', o.role, 'is_current', o.is_current)
      FROM officials_embeddings oe
      JOIN officials o ON o.id = oe.id
      WHERE p_query_embedding IS NOT NULL
        AND o.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'official')
      ORDER BY oe.embedding <=> p_query_embedding::halfvec(1536)
      LIMIT 20
    ) o_sub

    UNION ALL

    SELECT * FROM (
      SELECT
        m.id,
        'meeting'::TEXT,
        initcap(coalesce(m.meeting_type, 'regular')) || ' Meeting — ' ||
          to_char(m.meeting_date, 'FMMonth DD, YYYY'),
        left(coalesce(m.meeting_summary, ''), 160),
        '/meetings/' || m.id,
        (1 - (me.embedding <=> p_query_embedding::halfvec(1536)))::REAL,
        jsonb_build_object('meeting_date', m.meeting_date, 'meeting_type', m.meeting_type)
      FROM meetings_embeddings me
      JOIN meetings m ON m.id = me.id
      WHERE p_query_embedding IS NOT NULL
        AND m.city_fips = p_city_fips
        AND (p_result_type IS NULL OR p_result_type = 'meeting')
      ORDER BY me.embedding <=> p_query_embedding::halfvec(1536)
      LIMIT 20
    ) m_sub
  ),
  vec_ranked AS (
    SELECT
      v.id, v.result_type, v.title, v.snippet, v.url_path,
      v.sim_score, v.metadata,
      ROW_NUMBER() OVER (ORDER BY v.sim_score DESC) AS vec_rank
    FROM vec_results v
    WHERE v.sim_score > 0.2
  ),

  merged AS (
    SELECT
      coalesce(f.id, v.id) AS id,
      coalesce(f.result_type, v.result_type) AS result_type,
      coalesce(f.title, v.title) AS title,
      coalesce(f.snippet, v.snippet) AS snippet,
      coalesce(f.url_path, v.url_path) AS url_path,
      (coalesce(1.0 / (k + f.fts_rank), 0) +
       coalesce(1.0 / (k + v.vec_rank), 0))::REAL AS relevance_score,
      CASE
        WHEN f.id IS NOT NULL AND v.id IS NOT NULL THEN 'both'
        WHEN f.id IS NOT NULL THEN 'keyword'
        ELSE 'semantic'
      END AS match_type,
      coalesce(f.metadata, v.metadata) AS metadata
    FROM fts_ranked f
    FULL OUTER JOIN vec_ranked v
      ON f.id = v.id AND f.result_type = v.result_type
  )

  SELECT m.id, m.result_type, m.title, m.snippet, m.url_path,
         m.relevance_score, m.match_type, m.metadata
  FROM merged m
  ORDER BY m.relevance_score DESC
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;

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
  source_embedding halfvec(1536);
BEGIN
  SELECT aie.embedding INTO source_embedding
  FROM agenda_items_embeddings aie
  WHERE aie.id = p_item_id;

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
    (1 - (aie.embedding <=> source_embedding))::REAL AS similarity,
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
  FROM agenda_items_embeddings aie
  JOIN agenda_items ai ON ai.id = aie.id
  JOIN meetings m ON m.id = ai.meeting_id
  LEFT JOIN LATERAL (
    SELECT mo2.id, mo2.result AS motion_result
    FROM motions mo2
    WHERE mo2.agenda_item_id = ai.id
    ORDER BY mo2.id
    LIMIT 1
  ) mo ON true
  WHERE ai.id != p_item_id
    AND m.city_fips = p_city_fips
    AND (1 - (aie.embedding <=> source_embedding)) > 0.3
  ORDER BY aie.embedding <=> source_embedding
  LIMIT p_limit;
END;
$$;
