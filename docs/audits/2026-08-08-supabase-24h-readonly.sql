-- Supabase 24-hour idle/growth/RPC snapshot for Richmond Commons.
--
-- Read-only by construction: this file contains one SELECT statement. Run it
-- through Supabase's /database/query/read-only management endpoint using
-- scripts/capture-supabase-24h.ps1. Capture a baseline, then run the identical
-- query at least 24 hours later and compare cumulative-counter deltas. The
-- PostgreSQL statistics reset timestamps in the result make invalid deltas
-- explicit.

WITH
db_stats AS (
    SELECT d.datname,
           pg_database_size(d.datname) AS database_bytes,
           d.numbackends,
           d.xact_commit,
           d.xact_rollback,
           d.blks_read,
           d.blks_hit,
           d.tup_returned,
           d.tup_fetched,
           d.tup_inserted,
           d.tup_updated,
           d.tup_deleted,
           d.conflicts,
           d.temp_files,
           d.temp_bytes,
           d.deadlocks,
           d.blk_read_time,
           d.blk_write_time,
           d.session_time,
           d.active_time,
           d.idle_in_transaction_time,
           d.sessions,
           d.sessions_abandoned,
           d.sessions_fatal,
           d.sessions_killed,
           d.stats_reset
      FROM pg_stat_database d
     WHERE d.datname = current_database()
),
activity AS (
    SELECT COALESCE(state, '<none>') AS state,
           backend_type,
           count(*) AS connections,
           max(clock_timestamp() - state_change) AS oldest_state_age,
           max(clock_timestamp() - xact_start)
               FILTER (WHERE xact_start IS NOT NULL) AS oldest_transaction_age,
           max(clock_timestamp() - query_start)
               FILTER (WHERE state = 'active' AND query_start IS NOT NULL)
               AS oldest_active_query_age
      FROM pg_stat_activity
     WHERE datname = current_database()
       AND pid <> pg_backend_pid()
     GROUP BY COALESCE(state, '<none>'), backend_type
),
table_totals AS (
    SELECT count(*) AS public_tables,
           sum(pg_total_relation_size(s.relid)) AS public_total_bytes,
           sum(pg_relation_size(s.relid)) AS public_heap_bytes,
           sum(pg_indexes_size(s.relid)) AS public_index_bytes,
           sum(s.n_live_tup) AS estimated_live_rows,
           sum(s.n_dead_tup) AS estimated_dead_rows,
           sum(s.n_tup_ins) AS tuples_inserted,
           sum(s.n_tup_upd) AS tuples_updated,
           sum(s.n_tup_del) AS tuples_deleted,
           sum(s.seq_scan) AS sequential_scans,
           sum(s.idx_scan) AS index_scans
      FROM pg_stat_user_tables s
     WHERE s.schemaname = 'public'
),
largest_relations AS (
    SELECT s.relname,
           pg_total_relation_size(s.relid) AS total_bytes,
           pg_relation_size(s.relid) AS heap_bytes,
           pg_indexes_size(s.relid) AS index_bytes,
           s.n_live_tup,
           s.n_dead_tup,
           s.n_tup_ins,
           s.n_tup_upd,
           s.n_tup_del,
           s.seq_scan,
           s.idx_scan,
           s.last_autovacuum,
           s.last_autoanalyze
      FROM pg_stat_user_tables s
     WHERE s.schemaname = 'public'
     ORDER BY pg_total_relation_size(s.relid) DESC, s.relname
     LIMIT 25
),
rpc_catalog AS (
    SELECT p.oid,
           p.proname,
           pg_get_function_identity_arguments(p.oid) AS identity_arguments,
           pg_get_function_result(p.oid) AS result_type,
           pg_get_userbyid(p.proowner) AS owner,
           l.lanname AS language,
           p.prosecdef AS security_definer,
           p.provolatile AS volatility,
           p.proconfig,
           has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_execute,
           has_function_privilege('authenticated', p.oid, 'EXECUTE')
               AS authenticated_execute,
           has_function_privilege('service_role', p.oid, 'EXECUTE')
               AS service_role_execute,
           p.proname = ANY (ARRAY[
               'get_category_stats',
               'get_controversial_items',
               'get_contested_votes',
               'get_divergent_motions_detail',
               'get_meeting_counts',
               'get_meeting_flag_counts',
               'search_site',
               'search_hybrid',
               'find_similar_items',
               'reserve_llm_cost',
               'settle_llm_cost_reservation',
               'get_meeting_coverage_stats',
               'check_and_increment_rate_limit',
               'list_public_tables',
               'claim_due_source_change_jobs',
               'retry_source_change_job'
           ]) AS referenced_in_repository
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace
      JOIN pg_language l ON l.oid = p.prolang
     WHERE n.nspname = 'public'
       AND p.prokind = 'f'
),
rpc_statement_stats AS (
    -- PostgREST statements include the invoked function name in the normalized
    -- SQL. This is a bounded historical-use heuristic, not per-function
    -- instrumentation. track_functions is recorded below (normally "none").
    SELECT r.oid,
           COALESCE(sum(s.calls), 0)::bigint AS matching_statement_calls,
           COALESCE(sum(s.total_exec_time), 0)::double precision
               AS matching_total_exec_ms,
           COALESCE(sum(s.rows), 0)::bigint AS matching_rows,
           COALESCE(sum(s.shared_blks_hit), 0)::bigint AS matching_shared_hits,
           COALESCE(sum(s.shared_blks_read), 0)::bigint AS matching_shared_reads,
           COALESCE(sum(s.temp_blks_written), 0)::bigint
               AS matching_temp_blocks_written
      FROM rpc_catalog r
      LEFT JOIN extensions.pg_stat_statements s
        ON s.dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
       -- PostgREST emits quoted identifiers (for example,
       -- "public"."get_meeting_counts"(...)); direct SQL may be unquoted.
       -- Accept the optional closing identifier quote so both shapes count.
       AND s.query ~* (
           E'(^|[^a-zA-Z0-9_])' || r.proname || E'"?\\s*\\('
       )
     GROUP BY r.oid
),
rpc_surface AS (
    SELECT r.proname,
           r.identity_arguments,
           r.result_type,
           r.owner,
           r.language,
           r.security_definer,
           r.volatility,
           r.proconfig,
           r.anon_execute,
           r.authenticated_execute,
           r.service_role_execute,
           r.referenced_in_repository,
           s.matching_statement_calls,
           s.matching_total_exec_ms,
           s.matching_rows,
           s.matching_shared_hits,
           s.matching_shared_reads,
           s.matching_temp_blocks_written
      FROM rpc_catalog r
      JOIN rpc_statement_stats s USING (oid)
     ORDER BY r.proname, r.identity_arguments
),
top_statements AS (
    SELECT queryid,
           calls,
           total_exec_time,
           mean_exec_time,
           rows,
           shared_blks_hit,
           shared_blks_read,
           temp_blks_written,
           left(regexp_replace(query, E'[\\n\\r\\t]+', ' ', 'g'), 300) AS query
      FROM extensions.pg_stat_statements
     WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
     ORDER BY total_exec_time DESC
     LIMIT 20
)
SELECT jsonb_build_object(
    'observed_at', clock_timestamp(),
    'database', (SELECT to_jsonb(db_stats) FROM db_stats),
    'activity', COALESCE(
        (SELECT jsonb_agg(to_jsonb(activity) ORDER BY backend_type, state)
           FROM activity),
        '[]'::jsonb
    ),
    'table_totals', (SELECT to_jsonb(table_totals) FROM table_totals),
    'largest_relations', COALESCE(
        (SELECT jsonb_agg(to_jsonb(largest_relations)
                          ORDER BY total_bytes DESC, relname)
           FROM largest_relations),
        '[]'::jsonb
    ),
    'rpc_summary', jsonb_build_object(
        'track_functions', current_setting('track_functions'),
        'function_count', (SELECT count(*) FROM rpc_catalog),
        'repository_referenced_count',
            (SELECT count(*) FROM rpc_catalog WHERE referenced_in_repository),
        'anon_executable_count',
            (SELECT count(*) FROM rpc_catalog WHERE anon_execute),
        'authenticated_executable_count',
            (SELECT count(*) FROM rpc_catalog WHERE authenticated_execute),
        'service_role_executable_count',
            (SELECT count(*) FROM rpc_catalog WHERE service_role_execute),
        'security_definer_count',
            (SELECT count(*) FROM rpc_catalog WHERE security_definer),
        'anon_security_definer_count',
            (SELECT count(*) FROM rpc_catalog
              WHERE security_definer AND anon_execute),
        'pg_stat_statements_reset',
            (SELECT stats_reset FROM extensions.pg_stat_statements_info)
    ),
    'rpc_surface', COALESCE(
        (SELECT jsonb_agg(to_jsonb(rpc_surface)
                          ORDER BY proname, identity_arguments)
           FROM rpc_surface),
        '[]'::jsonb
    ),
    'top_statements', COALESCE(
        (SELECT jsonb_agg(to_jsonb(top_statements)
                          ORDER BY total_exec_time DESC)
           FROM top_statements),
        '[]'::jsonb
    )
) AS snapshot;
