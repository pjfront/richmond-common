-- Richmond Commons Preview schema baseline
-- Schema-only capture of production public DDL at migration 20260807013300.
-- Contains no production rows. Never apply this file to production.

--
-- PostgreSQL database dump
--


-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.10

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA extensions VERSION '1.1';
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions VERSION '1.3';
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions VERSION '0.8.2';


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: check_and_increment_rate_limit(text, integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.check_and_increment_rate_limit(p_bucket_key text, p_window_secs integer, p_max_count integer) RETURNS TABLE(allowed boolean, retry_after_secs integer)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
DECLARE
  v_window_start TIMESTAMPTZ;
  v_count INTEGER;
BEGIN
  v_window_start := to_timestamp(
    (EXTRACT(EPOCH FROM NOW())::BIGINT / p_window_secs) * p_window_secs
  );

  INSERT INTO rate_limit_buckets (bucket_key, window_start, count)
  VALUES (p_bucket_key, v_window_start, 1)
  ON CONFLICT (bucket_key, window_start)
  DO UPDATE SET count = rate_limit_buckets.count + 1
  RETURNING count INTO v_count;

  RETURN QUERY SELECT
    v_count <= p_max_count,
    GREATEST(
      0,
      p_window_secs - EXTRACT(EPOCH FROM (NOW() - v_window_start))::INTEGER
    );
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: source_change_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_change_jobs (
    change_id character varying(64) NOT NULL,
    city_fips character varying(7) DEFAULT '0660620'::character varying NOT NULL,
    source character varying(50) NOT NULL,
    watcher_source character varying(50) NOT NULL,
    fingerprint jsonb NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    attempt_count integer DEFAULT 0 NOT NULL,
    dispatch_generation integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 5 NOT NULL,
    next_attempt_at timestamp with time zone DEFAULT now() NOT NULL,
    lease_expires_at timestamp with time zone,
    dispatched_at timestamp with time zone,
    started_at timestamp with time zone,
    base_completed_at timestamp with time zone,
    completed_at timestamp with time zone,
    pipeline_run_id character varying(100),
    last_error text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT source_change_jobs_attempt_count_check CHECK ((attempt_count >= 0)),
    CONSTRAINT source_change_jobs_change_id_format CHECK (((change_id)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT source_change_jobs_dispatch_generation_check CHECK ((dispatch_generation >= 0)),
    CONSTRAINT source_change_jobs_max_attempts_check CHECK ((max_attempts > 0)),
    CONSTRAINT source_change_jobs_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'dispatched'::character varying, 'running'::character varying, 'retry_wait'::character varying, 'succeeded'::character varying, 'dead_letter'::character varying])::text[])))
);


--
-- Name: TABLE source_change_jobs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.source_change_jobs IS 'Private durable delivery and completion state for source-change events.';


--
-- Name: COLUMN source_change_jobs.base_completed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.source_change_jobs.base_completed_at IS 'Set after the source phase succeeds; retries may resume at enrichment.';


--
-- Name: claim_due_source_change_jobs(character varying, integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.claim_due_source_change_jobs(p_change_id character varying DEFAULT NULL::character varying, p_limit integer DEFAULT 25, p_lease_minutes integer DEFAULT 360) RETURNS SETOF public.source_change_jobs
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
BEGIN
    RETURN QUERY
    WITH due AS MATERIALIZED (
        SELECT j.change_id
        FROM source_change_jobs AS j
        WHERE (p_change_id IS NULL OR j.change_id = p_change_id)
          AND (
              (j.status IN ('pending', 'retry_wait')
               AND j.next_attempt_at <= NOW())
              OR
              (j.status IN ('dispatched', 'running')
               AND COALESCE(j.lease_expires_at, NOW()) <= NOW())
          )
        ORDER BY j.next_attempt_at, j.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 25), 100))
    ), dead AS (
        UPDATE source_change_jobs AS j
        SET status = 'dead_letter',
            lease_expires_at = NULL,
            completed_at = NOW(),
            last_error = COALESCE(
                j.last_error,
                'Dispatch or worker lease expired after maximum attempts'
            ),
            updated_at = NOW()
        FROM due
        WHERE j.change_id = due.change_id
          AND j.attempt_count >= j.max_attempts
        RETURNING j.*
    ), claimed AS (
        UPDATE source_change_jobs AS j
        SET status = 'dispatched',
            attempt_count = j.attempt_count + 1,
            dispatch_generation = j.dispatch_generation + 1,
            dispatched_at = NOW(),
            lease_expires_at = NOW()
                + make_interval(mins => GREATEST(1, p_lease_minutes)),
            completed_at = NULL,
            pipeline_run_id = NULL,
            updated_at = NOW()
        FROM due
        WHERE j.change_id = due.change_id
          AND j.attempt_count < j.max_attempts
        RETURNING j.*
    )
    SELECT * FROM dead
    UNION ALL
    SELECT * FROM claimed;
END;
$$;


--
-- Name: claim_source_change_job(character varying, character varying, integer, character varying, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.claim_source_change_job(p_change_id character varying, p_source character varying, p_dispatch_generation integer, p_pipeline_run_id character varying DEFAULT NULL::character varying, p_lease_minutes integer DEFAULT 420) RETURNS SETOF public.source_change_jobs
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
    UPDATE source_change_jobs AS j
    SET status = 'running',
        started_at = NOW(),
        lease_expires_at = NOW()
            + make_interval(mins => GREATEST(1, p_lease_minutes)),
        pipeline_run_id = p_pipeline_run_id,
        completed_at = NULL,
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND j.source = p_source
      AND j.status = 'dispatched'
      AND j.dispatch_generation = p_dispatch_generation
      AND j.lease_expires_at > NOW()
    RETURNING j.*;
$$;


--
-- Name: cleanup_rate_limit_buckets(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.cleanup_rate_limit_buckets() RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
DECLARE
  v_deleted INTEGER;
BEGIN
  DELETE FROM rate_limit_buckets
   WHERE window_start < NOW() - INTERVAL '1 day';
  GET DIAGNOSTICS v_deleted = ROW_COUNT;
  RETURN v_deleted;
END;
$$;


--
-- Name: complete_source_change_job(character varying, character varying, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.complete_source_change_job(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer) RETURNS SETOF public.source_change_jobs
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
    UPDATE source_change_jobs AS j
    SET status = 'succeeded',
        lease_expires_at = NULL,
        next_attempt_at = NOW(),
        completed_at = NOW(),
        last_error = NULL,
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND j.status = 'running'
      AND j.base_completed_at IS NOT NULL
      AND j.dispatch_generation = p_dispatch_generation
      AND j.pipeline_run_id IS NOT DISTINCT FROM p_pipeline_run_id
      AND j.lease_expires_at > NOW()
    RETURNING j.*;
$$;


--
-- Name: continue_source_change_job(character varying, character varying, integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.continue_source_change_job(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer, p_delay_seconds integer DEFAULT 60) RETURNS SETOF public.source_change_jobs
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
    UPDATE source_change_jobs AS j
    SET status = 'retry_wait',
        attempt_count = GREATEST(j.attempt_count - 1, 0),
        next_attempt_at = NOW() + make_interval(
            secs => GREATEST(1, LEAST(COALESCE(p_delay_seconds, 60), 900))
        ),
        lease_expires_at = NULL,
        completed_at = NULL,
        last_error = NULL,
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND j.status = 'running'
      AND j.base_completed_at IS NOT NULL
      AND j.dispatch_generation = p_dispatch_generation
      AND j.pipeline_run_id IS NOT DISTINCT FROM p_pipeline_run_id
      AND j.lease_expires_at > NOW()
    RETURNING j.*;
$$;


--
-- Name: find_similar_items(uuid, text, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.find_similar_items(p_item_id uuid, p_city_fips text DEFAULT '0660620'::text, p_limit integer DEFAULT 5) RETURNS TABLE(id uuid, title text, summary_headline text, meeting_id uuid, meeting_date date, item_number text, similarity real, vote_outcome text, public_comment_count integer, financial_amount text, category text, topic_label text)
    LANGUAGE plpgsql STABLE
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


--
-- Name: get_category_stats(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_category_stats(p_city_fips text DEFAULT '0660620'::text) RETURNS TABLE(category text, item_count bigint, vote_count bigint, split_vote_count bigint, unanimous_vote_count bigint, avg_controversy_score numeric, max_controversy_score numeric, total_public_comments bigint, percentage_of_agenda numeric)
    LANGUAGE plpgsql STABLE
    AS $$
BEGIN
  RETURN QUERY
  WITH first_motion_votes AS (
    SELECT DISTINCT ON (mo.agenda_item_id)
      mo.agenda_item_id AS fmv_item_id,
      count(*) FILTER (WHERE v.vote_choice = 'aye') AS fmv_ayes,
      count(*) FILTER (WHERE v.vote_choice = 'nay') AS fmv_nays
    FROM motions mo
    JOIN votes v ON v.motion_id = mo.id
    GROUP BY mo.id, mo.agenda_item_id
    ORDER BY mo.agenda_item_id, mo.id
  ),
  motion_counts AS (
    SELECT mo2.agenda_item_id AS mc_item_id, count(*)::INT AS mc_count
    FROM motions mo2
    GROUP BY mo2.agenda_item_id
  ),
  item_scores AS (
    SELECT
      ai.id AS item_id,
      COALESCE(ai.category, 'other') AS item_cat,
      COALESCE(mc.mc_count, 0) AS item_motion_count,
      fmv.fmv_ayes,
      fmv.fmv_nays,
      COALESCE(ai.public_comment_count, 0) AS item_comment_count,
      CASE
        WHEN ai.is_consent_calendar THEN 0.0
        ELSE round((
          LEAST(COALESCE(ai.public_comment_count, 0)::NUMERIC, 1) * 8.5
          + CASE
              WHEN fmv.fmv_ayes IS NULL OR (fmv.fmv_ayes + fmv.fmv_nays) = 0 THEN 0.0
              ELSE (1.0 - abs(fmv.fmv_ayes - fmv.fmv_nays)::NUMERIC / (fmv.fmv_ayes + fmv.fmv_nays)) * 1.0
            END
          + CASE WHEN mc.mc_count > 1 THEN 0.5 ELSE 0 END
        )::NUMERIC, 1)
      END AS item_controversy_score
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN first_motion_votes fmv ON fmv.fmv_item_id = ai.id
    LEFT JOIN motion_counts mc ON mc.mc_item_id = ai.id
    WHERE mt.city_fips = p_city_fips
  ),
  total AS (
    SELECT count(*) AS total_items FROM item_scores
  )
  SELECT
    s.item_cat::TEXT,
    count(*)::BIGINT,
    COALESCE(sum(s.item_motion_count), 0)::BIGINT,
    count(*) FILTER (WHERE s.fmv_nays > 0)::BIGINT,
    count(*) FILTER (WHERE s.fmv_ayes IS NOT NULL AND s.fmv_nays = 0)::BIGINT,
    CASE
      WHEN count(*) FILTER (WHERE s.item_controversy_score IS NOT NULL) > 0
      THEN round(avg(s.item_controversy_score)::NUMERIC, 1)
      ELSE 0
    END,
    COALESCE(max(s.item_controversy_score), 0),
    COALESCE(sum(s.item_comment_count), 0)::BIGINT,
    round((count(*)::NUMERIC / NULLIF((SELECT total_items FROM total), 0) * 100)::NUMERIC, 1)
  FROM item_scores s
  GROUP BY s.item_cat
  ORDER BY count(*) DESC;
END;
$$;


--
-- Name: get_contested_votes(text, uuid[]); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_contested_votes(p_city_fips text DEFAULT '0660620'::text, p_official_ids uuid[] DEFAULT NULL::uuid[]) RETURNS TABLE(motion_id uuid, official_id uuid, official_name text, vote_choice text, category text)
    LANGUAGE plpgsql STABLE
    AS $$
BEGIN
  RETURN QUERY
  WITH city_votes AS (
    SELECT
      v.motion_id,
      v.official_id,
      v.official_name::TEXT,
      v.vote_choice::TEXT,
      ai.category::TEXT
    FROM votes v
    JOIN motions m ON m.id = v.motion_id
    JOIN agenda_items ai ON ai.id = m.agenda_item_id
    JOIN meetings mt ON mt.id = ai.meeting_id
    WHERE mt.city_fips = p_city_fips
      AND v.official_id IS NOT NULL
      AND v.vote_choice IN ('aye', 'nay')
      AND (p_official_ids IS NULL OR v.official_id = ANY(p_official_ids))
  ),
  contested AS (
    SELECT cv.motion_id
    FROM city_votes cv
    GROUP BY cv.motion_id
    HAVING COUNT(DISTINCT cv.vote_choice) > 1
  )
  SELECT
    cv.motion_id,
    cv.official_id,
    cv.official_name,
    cv.vote_choice,
    cv.category
  FROM city_votes cv
  INNER JOIN contested c ON c.motion_id = cv.motion_id;
END;
$$;


--
-- Name: FUNCTION get_contested_votes(p_city_fips text, p_official_ids uuid[]); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.get_contested_votes(p_city_fips text, p_official_ids uuid[]) IS 'Contested aye/nay votes for a city. When p_official_ids is provided, votes are pre-filtered to those officials and contestedness is re-evaluated within that subset.';


--
-- Name: get_controversial_items(text, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_controversial_items(p_city_fips text DEFAULT '0660620'::text, p_limit integer DEFAULT 20) RETURNS TABLE(agenda_item_id uuid, meeting_id uuid, meeting_date date, item_number text, title text, category text, controversy_score numeric, vote_tally text, result text, public_comment_count bigint, motion_count bigint)
    LANGUAGE plpgsql STABLE
    AS $$
BEGIN
  RETURN QUERY
  WITH first_motion_votes AS (
    SELECT DISTINCT ON (mo.agenda_item_id)
      mo.agenda_item_id AS fmv_item_id,
      mo.vote_tally AS fmv_vote_tally,
      mo.result AS fmv_result,
      count(*) FILTER (WHERE v.vote_choice = 'aye') AS fmv_ayes,
      count(*) FILTER (WHERE v.vote_choice = 'nay') AS fmv_nays
    FROM motions mo
    JOIN votes v ON v.motion_id = mo.id
    GROUP BY mo.id, mo.agenda_item_id, mo.vote_tally, mo.result
    ORDER BY mo.agenda_item_id, mo.id
  ),
  motion_counts AS (
    SELECT mo2.agenda_item_id AS mc_item_id, count(*)::BIGINT AS mc_count
    FROM motions mo2
    GROUP BY mo2.agenda_item_id
  ),
  item_data AS (
    SELECT
      ai.id AS item_id,
      ai.meeting_id AS item_meeting_id,
      mt.meeting_date AS item_meeting_date,
      ai.item_number AS item_num,
      ai.title AS item_title,
      ai.category AS item_category,
      fmv.fmv_vote_tally,
      COALESCE(fmv.fmv_result, 'unknown') AS item_result,
      fmv.fmv_ayes,
      fmv.fmv_nays,
      COALESCE(mc.mc_count, 0) AS item_motion_count,
      COALESCE(ai.public_comment_count, 0)::BIGINT AS item_comment_count,
      -- Vote split closeness: 1.0 = tied, 0.0 = unanimous, NULL = no vote data
      CASE
        WHEN fmv.fmv_ayes IS NULL OR (fmv.fmv_ayes + fmv.fmv_nays) = 0 THEN 0.0
        ELSE (1.0 - abs(fmv.fmv_ayes - fmv.fmv_nays)::NUMERIC / (fmv.fmv_ayes + fmv.fmv_nays))
      END AS vote_split_factor
    FROM agenda_items ai
    JOIN meetings mt ON mt.id = ai.meeting_id
    LEFT JOIN first_motion_votes fmv ON fmv.fmv_item_id = ai.id
    LEFT JOIN motion_counts mc ON mc.mc_item_id = ai.id
    WHERE mt.city_fips = p_city_fips
      AND ai.is_consent_calendar = false
  )
  SELECT
    s.item_id,
    s.item_meeting_id,
    s.item_meeting_date,
    s.item_num::TEXT,
    s.item_title::TEXT,
    s.item_category::TEXT,
    -- Keep controversy_score column for backward compat; set to comment count
    s.item_comment_count::NUMERIC,
    s.fmv_vote_tally::TEXT,
    CASE WHEN s.fmv_ayes IS NOT NULL THEN s.item_result ELSE 'unknown' END::TEXT,
    s.item_comment_count,
    s.item_motion_count
  FROM item_data s
  WHERE s.item_comment_count > 0
     OR s.fmv_ayes IS NOT NULL
  ORDER BY
    s.item_comment_count DESC,
    s.vote_split_factor DESC,
    s.item_motion_count DESC
  LIMIT p_limit;
END;
$$;


--
-- Name: get_divergent_motions_detail(text, uuid[]); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_divergent_motions_detail(p_city_fips text DEFAULT '0660620'::text, p_official_ids uuid[] DEFAULT NULL::uuid[]) RETURNS TABLE(motion_id uuid, motion_text text, motion_result text, vote_tally text, meeting_id uuid, meeting_date date, agenda_item_id uuid, agenda_item_title text, agenda_item_number text, category text, topic_label text, is_procedural boolean, official_id uuid, official_name text, vote_choice text)
    LANGUAGE plpgsql STABLE
    AS $$
BEGIN
  RETURN QUERY
  WITH city_votes AS (
    SELECT
      v.motion_id,
      m.motion_text::TEXT AS motion_text,
      m.result::TEXT AS motion_result,
      m.vote_tally::TEXT AS vote_tally,
      ai.meeting_id,
      mt.meeting_date,
      ai.id AS agenda_item_id,
      ai.title::TEXT AS agenda_item_title,
      ai.item_number::TEXT AS agenda_item_number,
      ai.category::TEXT AS category,
      ai.topic_label::TEXT AS topic_label,
      (ai.category = 'procedural') AS is_procedural,
      v.official_id,
      v.official_name::TEXT AS official_name,
      v.vote_choice::TEXT AS vote_choice
    FROM votes v
    JOIN motions m ON m.id = v.motion_id
    JOIN agenda_items ai ON ai.id = m.agenda_item_id
    JOIN meetings mt ON mt.id = ai.meeting_id
    WHERE mt.city_fips = p_city_fips
      AND v.official_id IS NOT NULL
      AND v.vote_choice IN ('aye', 'nay', 'abstain', 'absent')
      AND (p_official_ids IS NULL OR v.official_id = ANY(p_official_ids))
  ),
  contested AS (
    SELECT cv.motion_id
    FROM city_votes cv
    WHERE cv.vote_choice IN ('aye', 'nay')
    GROUP BY cv.motion_id
    HAVING COUNT(DISTINCT cv.vote_choice) > 1
  )
  SELECT
    cv.motion_id,
    cv.motion_text,
    cv.motion_result,
    cv.vote_tally,
    cv.meeting_id,
    cv.meeting_date,
    cv.agenda_item_id,
    cv.agenda_item_title,
    cv.agenda_item_number,
    cv.category,
    cv.topic_label,
    cv.is_procedural,
    cv.official_id,
    cv.official_name,
    cv.vote_choice
  FROM city_votes cv
  INNER JOIN contested c ON c.motion_id = cv.motion_id;
END;
$$;


--
-- Name: FUNCTION get_divergent_motions_detail(p_city_fips text, p_official_ids uuid[]); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.get_divergent_motions_detail(p_city_fips text, p_official_ids uuid[]) IS 'Per-(motion, official) rows for contested motions in a city. When p_official_ids is provided, votes are pre-filtered to those officials and contestedness is re-evaluated within that subset.';


--
-- Name: get_meeting_counts(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_meeting_counts(p_city_fips text) RETURNS TABLE(meeting_id uuid, agenda_item_count bigint, vote_count bigint, categories jsonb, topic_labels jsonb)
    LANGUAGE plpgsql STABLE
    AS $$
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
$$;


--
-- Name: get_meeting_flag_counts(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_meeting_flag_counts(p_city_fips text) RETURNS TABLE(meeting_id uuid, flags_total bigint, flags_published bigint, items_scanned bigint)
    LANGUAGE sql STABLE
    AS $$
  WITH filtered_flags AS (
    SELECT
      cf.meeting_id,
      cf.confidence,
      cf.flag_type,
      -- Extract fields needed for government entity filtering from first evidence element
      cf.evidence->0->>'vendor' AS vendor,
      cf.evidence->0->>'match_type' AS match_type,
      cf.evidence->0->>'donor_employer' AS donor_employer
    FROM conflict_flags cf
    WHERE cf.city_fips = p_city_fips
      AND cf.is_current = true
  ),
  non_gov_flags AS (
    SELECT meeting_id, confidence
    FROM filtered_flags
    WHERE NOT (
      -- Case 1: donor_vendor_expenditure with government entity vendor
      (flag_type = 'donor_vendor_expenditure' AND vendor IS NOT NULL AND (
        lower(trim(vendor)) LIKE 'city of%'
        OR lower(trim(vendor)) LIKE 'city and county%'
        OR lower(trim(vendor)) LIKE 'city &%'
        OR lower(trim(vendor)) LIKE 'county of%'
        OR lower(trim(vendor)) LIKE 'state of%'
        OR lower(trim(vendor)) LIKE 'town of%'
        OR lower(trim(vendor)) LIKE 'district of%'
        OR lower(trim(vendor)) LIKE 'village of%'
        OR lower(trim(vendor)) LIKE 'borough of%'
        OR lower(trim(vendor)) LIKE '% county'
        OR lower(trim(vendor)) LIKE '% city'
        OR lower(trim(vendor)) LIKE '% state'
        OR lower(trim(vendor)) LIKE '% department'
      ))
      OR
      -- Case 2: employer-matched flags with government entity employer
      (match_type IS NOT NULL AND match_type LIKE 'employer_to_%' AND donor_employer IS NOT NULL AND (
        lower(trim(donor_employer)) LIKE 'city of%'
        OR lower(trim(donor_employer)) LIKE 'city and county%'
        OR lower(trim(donor_employer)) LIKE 'city &%'
        OR lower(trim(donor_employer)) LIKE 'county of%'
        OR lower(trim(donor_employer)) LIKE 'state of%'
        OR lower(trim(donor_employer)) LIKE 'town of%'
        OR lower(trim(donor_employer)) LIKE 'district of%'
        OR lower(trim(donor_employer)) LIKE 'village of%'
        OR lower(trim(donor_employer)) LIKE 'borough of%'
        OR lower(trim(donor_employer)) LIKE '% county'
        OR lower(trim(donor_employer)) LIKE '% city'
        OR lower(trim(donor_employer)) LIKE '% state'
        OR lower(trim(donor_employer)) LIKE '% department'
      ))
    )
  ),
  flag_agg AS (
    SELECT
      ngf.meeting_id,
      count(*) AS flags_total,
      count(*) FILTER (WHERE ngf.confidence >= 0.50) AS flags_published
    FROM non_gov_flags ngf
    GROUP BY ngf.meeting_id
  ),
  item_agg AS (
    SELECT ai.meeting_id, count(*) AS items_scanned
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
    GROUP BY ai.meeting_id
  )
  SELECT
    fa.meeting_id,
    fa.flags_total,
    fa.flags_published,
    COALESCE(ia.items_scanned, 0) AS items_scanned
  FROM flag_agg fa
  LEFT JOIN item_agg ia ON ia.meeting_id = fa.meeting_id;
$$;


--
-- Name: list_public_tables(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.list_public_tables() RETURNS TABLE(table_name text)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
  SELECT t.tablename::TEXT
  FROM pg_tables t
  WHERE t.schemaname = 'public'
  ORDER BY t.tablename;
$$;


--
-- Name: FUNCTION list_public_tables(); Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON FUNCTION public.list_public_tables() IS 'Returns public-schema table names. Used by /api/health to check applied migrations in one round-trip instead of probing each table individually.';


--
-- Name: mark_source_change_base_completed(character varying, character varying, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.mark_source_change_base_completed(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer) RETURNS SETOF public.source_change_jobs
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
    UPDATE source_change_jobs AS j
    SET base_completed_at = COALESCE(j.base_completed_at, NOW()),
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND j.status = 'running'
      AND j.dispatch_generation = p_dispatch_generation
      AND j.pipeline_run_id IS NOT DISTINCT FROM p_pipeline_run_id
      AND j.lease_expires_at > NOW()
    RETURNING j.*;
$$;


--
-- Name: merge_official_pair(uuid, uuid); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.merge_official_pair(p_keeper_id uuid, p_dupe_id uuid) RETURNS void
    LANGUAGE plpgsql
    AS $$
DECLARE
  v_rows int;
  v_keeper_name text;
  v_dupe_name text;
BEGIN
  -- Look up names for logging
  SELECT name INTO v_keeper_name FROM officials WHERE id = p_keeper_id;
  SELECT name INTO v_dupe_name FROM officials WHERE id = p_dupe_id;

  IF v_keeper_name IS NULL OR v_dupe_name IS NULL THEN
    RAISE NOTICE 'merge_official_pair: one or both IDs not found (keeper=%, dupe=%). Skipping.', p_keeper_id, p_dupe_id;
    RETURN;
  END IF;

  RAISE NOTICE 'Merging "%" (%) into "%" (%)', v_dupe_name, p_dupe_id, v_keeper_name, p_keeper_id;

  -- votes: no unique constraint on (motion_id, official_id), safe to update all
  UPDATE votes SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  votes: % rows rewired', v_rows; END IF;

  -- meeting_attendance: has UNIQUE (meeting_id, official_id)
  -- Delete dupe attendance where keeper already has a record for that meeting
  DELETE FROM meeting_attendance
  WHERE official_id = p_dupe_id
    AND meeting_id IN (
      SELECT meeting_id FROM meeting_attendance WHERE official_id = p_keeper_id
    );
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  meeting_attendance: % duplicate records removed', v_rows; END IF;

  -- Update remaining (non-conflicting) attendance records
  UPDATE meeting_attendance SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  meeting_attendance: % rows rewired', v_rows; END IF;

  -- committees
  UPDATE committees SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  committees: % rows rewired', v_rows; END IF;

  -- form700_filings
  UPDATE form700_filings SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  form700_filings: % rows rewired', v_rows; END IF;

  -- economic_interests
  UPDATE economic_interests SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  economic_interests: % rows rewired', v_rows; END IF;

  -- conflict_flags
  UPDATE conflict_flags SET official_id = p_keeper_id WHERE official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  conflict_flags: % rows rewired', v_rows; END IF;

  -- commission_members (appointed_by_official_id)
  UPDATE commission_members SET appointed_by_official_id = p_keeper_id
  WHERE appointed_by_official_id = p_dupe_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;
  IF v_rows > 0 THEN RAISE NOTICE '  commission_members: % rows rewired', v_rows; END IF;

  -- Delete the duplicate official record
  DELETE FROM officials WHERE id = p_dupe_id;
  RAISE NOTICE '  Deleted duplicate official "%"', v_dupe_name;
END;
$$;


--
-- Name: parse_vote_tally(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.parse_vote_tally(tally text) RETURNS TABLE(ayes integer, nays integer)
    LANGUAGE plpgsql IMMUTABLE
    AS $$
DECLARE
  m TEXT[];
  aye_names TEXT;
  noe_names TEXT;
  aye_count INT;
  noe_count INT;
BEGIN
  IF tally IS NULL OR tally = '' THEN
    RETURN;
  END IF;

  -- Format 1: "7-0" or "5 - 2"
  m := regexp_match(tally, '^(\d+)\s*-\s*(\d+)');
  IF m IS NOT NULL THEN
    ayes := m[1]::INT;
    nays := m[2]::INT;
    RETURN NEXT;
    RETURN;
  END IF;

  -- Format 2: "7 to 0"
  m := regexp_match(tally, '^(\d+)\s+to\s+(\d+)', 'i');
  IF m IS NOT NULL THEN
    ayes := m[1]::INT;
    nays := m[2]::INT;
    RETURN NEXT;
    RETURN;
  END IF;

  -- Format 3: "Ayes (6)" with optional "Noes (1)" / "Nays (1)"
  m := regexp_match(tally, 'Ayes?\s*\((\d+)\)', 'i');
  IF m IS NOT NULL THEN
    aye_count := m[1]::INT;
    m := regexp_match(tally, 'No(?:e|ay)s?\s*\((\d+)\)', 'i');
    noe_count := COALESCE(m[1]::INT, 0);
    ayes := aye_count;
    nays := noe_count;
    RETURN NEXT;
    RETURN;
  END IF;

  -- Format 4: "Ayes: Name1, Name2. Noes: Name3."
  m := regexp_match(tally, 'Ayes:\s*([^.]+)\.', 'i');
  IF m IS NOT NULL THEN
    aye_names := m[1];
    -- Count names: split by comma, filter out "none"
    SELECT count(*) INTO aye_count
    FROM unnest(string_to_array(aye_names, ',')) AS name
    WHERE trim(name) != '' AND lower(trim(name)) != 'none'
      AND trim(name) !~ '^\s*and\s';

    noe_count := 0;
    m := regexp_match(tally, 'Noes:\s*([^.]+)\.', 'i');
    IF m IS NOT NULL THEN
      noe_names := m[1];
      SELECT count(*) INTO noe_count
      FROM unnest(string_to_array(noe_names, ',')) AS name
      WHERE trim(name) != '' AND lower(trim(name)) != 'none'
        AND trim(name) !~ '^\s*and\s';
    END IF;

    IF aye_count > 0 THEN
      ayes := aye_count;
      nays := noe_count;
      RETURN NEXT;
      RETURN;
    END IF;
  END IF;

  -- Unparseable
  RETURN;
END;
$$;


--
-- Name: reserve_llm_cost(uuid, character varying, text, text, numeric, numeric, text, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.reserve_llm_cost(p_reservation_id uuid, p_city_fips character varying, p_model text, p_caller text, p_projected_cost numeric, p_monthly_cap numeric, p_event_type text DEFAULT NULL::text, p_metadata jsonb DEFAULT '{}'::jsonb) RETURNS TABLE(reserved boolean, committed_cost numeric, reason text)
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
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


--
-- Name: retry_source_change_job(character varying, text, integer, character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.retry_source_change_job(p_change_id character varying, p_error text, p_dispatch_generation integer, p_pipeline_run_id character varying DEFAULT NULL::character varying) RETURNS SETOF public.source_change_jobs
    LANGUAGE sql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
    UPDATE source_change_jobs AS j
    SET status = CASE
            WHEN j.attempt_count >= j.max_attempts THEN 'dead_letter'
            ELSE 'retry_wait'
        END,
        next_attempt_at = CASE
            WHEN j.attempt_count >= j.max_attempts THEN j.next_attempt_at
            ELSE NOW() + make_interval(
                mins => LEAST(
                    60,
                    CAST(power(2, GREATEST(j.attempt_count - 1, 0)) AS INTEGER)
                )
            )
        END,
        lease_expires_at = NULL,
        completed_at = CASE
            WHEN j.attempt_count >= j.max_attempts THEN NOW()
            ELSE NULL
        END,
        last_error = LEFT(COALESCE(p_error, 'Unknown source-change failure'), 4000),
        updated_at = NOW()
    WHERE j.change_id = p_change_id
      AND (
          (
              p_pipeline_run_id IS NULL
              AND p_dispatch_generation IS NOT NULL
              AND j.status = 'dispatched'
              AND j.dispatch_generation = p_dispatch_generation
          )
          OR
          (
              p_pipeline_run_id IS NOT NULL
              AND p_dispatch_generation IS NOT NULL
              AND j.status = 'running'
              AND j.dispatch_generation = p_dispatch_generation
              AND j.pipeline_run_id IS NOT DISTINCT FROM p_pipeline_run_id
              AND j.lease_expires_at > NOW()
          )
      )
    RETURNING j.*;
$$;


--
-- Name: rls_auto_enable(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.rls_auto_enable() RETURNS event_trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog'
    AS $$
DECLARE
  cmd record;
BEGIN
  FOR cmd IN
    SELECT *
    FROM pg_event_trigger_ddl_commands()
    WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
      AND object_type IN ('table','partitioned table')
  LOOP
     IF cmd.schema_name IS NOT NULL AND cmd.schema_name IN ('public') AND cmd.schema_name NOT IN ('pg_catalog','information_schema') AND cmd.schema_name NOT LIKE 'pg_toast%' AND cmd.schema_name NOT LIKE 'pg_temp%' THEN
      BEGIN
        EXECUTE format('alter table if exists %s enable row level security', cmd.object_identity);
        RAISE LOG 'rls_auto_enable: enabled RLS on %', cmd.object_identity;
      EXCEPTION
        WHEN OTHERS THEN
          RAISE LOG 'rls_auto_enable: failed to enable RLS on %', cmd.object_identity;
      END;
     ELSE
        RAISE LOG 'rls_auto_enable: skip % (either system schema or not in enforced list: %.)', cmd.object_identity, cmd.schema_name;
     END IF;
  END LOOP;
END;
$$;


--
-- Name: search_hybrid(text, extensions.vector, text, text, integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.search_hybrid(p_query text, p_query_embedding extensions.vector DEFAULT NULL::extensions.vector, p_city_fips text DEFAULT '0660620'::text, p_result_type text DEFAULT NULL::text, p_limit integer DEFAULT 20, p_offset integer DEFAULT 0) RETURNS TABLE(id uuid, result_type text, title text, snippet text, url_path text, relevance_score real, match_type text, metadata jsonb)
    LANGUAGE plpgsql STABLE
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


--
-- Name: search_site(text, text, text, integer, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.search_site(p_query text, p_city_fips text DEFAULT '0660620'::text, p_result_type text DEFAULT NULL::text, p_limit integer DEFAULT 20, p_offset integer DEFAULT 0) RETURNS TABLE(id uuid, result_type text, title text, snippet text, url_path text, relevance_score real, metadata jsonb)
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE
  tsq tsquery;
BEGIN
  tsq := plainto_tsquery('english', p_query);

  IF tsq IS NULL OR tsq = ''::tsquery THEN
    RETURN;
  END IF;

  RETURN QUERY
  WITH results AS (
    -- 1. Agenda items: title + description + summary + category + topic_label + headline
    SELECT
      ai.id,
      'agenda_item'::TEXT AS result_type,
      ai.title,
      ts_headline('english',
        coalesce(ai.plain_language_summary, coalesce(ai.description, ai.title)),
        tsq,
        'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
      ) AS snippet,
      '/meetings/' || ai.meeting_id AS url_path,
      ts_rank(
        to_tsvector('english',
          coalesce(ai.title, '') || ' ' ||
          coalesce(ai.description, '') || ' ' ||
          coalesce(ai.plain_language_summary, '') || ' ' ||
          coalesce(ai.category, '') || ' ' ||
          coalesce(ai.topic_label, '') || ' ' ||
          coalesce(ai.summary_headline, '')
        ),
        tsq
      ) AS relevance_score,
      jsonb_build_object(
        'meeting_date', m.meeting_date,
        'category', ai.category,
        'item_number', ai.item_number,
        'topic_label', ai.topic_label
      ) AS metadata
    FROM agenda_items ai
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
      AND to_tsvector('english',
            coalesce(ai.title, '') || ' ' ||
            coalesce(ai.description, '') || ' ' ||
            coalesce(ai.plain_language_summary, '') || ' ' ||
            coalesce(ai.category, '') || ' ' ||
            coalesce(ai.topic_label, '') || ' ' ||
            coalesce(ai.summary_headline, '')
          ) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'agenda_item')

    UNION ALL

    -- 2. Motions (vote explainers)
    SELECT
      mo.id,
      'vote_explainer'::TEXT AS result_type,
      coalesce(ai.title, 'Motion on item ' || ai.item_number) AS title,
      ts_headline('english',
        coalesce(mo.vote_explainer, ''),
        tsq,
        'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
      ) AS snippet,
      '/meetings/' || m.id AS url_path,
      ts_rank(
        to_tsvector('english', coalesce(mo.vote_explainer, '')),
        tsq
      ) AS relevance_score,
      jsonb_build_object(
        'meeting_date', m.meeting_date,
        'agenda_item_title', ai.title
      ) AS metadata
    FROM motions mo
    JOIN agenda_items ai ON ai.id = mo.agenda_item_id
    JOIN meetings m ON m.id = ai.meeting_id
    WHERE m.city_fips = p_city_fips
      AND to_tsvector('english', coalesce(mo.vote_explainer, '')) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'vote_explainer')

    UNION ALL

    -- 3. Officials: name + bio_summary
    SELECT
      o.id,
      'official'::TEXT AS result_type,
      o.name AS title,
      ts_headline('english',
        coalesce(o.bio_summary, o.name),
        tsq,
        'StartSel=<b>, StopSel=</b>, MaxWords=40, MinWords=20'
      ) AS snippet,
      '/council/' || lower(regexp_replace(regexp_replace(o.name, '\s+', '-', 'g'), '[^a-z0-9-]', '', 'g')) AS url_path,
      (ts_rank(
        to_tsvector('english', coalesce(o.name, '') || ' ' || coalesce(o.bio_summary, '')),
        tsq
      ) * 2)::REAL AS relevance_score,
      jsonb_build_object(
        'role', o.role,
        'is_current', o.is_current
      ) AS metadata
    FROM officials o
    WHERE o.city_fips = p_city_fips
      AND to_tsvector('english', coalesce(o.name, '') || ' ' || coalesce(o.bio_summary, '')) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'official')

    UNION ALL

    -- 4. Meetings: meeting_type + formatted date
    SELECT
      m.id,
      'meeting'::TEXT AS result_type,
      initcap(coalesce(m.meeting_type, 'regular')) || ' Meeting — ' ||
        to_char(m.meeting_date, 'FMMonth DD, YYYY') AS title,
      NULL::TEXT AS snippet,
      '/meetings/' || m.id AS url_path,
      (ts_rank(
        to_tsvector('english',
          coalesce(m.meeting_type, '') || ' ' ||
          coalesce(to_char(m.meeting_date, 'FMMonth YYYY FMMonth DD YYYY'), '')
        ),
        tsq
      ) * 1.5)::REAL AS relevance_score,
      jsonb_build_object(
        'meeting_date', m.meeting_date,
        'meeting_type', m.meeting_type
      ) AS metadata
    FROM meetings m
    WHERE m.city_fips = p_city_fips
      AND to_tsvector('english',
            coalesce(m.meeting_type, '') || ' ' ||
            coalesce(to_char(m.meeting_date, 'FMMonth YYYY FMMonth DD YYYY'), '')
          ) @@ tsq
      AND (p_result_type IS NULL OR p_result_type = 'meeting')
  )
  SELECT r.id, r.result_type, r.title, r.snippet, r.url_path, r.relevance_score, r.metadata
  FROM results r
  ORDER BY r.relevance_score DESC
  LIMIT p_limit
  OFFSET p_offset;
END;
$$;


--
-- Name: settle_llm_cost_reservation(uuid, numeric, integer, integer, jsonb); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.settle_llm_cost_reservation(p_reservation_id uuid, p_actual_cost numeric, p_input_tokens integer, p_output_tokens integer DEFAULT 0, p_metadata jsonb DEFAULT '{}'::jsonb) RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $_$
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
$_$;


--
-- Name: update_meeting_agenda_item_count(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.update_meeting_agenda_item_count() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
  affected_meeting_id UUID;
BEGIN
  affected_meeting_id := COALESCE(NEW.meeting_id, OLD.meeting_id);
  UPDATE meetings m
  SET agenda_item_count = (
    SELECT COUNT(*)::INT
    FROM agenda_items ai
    WHERE ai.meeting_id = affected_meeting_id
      AND ai.agenda_source_retired_at IS NULL
  )
  WHERE m.id = affected_meeting_id;

  IF TG_OP = 'UPDATE' AND OLD.meeting_id IS DISTINCT FROM NEW.meeting_id THEN
    UPDATE meetings m
    SET agenda_item_count = (
      SELECT COUNT(*)::INT
      FROM agenda_items ai
      WHERE ai.meeting_id = OLD.meeting_id
        AND ai.agenda_source_retired_at IS NULL
    )
    WHERE m.id = OLD.meeting_id;
  END IF;

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$;


--
-- Name: agenda_item_attachments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_item_attachments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agenda_item_id uuid NOT NULL,
    document_id text,
    filename text NOT NULL,
    source_url text,
    extracted_text text,
    char_count integer,
    mime_type text DEFAULT 'application/pdf'::text,
    created_at timestamp with time zone DEFAULT now(),
    source_revision_sha256 text,
    source_content_sha256 text,
    source_retired_at timestamp with time zone
);


--
-- Name: TABLE agenda_item_attachments; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.agenda_item_attachments IS 'Extracted text from eSCRIBE agenda item attachments (staff reports, contracts). Fed into summary generation.';


--
-- Name: COLUMN agenda_item_attachments.source_revision_sha256; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_item_attachments.source_revision_sha256 IS 'Complete eSCRIBE agenda revision that last confirmed this DocumentId on its exact item.';


--
-- Name: COLUMN agenda_item_attachments.source_content_sha256; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_item_attachments.source_content_sha256 IS 'SHA-256 of the downloaded current attachment bytes; prevents stale text from masquerading as a same-ID replacement.';


--
-- Name: COLUMN agenda_item_attachments.source_retired_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_item_attachments.source_retired_at IS 'Set when a complete later agenda omits this attachment; extracted text is preserved for service-role audit.';


--
-- Name: agenda_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_items (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    meeting_id uuid NOT NULL,
    item_number character varying(100) NOT NULL,
    title text NOT NULL,
    description text,
    department character varying(200),
    staff_contact character varying(500),
    category character varying(50),
    is_consent_calendar boolean DEFAULT false NOT NULL,
    was_pulled_from_consent boolean DEFAULT false NOT NULL,
    resolution_number character varying(200),
    financial_amount character varying(500),
    continued_from character varying(100),
    continued_to character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    plain_language_summary text,
    plain_language_generated_at timestamp with time zone,
    plain_language_model character varying(50),
    discussion_duration_minutes integer,
    public_comment_count integer,
    summary_headline text,
    topic_label character varying(50),
    proceeding_type character varying(30),
    ai_comment_summary text,
    plain_language_summary_provenance jsonb,
    legal_framework text,
    legal_framework_source text,
    legal_framework_classified_at timestamp with time zone,
    party_entities jsonb,
    proceeding_classification_attempts smallint DEFAULT 0 NOT NULL,
    proceeding_classification_last_error text,
    proceeding_classification_last_attempted_at timestamp with time zone,
    proceeding_classification_dead_lettered_at timestamp with time zone,
    proceeding_classification_claim_token uuid,
    proceeding_classification_claim_expires_at timestamp with time zone,
    agenda_source_authority text DEFAULT 'legacy'::text NOT NULL,
    agenda_source_revision_sha256 text,
    agenda_source_retired_at timestamp with time zone,
    CONSTRAINT agenda_items_legal_framework_check CHECK (((legal_framework IS NULL) OR (legal_framework = ANY (ARRAY['entitlement'::text, 'legislative'::text, 'contract'::text, 'appointment'::text, 'uncertain'::text])))),
    CONSTRAINT agenda_items_legal_framework_source_check CHECK (((legal_framework_source IS NULL) OR (legal_framework_source = ANY (ARRAY['heuristic'::text, 'llm'::text, 'manual'::text])))),
    CONSTRAINT agenda_items_proceeding_classification_attempts_check CHECK (((proceeding_classification_attempts >= 0) AND (proceeding_classification_attempts <= 3))),
    CONSTRAINT agenda_items_source_authority_check CHECK ((agenda_source_authority = ANY (ARRAY['legacy'::text, 'agenda'::text, 'minutes'::text]))),
    CONSTRAINT chk_proceeding_type CHECK (((proceeding_type IS NULL) OR ((proceeding_type)::text = ANY ((ARRAY['resolution'::character varying, 'ordinance'::character varying, 'contract'::character varying, 'appropriation'::character varying, 'appointment'::character varying, 'hearing'::character varying, 'proclamation'::character varying, 'report'::character varying, 'censure'::character varying, 'appeal'::character varying, 'consent'::character varying, 'other'::character varying])::text[]))))
);


--
-- Name: COLUMN agenda_items.plain_language_summary; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.plain_language_summary IS 'AI-generated plain English explanation of this agenda item (S3.1)';


--
-- Name: COLUMN agenda_items.plain_language_generated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.plain_language_generated_at IS 'When the plain language summary was generated';


--
-- Name: COLUMN agenda_items.plain_language_model; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.plain_language_model IS 'Which AI model generated the summary (e.g. claude-sonnet-4-20250514)';


--
-- Name: COLUMN agenda_items.summary_headline; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.summary_headline IS 'One-sentence short-form summary (~15-20 words) for compact card display. Generated during R1 alongside plain_language_summary.';


--
-- Name: COLUMN agenda_items.topic_label; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.topic_label IS 'Specific 1-4 word subject label (e.g. "Point Molate", "Police Training Contract"). Extracted by LLM alongside summary. Display gated by item significance.';


--
-- Name: COLUMN agenda_items.plain_language_summary_provenance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.plain_language_summary_provenance IS 'Provenance struct for plain_language_summary. Written by generate_summaries.py / plain_language_summarizer.py. Always kind=''agenda_packet'' (title + description + staff_report attachment, all from eSCRIBE agenda packet).';


--
-- Name: COLUMN agenda_items.legal_framework; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.legal_framework IS 'California ethics-law framework: entitlement | legislative | contract | appointment | uncertain. Determines which threshold model (Levine Act, PRA, §1090) applies to financial connections on this item. Distinct from agenda_items.proceeding_type (procedural classification — resolution, ordinance, etc.). NULL = not yet classified. See signal-significance-spec.md §1.';


--
-- Name: COLUMN agenda_items.legal_framework_source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.legal_framework_source IS 'How the framework was assigned: ''heuristic'' (keyword match), ''llm'' (LLM fallback for ambiguous items), ''manual'' (operator override). Used to audit precision and tune the heuristic over time.';


--
-- Name: COLUMN agenda_items.legal_framework_classified_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.legal_framework_classified_at IS 'When legal_framework was last set. NULL when legal_framework is NULL. Backfill scripts use this to find items needing reclassification after heuristic updates.';


--
-- Name: COLUMN agenda_items.party_entities; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.party_entities IS 'Array of {name, role, raw_text} extracted from the item. role values: ''applicant'' (Levine party), ''vendor'' (contract awardee), ''licensee'', ''subject'' (real property at issue). Empty array when item has no identifiable party (most legislative items). NULL when extraction has not yet run. See signal-significance-spec.md §2d.';


--
-- Name: COLUMN agenda_items.proceeding_classification_attempts; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.proceeding_classification_attempts IS 'Bounded LLM attempts; rows reaching 3 remain inspectable but leave the paid queue.';


--
-- Name: COLUMN agenda_items.proceeding_classification_last_error; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.proceeding_classification_last_error IS 'Last provider or validation error, truncated by the application.';


--
-- Name: COLUMN agenda_items.proceeding_classification_dead_lettered_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.proceeding_classification_dead_lettered_at IS 'Set when the third unsuccessful classification attempt is recorded.';


--
-- Name: COLUMN agenda_items.proceeding_classification_claim_token; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.proceeding_classification_claim_token IS 'Ephemeral worker ownership token; success/failure writes must match it.';


--
-- Name: COLUMN agenda_items.proceeding_classification_claim_expires_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.proceeding_classification_claim_expires_at IS 'Crash-recovery lease for claimed classification work.';


--
-- Name: COLUMN agenda_items.agenda_source_authority; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.agenda_source_authority IS 'Structured fact owner: legacy (unclassified), agenda (mutable plan), or minutes (adopted outcome; agenda may never overwrite/retire).';


--
-- Name: COLUMN agenda_items.agenda_source_revision_sha256; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.agenda_source_revision_sha256 IS 'Last complete eSCRIBE agenda revision that authoritatively confirmed this agenda-owned item. NULL is expected for legacy/minutes provenance; authority, not NULL alone, controls reconciliation.';


--
-- Name: COLUMN agenda_items.agenda_source_retired_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.agenda_items.agenda_source_retired_at IS 'Set only when a later complete eSCRIBE agenda omits a previously managed item; NULL rows are current.';


--
-- Name: agenda_items_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agenda_items_embeddings (
    id uuid NOT NULL,
    embedding extensions.halfvec(1536) NOT NULL,
    embedding_model character varying(50) NOT NULL,
    embedding_generated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: behested_payments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.behested_payments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    official_name character varying(300) NOT NULL,
    official_id uuid,
    payor_name character varying(500) NOT NULL,
    payor_city character varying(200),
    payor_state character varying(10),
    payee_name character varying(500) NOT NULL,
    payee_description text,
    amount numeric(12,2),
    payment_date date,
    filing_date date,
    description text,
    source character varying(50) DEFAULT 'fppc_form803'::character varying NOT NULL,
    source_url text,
    source_identifier character varying(500),
    filing_id character varying(100),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: bodies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bodies (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    name character varying(300) NOT NULL,
    body_type character varying(50) NOT NULL,
    short_name character varying(100),
    parent_body_id uuid,
    commission_id uuid,
    is_elected boolean DEFAULT false NOT NULL,
    num_seats smallint,
    meeting_schedule character varying(200),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: business_entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.business_entities (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips text NOT NULL,
    entity_name text NOT NULL,
    entity_number text,
    jurisdiction_code text DEFAULT 'us_ca'::text NOT NULL,
    entity_type text,
    current_status text,
    incorporation_date date,
    dissolution_date date,
    registered_address text,
    agent_name text,
    agent_address text,
    opencorporates_url text,
    raw_response jsonb,
    source_url text NOT NULL,
    source_publisher text DEFAULT 'California Secretary of State'::text NOT NULL,
    source_tier integer DEFAULT 1 NOT NULL,
    retrieved_at timestamp with time zone NOT NULL,
    extracted_at timestamp with time zone DEFAULT now() NOT NULL,
    confidence_score numeric(3,2),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: business_entity_officers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.business_entity_officers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    business_entity_id uuid NOT NULL,
    officer_name text NOT NULL,
    "position" text,
    start_date date,
    end_date date,
    is_inactive boolean DEFAULT false,
    opencorporates_officer_id bigint,
    source_url text NOT NULL,
    retrieved_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: cities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cities (
    fips_code character varying(7) NOT NULL,
    name character varying(100) NOT NULL,
    state character varying(2) NOT NULL,
    county character varying(100),
    population integer,
    timezone character varying(50) DEFAULT 'America/Los_Angeles'::character varying NOT NULL,
    charter_type character varying(50),
    website_url text,
    clerk_email character varying(255),
    council_size smallint,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: city_code_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.city_code_cases (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    case_type character varying(100),
    case_subtype character varying(200),
    violation_type character varying(200),
    violation character varying(500),
    status character varying(50),
    case_location character varying(500),
    site_address character varying(500),
    site_apn character varying(50),
    site_zip character varying(20),
    opened_date date,
    closed_date date,
    date_observed date,
    date_corrected date,
    neighborhood_council character varying(100),
    source character varying(50) DEFAULT 'socrata_code_cases'::character varying NOT NULL,
    socrata_row_id character varying(200),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: city_contracts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.city_contracts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips text NOT NULL,
    vendor_name text NOT NULL,
    description text,
    annual_cost numeric(12,2),
    total_cost numeric(12,2),
    contract_type text,
    department text,
    approval_date date,
    expiration_date date,
    contract_number text,
    awarding_body text,
    approval_action text,
    source_url text NOT NULL,
    extracted_at timestamp with time zone DEFAULT now() NOT NULL,
    source_tier integer DEFAULT 1 NOT NULL,
    confidence_score numeric(3,2),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: city_employees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.city_employees (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    name character varying(300) NOT NULL,
    normalized_name character varying(300) NOT NULL,
    job_title character varying(300),
    department character varying(200),
    is_department_head boolean DEFAULT false NOT NULL,
    hierarchy_level smallint DEFAULT 0 NOT NULL,
    annual_salary numeric,
    total_compensation numeric,
    fiscal_year character varying(4),
    is_current boolean DEFAULT true NOT NULL,
    source character varying(50) DEFAULT 'socrata_payroll'::character varying NOT NULL,
    socrata_record_id character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: city_expenditures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.city_expenditures (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    vendor_name character varying(500),
    normalized_vendor character varying(500),
    description character varying(1000),
    amount numeric,
    department character varying(300),
    fund character varying(300),
    fiscal_year character varying(4),
    expenditure_date date,
    source character varying(50) DEFAULT 'socrata_expenditures'::character varying NOT NULL,
    socrata_row_id character varying(200),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: city_licenses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.city_licenses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    company character varying(500),
    normalized_company character varying(500),
    company_dba character varying(500),
    business_type character varying(200),
    classification character varying(200),
    ownership_type character varying(100),
    status character varying(50),
    employees integer,
    license_issued date,
    license_expired date,
    business_start_date date,
    loc_address character varying(500),
    loc_city character varying(100),
    loc_zip character varying(20),
    site_address character varying(500),
    site_apn character varying(50),
    sic_code character varying(50),
    neighborhood_council character varying(100),
    source character varying(50) DEFAULT 'socrata_licenses'::character varying NOT NULL,
    socrata_row_id character varying(200),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: city_permits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.city_permits (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    permit_no character varying(50),
    permit_type character varying(100),
    permit_subtype character varying(100),
    description text,
    status character varying(50),
    situs_address character varying(500),
    situs_apn character varying(50),
    applied_date date,
    approved_date date,
    issued_date date,
    finaled_date date,
    expired_date date,
    applied_by character varying(200),
    fees_charged numeric,
    fees_paid numeric,
    job_value numeric,
    building_sqft numeric,
    units integer,
    project_number character varying(100),
    source character varying(50) DEFAULT 'socrata_permits'::character varying NOT NULL,
    socrata_row_id character varying(200),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: city_projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.city_projects (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    project_no character varying(50),
    project_name character varying(500),
    project_type character varying(100),
    project_subtype character varying(200),
    description text,
    status character varying(50),
    site_address character varying(500),
    site_apn character varying(50),
    site_zip character varying(20),
    zoning_code character varying(50),
    land_use character varying(200),
    occupancy_description character varying(200),
    resolution_no character varying(100),
    parent_project_no character varying(50),
    applied_date date,
    approved_date date,
    closed_date date,
    expired_date date,
    status_date date,
    applied_by character varying(200),
    approved_by character varying(200),
    affordability_level_applied character varying(100),
    affordability_level_approved character varying(100),
    neighborhood_council character varying(100),
    latitude numeric,
    longitude numeric,
    source character varying(50) DEFAULT 'socrata_projects'::character varying NOT NULL,
    socrata_row_id character varying(200),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: city_service_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.city_service_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    issue_type character varying(300),
    department character varying(200),
    description text,
    status character varying(50),
    created_via character varying(100),
    issue_address character varying(500),
    created_date date,
    due_date date,
    completed_date date,
    linked_doc character varying(500),
    latitude numeric,
    longitude numeric,
    source character varying(50) DEFAULT 'socrata_service_requests'::character varying NOT NULL,
    socrata_row_id character varying(200),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: closed_session_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.closed_session_items (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    meeting_id uuid NOT NULL,
    item_number character varying(200) NOT NULL,
    legal_authority text NOT NULL,
    description text NOT NULL,
    parties text[],
    reportable_action text
);


--
-- Name: comment_theme_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comment_theme_assignments (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    comment_id uuid NOT NULL,
    theme_id uuid NOT NULL,
    confidence real DEFAULT 0.9 NOT NULL,
    source character varying(30) DEFAULT 'llm'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: comment_themes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comment_themes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) DEFAULT '0660620'::character varying NOT NULL,
    slug character varying(100) NOT NULL,
    label character varying(200) NOT NULL,
    description text,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    merged_into_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: commission_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commission_members (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    commission_id uuid NOT NULL,
    name character varying(300) NOT NULL,
    normalized_name character varying(300) NOT NULL,
    role character varying(50) DEFAULT 'member'::character varying NOT NULL,
    appointed_by character varying(300),
    appointed_by_official_id uuid,
    term_start date,
    term_end date,
    is_current boolean DEFAULT true NOT NULL,
    source character varying(50) DEFAULT 'city_website'::character varying NOT NULL,
    source_meeting_id uuid,
    website_stale_since date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: commissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.commissions (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    name character varying(300) NOT NULL,
    commission_type character varying(50) DEFAULT 'advisory'::character varying NOT NULL,
    num_seats smallint,
    appointment_authority character varying(100),
    form700_required boolean DEFAULT false NOT NULL,
    term_length_years smallint,
    meeting_schedule character varying(200),
    escribemeetings_type character varying(200),
    archive_center_amid integer,
    website_roster_url character varying(500),
    last_website_scrape timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: committees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.committees (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    name character varying(500) NOT NULL,
    filer_id character varying(50),
    committee_type character varying(50),
    candidate_name character varying(200),
    official_id uuid,
    status character varying(20),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    election_id uuid
);


--
-- Name: conflict_flags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conflict_flags (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    agenda_item_id uuid,
    meeting_id uuid,
    official_id uuid,
    flag_type character varying(50) NOT NULL,
    description text NOT NULL,
    evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    confidence numeric(3,2) NOT NULL,
    legal_reference text,
    reviewed boolean DEFAULT false NOT NULL,
    reviewed_at timestamp with time zone,
    reviewed_by character varying(200),
    false_positive boolean,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    scan_run_id uuid,
    scan_mode character varying(20),
    data_cutoff_date date,
    superseded_by uuid,
    is_current boolean DEFAULT true NOT NULL,
    publication_tier smallint,
    confidence_factors jsonb,
    scanner_version integer DEFAULT 2,
    match_details jsonb,
    significance_tier text,
    significance_assigned_at timestamp with time zone,
    significance_rationale text,
    influence_pattern_id smallint,
    CONSTRAINT conflict_flags_confidence_check CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric))),
    CONSTRAINT conflict_flags_significance_tier_check CHECK (((significance_tier IS NULL) OR (significance_tier = ANY (ARRAY['legal_threshold'::text, 'pattern'::text, 'connection'::text]))))
);


--
-- Name: COLUMN conflict_flags.publication_tier; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conflict_flags.publication_tier IS 'Scanner-assigned tier: 1=public-ready, 2=operator review, 3=low confidence/internal';


--
-- Name: COLUMN conflict_flags.significance_tier; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conflict_flags.significance_tier IS 'Scanner v4 tier (signal-significance-spec.md): ''legal_threshold'' (A — public, with statute citation) | ''pattern'' (B — public, cross-meeting pattern with confidence ≥ 0.70) | ''connection'' (C — operator-only, no legal threshold or pattern). NULL on legacy flags pre-classification. Public summary counts include only A + B. Frontend filters significance_tier IN (legal_threshold, pattern).';


--
-- Name: COLUMN conflict_flags.significance_assigned_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conflict_flags.significance_assigned_at IS 'When significance_tier was last computed. Used to find flags needing reclassification after threshold/pattern detector updates.';


--
-- Name: COLUMN conflict_flags.significance_rationale; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.conflict_flags.significance_rationale IS 'Human-readable explanation of why this tier was assigned. Tier A flags cite the statute and amount ("Levine Act §84308 — $600 contribution >$500 threshold for entitlement proceedings"). Tier B flags cite the pattern ("Donor X appears in 5 items across 3 meetings, total $4,200"). Tier C rows leave this NULL or short.';


--
-- Name: contributions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contributions (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    donor_id uuid NOT NULL,
    committee_id uuid NOT NULL,
    amount numeric(12,2) NOT NULL,
    contribution_date date NOT NULL,
    contribution_type character varying(30) NOT NULL,
    filing_id character varying(100),
    schedule character varying(10),
    source character varying(50) NOT NULL,
    document_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    contributor_type character varying(20),
    contributor_type_source character varying(20),
    entity_code character varying(10),
    election_id uuid
);


--
-- Name: COLUMN contributions.contributor_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.contributions.contributor_type IS 'Contributor classification: corporate, union, individual, pac_ie, other';


--
-- Name: COLUMN contributions.contributor_type_source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.contributions.contributor_type_source IS 'How contributor_type was determined: entity_cd, inferred, manual';


--
-- Name: COLUMN contributions.entity_code; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.contributions.entity_code IS 'Raw FPPC entity code from CAL-ACCESS ENTITY_CD field';


--
-- Name: court_case_matches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.court_case_matches (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    court_party_id uuid NOT NULL,
    case_id uuid NOT NULL,
    official_id uuid,
    donor_id uuid,
    entity_type character varying(30) NOT NULL,
    entity_name character varying(500) NOT NULL,
    match_type character varying(30) NOT NULL,
    confidence numeric(3,2) NOT NULL,
    reviewed boolean DEFAULT false NOT NULL,
    reviewed_at timestamp with time zone,
    false_positive boolean,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT court_case_matches_confidence_check CHECK (((confidence >= (0)::numeric) AND (confidence <= (1)::numeric)))
);


--
-- Name: TABLE court_case_matches; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.court_case_matches IS 'Cross-reference matches between court parties and known entities. Confidence-scored, reviewable.';


--
-- Name: COLUMN court_case_matches.match_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.court_case_matches.match_type IS 'How the match was found: exact, contains, fuzzy, last_name_only';


--
-- Name: COLUMN court_case_matches.confidence; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.court_case_matches.confidence IS 'Match confidence: 0.9=exact, 0.7=contains, 0.5=fuzzy, 0.3=last_name_only';


--
-- Name: court_case_parties; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.court_case_parties (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    case_id uuid NOT NULL,
    party_name character varying(500) NOT NULL,
    normalized_name character varying(500) NOT NULL,
    party_type character varying(50) NOT NULL,
    is_organization boolean DEFAULT false NOT NULL,
    attorney character varying(300),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE court_case_parties; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.court_case_parties IS 'Parties in court cases. Normalized names enable cross-reference matching against officials/donors.';


--
-- Name: court_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.court_cases (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    county_fips character varying(5) NOT NULL,
    case_number character varying(100) NOT NULL,
    case_type character varying(100),
    case_category character varying(200),
    case_title character varying(1000),
    filing_date date,
    case_status character varying(50),
    disposition character varying(200),
    disposition_date date,
    court_name character varying(200),
    judge character varying(200),
    source_url text,
    source character varying(50) DEFAULT 'tyler_odyssey'::character varying NOT NULL,
    credibility_tier integer DEFAULT 1 NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE court_cases; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.court_cases IS 'Court cases from Tyler Odyssey portal lookups. Cross-referenced against officials/donors (S8.2).';


--
-- Name: COLUMN court_cases.county_fips; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.court_cases.county_fips IS 'County FIPS code (e.g., 06013 for Contra Costa). Supports multi-county lookup.';


--
-- Name: cpra_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cpra_requests (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    request_text text NOT NULL,
    target_department character varying(200),
    legal_basis text DEFAULT 'California Public Records Act (Gov. Code § 6250 et seq.)'::text,
    filed_date date,
    response_due date,
    status character varying(30) DEFAULT 'draft'::character varying NOT NULL,
    response_notes text,
    document_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: data_sync_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_sync_log (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    source character varying(50) NOT NULL,
    sync_type character varying(30) NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    records_fetched integer,
    records_new integer,
    records_updated integer,
    status character varying(20) DEFAULT 'running'::character varying NOT NULL,
    error_message text,
    triggered_by character varying(50),
    pipeline_run_id character varying(100),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    change_id character varying(64)
);


--
-- Name: COLUMN data_sync_log.change_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.data_sync_log.change_id IS 'Deterministic detector fingerprint hash; null for manual/scheduled syncs.';


--
-- Name: document_references; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_references (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    source_document_id uuid NOT NULL,
    referenced_description text NOT NULL,
    expected_url text,
    found boolean DEFAULT false NOT NULL,
    resolved_document_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    source_type character varying(50) NOT NULL,
    source_url text,
    source_identifier character varying(100),
    raw_content bytea,
    raw_text text,
    content_hash character varying(64),
    mime_type character varying(100),
    credibility_tier smallint NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    source_retired_at timestamp with time zone,
    CONSTRAINT documents_credibility_tier_check CHECK (((credibility_tier >= 1) AND (credibility_tier <= 4)))
);


--
-- Name: COLUMN documents.source_retired_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.documents.source_retired_at IS 'Superseded/withdrawn source revision. Service-role audit remains available; public reads see current revisions only.';


--
-- Name: donors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.donors (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    name character varying(300) NOT NULL,
    normalized_name character varying(300) NOT NULL,
    employer character varying(300),
    normalized_employer character varying(300),
    occupation character varying(200),
    address text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    donor_pattern character varying(20),
    total_contributed numeric(12,2),
    contribution_span_days integer,
    distinct_recipients integer,
    entity_type character varying(20),
    entity_slug character varying(400)
);


--
-- Name: COLUMN donors.donor_pattern; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.donors.donor_pattern IS 'Computed pattern: grassroots, targeted, mega, pac, regular';


--
-- Name: COLUMN donors.total_contributed; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.donors.total_contributed IS 'Denormalized sum of all contributions from this donor';


--
-- Name: COLUMN donors.contribution_span_days; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.donors.contribution_span_days IS 'Days between first and last contribution';


--
-- Name: COLUMN donors.distinct_recipients; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.donors.distinct_recipients IS 'Number of distinct committees this donor has contributed to';


--
-- Name: COLUMN donors.entity_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.donors.entity_type IS 'person | union | corporation | committee | other_org';


--
-- Name: COLUMN donors.entity_slug; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.donors.entity_slug IS 'URL-safe slug for entity profile pages';


--
-- Name: donor_context; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.donor_context WITH (security_invoker='on') AS
 SELECT d.id AS donor_id,
    d.city_fips,
    d.name AS donor_name,
    d.normalized_name,
    d.employer,
    d.normalized_employer,
    d.occupation,
    count(c.id) AS contribution_count,
    COALESCE(sum(c.amount), (0)::numeric) AS total_contributed,
    avg(c.amount) AS avg_contribution,
    min(c.amount) AS min_contribution,
    max(c.amount) AS max_contribution,
    count(DISTINCT c.committee_id) AS distinct_recipients,
    min(c.contribution_date) AS first_contribution,
    max(c.contribution_date) AS last_contribution,
    (max(c.contribution_date) - min(c.contribution_date)) AS contribution_span_days,
    ( SELECT count(DISTINCT d2.id) AS count
           FROM public.donors d2
          WHERE (((d2.normalized_employer)::text = (d.normalized_employer)::text) AND (d2.id <> d.id) AND (d.normalized_employer IS NOT NULL) AND ((d.normalized_employer)::text <> ''::text))) AS employer_network_size
   FROM (public.donors d
     LEFT JOIN public.contributions c ON (((c.donor_id = d.id) AND ((c.city_fips)::text = (d.city_fips)::text))))
  GROUP BY d.id, d.city_fips, d.name, d.normalized_name, d.employer, d.normalized_employer, d.occupation;


--
-- Name: VIEW donor_context; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.donor_context IS 'Aggregated donor statistics for contribution pattern analysis (S5.2)';


--
-- Name: economic_interests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.economic_interests (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    official_id uuid,
    filing_year integer NOT NULL,
    schedule character varying(10) NOT NULL,
    interest_type character varying(50) NOT NULL,
    description text NOT NULL,
    value_range character varying(100),
    location text,
    source_url text,
    document_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    filing_id uuid
);


--
-- Name: COLUMN economic_interests.filing_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.economic_interests.filing_id IS 'FK to form700_filings. Links individual interest entries to their parent filing.';


--
-- Name: election_candidates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.election_candidates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    election_id uuid NOT NULL,
    official_id uuid,
    candidate_name character varying(300) NOT NULL,
    normalized_name character varying(300) NOT NULL,
    office_sought character varying(200) NOT NULL,
    party character varying(100),
    fppc_id character varying(50),
    committee_id uuid,
    status character varying(30) DEFAULT 'filed'::character varying NOT NULL,
    is_incumbent boolean DEFAULT false NOT NULL,
    source character varying(50) DEFAULT 'netfile'::character varying NOT NULL,
    source_url text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    qualification_date date,
    source_tier integer,
    confidence_score numeric(3,2),
    extracted_at timestamp with time zone
);


--
-- Name: elections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.elections (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    election_date date NOT NULL,
    election_type character varying(30) NOT NULL,
    election_name character varying(300),
    jurisdiction character varying(200),
    filing_deadline date,
    source character varying(50) DEFAULT 'seed'::character varying NOT NULL,
    source_url text,
    source_tier integer DEFAULT 1 NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: email_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.email_preferences (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    subscriber_id uuid NOT NULL,
    preference_type character varying(20) NOT NULL,
    preference_value character varying(100) NOT NULL,
    city_fips character varying(7) DEFAULT '0660620'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT email_preferences_preference_type_check CHECK (((preference_type)::text = ANY ((ARRAY['topic'::character varying, 'district'::character varying, 'candidate'::character varying])::text[])))
);


--
-- Name: email_subscribers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.email_subscribers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email character varying(255) NOT NULL,
    name character varying(200),
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    subscribed_at timestamp with time zone DEFAULT now() NOT NULL,
    unsubscribed_at timestamp with time zone,
    city_fips character varying(7) DEFAULT '0660620'::character varying NOT NULL,
    source character varying(50) DEFAULT 'website'::character varying NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb,
    unsubscribe_token uuid DEFAULT gen_random_uuid() NOT NULL,
    last_orientation_meeting_id uuid,
    CONSTRAINT email_subscribers_source_check CHECK (((source)::text = ANY ((ARRAY['website'::character varying, 'manual'::character varying])::text[]))),
    CONSTRAINT email_subscribers_status_check CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'unsubscribed'::character varying])::text[])))
);


--
-- Name: COLUMN email_subscribers.last_orientation_meeting_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.email_subscribers.last_orientation_meeting_id IS 'Most recent meeting whose orientation preview was emailed to this subscriber. Set by /api/subscribe (signup-time send) and /api/email/send-orientation (broadcast). Broadcast filters by: meeting_id != last_orientation_meeting_id.';


--
-- Name: entity_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_links (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    person_name character varying(300) NOT NULL,
    normalized_person_name character varying(300) NOT NULL,
    organization_id uuid NOT NULL,
    role character varying(100) NOT NULL,
    role_detail character varying(200),
    donor_id uuid,
    official_id uuid,
    confidence numeric(3,2) DEFAULT 0.80 NOT NULL,
    source character varying(50) NOT NULL,
    source_url text,
    effective_date date,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: entity_name_matches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_name_matches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_name text NOT NULL,
    source_table text NOT NULL,
    source_record_id uuid NOT NULL,
    business_entity_id uuid,
    match_confidence numeric(3,2) NOT NULL,
    match_method text NOT NULL,
    reviewed boolean DEFAULT false,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: external_references; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.external_references (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    document_id uuid NOT NULL,
    entity_type character varying(50) NOT NULL,
    entity_id uuid,
    entity_name character varying(300),
    mention_type character varying(50),
    excerpt text,
    sentiment character varying(20),
    confidence numeric(3,2),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: extraction_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.extraction_runs (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    document_id uuid NOT NULL,
    extraction_model character varying(100) NOT NULL,
    extraction_prompt_version character varying(50),
    extracted_data jsonb NOT NULL,
    input_tokens integer,
    output_tokens integer,
    cost_usd numeric(8,4),
    extracted_at timestamp with time zone DEFAULT now() NOT NULL,
    is_current boolean DEFAULT true NOT NULL
);


--
-- Name: filing_period_briefings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.filing_period_briefings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    election_id uuid,
    period_label character varying(100) NOT NULL,
    period_kind character varying(40) NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    filed_through date,
    sections jsonb DEFAULT '{}'::jsonb NOT NULL,
    section_tiers jsonb DEFAULT '{}'::jsonb NOT NULL,
    provenance jsonb,
    generator character varying(100) DEFAULT 'filing_period_briefing.py'::character varying NOT NULL,
    generator_version character varying(50),
    model_version character varying(100),
    contributions_considered integer,
    paper_filings_considered integer,
    publication_tier character varying(20) DEFAULT 'graduated'::character varying NOT NULL,
    is_current boolean DEFAULT true NOT NULL,
    generated_at timestamp with time zone DEFAULT now() NOT NULL,
    superseded_at timestamp with time zone,
    notes text
);


--
-- Name: TABLE filing_period_briefings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.filing_period_briefings IS 'Structured filing-period briefings — campaign-finance equivalent of meeting recaps. One row per (city, election, period). Sections are JSONB so per-candidate and cross-candidate views render from the same artifact. See docs/plans/2026-04-28-filing-period-briefings.md.';


--
-- Name: COLUMN filing_period_briefings.sections; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.filing_period_briefings.sections IS 'JSONB blob keyed by section id (F1_totals through F9_levine_exposure). Each section value is structured per signal-significance-spec.md. The renderer slices this by candidate for the candidate page and by cross-race for the finance dashboard.';


--
-- Name: COLUMN filing_period_briefings.section_tiers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.filing_period_briefings.section_tiers IS 'Per-section A/B/C tier (Scanner v4 model). Sections at Tier C are operator-only even when the briefing as a whole is published. Per-section tiering lets framing-sensitive sections (F5, F9) graduate independently.';


--
-- Name: COLUMN filing_period_briefings.publication_tier; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.filing_period_briefings.publication_tier IS 'Briefing-level publication tier (team-operations.md rubric): public | operator | graduated. Defaults to ''graduated'' per the briefing spec — a new feature category with AI-generated narrative needs operator review.';


--
-- Name: form700_filings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.form700_filings (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    official_id uuid,
    filer_name character varying(300) NOT NULL,
    filer_agency character varying(300),
    filer_position character varying(300),
    statement_type character varying(30) NOT NULL,
    period_start date,
    period_end date,
    filing_year integer NOT NULL,
    source character varying(50) NOT NULL,
    source_url text NOT NULL,
    document_id uuid,
    no_interests_declared boolean DEFAULT false NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    source_tier smallint DEFAULT 1 NOT NULL,
    confidence_score numeric(3,2) DEFAULT 0.5 NOT NULL,
    extracted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE form700_filings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.form700_filings IS 'Form 700 (Statement of Economic Interests) filing metadata. Parent table for economic_interests.';


--
-- Name: COLUMN form700_filings.statement_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.form700_filings.statement_type IS 'Filing type: annual, assuming_office, leaving_office, candidate, amendment';


--
-- Name: COLUMN form700_filings.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.form700_filings.source IS 'Where the filing was obtained: fppc, netfile_sei, city_clerk';


--
-- Name: COLUMN form700_filings.no_interests_declared; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.form700_filings.no_interests_declared IS 'True if filer checked "No reportable interests" on all schedules';


--
-- Name: form_summary_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.form_summary_cache (
    filing_id character varying NOT NULL,
    committee character varying NOT NULL,
    city_fips character varying DEFAULT '0660620'::character varying NOT NULL,
    summary jsonb NOT NULL,
    extracted_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE form_summary_cache; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.form_summary_cache IS 'Cached Form 460 cover-page summaries extracted by Anthropic Vision API. Source of truth for paper_filing_reconciliation. Replaces the file-based cache at src/data/form_summaries.json which was lost between cloud runs.';


--
-- Name: COLUMN form_summary_cache.summary; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.form_summary_cache.summary IS 'Full JSONB blob from parse_form460_summary_with_vision: monetary_this_period, loans_this_period, unitemized_this_period, period_start, period_end, total_cycle_to_date, etc. Reconciliation reads monetary_this_period and period dates.';


--
-- Name: friendly_amendments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.friendly_amendments (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    motion_id uuid NOT NULL,
    proposed_by character varying(200) NOT NULL,
    description text NOT NULL,
    accepted boolean NOT NULL
);


--
-- Name: independent_expenditures; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.independent_expenditures (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    committee_name character varying(500) NOT NULL,
    candidate_name character varying(255),
    support_or_oppose character varying(1),
    amount numeric(12,2),
    expenditure_date date,
    description text,
    expenditure_code character varying(10),
    payee_name character varying(500),
    filing_id character varying(50),
    source character varying(50) DEFAULT 'calaccess'::character varying,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: influence_patterns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.influence_patterns (
    id smallint NOT NULL,
    pattern_name text NOT NULL,
    description text NOT NULL,
    signal_types text[] DEFAULT '{}'::text[] NOT NULL,
    sort_order smallint DEFAULT 0 NOT NULL,
    source_doc text DEFAULT 'docs/research/political-influence-tracing.md'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: influence_patterns_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.influence_patterns ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.influence_patterns_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: item_theme_narratives; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.item_theme_narratives (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agenda_item_id uuid NOT NULL,
    theme_id uuid NOT NULL,
    narrative text NOT NULL,
    comment_count integer DEFAULT 0 NOT NULL,
    confidence real DEFAULT 0.9 NOT NULL,
    model character varying(50),
    generated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: item_topics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.item_topics (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    agenda_item_id uuid NOT NULL,
    topic_id uuid NOT NULL,
    confidence real DEFAULT 1.0 NOT NULL,
    source character varying(20) DEFAULT 'keyword'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE item_topics; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.item_topics IS 'Junction table linking agenda items to topics. An item can have multiple topics.';


--
-- Name: llm_cost_reservations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.llm_cost_reservations (
    id uuid NOT NULL,
    city_fips character varying DEFAULT '0660620'::character varying NOT NULL,
    model text NOT NULL,
    caller text NOT NULL,
    event_type text,
    projected_cost numeric(14,8) NOT NULL,
    actual_cost numeric(14,8),
    status text DEFAULT 'reserved'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    settled_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT llm_cost_reservations_actual_cost_check CHECK ((actual_cost >= (0)::numeric)),
    CONSTRAINT llm_cost_reservations_projected_cost_check CHECK ((projected_cost >= (0)::numeric)),
    CONSTRAINT llm_cost_reservations_settlement_shape CHECK ((((status = 'reserved'::text) AND (actual_cost IS NULL) AND (settled_at IS NULL)) OR ((status = 'settled'::text) AND (actual_cost IS NOT NULL) AND (settled_at IS NOT NULL)))),
    CONSTRAINT llm_cost_reservations_status_check CHECK ((status = ANY (ARRAY['reserved'::text, 'settled'::text])))
);


--
-- Name: TABLE llm_cost_reservations; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.llm_cost_reservations IS 'Service-only atomic monthly LLM spend reservations. Reserved rows count at their conservative ceiling; settled rows count at provider-reported cost.';


--
-- Name: COLUMN llm_cost_reservations.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.llm_cost_reservations.status IS 'reserved remains fail-closed after ambiguous/crashed requests; settled has actual_cost.';


--
-- Name: lobbyist_document_extractions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lobbyist_document_extractions (
    city_fips character varying(7) DEFAULT '0660620'::character varying NOT NULL,
    document_id bigint NOT NULL,
    content_sha256 text NOT NULL,
    records jsonb NOT NULL,
    extraction_provider text NOT NULL,
    extraction_model text NOT NULL,
    prompt_version text NOT NULL,
    source_url text NOT NULL,
    extracted_at timestamp with time zone DEFAULT now() NOT NULL,
    source_tier smallint DEFAULT 1 NOT NULL,
    confidence_score numeric(3,2) NOT NULL,
    ai_generated boolean DEFAULT true NOT NULL,
    CONSTRAINT lobbyist_document_extractions_ai_generated_check CHECK (ai_generated),
    CONSTRAINT lobbyist_document_extractions_confidence_score_check CHECK (((confidence_score >= (0)::numeric) AND (confidence_score <= (1)::numeric))),
    CONSTRAINT lobbyist_document_extractions_content_sha256_check CHECK ((content_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT lobbyist_document_extractions_extraction_model_check CHECK ((btrim(extraction_model) <> ''::text)),
    CONSTRAINT lobbyist_document_extractions_extraction_provider_check CHECK ((btrim(extraction_provider) <> ''::text)),
    CONSTRAINT lobbyist_document_extractions_prompt_version_check CHECK ((btrim(prompt_version) <> ''::text)),
    CONSTRAINT lobbyist_document_extractions_records_check CHECK ((jsonb_typeof(records) = 'array'::text)),
    CONSTRAINT lobbyist_document_extractions_source_tier_check CHECK (((source_tier >= 1) AND (source_tier <= 4))),
    CONSTRAINT lobbyist_document_extractions_source_url_check CHECK ((btrim(source_url) <> ''::text))
);


--
-- Name: TABLE lobbyist_document_extractions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.lobbyist_document_extractions IS 'Service-only cache of structurally validated AI extraction results for official Richmond lobbyist registration PDFs, keyed by exact content hash.';


--
-- Name: COLUMN lobbyist_document_extractions.confidence_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.lobbyist_document_extractions.confidence_score IS 'Confidence in the structurally validated extraction receipt, not an independent factual verification of every model-read checkmark.';


--
-- Name: lobbyist_registrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lobbyist_registrations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    lobbyist_name character varying(300) NOT NULL,
    lobbyist_firm character varying(500),
    client_name character varying(500) NOT NULL,
    registration_date date,
    expiration_date date,
    topics text,
    city_agencies text,
    lobbyist_address text,
    lobbyist_phone character varying(50),
    lobbyist_email character varying(200),
    status character varying(50) DEFAULT 'active'::character varying,
    source character varying(50) DEFAULT 'city_clerk'::character varying NOT NULL,
    source_url text,
    source_identifier character varying(500),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: meeting_attendance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.meeting_attendance (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    meeting_id uuid NOT NULL,
    official_id uuid NOT NULL,
    status character varying(20) NOT NULL,
    notes text,
    body_id uuid
);


--
-- Name: meetings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.meetings (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    document_id uuid,
    meeting_date date NOT NULL,
    meeting_type character varying(30) NOT NULL,
    call_to_order_time character varying(100),
    adjournment_time character varying(50),
    presiding_officer character varying(200),
    minutes_url text,
    agenda_url text,
    video_url text,
    adjourned_in_memory_of text,
    next_meeting_date character varying(100),
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    body_id uuid NOT NULL,
    meeting_summary text,
    orientation_preview text,
    meeting_recap text,
    recap_emailed_at timestamp with time zone,
    transcript_recap text,
    transcript_recap_source character varying(30),
    transcript_recap_generated_at timestamp with time zone,
    transcript_recap_emailed_at timestamp with time zone,
    agenda_item_count integer DEFAULT 0 NOT NULL,
    orientation_emailed_at timestamp with time zone,
    transcript_recap_corrected_at timestamp with time zone,
    meeting_recap_provenance jsonb,
    transcript_recap_provenance jsonb,
    meeting_summary_provenance jsonb,
    orientation_preview_provenance jsonb,
    source_cancelled_at timestamp with time zone,
    source_meeting_guid text
);


--
-- Name: COLUMN meetings.recap_emailed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.meetings.recap_emailed_at IS 'When the recap email was last sent to subscribers';


--
-- Name: COLUMN meetings.orientation_emailed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.meetings.orientation_emailed_at IS 'When the pre-meeting orientation preview email was sent to subscribers';


--
-- Name: COLUMN meetings.transcript_recap_corrected_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.meetings.transcript_recap_corrected_at IS 'When transcript_recap was last post-processed by correct_recap_names.py (name-correction pass using canonical_names.md). NULL if never corrected.';


--
-- Name: COLUMN meetings.meeting_recap_provenance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.meetings.meeting_recap_provenance IS 'Provenance struct for meeting_recap. Written by generate_meeting_recaps.py in the same UPDATE as meeting_recap. Discriminated union — see migration 095 header for the kind variants.';


--
-- Name: COLUMN meetings.transcript_recap_provenance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.meetings.transcript_recap_provenance IS 'Provenance struct for transcript_recap. Written by post_meeting_recap.py / correct_recap_names.py. Replaces the flat transcript_recap_source column with the unified Provenance shape.';


--
-- Name: COLUMN meetings.meeting_summary_provenance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.meetings.meeting_summary_provenance IS 'Provenance struct for meeting_summary. Written by generate_meeting_summaries.py. May be ''mixed'' when summary aggregates both minutes-source and transcript-source motions (Entry 51 dishonest-attribution risk).';


--
-- Name: COLUMN meetings.orientation_preview_provenance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.meetings.orientation_preview_provenance IS 'Provenance struct for orientation_preview. Written by generate_orientation_previews.py. Always kind=''agenda_packet''; column exists for schema consistency and to enable the unified <SourceAttribution> render path.';


--
-- Name: COLUMN meetings.source_cancelled_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.meetings.source_cancelled_at IS 'Authoritative eSCRIBE cancellation; cleared by agenda revival or adopted minutes.';


--
-- Name: COLUMN meetings.source_meeting_guid; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.meetings.source_meeting_guid IS 'Stable upstream eSCRIBE meeting GUID. Date/name/type may change without creating a second logical meeting.';


--
-- Name: meetings_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.meetings_embeddings (
    id uuid NOT NULL,
    embedding extensions.halfvec(1536) NOT NULL,
    embedding_model character varying(50) NOT NULL,
    embedding_generated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: motions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.motions (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    agenda_item_id uuid NOT NULL,
    motion_type character varying(30) NOT NULL,
    motion_text text NOT NULL,
    moved_by character varying(200),
    seconded_by character varying(200),
    result character varying(50) NOT NULL,
    vote_tally text,
    resolution_number character varying(200),
    sequence_number smallint DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    vote_explainer text,
    vote_explainer_generated_at timestamp with time zone,
    vote_explainer_model character varying(50),
    source character varying(20) DEFAULT 'minutes'::character varying
);


--
-- Name: COLUMN motions.vote_explainer; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.motions.vote_explainer IS 'AI-generated contextual vote explanation (S3.2). What was decided, why it matters, was it contentious.';


--
-- Name: COLUMN motions.vote_explainer_generated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.motions.vote_explainer_generated_at IS 'When the vote explainer was generated';


--
-- Name: COLUMN motions.vote_explainer_model; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.motions.vote_explainer_model IS 'Which AI model generated the explainer (e.g. claude-sonnet-4-20250514)';


--
-- Name: COLUMN motions.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.motions.source IS 'Origin of this motion record. ''minutes'' = extracted from official minutes PDF (ground truth, 4-6 week lag). ''transcript'' = preliminary extraction from transcript_recap text (1-3 day lag, may be incomplete). When minutes arrive, transcript-sourced rows for the same agenda_item are deleted before inserting minutes-sourced rows.';


--
-- Name: motions_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.motions_embeddings (
    id uuid NOT NULL,
    embedding extensions.halfvec(1536) NOT NULL,
    embedding_model character varying(50) NOT NULL,
    embedding_generated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: neighborhood_councils; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.neighborhood_councils (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) DEFAULT '0660620'::character varying NOT NULL,
    name text NOT NULL,
    short_name text,
    nc_type text DEFAULT 'neighborhood_council'::text NOT NULL,
    geojson_codes integer[] DEFAULT '{}'::integer[] NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    meeting_schedule text,
    meeting_time text,
    meeting_location text,
    city_page_url text,
    city_page_id integer,
    document_center_path text,
    contact_email text DEFAULT 'neighborhoods@ci.richmond.ca.us'::text,
    president text,
    vice_president text,
    notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE neighborhood_councils; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.neighborhood_councils IS 'Registry of Richmond neighborhood councils and HOAs with meeting info and GeoJSON mapping';


--
-- Name: COLUMN neighborhood_councils.nc_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.neighborhood_councils.nc_type IS 'neighborhood_council or hoa';


--
-- Name: COLUMN neighborhood_councils.geojson_codes; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.neighborhood_councils.geojson_codes IS 'Array of code values from richmond-neighborhoods.geojson that map to this NC';


--
-- Name: nextrequest_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nextrequest_documents (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    request_id uuid NOT NULL,
    document_id uuid,
    filename character varying(500),
    file_type character varying(50),
    file_size_bytes integer,
    page_count integer,
    download_url text,
    has_redactions boolean,
    released_date date,
    extracted_text text,
    extraction_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    extraction_metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    source_document_id bigint,
    source_removed_at timestamp with time zone
);


--
-- Name: COLUMN nextrequest_documents.source_document_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.nextrequest_documents.source_document_id IS 'Stable integer document ID from the NextRequest public API.';


--
-- Name: COLUMN nextrequest_documents.source_removed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.nextrequest_documents.source_removed_at IS 'Set only after a complete per-request public-document listing proves the document is absent/private; cleared if it reappears.';


--
-- Name: nextrequest_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nextrequest_requests (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    request_number character varying(50) NOT NULL,
    request_text text NOT NULL,
    requester_name character varying(200),
    department text,
    status character varying(50) NOT NULL,
    submitted_date date,
    due_date date,
    closed_date date,
    days_to_close integer,
    document_count integer DEFAULT 0,
    portal_url text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    source_removed_at timestamp with time zone
);


--
-- Name: COLUMN nextrequest_requests.source_removed_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.nextrequest_requests.source_removed_at IS 'Set only after a complete unfiltered public-request listing proves the request is absent; cleared if it reappears.';


--
-- Name: officials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.officials (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    name character varying(200) NOT NULL,
    normalized_name character varying(200) NOT NULL,
    role character varying(50) NOT NULL,
    seat character varying(20),
    party_affiliation character varying(50),
    term_start date,
    term_end date,
    is_current boolean DEFAULT false NOT NULL,
    email character varying(255),
    phone character varying(50),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    bio_factual jsonb,
    bio_summary text,
    bio_generated_at timestamp with time zone,
    bio_model character varying(50),
    bio_summary_provenance jsonb
);


--
-- Name: COLUMN officials.bio_factual; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.officials.bio_factual IS 'Layer 1: factual profile data derived from DB queries (JSON)';


--
-- Name: COLUMN officials.bio_summary; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.officials.bio_summary IS 'Layer 2: AI-synthesized narrative summary (Graduated tier)';


--
-- Name: COLUMN officials.bio_generated_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.officials.bio_generated_at IS 'Timestamp of last bio generation';


--
-- Name: COLUMN officials.bio_model; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.officials.bio_model IS 'Model used for Layer 2 generation (e.g. claude-sonnet-4-5-20250514)';


--
-- Name: COLUMN officials.bio_summary_provenance; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.officials.bio_summary_provenance IS 'Provenance struct for bio_summary. Written by generate_bios.py. Carries {from_minutes, from_transcript} vote counts so the bio UI can disclose when stats include transcript-extracted votes (which are pre-minutes and may revise). Highest-stakes provenance in the catalog: per-person attribution carries the most credibility weight.';


--
-- Name: officials_embeddings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.officials_embeddings (
    id uuid NOT NULL,
    embedding extensions.halfvec(1536) NOT NULL,
    embedding_model character varying(50) NOT NULL,
    embedding_generated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: opencorporates_api_usage; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.opencorporates_api_usage (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    endpoint text NOT NULL,
    query_params jsonb,
    response_status integer NOT NULL,
    called_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: operator_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.operator_config (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    publication jsonb DEFAULT '{"tier_low": 0.50, "blocklist": ["corruption", "corrupt", "illegal", "illegally", "bribery", "bribe", "kickback", "scandal", "scandalous", "suspicious", "suspiciously"], "tier_high": 0.85, "hedge_text": "Other explanations may exist.", "tier_medium": 0.70, "hedge_enabled": true}'::jsonb NOT NULL,
    evidence jsonb DEFAULT '{"sitting_mult": 1.0, "anomaly_factor": 0.20, "match_strength": 0.35, "corroboration_2": 1.15, "temporal_factor": 0.25, "financial_factor": 0.20, "non_sitting_mult": 0.6, "corroboration_3plus": 1.30}'::jsonb NOT NULL,
    temporal jsonb DEFAULT '{"bands": [{"days": 90, "factor": 1.0}, {"days": 180, "factor": 0.8}, {"days": 365, "factor": 0.6}, {"days": 730, "factor": 0.4}], "beyond_factor": 0.2, "post_vote_penalty": 0.70, "anomaly_boost_days": 30, "anomaly_boost_amount": 0.10}'::jsonb NOT NULL,
    financial jsonb DEFAULT '[{"min": 5000, "factor": 1.0}, {"min": 1000, "factor": 0.7}, {"min": 500, "factor": 0.5}, {"min": 100, "factor": 0.3}, {"min": 0, "factor": 0.1}]'::jsonb NOT NULL,
    quality jsonb DEFAULT '{"weight_urls": 20, "weight_items": 30, "weight_votes": 30, "min_baselines": 50, "anomaly_stddev": 2.0, "default_anomaly": 0.5, "weight_attendance": 20}'::jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_by text DEFAULT 'operator'::text NOT NULL
);


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    name character varying(500) NOT NULL,
    normalized_name character varying(500) NOT NULL,
    entity_number character varying(50),
    entity_type character varying(50),
    jurisdiction character varying(50),
    status character varying(30),
    registered_agent character varying(300),
    formation_date date,
    source character varying(50) NOT NULL,
    source_url text,
    source_updated_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: paper_filing_zero_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.paper_filing_zero_results (
    city_fips character varying(7) DEFAULT '0660620'::character varying NOT NULL,
    filing_id character varying NOT NULL,
    committee text NOT NULL,
    form_type character varying(3) NOT NULL,
    result_kind character varying(40) NOT NULL,
    extraction_method character varying(24) NOT NULL,
    extraction_model character varying(100) NOT NULL,
    source_url text NOT NULL,
    extracted_at timestamp with time zone DEFAULT now() NOT NULL,
    source_tier smallint DEFAULT 1 NOT NULL,
    confidence_score numeric(3,2) NOT NULL,
    CONSTRAINT paper_filing_zero_results_confidence_score_check CHECK (((confidence_score >= (0)::numeric) AND (confidence_score <= (1)::numeric))),
    CONSTRAINT paper_filing_zero_results_extraction_method_check CHECK (((extraction_method)::text = ANY ((ARRAY['rss_classification'::character varying, 'text_llm'::character varying, 'vision_llm'::character varying])::text[]))),
    CONSTRAINT paper_filing_zero_results_form_type_check CHECK (((form_type)::text = ANY ((ARRAY['410'::character varying, '460'::character varying, '497'::character varying])::text[]))),
    CONSTRAINT paper_filing_zero_results_result_kind_check CHECK (((result_kind)::text = ANY ((ARRAY['not_contribution_form'::character varying, 'extractor_returned_zero'::character varying])::text[]))),
    CONSTRAINT paper_filing_zero_results_source_tier_check CHECK (((source_tier >= 1) AND (source_tier <= 4))),
    CONSTRAINT paper_filing_zero_results_source_url_check CHECK ((btrim(source_url) <> ''::text))
);


--
-- Name: TABLE paper_filing_zero_results; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.paper_filing_zero_results IS 'Operator-only durable receipts for paper filings whose completed processing intentionally produced no contribution rows. Used for cross-CI idempotency; not a public claim of zero financial activity.';


--
-- Name: COLUMN paper_filing_zero_results.confidence_score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.paper_filing_zero_results.confidence_score IS 'Confidence that the recorded terminal pipeline outcome occurred. A value of 1.00 records a deterministic Form 410 classification or a structurally validated tool result; it does not rate semantic OCR accuracy.';


--
-- Name: pb_class_specs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pb_class_specs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips text DEFAULT '0660620'::text NOT NULL,
    title text NOT NULL,
    class_code text,
    department text,
    salary_range text,
    definition text,
    duties text,
    qualifications text,
    source_url text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now(),
    salary_min numeric(12,2),
    salary_max numeric(12,2),
    salary_type text,
    neogov_spec_id text
);


--
-- Name: TABLE pb_class_specs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pb_class_specs IS 'NEOGOV classification specifications - the board-approved job descriptions. PBC-owned table.';


--
-- Name: COLUMN pb_class_specs.salary_min; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pb_class_specs.salary_min IS 'Parsed minimum salary from spec (numeric for comparison)';


--
-- Name: COLUMN pb_class_specs.salary_max; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pb_class_specs.salary_max IS 'Parsed maximum salary from spec (numeric for comparison)';


--
-- Name: COLUMN pb_class_specs.salary_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pb_class_specs.salary_type IS 'Salary period: hourly, monthly, annually';


--
-- Name: COLUMN pb_class_specs.neogov_spec_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.pb_class_specs.neogov_spec_id IS 'NEOGOV classification spec ID for deduplication';


--
-- Name: pb_classification_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pb_classification_actions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips text DEFAULT '0660620'::text NOT NULL,
    meeting_id uuid,
    agenda_item_id uuid,
    action_type text NOT NULL,
    classification_title text NOT NULL,
    department text,
    action_date date NOT NULL,
    vote_result text,
    notes text,
    posting_found boolean DEFAULT false,
    posting_id uuid,
    days_to_posting integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE pb_classification_actions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pb_classification_actions IS 'Personnel Board classification actions cross-referenced to job postings. PBC-owned table.';


--
-- Name: pb_employee_compensation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pb_employee_compensation (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips text DEFAULT '0660620'::text NOT NULL,
    year integer NOT NULL,
    employee_name text NOT NULL,
    job_title text NOT NULL,
    department text,
    regular_pay numeric(12,2),
    overtime_pay numeric(12,2),
    other_pay numeric(12,2),
    total_pay numeric(12,2),
    benefits numeric(12,2),
    pension_debt numeric(12,2),
    total_compensation numeric(12,2),
    source_url text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE pb_employee_compensation; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pb_employee_compensation IS 'Transparent California employee compensation data (2011-2024). PBC-owned table.';


--
-- Name: pb_job_postings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pb_job_postings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips text DEFAULT '0660620'::text NOT NULL,
    neogov_id text,
    title text NOT NULL,
    department text,
    salary_min numeric(12,2),
    salary_max numeric(12,2),
    salary_type text,
    classification text,
    exempt_status text,
    posted_date date,
    closing_date date,
    is_promotional boolean DEFAULT false,
    status text DEFAULT 'unknown'::text,
    raw_description text,
    source_url text NOT NULL,
    ingested_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE pb_job_postings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pb_job_postings IS 'NEOGOV job postings - active and historical. PBC-owned table.';


--
-- Name: pb_new_employees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pb_new_employees (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips text DEFAULT '0660620'::text NOT NULL,
    employee_name text NOT NULL,
    job_title text NOT NULL,
    department text,
    employment_type text,
    report_month text,
    meeting_date date NOT NULL,
    meeting_id uuid,
    posting_id uuid,
    payroll_match boolean DEFAULT false,
    source_transcript text,
    extracted_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE pb_new_employees; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pb_new_employees IS 'New employees announced at City Council meetings, extracted from Granicus transcripts. PBC-owned table.';


--
-- Name: pb_research_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pb_research_log (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips text DEFAULT '0660620'::text NOT NULL,
    title text NOT NULL,
    body text,
    finding_type text DEFAULT 'observation'::text NOT NULL,
    status text DEFAULT 'draft'::text NOT NULL,
    priority text DEFAULT 'normal'::text NOT NULL,
    core_values text[] DEFAULT '{}'::text[] NOT NULL,
    lever text,
    evidence jsonb DEFAULT '[]'::jsonb NOT NULL,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    actioned_date date,
    actioned_notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE pb_research_log; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pb_research_log IS 'Research findings, execution gaps, spec gaps, and opportunities. PBC-owned table.';


--
-- Name: pending_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pending_decisions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    decision_type character varying(50) NOT NULL,
    severity character varying(20) DEFAULT 'info'::character varying NOT NULL,
    title text NOT NULL,
    description text NOT NULL,
    evidence jsonb DEFAULT '{}'::jsonb,
    source character varying(50) NOT NULL,
    entity_type character varying(50),
    entity_id text,
    link text,
    dedup_key character varying(200),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    resolved_at timestamp with time zone,
    resolved_by text,
    resolution_note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT pending_decisions_decision_type_check CHECK (((decision_type)::text = ANY ((ARRAY['staleness_alert'::character varying, 'anomaly'::character varying, 'data_quality'::character varying, 'tier_graduation'::character varying, 'conflict_review'::character varying, 'assessment_finding'::character varying, 'pipeline_failure'::character varying, 'general'::character varying])::text[])))
);


--
-- Name: TABLE pending_decisions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pending_decisions IS 'Operator decision queue (S7). Created by pipeline producers, resolved in Claude Code sessions.';


--
-- Name: pipeline_journal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_journal (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) NOT NULL,
    session_id uuid NOT NULL,
    entry_type character varying(50) NOT NULL,
    zone character varying(20) DEFAULT 'observation'::character varying NOT NULL,
    target_artifact text,
    description text NOT NULL,
    metrics jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE pipeline_journal; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.pipeline_journal IS 'Append-only log for pipeline self-assessment (Autonomy Zones Phase A). Never delete or update rows.';


--
-- Name: public_comments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.public_comments (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    meeting_id uuid NOT NULL,
    agenda_item_id uuid,
    speaker_name character varying(200) NOT NULL,
    method character varying(30) NOT NULL,
    summary text,
    comment_type character varying(30) DEFAULT 'public'::character varying NOT NULL,
    submitted_by_system boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    source character varying(30) DEFAULT 'minutes'::character varying,
    confidence real DEFAULT 1.0,
    extracted_at timestamp with time zone,
    city_fips character varying(7) DEFAULT '0660620'::character varying,
    name_confidence character varying(10) DEFAULT 'high'::character varying
);


--
-- Name: rate_limit_buckets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rate_limit_buckets (
    bucket_key text NOT NULL,
    window_start timestamp with time zone NOT NULL,
    count integer DEFAULT 0 NOT NULL
);


--
-- Name: scan_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scan_runs (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    meeting_id uuid,
    scan_mode character varying(20) NOT NULL,
    data_cutoff_date date,
    model_version character varying(100),
    prompt_version character varying(50),
    scanner_version character varying(50),
    contributions_count integer,
    contributions_sources jsonb,
    form700_count integer,
    flags_found integer DEFAULT 0 NOT NULL,
    flags_by_tier jsonb,
    clean_items_count integer,
    enriched_items_count integer,
    execution_time_seconds numeric(8,2),
    triggered_by character varying(50),
    pipeline_run_id character varying(100),
    status character varying(20) DEFAULT 'running'::character varying NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: search_queries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_queries (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) DEFAULT '0660620'::character varying NOT NULL,
    query_text text NOT NULL,
    result_count integer DEFAULT 0 NOT NULL,
    result_type_filter text,
    search_mode character varying(20) DEFAULT 'keyword'::character varying NOT NULL,
    client_hash character varying(64),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: source_watch_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_watch_state (
    source text NOT NULL,
    city_fips text DEFAULT '0660620'::text NOT NULL,
    fingerprint jsonb DEFAULT '{}'::jsonb NOT NULL,
    last_checked_at timestamp with time zone DEFAULT now(),
    last_changed_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: topics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.topics (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    city_fips character varying(7) DEFAULT '0660620'::character varying NOT NULL,
    slug character varying(100) NOT NULL,
    name character varying(200) NOT NULL,
    description text,
    primary_category character varying(50),
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    merged_into_id uuid,
    color_classes character varying(100),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    keywords text[] DEFAULT '{}'::text[] NOT NULL
);


--
-- Name: TABLE topics; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.topics IS 'Dynamic civic topics discovered by LLM extraction or keyword matching. Emergent layer on top of categories.';


--
-- Name: COLUMN topics.keywords; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.topics.keywords IS 'Lowercased substrings matched against agenda item text and news article text. Case-insensitive substring match; any hit counts.';


--
-- Name: user_feedback; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_feedback (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    city_fips character varying(7) NOT NULL,
    feedback_type character varying(30) NOT NULL,
    entity_type character varying(50),
    entity_id uuid,
    flag_verdict character varying(20),
    field_name character varying(100),
    current_value text,
    suggested_value text,
    conflict_nature character varying(50),
    official_name character varying(200),
    description text,
    evidence_url text,
    evidence_text text,
    submitter_email character varying(255),
    submitter_name character varying(200),
    is_anonymous boolean DEFAULT true NOT NULL,
    session_id character varying(100),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    moderator_notes text,
    reviewed_at timestamp with time zone,
    reviewed_by character varying(200),
    action_taken text,
    action_entity_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    page_url text
);


--
-- Name: v_appointment_network; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_appointment_network WITH (security_invoker='on') AS
 SELECT cm.city_fips,
    cm.appointed_by,
    o.id AS appointing_official_id,
    o.name AS appointing_official_name,
    c.name AS commission_name,
    c.commission_type,
    cm.name AS commissioner_name,
    cm.role,
    cm.term_start,
    cm.term_end,
    cm.is_current,
    cm.source
   FROM ((public.commission_members cm
     JOIN public.commissions c ON ((cm.commission_id = c.id)))
     LEFT JOIN public.officials o ON ((cm.appointed_by_official_id = o.id)))
  WHERE (cm.appointed_by IS NOT NULL);


--
-- Name: v_behested_by_official; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_behested_by_official AS
 SELECT city_fips,
    official_name,
    official_id,
    count(*) AS payment_count,
    sum(amount) AS total_amount,
    min(payment_date) AS earliest_payment,
    max(payment_date) AS latest_payment,
    count(DISTINCT payor_name) AS unique_payors,
    count(DISTINCT payee_name) AS unique_payees
   FROM public.behested_payments bp
  GROUP BY city_fips, official_name, official_id;


--
-- Name: v_body_meeting_counts; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_body_meeting_counts AS
 SELECT b.id AS body_id,
    b.city_fips,
    b.name AS body_name,
    b.body_type,
    b.short_name,
    b.is_active,
    count(m.id) AS meeting_count,
    min(m.meeting_date) AS first_meeting,
    max(m.meeting_date) AS last_meeting
   FROM (public.bodies b
     LEFT JOIN public.meetings m ON ((b.id = m.body_id)))
  GROUP BY b.id, b.city_fips, b.name, b.body_type, b.short_name, b.is_active;


--
-- Name: v_body_roster; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_body_roster AS
 SELECT b.id AS body_id,
    b.city_fips,
    b.name AS body_name,
    b.body_type,
    o.id AS member_id,
    o.name AS member_name,
    o.normalized_name,
    o.role,
    o.term_start,
    o.term_end,
    o.is_current,
    'officials'::text AS source_table
   FROM (public.bodies b
     JOIN public.officials o ON ((((o.city_fips)::text = (b.city_fips)::text) AND (o.is_current = true))))
  WHERE (((b.body_type)::text = 'city_council'::text) AND ((o.role)::text = ANY ((ARRAY['mayor'::character varying, 'vice_mayor'::character varying, 'councilmember'::character varying])::text[])))
UNION ALL
 SELECT b.id AS body_id,
    b.city_fips,
    b.name AS body_name,
    b.body_type,
    cm.id AS member_id,
    cm.name AS member_name,
    cm.normalized_name,
    cm.role,
    cm.term_start,
    cm.term_end,
    cm.is_current,
    'commission_members'::text AS source_table
   FROM (public.bodies b
     JOIN public.commission_members cm ON (((cm.commission_id = b.commission_id) AND (cm.is_current = true))))
  WHERE (b.commission_id IS NOT NULL);


--
-- Name: v_code_enforcement_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_code_enforcement_summary AS
 SELECT city_fips,
    case_type,
    (EXTRACT(year FROM opened_date))::integer AS year,
    count(*) AS total_cases,
    count(*) FILTER (WHERE (closed_date IS NOT NULL)) AS closed_cases,
    (avg((closed_date - opened_date)))::integer AS avg_days_to_close
   FROM public.city_code_cases
  WHERE (opened_date IS NOT NULL)
  GROUP BY city_fips, case_type, (EXTRACT(year FROM opened_date));


--
-- Name: v_commission_staleness; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_commission_staleness WITH (security_invoker='on') AS
 SELECT c.id AS commission_id,
    c.city_fips,
    c.name AS commission_name,
    c.last_website_scrape,
    count(cm.id) FILTER (WHERE (cm.website_stale_since IS NOT NULL)) AS stale_members,
    count(cm.id) FILTER (WHERE (cm.is_current = true)) AS total_current_members,
    min(cm.website_stale_since) AS oldest_stale_since,
    (CURRENT_DATE - min(cm.website_stale_since)) AS max_days_stale,
    array_agg(cm.name ORDER BY cm.name) FILTER (WHERE (cm.website_stale_since IS NOT NULL)) AS stale_member_names
   FROM (public.commissions c
     LEFT JOIN public.commission_members cm ON ((c.id = cm.commission_id)))
  GROUP BY c.id, c.city_fips, c.name, c.last_website_scrape
 HAVING (count(cm.id) FILTER (WHERE (cm.website_stale_since IS NOT NULL)) > 0);


--
-- Name: v_court_entity_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_court_entity_summary WITH (security_invoker='on') AS
 SELECT cm.city_fips,
    cm.entity_type,
    cm.entity_name,
    cm.official_id,
    cm.donor_id,
    count(DISTINCT cm.case_id) AS case_count,
    count(DISTINCT cm.court_party_id) AS party_count,
    max(cm.confidence) AS max_confidence,
    avg(cm.confidence) AS avg_confidence,
    array_agg(DISTINCT cc.case_type) AS case_types,
    min(cc.filing_date) AS earliest_case,
    max(cc.filing_date) AS latest_case,
    sum(
        CASE
            WHEN (cm.false_positive = true) THEN 1
            ELSE 0
        END) AS false_positive_count
   FROM (public.court_case_matches cm
     JOIN public.court_cases cc ON ((cm.case_id = cc.id)))
  WHERE (cm.false_positive IS NOT TRUE)
  GROUP BY cm.city_fips, cm.entity_type, cm.entity_name, cm.official_id, cm.donor_id;


--
-- Name: VIEW v_court_entity_summary; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_court_entity_summary IS 'Aggregated court case involvement by matched entity for conflict detection (S8.2)';


--
-- Name: votes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.votes (
    id uuid DEFAULT extensions.uuid_generate_v4() NOT NULL,
    motion_id uuid NOT NULL,
    official_id uuid,
    official_name character varying(200) NOT NULL,
    official_role character varying(50),
    vote_choice character varying(100) NOT NULL,
    source character varying(20) DEFAULT 'minutes'::character varying
);


--
-- Name: COLUMN votes.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.votes.source IS 'Origin of this vote record. Inherits semantics from motions.source.';


--
-- Name: v_donor_vote_crossref; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_donor_vote_crossref WITH (security_invoker='on') AS
 SELECT co.city_fips,
    d.name AS donor_name,
    d.employer AS donor_employer,
    co.amount,
    co.contribution_date,
    cm.name AS committee_name,
    cm.candidate_name,
    o.name AS official_name,
    m.meeting_date,
    ai.item_number,
    ai.title AS item_title,
    ai.financial_amount,
    v.vote_choice
   FROM (((((((public.contributions co
     JOIN public.donors d ON ((co.donor_id = d.id)))
     JOIN public.committees cm ON ((co.committee_id = cm.id)))
     LEFT JOIN public.officials o ON ((cm.official_id = o.id)))
     LEFT JOIN public.votes v ON ((v.official_id = o.id)))
     LEFT JOIN public.motions mt ON ((v.motion_id = mt.id)))
     LEFT JOIN public.agenda_items ai ON ((mt.agenda_item_id = ai.id)))
     LEFT JOIN public.meetings m ON ((ai.meeting_id = m.id)));


--
-- Name: v_entity_connections; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_entity_connections AS
 SELECT el.city_fips,
    el.person_name,
    el.normalized_person_name,
    el.role,
    el.role_detail,
    o.name AS organization_name,
    o.entity_type,
    o.entity_number,
    o.status AS org_status,
    o.source AS org_source,
    el.donor_id,
    el.official_id,
    el.confidence,
    el.effective_date
   FROM (public.entity_links el
     JOIN public.organizations o ON ((o.id = el.organization_id)))
  ORDER BY el.person_name, o.name;


--
-- Name: v_feedback_ground_truth; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_feedback_ground_truth WITH (security_invoker='on') AS
 SELECT uf.id AS feedback_id,
    uf.entity_id AS conflict_flag_id,
    cf.scan_run_id,
        CASE uf.flag_verdict
            WHEN 'confirm'::text THEN true
            WHEN 'dispute'::text THEN false
            ELSE NULL::boolean
        END AS ground_truth,
    'user_feedback'::text AS ground_truth_source,
    uf.description AS audit_notes,
    uf.created_at
   FROM (public.user_feedback uf
     JOIN public.conflict_flags cf ON ((uf.entity_id = cf.id)))
  WHERE (((uf.feedback_type)::text = 'flag_accuracy'::text) AND ((uf.status)::text = ANY ((ARRAY['accepted'::character varying, 'acted_on'::character varying])::text[])));


--
-- Name: v_influence_pattern_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_influence_pattern_summary AS
 SELECT cf.city_fips,
    ip.id AS pattern_id,
    ip.pattern_name,
    ip.sort_order,
    count(*) AS flag_count,
    count(DISTINCT cf.meeting_id) AS meeting_count,
    count(DISTINCT cf.official_id) AS official_count,
    avg(cf.confidence) AS avg_confidence,
    max(cf.confidence) AS max_confidence,
    count(*) FILTER (WHERE (cf.confidence >= 0.85)) AS high_confidence_flags,
    count(*) FILTER (WHERE ((cf.confidence >= 0.70) AND (cf.confidence < 0.85))) AS medium_confidence_flags
   FROM (public.conflict_flags cf
     JOIN public.influence_patterns ip ON ((ip.id = cf.influence_pattern_id)))
  WHERE (cf.is_current = true)
  GROUP BY cf.city_fips, ip.id, ip.pattern_name, ip.sort_order
  ORDER BY ip.sort_order;


--
-- Name: v_license_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_license_summary AS
 SELECT city_fips,
    business_type,
    status,
    count(*) AS total,
    sum(employees) AS total_employees
   FROM public.city_licenses
  GROUP BY city_fips, business_type, status;


--
-- Name: v_lobbyist_clients; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_lobbyist_clients AS
 SELECT city_fips,
    lobbyist_name,
    lobbyist_firm,
    client_name,
    registration_date,
    expiration_date,
    topics,
    status
   FROM public.lobbyist_registrations lr
  WHERE (((status)::text = 'active'::text) OR (expiration_date IS NULL) OR (expiration_date >= CURRENT_DATE));


--
-- Name: v_permit_activity; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_permit_activity AS
 SELECT city_fips,
    permit_type,
    (EXTRACT(year FROM applied_date))::integer AS year,
    count(*) AS total_permits,
    count(*) FILTER (WHERE ((status)::text = 'ISSUED'::text)) AS issued,
    count(*) FILTER (WHERE ((status)::text = 'FINALED'::text)) AS finaled,
    sum(job_value) AS total_job_value,
    sum(fees_charged) AS total_fees
   FROM public.city_permits
  WHERE (applied_date IS NOT NULL)
  GROUP BY city_fips, permit_type, (EXTRACT(year FROM applied_date));


--
-- Name: v_split_votes; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_split_votes WITH (security_invoker='on') AS
 SELECT m.city_fips,
    m.meeting_date,
    ai.item_number,
    ai.title AS item_title,
    ai.category,
    mt.motion_type,
    mt.result,
    mt.vote_tally,
    mt.id AS motion_id
   FROM ((public.motions mt
     JOIN public.agenda_items ai ON ((mt.agenda_item_id = ai.id)))
     JOIN public.meetings m ON ((ai.meeting_id = m.id)))
  WHERE ((mt.vote_tally !~~ '7-0'::text) AND (mt.vote_tally !~~ '%-0'::text) AND (mt.result IS NOT NULL));


--
-- Name: v_staff_agenda_context; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_staff_agenda_context WITH (security_invoker='on') AS
 SELECT ai.id AS agenda_item_id,
    ai.title AS item_title,
    ai.department AS item_department,
    m.meeting_date,
    m.city_fips,
    ce.name AS dept_head_name,
    ce.job_title AS dept_head_title,
    ce.department AS employee_department,
    ce.annual_salary,
    ce.hierarchy_level
   FROM ((public.agenda_items ai
     JOIN public.meetings m ON ((ai.meeting_id = m.id)))
     LEFT JOIN public.city_employees ce ON ((((m.city_fips)::text = (ce.city_fips)::text) AND (ce.is_current = true) AND (ce.is_department_head = true) AND (lower((ai.department)::text) = lower((ce.department)::text)))))
  WHERE (ai.department IS NOT NULL);


--
-- Name: v_topic_stats; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_topic_stats AS
 SELECT t.id,
    t.slug,
    t.name,
    t.primary_category,
    t.status,
    t.color_classes,
    count(DISTINCT it.agenda_item_id) AS item_count,
    min(m.meeting_date) AS first_seen,
    max(m.meeting_date) AS last_seen
   FROM (((public.topics t
     LEFT JOIN public.item_topics it ON ((it.topic_id = t.id)))
     LEFT JOIN public.agenda_items ai ON ((ai.id = it.agenda_item_id)))
     LEFT JOIN public.meetings m ON ((m.id = ai.meeting_id)))
  WHERE ((t.status)::text = 'active'::text)
  GROUP BY t.id, t.slug, t.name, t.primary_category, t.status, t.color_classes;


--
-- Name: v_vendor_spending_summary; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_vendor_spending_summary WITH (security_invoker='on') AS
 SELECT city_fips,
    vendor_name,
    normalized_vendor,
    fiscal_year,
    count(*) AS transaction_count,
    sum(amount) AS total_amount,
    min(expenditure_date) AS first_payment,
    max(expenditure_date) AS last_payment
   FROM public.city_expenditures
  GROUP BY city_fips, vendor_name, normalized_vendor, fiscal_year;


--
-- Name: v_votes_with_context; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_votes_with_context WITH (security_invoker='on') AS
 SELECT m.city_fips,
    m.meeting_date,
    m.meeting_type,
    ai.item_number,
    ai.title AS item_title,
    ai.category,
    ai.is_consent_calendar,
    ai.financial_amount,
    mt.motion_type,
    mt.motion_text,
    mt.result AS motion_result,
    mt.vote_tally,
    v.official_name,
    v.official_role,
    v.vote_choice,
    o.id AS official_id
   FROM ((((public.votes v
     JOIN public.motions mt ON ((v.motion_id = mt.id)))
     JOIN public.agenda_items ai ON ((mt.agenda_item_id = ai.id)))
     JOIN public.meetings m ON ((ai.meeting_id = m.id)))
     LEFT JOIN public.officials o ON ((v.official_id = o.id)));


--
-- Name: agenda_item_attachments agenda_item_attachments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_item_attachments
    ADD CONSTRAINT agenda_item_attachments_pkey PRIMARY KEY (id);


--
-- Name: agenda_items_embeddings agenda_items_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_items_embeddings
    ADD CONSTRAINT agenda_items_embeddings_pkey PRIMARY KEY (id);


--
-- Name: agenda_items agenda_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_items
    ADD CONSTRAINT agenda_items_pkey PRIMARY KEY (id);


--
-- Name: behested_payments behested_payments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.behested_payments
    ADD CONSTRAINT behested_payments_pkey PRIMARY KEY (id);


--
-- Name: bodies bodies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bodies
    ADD CONSTRAINT bodies_pkey PRIMARY KEY (id);


--
-- Name: business_entities business_entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.business_entities
    ADD CONSTRAINT business_entities_pkey PRIMARY KEY (id);


--
-- Name: business_entity_officers business_entity_officers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.business_entity_officers
    ADD CONSTRAINT business_entity_officers_pkey PRIMARY KEY (id);


--
-- Name: cities cities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cities
    ADD CONSTRAINT cities_pkey PRIMARY KEY (fips_code);


--
-- Name: city_code_cases city_code_cases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_code_cases
    ADD CONSTRAINT city_code_cases_pkey PRIMARY KEY (id);


--
-- Name: city_contracts city_contracts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_contracts
    ADD CONSTRAINT city_contracts_pkey PRIMARY KEY (id);


--
-- Name: city_employees city_employees_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_employees
    ADD CONSTRAINT city_employees_pkey PRIMARY KEY (id);


--
-- Name: city_expenditures city_expenditures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_expenditures
    ADD CONSTRAINT city_expenditures_pkey PRIMARY KEY (id);


--
-- Name: city_licenses city_licenses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_licenses
    ADD CONSTRAINT city_licenses_pkey PRIMARY KEY (id);


--
-- Name: city_permits city_permits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_permits
    ADD CONSTRAINT city_permits_pkey PRIMARY KEY (id);


--
-- Name: city_projects city_projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_projects
    ADD CONSTRAINT city_projects_pkey PRIMARY KEY (id);


--
-- Name: city_service_requests city_service_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_service_requests
    ADD CONSTRAINT city_service_requests_pkey PRIMARY KEY (id);


--
-- Name: closed_session_items closed_session_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.closed_session_items
    ADD CONSTRAINT closed_session_items_pkey PRIMARY KEY (id);


--
-- Name: comment_theme_assignments comment_theme_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment_theme_assignments
    ADD CONSTRAINT comment_theme_assignments_pkey PRIMARY KEY (id);


--
-- Name: comment_themes comment_themes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment_themes
    ADD CONSTRAINT comment_themes_pkey PRIMARY KEY (id);


--
-- Name: commission_members commission_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_members
    ADD CONSTRAINT commission_members_pkey PRIMARY KEY (id);


--
-- Name: commissions commissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commissions
    ADD CONSTRAINT commissions_pkey PRIMARY KEY (id);


--
-- Name: committees committees_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.committees
    ADD CONSTRAINT committees_pkey PRIMARY KEY (id);


--
-- Name: conflict_flags conflict_flags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conflict_flags
    ADD CONSTRAINT conflict_flags_pkey PRIMARY KEY (id);


--
-- Name: contributions contributions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contributions
    ADD CONSTRAINT contributions_pkey PRIMARY KEY (id);


--
-- Name: court_case_matches court_case_matches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_case_matches
    ADD CONSTRAINT court_case_matches_pkey PRIMARY KEY (id);


--
-- Name: court_case_parties court_case_parties_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_case_parties
    ADD CONSTRAINT court_case_parties_pkey PRIMARY KEY (id);


--
-- Name: court_cases court_cases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_cases
    ADD CONSTRAINT court_cases_pkey PRIMARY KEY (id);


--
-- Name: cpra_requests cpra_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cpra_requests
    ADD CONSTRAINT cpra_requests_pkey PRIMARY KEY (id);


--
-- Name: data_sync_log data_sync_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_sync_log
    ADD CONSTRAINT data_sync_log_pkey PRIMARY KEY (id);


--
-- Name: document_references document_references_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_references
    ADD CONSTRAINT document_references_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: donors donors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.donors
    ADD CONSTRAINT donors_pkey PRIMARY KEY (id);


--
-- Name: economic_interests economic_interests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.economic_interests
    ADD CONSTRAINT economic_interests_pkey PRIMARY KEY (id);


--
-- Name: election_candidates election_candidates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.election_candidates
    ADD CONSTRAINT election_candidates_pkey PRIMARY KEY (id);


--
-- Name: elections elections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.elections
    ADD CONSTRAINT elections_pkey PRIMARY KEY (id);


--
-- Name: email_preferences email_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_preferences
    ADD CONSTRAINT email_preferences_pkey PRIMARY KEY (id);


--
-- Name: email_preferences email_preferences_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_preferences
    ADD CONSTRAINT email_preferences_unique UNIQUE (subscriber_id, preference_type, preference_value);


--
-- Name: email_subscribers email_subscribers_email_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_subscribers
    ADD CONSTRAINT email_subscribers_email_unique UNIQUE (email);


--
-- Name: email_subscribers email_subscribers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_subscribers
    ADD CONSTRAINT email_subscribers_pkey PRIMARY KEY (id);


--
-- Name: entity_links entity_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_links
    ADD CONSTRAINT entity_links_pkey PRIMARY KEY (id);


--
-- Name: entity_name_matches entity_name_matches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_name_matches
    ADD CONSTRAINT entity_name_matches_pkey PRIMARY KEY (id);


--
-- Name: external_references external_references_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_references
    ADD CONSTRAINT external_references_pkey PRIMARY KEY (id);


--
-- Name: extraction_runs extraction_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction_runs
    ADD CONSTRAINT extraction_runs_pkey PRIMARY KEY (id);


--
-- Name: filing_period_briefings filing_period_briefings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filing_period_briefings
    ADD CONSTRAINT filing_period_briefings_pkey PRIMARY KEY (id);


--
-- Name: form700_filings form700_filings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form700_filings
    ADD CONSTRAINT form700_filings_pkey PRIMARY KEY (id);


--
-- Name: form_summary_cache form_summary_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form_summary_cache
    ADD CONSTRAINT form_summary_cache_pkey PRIMARY KEY (filing_id);


--
-- Name: friendly_amendments friendly_amendments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friendly_amendments
    ADD CONSTRAINT friendly_amendments_pkey PRIMARY KEY (id);


--
-- Name: independent_expenditures independent_expenditures_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.independent_expenditures
    ADD CONSTRAINT independent_expenditures_pkey PRIMARY KEY (id);


--
-- Name: influence_patterns influence_patterns_pattern_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.influence_patterns
    ADD CONSTRAINT influence_patterns_pattern_name_key UNIQUE (pattern_name);


--
-- Name: influence_patterns influence_patterns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.influence_patterns
    ADD CONSTRAINT influence_patterns_pkey PRIMARY KEY (id);


--
-- Name: item_theme_narratives item_theme_narratives_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.item_theme_narratives
    ADD CONSTRAINT item_theme_narratives_pkey PRIMARY KEY (id);


--
-- Name: item_topics item_topics_agenda_item_id_topic_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.item_topics
    ADD CONSTRAINT item_topics_agenda_item_id_topic_id_key UNIQUE (agenda_item_id, topic_id);


--
-- Name: item_topics item_topics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.item_topics
    ADD CONSTRAINT item_topics_pkey PRIMARY KEY (id);


--
-- Name: llm_cost_reservations llm_cost_reservations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.llm_cost_reservations
    ADD CONSTRAINT llm_cost_reservations_pkey PRIMARY KEY (id);


--
-- Name: lobbyist_document_extractions lobbyist_document_extractions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lobbyist_document_extractions
    ADD CONSTRAINT lobbyist_document_extractions_pkey PRIMARY KEY (city_fips, document_id, content_sha256, extraction_provider, extraction_model, prompt_version);


--
-- Name: lobbyist_registrations lobbyist_registrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lobbyist_registrations
    ADD CONSTRAINT lobbyist_registrations_pkey PRIMARY KEY (id);


--
-- Name: meeting_attendance meeting_attendance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meeting_attendance
    ADD CONSTRAINT meeting_attendance_pkey PRIMARY KEY (id);


--
-- Name: meetings_embeddings meetings_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings_embeddings
    ADD CONSTRAINT meetings_embeddings_pkey PRIMARY KEY (id);


--
-- Name: meetings meetings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_pkey PRIMARY KEY (id);


--
-- Name: motions_embeddings motions_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.motions_embeddings
    ADD CONSTRAINT motions_embeddings_pkey PRIMARY KEY (id);


--
-- Name: motions motions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.motions
    ADD CONSTRAINT motions_pkey PRIMARY KEY (id);


--
-- Name: neighborhood_councils neighborhood_councils_city_fips_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.neighborhood_councils
    ADD CONSTRAINT neighborhood_councils_city_fips_name_key UNIQUE (city_fips, name);


--
-- Name: neighborhood_councils neighborhood_councils_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.neighborhood_councils
    ADD CONSTRAINT neighborhood_councils_pkey PRIMARY KEY (id);


--
-- Name: nextrequest_documents nextrequest_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextrequest_documents
    ADD CONSTRAINT nextrequest_documents_pkey PRIMARY KEY (id);


--
-- Name: nextrequest_requests nextrequest_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextrequest_requests
    ADD CONSTRAINT nextrequest_requests_pkey PRIMARY KEY (id);


--
-- Name: officials_embeddings officials_embeddings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.officials_embeddings
    ADD CONSTRAINT officials_embeddings_pkey PRIMARY KEY (id);


--
-- Name: officials officials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.officials
    ADD CONSTRAINT officials_pkey PRIMARY KEY (id);


--
-- Name: opencorporates_api_usage opencorporates_api_usage_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.opencorporates_api_usage
    ADD CONSTRAINT opencorporates_api_usage_pkey PRIMARY KEY (id);


--
-- Name: operator_config operator_config_city_fips_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operator_config
    ADD CONSTRAINT operator_config_city_fips_key UNIQUE (city_fips);


--
-- Name: operator_config operator_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operator_config
    ADD CONSTRAINT operator_config_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: paper_filing_zero_results paper_filing_zero_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.paper_filing_zero_results
    ADD CONSTRAINT paper_filing_zero_results_pkey PRIMARY KEY (city_fips, filing_id);


--
-- Name: pb_class_specs pb_class_specs_city_fips_title_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_class_specs
    ADD CONSTRAINT pb_class_specs_city_fips_title_key UNIQUE (city_fips, title);


--
-- Name: pb_class_specs pb_class_specs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_class_specs
    ADD CONSTRAINT pb_class_specs_pkey PRIMARY KEY (id);


--
-- Name: pb_classification_actions pb_classification_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_classification_actions
    ADD CONSTRAINT pb_classification_actions_pkey PRIMARY KEY (id);


--
-- Name: pb_classification_actions pb_classification_actions_unique_action; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_classification_actions
    ADD CONSTRAINT pb_classification_actions_unique_action UNIQUE (city_fips, agenda_item_id);


--
-- Name: pb_employee_compensation pb_employee_compensation_city_fips_year_employee_name_job_t_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_employee_compensation
    ADD CONSTRAINT pb_employee_compensation_city_fips_year_employee_name_job_t_key UNIQUE (city_fips, year, employee_name, job_title);


--
-- Name: pb_employee_compensation pb_employee_compensation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_employee_compensation
    ADD CONSTRAINT pb_employee_compensation_pkey PRIMARY KEY (id);


--
-- Name: pb_job_postings pb_job_postings_city_fips_neogov_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_job_postings
    ADD CONSTRAINT pb_job_postings_city_fips_neogov_id_key UNIQUE (city_fips, neogov_id);


--
-- Name: pb_job_postings pb_job_postings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_job_postings
    ADD CONSTRAINT pb_job_postings_pkey PRIMARY KEY (id);


--
-- Name: pb_new_employees pb_new_employees_city_fips_employee_name_job_title_meeting__key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_new_employees
    ADD CONSTRAINT pb_new_employees_city_fips_employee_name_job_title_meeting__key UNIQUE (city_fips, employee_name, job_title, meeting_date);


--
-- Name: pb_new_employees pb_new_employees_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_new_employees
    ADD CONSTRAINT pb_new_employees_pkey PRIMARY KEY (id);


--
-- Name: pb_research_log pb_research_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_research_log
    ADD CONSTRAINT pb_research_log_pkey PRIMARY KEY (id);


--
-- Name: pending_decisions pending_decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pending_decisions
    ADD CONSTRAINT pending_decisions_pkey PRIMARY KEY (id);


--
-- Name: pipeline_journal pipeline_journal_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_journal
    ADD CONSTRAINT pipeline_journal_pkey PRIMARY KEY (id);


--
-- Name: public_comments public_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.public_comments
    ADD CONSTRAINT public_comments_pkey PRIMARY KEY (id);


--
-- Name: rate_limit_buckets rate_limit_buckets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rate_limit_buckets
    ADD CONSTRAINT rate_limit_buckets_pkey PRIMARY KEY (bucket_key, window_start);


--
-- Name: scan_runs scan_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_runs
    ADD CONSTRAINT scan_runs_pkey PRIMARY KEY (id);


--
-- Name: search_queries search_queries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_queries
    ADD CONSTRAINT search_queries_pkey PRIMARY KEY (id);


--
-- Name: source_change_jobs source_change_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_change_jobs
    ADD CONSTRAINT source_change_jobs_pkey PRIMARY KEY (change_id);


--
-- Name: source_watch_state source_watch_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_watch_state
    ADD CONSTRAINT source_watch_state_pkey PRIMARY KEY (source);


--
-- Name: topics topics_city_fips_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT topics_city_fips_slug_key UNIQUE (city_fips, slug);


--
-- Name: topics topics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT topics_pkey PRIMARY KEY (id);


--
-- Name: agenda_items uq_agenda_item; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_items
    ADD CONSTRAINT uq_agenda_item UNIQUE (meeting_id, item_number);


--
-- Name: meeting_attendance uq_attendance; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meeting_attendance
    ADD CONSTRAINT uq_attendance UNIQUE (meeting_id, official_id);


--
-- Name: behested_payments uq_behested_dedup; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.behested_payments
    ADD CONSTRAINT uq_behested_dedup UNIQUE (city_fips, source, source_identifier);


--
-- Name: bodies uq_bodies; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bodies
    ADD CONSTRAINT uq_bodies UNIQUE (city_fips, name);


--
-- Name: city_code_cases uq_city_code_case; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_code_cases
    ADD CONSTRAINT uq_city_code_case UNIQUE (city_fips, socrata_row_id);


--
-- Name: city_employees uq_city_employee; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_employees
    ADD CONSTRAINT uq_city_employee UNIQUE (city_fips, normalized_name, department, fiscal_year);


--
-- Name: city_expenditures uq_city_expenditure; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_expenditures
    ADD CONSTRAINT uq_city_expenditure UNIQUE (city_fips, socrata_row_id);


--
-- Name: city_licenses uq_city_license; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_licenses
    ADD CONSTRAINT uq_city_license UNIQUE (city_fips, socrata_row_id);


--
-- Name: city_permits uq_city_permit; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_permits
    ADD CONSTRAINT uq_city_permit UNIQUE (city_fips, socrata_row_id);


--
-- Name: city_projects uq_city_project; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_projects
    ADD CONSTRAINT uq_city_project UNIQUE (city_fips, socrata_row_id);


--
-- Name: city_service_requests uq_city_service_request; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_service_requests
    ADD CONSTRAINT uq_city_service_request UNIQUE (city_fips, socrata_row_id);


--
-- Name: closed_session_items uq_closed_session; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.closed_session_items
    ADD CONSTRAINT uq_closed_session UNIQUE (meeting_id, item_number);


--
-- Name: comment_theme_assignments uq_comment_theme; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment_theme_assignments
    ADD CONSTRAINT uq_comment_theme UNIQUE (comment_id, theme_id);


--
-- Name: commissions uq_commission; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commissions
    ADD CONSTRAINT uq_commission UNIQUE (city_fips, name);


--
-- Name: commission_members uq_commission_member; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_members
    ADD CONSTRAINT uq_commission_member UNIQUE (city_fips, commission_id, normalized_name);


--
-- Name: court_cases uq_court_case; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_cases
    ADD CONSTRAINT uq_court_case UNIQUE (county_fips, case_number);


--
-- Name: documents uq_documents_hash; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT uq_documents_hash UNIQUE (city_fips, content_hash);


--
-- Name: entity_links uq_entity_link; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_links
    ADD CONSTRAINT uq_entity_link UNIQUE (city_fips, normalized_person_name, organization_id, role, source);


--
-- Name: item_theme_narratives uq_item_theme_narrative; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.item_theme_narratives
    ADD CONSTRAINT uq_item_theme_narrative UNIQUE (agenda_item_id, theme_id);


--
-- Name: lobbyist_registrations uq_lobbyist_dedup; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lobbyist_registrations
    ADD CONSTRAINT uq_lobbyist_dedup UNIQUE (city_fips, source, source_identifier);


--
-- Name: meetings uq_meetings_date_type_body; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT uq_meetings_date_type_body UNIQUE (city_fips, meeting_date, meeting_type, body_id);


--
-- Name: nextrequest_requests uq_nextrequest; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextrequest_requests
    ADD CONSTRAINT uq_nextrequest UNIQUE (city_fips, request_number);


--
-- Name: officials uq_officials_name_term; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.officials
    ADD CONSTRAINT uq_officials_name_term UNIQUE (city_fips, normalized_name, term_start);


--
-- Name: organizations uq_org_source; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT uq_org_source UNIQUE (city_fips, source, entity_number);


--
-- Name: comment_themes uq_theme_slug_city; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment_themes
    ADD CONSTRAINT uq_theme_slug_city UNIQUE (city_fips, slug);


--
-- Name: votes uq_votes; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.votes
    ADD CONSTRAINT uq_votes UNIQUE (motion_id, official_name);


--
-- Name: user_feedback user_feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feedback
    ADD CONSTRAINT user_feedback_pkey PRIMARY KEY (id);


--
-- Name: votes votes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.votes
    ADD CONSTRAINT votes_pkey PRIMARY KEY (id);


--
-- Name: agenda_items_legal_framework_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agenda_items_legal_framework_idx ON public.agenda_items USING btree (legal_framework) WHERE (legal_framework IS NOT NULL);


--
-- Name: agenda_items_party_entities_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX agenda_items_party_entities_idx ON public.agenda_items USING gin (party_entities) WHERE (party_entities IS NOT NULL);


--
-- Name: conflict_flags_significance_tier_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX conflict_flags_significance_tier_idx ON public.conflict_flags USING btree (significance_tier) WHERE (significance_tier IS NOT NULL);


--
-- Name: form_summary_cache_committee_period_uniq; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX form_summary_cache_committee_period_uniq ON public.form_summary_cache USING btree (committee, ((summary ->> 'period_start'::text)), ((summary ->> 'period_end'::text)));


--
-- Name: idx_agenda_item_attachments_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_item_attachments_active ON public.agenda_item_attachments USING btree (agenda_item_id, document_id) WHERE (source_retired_at IS NULL);


--
-- Name: idx_agenda_items_active_meeting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_active_meeting ON public.agenda_items USING btree (meeting_id, item_number) WHERE (agenda_source_retired_at IS NULL);


--
-- Name: idx_agenda_items_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_category ON public.agenda_items USING btree (category);


--
-- Name: idx_agenda_items_category_meeting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_category_meeting ON public.agenda_items USING btree (category, meeting_id);


--
-- Name: idx_agenda_items_embeddings_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_embeddings_hnsw ON public.agenda_items_embeddings USING hnsw (embedding extensions.halfvec_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: idx_agenda_items_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_fts ON public.agenda_items USING gin (to_tsvector('english'::regconfig, ((((((((((COALESCE(title, ''::text) || ' '::text) || COALESCE(description, ''::text)) || ' '::text) || COALESCE(plain_language_summary, ''::text)) || ' '::text) || (COALESCE(category, ''::character varying))::text) || ' '::text) || (COALESCE(topic_label, ''::character varying))::text) || ' '::text) || COALESCE(summary_headline, ''::text))));


--
-- Name: idx_agenda_items_meeting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_meeting ON public.agenda_items USING btree (meeting_id);


--
-- Name: idx_agenda_items_meeting_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_meeting_id ON public.agenda_items USING btree (meeting_id);


--
-- Name: idx_agenda_items_proceeding_classification_claims; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_proceeding_classification_claims ON public.agenda_items USING btree (proceeding_classification_claim_expires_at) WHERE (proceeding_classification_claim_token IS NOT NULL);


--
-- Name: idx_agenda_items_proceeding_classification_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_proceeding_classification_pending ON public.agenda_items USING btree (proceeding_classification_attempts, id) WHERE ((proceeding_type IS NULL) AND (proceeding_classification_attempts < 3));


--
-- Name: idx_agenda_items_proceeding_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agenda_items_proceeding_type ON public.agenda_items USING btree (proceeding_type) WHERE (proceeding_type IS NOT NULL);


--
-- Name: idx_aia_agenda_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_aia_agenda_item_id ON public.agenda_item_attachments USING btree (agenda_item_id);


--
-- Name: idx_aia_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_aia_document_id ON public.agenda_item_attachments USING btree (document_id);


--
-- Name: idx_attendance_body; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_attendance_body ON public.meeting_attendance USING btree (body_id);


--
-- Name: idx_attendance_meeting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_attendance_meeting ON public.meeting_attendance USING btree (meeting_id);


--
-- Name: idx_behested_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_behested_date ON public.behested_payments USING btree (payment_date);


--
-- Name: idx_behested_official; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_behested_official ON public.behested_payments USING btree (official_id);


--
-- Name: idx_behested_official_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_behested_official_name ON public.behested_payments USING btree (official_name);


--
-- Name: idx_behested_payee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_behested_payee ON public.behested_payments USING btree (payee_name);


--
-- Name: idx_behested_payor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_behested_payor ON public.behested_payments USING btree (payor_name);


--
-- Name: idx_bodies_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bodies_active ON public.bodies USING btree (city_fips, is_active) WHERE (is_active = true);


--
-- Name: idx_bodies_commission; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bodies_commission ON public.bodies USING btree (commission_id);


--
-- Name: idx_bodies_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bodies_type ON public.bodies USING btree (body_type);


--
-- Name: idx_business_entities_city_fips; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_business_entities_city_fips ON public.business_entities USING btree (city_fips);


--
-- Name: idx_business_entities_jurisdiction; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_business_entities_jurisdiction ON public.business_entities USING btree (jurisdiction_code);


--
-- Name: idx_business_entities_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_business_entities_name ON public.business_entities USING btree (entity_name);


--
-- Name: idx_business_entities_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_business_entities_number ON public.business_entities USING btree (entity_number);


--
-- Name: idx_city_code_cases_address; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_code_cases_address ON public.city_code_cases USING btree (site_address);


--
-- Name: idx_city_code_cases_opened; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_code_cases_opened ON public.city_code_cases USING btree (opened_date);


--
-- Name: idx_city_code_cases_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_code_cases_status ON public.city_code_cases USING btree (status);


--
-- Name: idx_city_code_cases_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_code_cases_type ON public.city_code_cases USING btree (case_type);


--
-- Name: idx_city_contracts_approval_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_contracts_approval_date ON public.city_contracts USING btree (approval_date);


--
-- Name: idx_city_contracts_city_fips; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_contracts_city_fips ON public.city_contracts USING btree (city_fips);


--
-- Name: idx_city_contracts_contract_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_contracts_contract_type ON public.city_contracts USING btree (contract_type);


--
-- Name: idx_city_contracts_department; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_contracts_department ON public.city_contracts USING btree (department);


--
-- Name: idx_city_contracts_vendor_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_contracts_vendor_name ON public.city_contracts USING btree (vendor_name);


--
-- Name: idx_city_employees_current; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_employees_current ON public.city_employees USING btree (is_current, city_fips);


--
-- Name: idx_city_employees_dept; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_employees_dept ON public.city_employees USING btree (department);


--
-- Name: idx_city_employees_hierarchy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_employees_hierarchy ON public.city_employees USING btree (hierarchy_level, city_fips);


--
-- Name: idx_city_employees_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_employees_name ON public.city_employees USING btree (normalized_name);


--
-- Name: idx_city_employees_salary; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_employees_salary ON public.city_employees USING btree (annual_salary DESC);


--
-- Name: idx_city_expenditures_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_expenditures_date ON public.city_expenditures USING btree (expenditure_date DESC);


--
-- Name: idx_city_expenditures_dept; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_expenditures_dept ON public.city_expenditures USING btree (department);


--
-- Name: idx_city_expenditures_fy; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_expenditures_fy ON public.city_expenditures USING btree (fiscal_year, city_fips);


--
-- Name: idx_city_expenditures_vendor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_expenditures_vendor ON public.city_expenditures USING btree (normalized_vendor);


--
-- Name: idx_city_licenses_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_licenses_company ON public.city_licenses USING btree (normalized_company);


--
-- Name: idx_city_licenses_issued; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_licenses_issued ON public.city_licenses USING btree (license_issued);


--
-- Name: idx_city_licenses_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_licenses_status ON public.city_licenses USING btree (status);


--
-- Name: idx_city_licenses_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_licenses_type ON public.city_licenses USING btree (business_type);


--
-- Name: idx_city_projects_address; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_projects_address ON public.city_projects USING btree (site_address);


--
-- Name: idx_city_projects_applied; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_projects_applied ON public.city_projects USING btree (applied_date);


--
-- Name: idx_city_projects_applied_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_projects_applied_by ON public.city_projects USING btree (applied_by);


--
-- Name: idx_city_projects_resolution; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_projects_resolution ON public.city_projects USING btree (resolution_no);


--
-- Name: idx_city_projects_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_projects_status ON public.city_projects USING btree (status);


--
-- Name: idx_city_projects_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_projects_type ON public.city_projects USING btree (project_type);


--
-- Name: idx_city_service_requests_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_service_requests_created ON public.city_service_requests USING btree (created_date);


--
-- Name: idx_city_service_requests_dept; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_service_requests_dept ON public.city_service_requests USING btree (department);


--
-- Name: idx_city_service_requests_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_service_requests_status ON public.city_service_requests USING btree (status);


--
-- Name: idx_city_service_requests_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_city_service_requests_type ON public.city_service_requests USING btree (issue_type);


--
-- Name: idx_comments_meeting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_comments_meeting ON public.public_comments USING btree (meeting_id);


--
-- Name: idx_comments_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_comments_source ON public.public_comments USING btree (source);


--
-- Name: idx_commission_members_commission; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_commission_members_commission ON public.commission_members USING btree (commission_id);


--
-- Name: idx_commission_members_current; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_commission_members_current ON public.commission_members USING btree (is_current, city_fips);


--
-- Name: idx_commission_members_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_commission_members_name ON public.commission_members USING btree (normalized_name);


--
-- Name: idx_commission_members_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_commission_members_source ON public.commission_members USING btree (source);


--
-- Name: idx_commission_members_stale; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_commission_members_stale ON public.commission_members USING btree (website_stale_since) WHERE (website_stale_since IS NOT NULL);


--
-- Name: idx_commissions_form700; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_commissions_form700 ON public.commissions USING btree (form700_required, city_fips);


--
-- Name: idx_commissions_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_commissions_fts ON public.commissions USING gin (to_tsvector('english'::regconfig, (COALESCE(name, ''::character varying))::text));


--
-- Name: idx_commissions_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_commissions_type ON public.commissions USING btree (commission_type);


--
-- Name: idx_committees_election; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_committees_election ON public.committees USING btree (election_id);


--
-- Name: idx_committees_filer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_committees_filer ON public.committees USING btree (filer_id);


--
-- Name: idx_committees_official; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_committees_official ON public.committees USING btree (official_id);


--
-- Name: idx_conflict_flags_confidence_factors; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conflict_flags_confidence_factors ON public.conflict_flags USING gin (confidence_factors);


--
-- Name: idx_conflict_flags_match_details; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conflict_flags_match_details ON public.conflict_flags USING gin (match_details);


--
-- Name: idx_conflict_flags_pattern; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conflict_flags_pattern ON public.conflict_flags USING btree (influence_pattern_id) WHERE (influence_pattern_id IS NOT NULL);


--
-- Name: idx_conflict_flags_scanner_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conflict_flags_scanner_version ON public.conflict_flags USING btree (scanner_version);


--
-- Name: idx_conflict_flags_superseded_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_conflict_flags_superseded_by ON public.conflict_flags USING btree (superseded_by) WHERE (superseded_by IS NOT NULL);


--
-- Name: idx_contributions_amount; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_contributions_amount ON public.contributions USING btree (amount);


--
-- Name: idx_contributions_committee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_contributions_committee ON public.contributions USING btree (committee_id);


--
-- Name: idx_contributions_contributor_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_contributions_contributor_type ON public.contributions USING btree (contributor_type) WHERE (contributor_type IS NOT NULL);


--
-- Name: idx_contributions_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_contributions_date ON public.contributions USING btree (contribution_date);


--
-- Name: idx_contributions_donor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_contributions_donor ON public.contributions USING btree (donor_id);


--
-- Name: idx_contributions_election; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_contributions_election ON public.contributions USING btree (election_id);


--
-- Name: idx_court_cases_county; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_cases_county ON public.court_cases USING btree (county_fips);


--
-- Name: idx_court_cases_filing; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_cases_filing ON public.court_cases USING btree (filing_date DESC);


--
-- Name: idx_court_cases_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_cases_status ON public.court_cases USING btree (case_status);


--
-- Name: idx_court_matches_case; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_matches_case ON public.court_case_matches USING btree (case_id);


--
-- Name: idx_court_matches_confidence; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_matches_confidence ON public.court_case_matches USING btree (confidence DESC);


--
-- Name: idx_court_matches_donor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_matches_donor ON public.court_case_matches USING btree (donor_id);


--
-- Name: idx_court_matches_official; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_matches_official ON public.court_case_matches USING btree (official_id);


--
-- Name: idx_court_matches_unreviewed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_matches_unreviewed ON public.court_case_matches USING btree (city_fips) WHERE (reviewed = false);


--
-- Name: idx_court_parties_case; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_parties_case ON public.court_case_parties USING btree (case_id);


--
-- Name: idx_court_parties_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_parties_name ON public.court_case_parties USING btree (normalized_name);


--
-- Name: idx_court_parties_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_court_parties_type ON public.court_case_parties USING btree (party_type);


--
-- Name: idx_cpra_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cpra_status ON public.cpra_requests USING btree (status);


--
-- Name: idx_documents_ingested_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_ingested_at ON public.documents USING btree (ingested_at);


--
-- Name: idx_documents_metadata; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_metadata ON public.documents USING gin (metadata);


--
-- Name: idx_documents_source_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_source_type ON public.documents USING btree (source_type);


--
-- Name: idx_donors_employer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_donors_employer ON public.donors USING btree (normalized_employer);


--
-- Name: idx_donors_entity_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_donors_entity_slug ON public.donors USING btree (entity_slug);


--
-- Name: idx_donors_entity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_donors_entity_type ON public.donors USING btree (entity_type);


--
-- Name: idx_donors_normalized; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_donors_normalized ON public.donors USING btree (normalized_name);


--
-- Name: idx_ec_committee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ec_committee ON public.election_candidates USING btree (committee_id);


--
-- Name: idx_ec_election; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ec_election ON public.election_candidates USING btree (election_id);


--
-- Name: idx_ec_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ec_name ON public.election_candidates USING btree (normalized_name);


--
-- Name: idx_ec_official; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ec_official ON public.election_candidates USING btree (official_id);


--
-- Name: idx_elections_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_elections_date ON public.elections USING btree (election_date);


--
-- Name: idx_email_preferences_fips; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_preferences_fips ON public.email_preferences USING btree (city_fips);


--
-- Name: idx_email_preferences_subscriber; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_preferences_subscriber ON public.email_preferences USING btree (subscriber_id);


--
-- Name: idx_email_preferences_type_value; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_preferences_type_value ON public.email_preferences USING btree (preference_type, preference_value);


--
-- Name: idx_email_subscribers_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_subscribers_email ON public.email_subscribers USING btree (email);


--
-- Name: idx_email_subscribers_fips; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_subscribers_fips ON public.email_subscribers USING btree (city_fips);


--
-- Name: idx_email_subscribers_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_subscribers_status ON public.email_subscribers USING btree (status) WHERE ((status)::text = 'active'::text);


--
-- Name: idx_email_subscribers_token; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_email_subscribers_token ON public.email_subscribers USING btree (unsubscribe_token);


--
-- Name: idx_entity_links_donor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entity_links_donor ON public.entity_links USING btree (donor_id);


--
-- Name: idx_entity_links_official; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entity_links_official ON public.entity_links USING btree (official_id);


--
-- Name: idx_entity_links_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entity_links_org ON public.entity_links USING btree (organization_id);


--
-- Name: idx_entity_links_person; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entity_links_person ON public.entity_links USING btree (normalized_person_name);


--
-- Name: idx_entity_links_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entity_links_source ON public.entity_links USING btree (source);


--
-- Name: idx_entity_officers_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entity_officers_entity ON public.business_entity_officers USING btree (business_entity_id);


--
-- Name: idx_entity_officers_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_entity_officers_name ON public.business_entity_officers USING btree (officer_name);


--
-- Name: idx_ext_refs_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ext_refs_document ON public.external_references USING btree (document_id);


--
-- Name: idx_ext_refs_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ext_refs_entity ON public.external_references USING btree (entity_type, entity_id);


--
-- Name: idx_extraction_runs_current; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extraction_runs_current ON public.extraction_runs USING btree (document_id) WHERE (is_current = true);


--
-- Name: idx_extraction_runs_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_extraction_runs_document ON public.extraction_runs USING btree (document_id);


--
-- Name: idx_feedback_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_feedback_created ON public.user_feedback USING btree (created_at);


--
-- Name: idx_feedback_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_feedback_entity ON public.user_feedback USING btree (entity_type, entity_id);


--
-- Name: idx_feedback_pending; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_feedback_pending ON public.user_feedback USING btree (city_fips) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_feedback_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_feedback_status ON public.user_feedback USING btree (status);


--
-- Name: idx_feedback_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_feedback_type ON public.user_feedback USING btree (feedback_type);


--
-- Name: idx_flags_current; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_flags_current ON public.conflict_flags USING btree (meeting_id) WHERE (is_current = true);


--
-- Name: idx_flags_meeting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_flags_meeting ON public.conflict_flags USING btree (meeting_id);


--
-- Name: idx_flags_official; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_flags_official ON public.conflict_flags USING btree (official_id);


--
-- Name: idx_flags_publication_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_flags_publication_tier ON public.conflict_flags USING btree (publication_tier) WHERE (is_current = true);


--
-- Name: idx_flags_scan_run; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_flags_scan_run ON public.conflict_flags USING btree (scan_run_id);


--
-- Name: idx_flags_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_flags_type ON public.conflict_flags USING btree (flag_type);


--
-- Name: idx_flags_unreviewed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_flags_unreviewed ON public.conflict_flags USING btree (city_fips) WHERE (reviewed = false);


--
-- Name: idx_form700_filings_city; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_form700_filings_city ON public.form700_filings USING btree (city_fips);


--
-- Name: idx_form700_filings_official; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_form700_filings_official ON public.form700_filings USING btree (official_id);


--
-- Name: idx_form700_filings_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_form700_filings_year ON public.form700_filings USING btree (filing_year);


--
-- Name: idx_form_summary_cache_city; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_form_summary_cache_city ON public.form_summary_cache USING btree (city_fips);


--
-- Name: idx_form_summary_cache_committee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_form_summary_cache_committee ON public.form_summary_cache USING btree (committee);


--
-- Name: idx_fpb_election; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fpb_election ON public.filing_period_briefings USING btree (election_id);


--
-- Name: idx_fpb_period_end; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fpb_period_end ON public.filing_period_briefings USING btree (period_end);


--
-- Name: idx_fpb_publication_tier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_fpb_publication_tier ON public.filing_period_briefings USING btree (publication_tier);


--
-- Name: idx_ie_candidate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ie_candidate ON public.independent_expenditures USING btree (city_fips, candidate_name);


--
-- Name: idx_ie_committee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ie_committee ON public.independent_expenditures USING btree (city_fips, committee_name);


--
-- Name: idx_interests_filing; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interests_filing ON public.economic_interests USING btree (filing_id);


--
-- Name: idx_interests_official; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interests_official ON public.economic_interests USING btree (official_id);


--
-- Name: idx_interests_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interests_type ON public.economic_interests USING btree (interest_type);


--
-- Name: idx_item_topics_agenda_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_item_topics_agenda_item_id ON public.item_topics USING btree (agenda_item_id);


--
-- Name: idx_item_topics_topic_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_item_topics_topic_id ON public.item_topics USING btree (topic_id);


--
-- Name: idx_llm_cost_reservations_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_llm_cost_reservations_month ON public.llm_cost_reservations USING btree (created_at);


--
-- Name: idx_llm_cost_reservations_open; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_llm_cost_reservations_open ON public.llm_cost_reservations USING btree (created_at) WHERE (status = 'reserved'::text);


--
-- Name: idx_lobbyist_client; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lobbyist_client ON public.lobbyist_registrations USING btree (client_name);


--
-- Name: idx_lobbyist_document_extractions_latest; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lobbyist_document_extractions_latest ON public.lobbyist_document_extractions USING btree (city_fips, document_id, extracted_at DESC);


--
-- Name: idx_lobbyist_firm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lobbyist_firm ON public.lobbyist_registrations USING btree (lobbyist_firm);


--
-- Name: idx_lobbyist_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lobbyist_name ON public.lobbyist_registrations USING btree (lobbyist_name);


--
-- Name: idx_lobbyist_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lobbyist_status ON public.lobbyist_registrations USING btree (status);


--
-- Name: idx_meetings_body; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_meetings_body ON public.meetings USING btree (body_id);


--
-- Name: idx_meetings_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_meetings_date ON public.meetings USING btree (meeting_date);


--
-- Name: idx_meetings_embeddings_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_meetings_embeddings_hnsw ON public.meetings_embeddings USING hnsw (embedding extensions.halfvec_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: idx_meetings_source_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_meetings_source_active ON public.meetings USING btree (city_fips, meeting_date DESC) WHERE (source_cancelled_at IS NULL);


--
-- Name: idx_meetings_source_guid; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_meetings_source_guid ON public.meetings USING btree (city_fips, source_meeting_guid) WHERE (source_meeting_guid IS NOT NULL);


--
-- Name: idx_motions_agenda_item; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_motions_agenda_item ON public.motions USING btree (agenda_item_id);


--
-- Name: idx_motions_agenda_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_motions_agenda_item_id ON public.motions USING btree (agenda_item_id);


--
-- Name: idx_motions_embeddings_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_motions_embeddings_hnsw ON public.motions_embeddings USING hnsw (embedding extensions.halfvec_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: idx_motions_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_motions_fts ON public.motions USING gin (to_tsvector('english'::regconfig, COALESCE(vote_explainer, ''::text)));


--
-- Name: idx_motions_result; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_motions_result ON public.motions USING btree (result);


--
-- Name: idx_name_matches_entity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_name_matches_entity ON public.entity_name_matches USING btree (business_entity_id);


--
-- Name: idx_name_matches_review_queue; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_name_matches_review_queue ON public.entity_name_matches USING btree (reviewed, match_confidence) WHERE (reviewed = false);


--
-- Name: idx_name_matches_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_name_matches_source ON public.entity_name_matches USING btree (source_name);


--
-- Name: idx_name_matches_source_table; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_name_matches_source_table ON public.entity_name_matches USING btree (source_table, source_record_id);


--
-- Name: idx_neighborhood_councils_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_neighborhood_councils_active ON public.neighborhood_councils USING btree (is_active);


--
-- Name: idx_neighborhood_councils_geojson_codes; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_neighborhood_councils_geojson_codes ON public.neighborhood_councils USING gin (geojson_codes);


--
-- Name: idx_nextrequest_dept; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nextrequest_dept ON public.nextrequest_requests USING btree (department);


--
-- Name: idx_nextrequest_docs_extraction; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nextrequest_docs_extraction ON public.nextrequest_documents USING btree (extraction_status);


--
-- Name: idx_nextrequest_docs_request; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nextrequest_docs_request ON public.nextrequest_documents USING btree (request_id);


--
-- Name: idx_nextrequest_documents_public; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nextrequest_documents_public ON public.nextrequest_documents USING btree (request_id, released_date DESC) WHERE (source_removed_at IS NULL);


--
-- Name: idx_nextrequest_requests_public; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nextrequest_requests_public ON public.nextrequest_requests USING btree (city_fips, submitted_date DESC) WHERE (source_removed_at IS NULL);


--
-- Name: idx_nextrequest_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nextrequest_status ON public.nextrequest_requests USING btree (status);


--
-- Name: idx_nextrequest_submitted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nextrequest_submitted ON public.nextrequest_requests USING btree (submitted_date);


--
-- Name: idx_oc_api_usage_called_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_oc_api_usage_called_at ON public.opencorporates_api_usage USING btree (called_at);


--
-- Name: idx_officials_current; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_officials_current ON public.officials USING btree (city_fips) WHERE (is_current = true);


--
-- Name: idx_officials_embeddings_hnsw; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_officials_embeddings_hnsw ON public.officials_embeddings USING hnsw (embedding extensions.halfvec_cosine_ops) WITH (m='16', ef_construction='64');


--
-- Name: idx_officials_fts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_officials_fts ON public.officials USING gin (to_tsvector('english'::regconfig, (((COALESCE(name, ''::character varying))::text || ' '::text) || COALESCE(bio_summary, ''::text))));


--
-- Name: idx_officials_normalized_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_officials_normalized_name ON public.officials USING btree (normalized_name);


--
-- Name: idx_organizations_entity_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_organizations_entity_number ON public.organizations USING btree (entity_number);


--
-- Name: idx_organizations_entity_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_organizations_entity_type ON public.organizations USING btree (entity_type);


--
-- Name: idx_organizations_normalized_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_organizations_normalized_name ON public.organizations USING btree (normalized_name);


--
-- Name: idx_organizations_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_organizations_source ON public.organizations USING btree (source);


--
-- Name: idx_organizations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_organizations_status ON public.organizations USING btree (status);


--
-- Name: idx_pb_class_actions_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_class_actions_date ON public.pb_classification_actions USING btree (action_date);


--
-- Name: idx_pb_class_actions_posting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_class_actions_posting ON public.pb_classification_actions USING btree (posting_found);


--
-- Name: idx_pb_class_specs_fips; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_class_specs_fips ON public.pb_class_specs USING btree (city_fips);


--
-- Name: idx_pb_class_specs_neogov_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_pb_class_specs_neogov_id ON public.pb_class_specs USING btree (city_fips, neogov_spec_id) WHERE (neogov_spec_id IS NOT NULL);


--
-- Name: idx_pb_class_specs_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_class_specs_title ON public.pb_class_specs USING btree (title);


--
-- Name: idx_pb_emp_comp_dept; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_emp_comp_dept ON public.pb_employee_compensation USING btree (department);


--
-- Name: idx_pb_emp_comp_fips; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_emp_comp_fips ON public.pb_employee_compensation USING btree (city_fips);


--
-- Name: idx_pb_emp_comp_ot_analysis; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_emp_comp_ot_analysis ON public.pb_employee_compensation USING btree (city_fips, year, department) WHERE (overtime_pay > (0)::numeric);


--
-- Name: idx_pb_emp_comp_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_emp_comp_title ON public.pb_employee_compensation USING btree (job_title);


--
-- Name: idx_pb_emp_comp_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_emp_comp_year ON public.pb_employee_compensation USING btree (year);


--
-- Name: idx_pb_new_emp_dept; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_new_emp_dept ON public.pb_new_employees USING btree (department);


--
-- Name: idx_pb_new_emp_fips; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_new_emp_fips ON public.pb_new_employees USING btree (city_fips);


--
-- Name: idx_pb_new_emp_meeting_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_new_emp_meeting_date ON public.pb_new_employees USING btree (meeting_date);


--
-- Name: idx_pb_new_emp_report_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_new_emp_report_month ON public.pb_new_employees USING btree (report_month);


--
-- Name: idx_pb_new_emp_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_new_emp_title ON public.pb_new_employees USING btree (job_title);


--
-- Name: idx_pb_new_emp_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_new_emp_type ON public.pb_new_employees USING btree (employment_type);


--
-- Name: idx_pb_postings_dates; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_postings_dates ON public.pb_job_postings USING btree (posted_date, closing_date);


--
-- Name: idx_pb_postings_fips; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_postings_fips ON public.pb_job_postings USING btree (city_fips);


--
-- Name: idx_pb_postings_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_postings_status ON public.pb_job_postings USING btree (status);


--
-- Name: idx_pb_postings_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_postings_title ON public.pb_job_postings USING btree (title);


--
-- Name: idx_pb_research_log_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_research_log_created ON public.pb_research_log USING btree (created_at DESC);


--
-- Name: idx_pb_research_log_fips; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_research_log_fips ON public.pb_research_log USING btree (city_fips);


--
-- Name: idx_pb_research_log_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_research_log_priority ON public.pb_research_log USING btree (priority);


--
-- Name: idx_pb_research_log_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_research_log_status ON public.pb_research_log USING btree (status);


--
-- Name: idx_pb_research_log_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_research_log_tags ON public.pb_research_log USING gin (tags);


--
-- Name: idx_pb_research_log_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_research_log_type ON public.pb_research_log USING btree (finding_type);


--
-- Name: idx_pb_research_log_values; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pb_research_log_values ON public.pb_research_log USING gin (core_values);


--
-- Name: idx_pd_city_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pd_city_status ON public.pending_decisions USING btree (city_fips, status, created_at DESC);


--
-- Name: idx_pd_dedup_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_pd_dedup_unique ON public.pending_decisions USING btree (dedup_key) WHERE (((status)::text = 'pending'::text) AND (dedup_key IS NOT NULL));


--
-- Name: idx_pd_resolved; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pd_resolved ON public.pending_decisions USING btree (city_fips, resolved_at DESC) WHERE ((status)::text <> 'pending'::text);


--
-- Name: idx_pd_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pd_severity ON public.pending_decisions USING btree (severity, created_at DESC) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_pd_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pd_type ON public.pending_decisions USING btree (decision_type) WHERE ((status)::text = 'pending'::text);


--
-- Name: idx_pj_anomalies; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pj_anomalies ON public.pipeline_journal USING btree (city_fips, created_at DESC) WHERE ((entry_type)::text = 'anomaly_detected'::text);


--
-- Name: idx_pj_assessments; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pj_assessments ON public.pipeline_journal USING btree (city_fips, created_at DESC) WHERE ((entry_type)::text = 'assessment'::text);


--
-- Name: idx_pj_city_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pj_city_created ON public.pipeline_journal USING btree (city_fips, created_at DESC);


--
-- Name: idx_pj_session; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pj_session ON public.pipeline_journal USING btree (session_id);


--
-- Name: idx_pj_type_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pj_type_created ON public.pipeline_journal USING btree (entry_type, created_at DESC);


--
-- Name: idx_public_comments_agenda_item_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_public_comments_agenda_item_id ON public.public_comments USING btree (agenda_item_id) WHERE (agenda_item_id IS NOT NULL);


--
-- Name: idx_rate_limit_buckets_window; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rate_limit_buckets_window ON public.rate_limit_buckets USING btree (window_start);


--
-- Name: idx_scan_runs_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_runs_created ON public.scan_runs USING btree (created_at);


--
-- Name: idx_scan_runs_meeting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_runs_meeting ON public.scan_runs USING btree (meeting_id);


--
-- Name: idx_scan_runs_mode; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_runs_mode ON public.scan_runs USING btree (scan_mode);


--
-- Name: idx_scan_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scan_runs_status ON public.scan_runs USING btree (status);


--
-- Name: idx_search_queries_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_search_queries_created ON public.search_queries USING btree (city_fips, created_at DESC);


--
-- Name: idx_search_queries_zero_results; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_search_queries_zero_results ON public.search_queries USING btree (city_fips, created_at DESC) WHERE (result_count = 0);


--
-- Name: idx_source_change_jobs_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_source_change_jobs_due ON public.source_change_jobs USING btree (status, next_attempt_at, lease_expires_at) WHERE ((status)::text = ANY ((ARRAY['pending'::character varying, 'dispatched'::character varying, 'running'::character varying, 'retry_wait'::character varying])::text[]));


--
-- Name: idx_source_change_jobs_source_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_source_change_jobs_source_created ON public.source_change_jobs USING btree (source, created_at DESC);


--
-- Name: idx_sync_log_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sync_log_source ON public.data_sync_log USING btree (source);


--
-- Name: idx_sync_log_started; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sync_log_started ON public.data_sync_log USING btree (started_at);


--
-- Name: idx_sync_log_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sync_log_status ON public.data_sync_log USING btree (status);


--
-- Name: idx_theme_assignments_comment; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_theme_assignments_comment ON public.comment_theme_assignments USING btree (comment_id);


--
-- Name: idx_theme_assignments_theme; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_theme_assignments_theme ON public.comment_theme_assignments USING btree (theme_id);


--
-- Name: idx_theme_narratives_item; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_theme_narratives_item ON public.item_theme_narratives USING btree (agenda_item_id);


--
-- Name: idx_theme_narratives_theme; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_theme_narratives_theme ON public.item_theme_narratives USING btree (theme_id);


--
-- Name: idx_topics_keywords_gin; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_topics_keywords_gin ON public.topics USING gin (keywords);


--
-- Name: idx_topics_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_topics_status ON public.topics USING btree (status) WHERE ((status)::text = 'active'::text);


--
-- Name: idx_votes_choice; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_votes_choice ON public.votes USING btree (vote_choice);


--
-- Name: idx_votes_motion; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_votes_motion ON public.votes USING btree (motion_id);


--
-- Name: idx_votes_motion_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_votes_motion_id ON public.votes USING btree (motion_id);


--
-- Name: idx_votes_official; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_votes_official ON public.votes USING btree (official_id);


--
-- Name: idx_votes_vote_choice; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_votes_vote_choice ON public.votes USING btree (vote_choice);


--
-- Name: meetings_meeting_recap_provenance_kind_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX meetings_meeting_recap_provenance_kind_idx ON public.meetings USING btree (((meeting_recap_provenance ->> 'kind'::text))) WHERE (meeting_recap_provenance IS NOT NULL);


--
-- Name: meetings_meeting_summary_provenance_kind_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX meetings_meeting_summary_provenance_kind_idx ON public.meetings USING btree (((meeting_summary_provenance ->> 'kind'::text))) WHERE (meeting_summary_provenance IS NOT NULL);


--
-- Name: motions_source_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX motions_source_idx ON public.motions USING btree (source);


--
-- Name: officials_bio_summary_provenance_kind_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX officials_bio_summary_provenance_kind_idx ON public.officials USING btree (((bio_summary_provenance ->> 'kind'::text))) WHERE (bio_summary_provenance IS NOT NULL);


--
-- Name: uq_business_entities_number_jurisdiction; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_business_entities_number_jurisdiction ON public.business_entities USING btree (entity_number, jurisdiction_code) WHERE (entity_number IS NOT NULL);


--
-- Name: uq_city_contracts_vendor_number_date; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_city_contracts_vendor_number_date ON public.city_contracts USING btree (vendor_name, contract_number, approval_date) WHERE (contract_number IS NOT NULL);


--
-- Name: uq_contributions_dedup; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_contributions_dedup ON public.contributions USING btree (donor_id, amount, contribution_date, committee_id) WHERE (contribution_date IS NOT NULL);


--
-- Name: uq_data_sync_log_change_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_data_sync_log_change_id ON public.data_sync_log USING btree (city_fips, source, change_id) WHERE (change_id IS NOT NULL);


--
-- Name: uq_donors; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_donors ON public.donors USING btree (city_fips, normalized_name, COALESCE(employer, ''::character varying));


--
-- Name: uq_election_candidates; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_election_candidates ON public.election_candidates USING btree (city_fips, election_id, normalized_name, office_sought);


--
-- Name: uq_elections_city_date_type; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_elections_city_date_type ON public.elections USING btree (city_fips, election_date, election_type);


--
-- Name: uq_extraction_runs_document; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_extraction_runs_document ON public.extraction_runs USING btree (document_id);


--
-- Name: uq_filing_period_briefings_current; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_filing_period_briefings_current ON public.filing_period_briefings USING btree (city_fips, election_id, period_label) WHERE is_current;


--
-- Name: uq_form700_filing; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_form700_filing ON public.form700_filings USING btree (city_fips, filer_name, filing_year, statement_type, source);


--
-- Name: uq_independent_expenditures_natural_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_independent_expenditures_natural_key ON public.independent_expenditures USING btree (city_fips, committee_name, COALESCE(payee_name, ''::character varying), amount, expenditure_date, COALESCE(support_or_oppose, ''::character varying), COALESCE(candidate_name, ''::character varying));


--
-- Name: uq_motions_natural_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_motions_natural_key ON public.motions USING btree (agenda_item_id, motion_type, COALESCE(motion_text, ''::text), COALESCE(result, ''::character varying));


--
-- Name: uq_nextrequest_documents_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_nextrequest_documents_source_id ON public.nextrequest_documents USING btree (request_id, source_document_id) WHERE (source_document_id IS NOT NULL);


--
-- Name: uq_public_comments_natural_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_public_comments_natural_key ON public.public_comments USING btree (meeting_id, COALESCE((agenda_item_id)::text, ''::text), COALESCE(speaker_name, ''::character varying), COALESCE(summary, ''::text));


--
-- Name: votes_source_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX votes_source_idx ON public.votes USING btree (source);


--
-- Name: agenda_items trg_agenda_item_count; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_agenda_item_count AFTER INSERT OR DELETE OR UPDATE OF agenda_source_retired_at, meeting_id ON public.agenda_items FOR EACH ROW EXECUTE FUNCTION public.update_meeting_agenda_item_count();


--
-- Name: agenda_item_attachments agenda_item_attachments_agenda_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_item_attachments
    ADD CONSTRAINT agenda_item_attachments_agenda_item_id_fkey FOREIGN KEY (agenda_item_id) REFERENCES public.agenda_items(id) ON DELETE CASCADE;


--
-- Name: agenda_items_embeddings agenda_items_embeddings_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_items_embeddings
    ADD CONSTRAINT agenda_items_embeddings_id_fkey FOREIGN KEY (id) REFERENCES public.agenda_items(id) ON DELETE CASCADE;


--
-- Name: agenda_items agenda_items_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agenda_items
    ADD CONSTRAINT agenda_items_meeting_id_fkey FOREIGN KEY (meeting_id) REFERENCES public.meetings(id) ON DELETE CASCADE;


--
-- Name: behested_payments behested_payments_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.behested_payments
    ADD CONSTRAINT behested_payments_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: behested_payments behested_payments_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.behested_payments
    ADD CONSTRAINT behested_payments_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id);


--
-- Name: bodies bodies_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bodies
    ADD CONSTRAINT bodies_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: bodies bodies_commission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bodies
    ADD CONSTRAINT bodies_commission_id_fkey FOREIGN KEY (commission_id) REFERENCES public.commissions(id) ON DELETE SET NULL;


--
-- Name: bodies bodies_parent_body_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bodies
    ADD CONSTRAINT bodies_parent_body_id_fkey FOREIGN KEY (parent_body_id) REFERENCES public.bodies(id);


--
-- Name: business_entity_officers business_entity_officers_business_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.business_entity_officers
    ADD CONSTRAINT business_entity_officers_business_entity_id_fkey FOREIGN KEY (business_entity_id) REFERENCES public.business_entities(id) ON DELETE CASCADE;


--
-- Name: city_code_cases city_code_cases_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_code_cases
    ADD CONSTRAINT city_code_cases_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: city_employees city_employees_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_employees
    ADD CONSTRAINT city_employees_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: city_expenditures city_expenditures_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_expenditures
    ADD CONSTRAINT city_expenditures_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: city_licenses city_licenses_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_licenses
    ADD CONSTRAINT city_licenses_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: city_permits city_permits_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_permits
    ADD CONSTRAINT city_permits_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: city_projects city_projects_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_projects
    ADD CONSTRAINT city_projects_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: city_service_requests city_service_requests_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.city_service_requests
    ADD CONSTRAINT city_service_requests_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: closed_session_items closed_session_items_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.closed_session_items
    ADD CONSTRAINT closed_session_items_meeting_id_fkey FOREIGN KEY (meeting_id) REFERENCES public.meetings(id) ON DELETE CASCADE;


--
-- Name: comment_theme_assignments comment_theme_assignments_comment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment_theme_assignments
    ADD CONSTRAINT comment_theme_assignments_comment_id_fkey FOREIGN KEY (comment_id) REFERENCES public.public_comments(id) ON DELETE CASCADE;


--
-- Name: comment_theme_assignments comment_theme_assignments_theme_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment_theme_assignments
    ADD CONSTRAINT comment_theme_assignments_theme_id_fkey FOREIGN KEY (theme_id) REFERENCES public.comment_themes(id) ON DELETE CASCADE;


--
-- Name: comment_themes comment_themes_merged_into_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment_themes
    ADD CONSTRAINT comment_themes_merged_into_id_fkey FOREIGN KEY (merged_into_id) REFERENCES public.comment_themes(id);


--
-- Name: commission_members commission_members_appointed_by_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_members
    ADD CONSTRAINT commission_members_appointed_by_official_id_fkey FOREIGN KEY (appointed_by_official_id) REFERENCES public.officials(id);


--
-- Name: commission_members commission_members_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_members
    ADD CONSTRAINT commission_members_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: commission_members commission_members_commission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_members
    ADD CONSTRAINT commission_members_commission_id_fkey FOREIGN KEY (commission_id) REFERENCES public.commissions(id) ON DELETE CASCADE;


--
-- Name: commission_members commission_members_source_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commission_members
    ADD CONSTRAINT commission_members_source_meeting_id_fkey FOREIGN KEY (source_meeting_id) REFERENCES public.meetings(id);


--
-- Name: commissions commissions_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.commissions
    ADD CONSTRAINT commissions_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: committees committees_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.committees
    ADD CONSTRAINT committees_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: committees committees_election_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.committees
    ADD CONSTRAINT committees_election_id_fkey FOREIGN KEY (election_id) REFERENCES public.elections(id);


--
-- Name: committees committees_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.committees
    ADD CONSTRAINT committees_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id);


--
-- Name: conflict_flags conflict_flags_agenda_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conflict_flags
    ADD CONSTRAINT conflict_flags_agenda_item_id_fkey FOREIGN KEY (agenda_item_id) REFERENCES public.agenda_items(id);


--
-- Name: conflict_flags conflict_flags_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conflict_flags
    ADD CONSTRAINT conflict_flags_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: conflict_flags conflict_flags_influence_pattern_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conflict_flags
    ADD CONSTRAINT conflict_flags_influence_pattern_id_fkey FOREIGN KEY (influence_pattern_id) REFERENCES public.influence_patterns(id) ON DELETE SET NULL;


--
-- Name: conflict_flags conflict_flags_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conflict_flags
    ADD CONSTRAINT conflict_flags_meeting_id_fkey FOREIGN KEY (meeting_id) REFERENCES public.meetings(id);


--
-- Name: conflict_flags conflict_flags_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conflict_flags
    ADD CONSTRAINT conflict_flags_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id);


--
-- Name: conflict_flags conflict_flags_scan_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conflict_flags
    ADD CONSTRAINT conflict_flags_scan_run_id_fkey FOREIGN KEY (scan_run_id) REFERENCES public.scan_runs(id);


--
-- Name: conflict_flags conflict_flags_superseded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conflict_flags
    ADD CONSTRAINT conflict_flags_superseded_by_fkey FOREIGN KEY (superseded_by) REFERENCES public.conflict_flags(id);


--
-- Name: contributions contributions_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contributions
    ADD CONSTRAINT contributions_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: contributions contributions_committee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contributions
    ADD CONSTRAINT contributions_committee_id_fkey FOREIGN KEY (committee_id) REFERENCES public.committees(id);


--
-- Name: contributions contributions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contributions
    ADD CONSTRAINT contributions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: contributions contributions_donor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contributions
    ADD CONSTRAINT contributions_donor_id_fkey FOREIGN KEY (donor_id) REFERENCES public.donors(id);


--
-- Name: contributions contributions_election_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contributions
    ADD CONSTRAINT contributions_election_id_fkey FOREIGN KEY (election_id) REFERENCES public.elections(id);


--
-- Name: court_case_matches court_case_matches_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_case_matches
    ADD CONSTRAINT court_case_matches_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.court_cases(id) ON DELETE CASCADE;


--
-- Name: court_case_matches court_case_matches_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_case_matches
    ADD CONSTRAINT court_case_matches_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: court_case_matches court_case_matches_court_party_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_case_matches
    ADD CONSTRAINT court_case_matches_court_party_id_fkey FOREIGN KEY (court_party_id) REFERENCES public.court_case_parties(id) ON DELETE CASCADE;


--
-- Name: court_case_matches court_case_matches_donor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_case_matches
    ADD CONSTRAINT court_case_matches_donor_id_fkey FOREIGN KEY (donor_id) REFERENCES public.donors(id);


--
-- Name: court_case_matches court_case_matches_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_case_matches
    ADD CONSTRAINT court_case_matches_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id);


--
-- Name: court_case_parties court_case_parties_case_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_case_parties
    ADD CONSTRAINT court_case_parties_case_id_fkey FOREIGN KEY (case_id) REFERENCES public.court_cases(id) ON DELETE CASCADE;


--
-- Name: court_cases court_cases_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.court_cases
    ADD CONSTRAINT court_cases_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: cpra_requests cpra_requests_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cpra_requests
    ADD CONSTRAINT cpra_requests_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: cpra_requests cpra_requests_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cpra_requests
    ADD CONSTRAINT cpra_requests_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: data_sync_log data_sync_log_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_sync_log
    ADD CONSTRAINT data_sync_log_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: document_references document_references_resolved_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_references
    ADD CONSTRAINT document_references_resolved_document_id_fkey FOREIGN KEY (resolved_document_id) REFERENCES public.documents(id);


--
-- Name: document_references document_references_source_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_references
    ADD CONSTRAINT document_references_source_document_id_fkey FOREIGN KEY (source_document_id) REFERENCES public.documents(id);


--
-- Name: donors donors_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.donors
    ADD CONSTRAINT donors_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: economic_interests economic_interests_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.economic_interests
    ADD CONSTRAINT economic_interests_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: economic_interests economic_interests_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.economic_interests
    ADD CONSTRAINT economic_interests_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: economic_interests economic_interests_filing_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.economic_interests
    ADD CONSTRAINT economic_interests_filing_id_fkey FOREIGN KEY (filing_id) REFERENCES public.form700_filings(id);


--
-- Name: economic_interests economic_interests_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.economic_interests
    ADD CONSTRAINT economic_interests_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id);


--
-- Name: election_candidates election_candidates_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.election_candidates
    ADD CONSTRAINT election_candidates_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: election_candidates election_candidates_committee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.election_candidates
    ADD CONSTRAINT election_candidates_committee_id_fkey FOREIGN KEY (committee_id) REFERENCES public.committees(id) ON DELETE SET NULL;


--
-- Name: election_candidates election_candidates_election_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.election_candidates
    ADD CONSTRAINT election_candidates_election_id_fkey FOREIGN KEY (election_id) REFERENCES public.elections(id) ON DELETE CASCADE;


--
-- Name: election_candidates election_candidates_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.election_candidates
    ADD CONSTRAINT election_candidates_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id) ON DELETE SET NULL;


--
-- Name: elections elections_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.elections
    ADD CONSTRAINT elections_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: email_preferences email_preferences_subscriber_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_preferences
    ADD CONSTRAINT email_preferences_subscriber_id_fkey FOREIGN KEY (subscriber_id) REFERENCES public.email_subscribers(id) ON DELETE CASCADE;


--
-- Name: email_subscribers email_subscribers_last_orientation_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.email_subscribers
    ADD CONSTRAINT email_subscribers_last_orientation_meeting_id_fkey FOREIGN KEY (last_orientation_meeting_id) REFERENCES public.meetings(id) ON DELETE SET NULL;


--
-- Name: entity_links entity_links_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_links
    ADD CONSTRAINT entity_links_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: entity_links entity_links_donor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_links
    ADD CONSTRAINT entity_links_donor_id_fkey FOREIGN KEY (donor_id) REFERENCES public.donors(id);


--
-- Name: entity_links entity_links_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_links
    ADD CONSTRAINT entity_links_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id);


--
-- Name: entity_links entity_links_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_links
    ADD CONSTRAINT entity_links_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: entity_name_matches entity_name_matches_business_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_name_matches
    ADD CONSTRAINT entity_name_matches_business_entity_id_fkey FOREIGN KEY (business_entity_id) REFERENCES public.business_entities(id) ON DELETE SET NULL;


--
-- Name: external_references external_references_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.external_references
    ADD CONSTRAINT external_references_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: extraction_runs extraction_runs_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.extraction_runs
    ADD CONSTRAINT extraction_runs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: filing_period_briefings filing_period_briefings_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filing_period_briefings
    ADD CONSTRAINT filing_period_briefings_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: filing_period_briefings filing_period_briefings_election_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.filing_period_briefings
    ADD CONSTRAINT filing_period_briefings_election_id_fkey FOREIGN KEY (election_id) REFERENCES public.elections(id) ON DELETE SET NULL;


--
-- Name: form700_filings form700_filings_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form700_filings
    ADD CONSTRAINT form700_filings_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: form700_filings form700_filings_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form700_filings
    ADD CONSTRAINT form700_filings_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: form700_filings form700_filings_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.form700_filings
    ADD CONSTRAINT form700_filings_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id);


--
-- Name: friendly_amendments friendly_amendments_motion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.friendly_amendments
    ADD CONSTRAINT friendly_amendments_motion_id_fkey FOREIGN KEY (motion_id) REFERENCES public.motions(id) ON DELETE CASCADE;


--
-- Name: item_theme_narratives item_theme_narratives_agenda_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.item_theme_narratives
    ADD CONSTRAINT item_theme_narratives_agenda_item_id_fkey FOREIGN KEY (agenda_item_id) REFERENCES public.agenda_items(id) ON DELETE CASCADE;


--
-- Name: item_theme_narratives item_theme_narratives_theme_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.item_theme_narratives
    ADD CONSTRAINT item_theme_narratives_theme_id_fkey FOREIGN KEY (theme_id) REFERENCES public.comment_themes(id) ON DELETE CASCADE;


--
-- Name: item_topics item_topics_agenda_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.item_topics
    ADD CONSTRAINT item_topics_agenda_item_id_fkey FOREIGN KEY (agenda_item_id) REFERENCES public.agenda_items(id) ON DELETE CASCADE;


--
-- Name: item_topics item_topics_topic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.item_topics
    ADD CONSTRAINT item_topics_topic_id_fkey FOREIGN KEY (topic_id) REFERENCES public.topics(id) ON DELETE CASCADE;


--
-- Name: lobbyist_registrations lobbyist_registrations_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lobbyist_registrations
    ADD CONSTRAINT lobbyist_registrations_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: meeting_attendance meeting_attendance_body_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meeting_attendance
    ADD CONSTRAINT meeting_attendance_body_id_fkey FOREIGN KEY (body_id) REFERENCES public.bodies(id);


--
-- Name: meeting_attendance meeting_attendance_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meeting_attendance
    ADD CONSTRAINT meeting_attendance_meeting_id_fkey FOREIGN KEY (meeting_id) REFERENCES public.meetings(id) ON DELETE CASCADE;


--
-- Name: meeting_attendance meeting_attendance_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meeting_attendance
    ADD CONSTRAINT meeting_attendance_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id);


--
-- Name: meetings meetings_body_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_body_id_fkey FOREIGN KEY (body_id) REFERENCES public.bodies(id);


--
-- Name: meetings meetings_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: meetings meetings_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: meetings_embeddings meetings_embeddings_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.meetings_embeddings
    ADD CONSTRAINT meetings_embeddings_id_fkey FOREIGN KEY (id) REFERENCES public.meetings(id) ON DELETE CASCADE;


--
-- Name: motions motions_agenda_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.motions
    ADD CONSTRAINT motions_agenda_item_id_fkey FOREIGN KEY (agenda_item_id) REFERENCES public.agenda_items(id) ON DELETE CASCADE;


--
-- Name: motions_embeddings motions_embeddings_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.motions_embeddings
    ADD CONSTRAINT motions_embeddings_id_fkey FOREIGN KEY (id) REFERENCES public.motions(id) ON DELETE CASCADE;


--
-- Name: nextrequest_documents nextrequest_documents_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextrequest_documents
    ADD CONSTRAINT nextrequest_documents_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id);


--
-- Name: nextrequest_documents nextrequest_documents_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextrequest_documents
    ADD CONSTRAINT nextrequest_documents_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.nextrequest_requests(id) ON DELETE CASCADE;


--
-- Name: nextrequest_requests nextrequest_requests_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nextrequest_requests
    ADD CONSTRAINT nextrequest_requests_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: officials officials_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.officials
    ADD CONSTRAINT officials_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: officials_embeddings officials_embeddings_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.officials_embeddings
    ADD CONSTRAINT officials_embeddings_id_fkey FOREIGN KEY (id) REFERENCES public.officials(id) ON DELETE CASCADE;


--
-- Name: organizations organizations_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: pb_classification_actions pb_classification_actions_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pb_classification_actions
    ADD CONSTRAINT pb_classification_actions_posting_id_fkey FOREIGN KEY (posting_id) REFERENCES public.pb_job_postings(id);


--
-- Name: public_comments public_comments_agenda_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.public_comments
    ADD CONSTRAINT public_comments_agenda_item_id_fkey FOREIGN KEY (agenda_item_id) REFERENCES public.agenda_items(id);


--
-- Name: public_comments public_comments_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.public_comments
    ADD CONSTRAINT public_comments_meeting_id_fkey FOREIGN KEY (meeting_id) REFERENCES public.meetings(id) ON DELETE CASCADE;


--
-- Name: scan_runs scan_runs_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_runs
    ADD CONSTRAINT scan_runs_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: scan_runs scan_runs_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scan_runs
    ADD CONSTRAINT scan_runs_meeting_id_fkey FOREIGN KEY (meeting_id) REFERENCES public.meetings(id);


--
-- Name: source_change_jobs source_change_jobs_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_change_jobs
    ADD CONSTRAINT source_change_jobs_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: topics topics_merged_into_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT topics_merged_into_id_fkey FOREIGN KEY (merged_into_id) REFERENCES public.topics(id);


--
-- Name: user_feedback user_feedback_city_fips_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_feedback
    ADD CONSTRAINT user_feedback_city_fips_fkey FOREIGN KEY (city_fips) REFERENCES public.cities(fips_code);


--
-- Name: votes votes_motion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.votes
    ADD CONSTRAINT votes_motion_id_fkey FOREIGN KEY (motion_id) REFERENCES public.motions(id) ON DELETE CASCADE;


--
-- Name: votes votes_official_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.votes
    ADD CONSTRAINT votes_official_id_fkey FOREIGN KEY (official_id) REFERENCES public.officials(id);


--
-- Name: pb_new_employees Anon insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Anon insert" ON public.pb_new_employees FOR INSERT WITH CHECK (true);


--
-- Name: pb_new_employees Anon update; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Anon update" ON public.pb_new_employees FOR UPDATE USING (true) WITH CHECK (true);


--
-- Name: agenda_item_attachments Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.agenda_item_attachments FOR SELECT USING (((source_retired_at IS NULL) AND (EXISTS ( SELECT 1
   FROM public.agenda_items ai
  WHERE ((ai.id = agenda_item_attachments.agenda_item_id) AND (ai.agenda_source_retired_at IS NULL))))));


--
-- Name: agenda_items Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.agenda_items FOR SELECT USING (((agenda_source_retired_at IS NULL) AND (EXISTS ( SELECT 1
   FROM public.meetings parent_meeting
  WHERE ((parent_meeting.id = agenda_items.meeting_id) AND (parent_meeting.source_cancelled_at IS NULL))))));


--
-- Name: agenda_items_embeddings Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.agenda_items_embeddings FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.agenda_items ai
  WHERE ((ai.id = agenda_items_embeddings.id) AND (ai.agenda_source_retired_at IS NULL)))));


--
-- Name: bodies Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.bodies FOR SELECT USING (true);


--
-- Name: business_entities Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.business_entities FOR SELECT USING (true);


--
-- Name: business_entity_officers Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.business_entity_officers FOR SELECT USING (true);


--
-- Name: cities Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.cities FOR SELECT USING (true);


--
-- Name: city_code_cases Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.city_code_cases FOR SELECT USING (true);


--
-- Name: city_contracts Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.city_contracts FOR SELECT USING (true);


--
-- Name: city_employees Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.city_employees FOR SELECT USING (true);


--
-- Name: city_expenditures Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.city_expenditures FOR SELECT USING (true);


--
-- Name: city_licenses Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.city_licenses FOR SELECT USING (true);


--
-- Name: city_permits Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.city_permits FOR SELECT USING (true);


--
-- Name: city_projects Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.city_projects FOR SELECT USING (true);


--
-- Name: city_service_requests Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.city_service_requests FOR SELECT USING (true);


--
-- Name: closed_session_items Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.closed_session_items FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.meetings parent_meeting
  WHERE ((parent_meeting.id = closed_session_items.meeting_id) AND (parent_meeting.source_cancelled_at IS NULL)))));


--
-- Name: comment_theme_assignments Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.comment_theme_assignments FOR SELECT USING ((EXISTS ( SELECT 1
   FROM ((public.public_comments pc
     JOIN public.meetings parent_meeting ON ((parent_meeting.id = pc.meeting_id)))
     LEFT JOIN public.agenda_items ai ON ((ai.id = pc.agenda_item_id)))
  WHERE ((pc.id = comment_theme_assignments.comment_id) AND (parent_meeting.source_cancelled_at IS NULL) AND ((pc.agenda_item_id IS NULL) OR (ai.agenda_source_retired_at IS NULL))))));


--
-- Name: comment_themes Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.comment_themes FOR SELECT USING (true);


--
-- Name: commission_members Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.commission_members FOR SELECT USING (true);


--
-- Name: commissions Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.commissions FOR SELECT USING (true);


--
-- Name: committees Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.committees FOR SELECT USING (true);


--
-- Name: conflict_flags Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.conflict_flags FOR SELECT USING ((((meeting_id IS NULL) OR (EXISTS ( SELECT 1
   FROM public.meetings parent_meeting
  WHERE ((parent_meeting.id = conflict_flags.meeting_id) AND (parent_meeting.source_cancelled_at IS NULL))))) AND ((agenda_item_id IS NULL) OR (EXISTS ( SELECT 1
   FROM public.agenda_items ai
  WHERE ((ai.id = conflict_flags.agenda_item_id) AND (ai.agenda_source_retired_at IS NULL)))))));


--
-- Name: contributions Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.contributions FOR SELECT USING (true);


--
-- Name: court_case_matches Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.court_case_matches FOR SELECT USING (true);


--
-- Name: court_case_parties Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.court_case_parties FOR SELECT USING (true);


--
-- Name: court_cases Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.court_cases FOR SELECT USING (true);


--
-- Name: cpra_requests Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.cpra_requests FOR SELECT USING (true);


--
-- Name: data_sync_log Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.data_sync_log FOR SELECT USING (true);


--
-- Name: document_references Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.document_references FOR SELECT USING (((EXISTS ( SELECT 1
   FROM public.documents source_document
  WHERE ((source_document.id = document_references.source_document_id) AND (source_document.source_retired_at IS NULL)))) AND ((resolved_document_id IS NULL) OR (EXISTS ( SELECT 1
   FROM public.documents resolved_document
  WHERE ((resolved_document.id = document_references.resolved_document_id) AND (resolved_document.source_retired_at IS NULL)))))));


--
-- Name: documents Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.documents FOR SELECT USING ((source_retired_at IS NULL));


--
-- Name: donors Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.donors FOR SELECT USING (true);


--
-- Name: economic_interests Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.economic_interests FOR SELECT USING (true);


--
-- Name: election_candidates Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.election_candidates FOR SELECT USING (true);


--
-- Name: elections Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.elections FOR SELECT USING (true);


--
-- Name: entity_links Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.entity_links FOR SELECT USING (true);


--
-- Name: entity_name_matches Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.entity_name_matches FOR SELECT USING (true);


--
-- Name: external_references Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.external_references FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.documents parent_document
  WHERE ((parent_document.id = external_references.document_id) AND (parent_document.source_retired_at IS NULL)))));


--
-- Name: extraction_runs Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.extraction_runs FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.documents parent_document
  WHERE ((parent_document.id = extraction_runs.document_id) AND (parent_document.source_retired_at IS NULL)))));


--
-- Name: form700_filings Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.form700_filings FOR SELECT USING (true);


--
-- Name: friendly_amendments Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.friendly_amendments FOR SELECT USING ((EXISTS ( SELECT 1
   FROM ((public.motions mo
     JOIN public.agenda_items ai ON ((ai.id = mo.agenda_item_id)))
     JOIN public.meetings parent_meeting ON ((parent_meeting.id = ai.meeting_id)))
  WHERE ((mo.id = friendly_amendments.motion_id) AND (ai.agenda_source_retired_at IS NULL) AND (parent_meeting.source_cancelled_at IS NULL)))));


--
-- Name: independent_expenditures Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.independent_expenditures FOR SELECT USING (true);


--
-- Name: influence_patterns Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.influence_patterns FOR SELECT USING (true);


--
-- Name: item_theme_narratives Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.item_theme_narratives FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.agenda_items ai
  WHERE ((ai.id = item_theme_narratives.agenda_item_id) AND (ai.agenda_source_retired_at IS NULL)))));


--
-- Name: item_topics Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.item_topics FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.agenda_items ai
  WHERE ((ai.id = item_topics.agenda_item_id) AND (ai.agenda_source_retired_at IS NULL)))));


--
-- Name: meeting_attendance Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.meeting_attendance FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.meetings parent_meeting
  WHERE ((parent_meeting.id = meeting_attendance.meeting_id) AND (parent_meeting.source_cancelled_at IS NULL)))));


--
-- Name: meetings Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.meetings FOR SELECT USING ((source_cancelled_at IS NULL));


--
-- Name: meetings_embeddings Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.meetings_embeddings FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.meetings parent_meeting
  WHERE ((parent_meeting.id = meetings_embeddings.id) AND (parent_meeting.source_cancelled_at IS NULL)))));


--
-- Name: motions Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.motions FOR SELECT USING ((EXISTS ( SELECT 1
   FROM public.agenda_items ai
  WHERE ((ai.id = motions.agenda_item_id) AND (ai.agenda_source_retired_at IS NULL)))));


--
-- Name: motions_embeddings Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.motions_embeddings FOR SELECT USING ((EXISTS ( SELECT 1
   FROM (public.motions mo
     JOIN public.agenda_items ai ON ((ai.id = mo.agenda_item_id)))
  WHERE ((mo.id = motions_embeddings.id) AND (ai.agenda_source_retired_at IS NULL)))));


--
-- Name: nextrequest_documents Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.nextrequest_documents FOR SELECT USING (((source_removed_at IS NULL) AND (EXISTS ( SELECT 1
   FROM public.nextrequest_requests parent_request
  WHERE ((parent_request.id = nextrequest_documents.request_id) AND (parent_request.source_removed_at IS NULL))))));


--
-- Name: nextrequest_requests Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.nextrequest_requests FOR SELECT USING ((source_removed_at IS NULL));


--
-- Name: officials Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.officials FOR SELECT USING (true);


--
-- Name: organizations Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.organizations FOR SELECT USING (true);


--
-- Name: pb_class_specs Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.pb_class_specs FOR SELECT USING (true);


--
-- Name: pb_classification_actions Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.pb_classification_actions FOR SELECT USING (true);


--
-- Name: pb_employee_compensation Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.pb_employee_compensation FOR SELECT USING (true);


--
-- Name: pb_job_postings Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.pb_job_postings FOR SELECT USING (true);


--
-- Name: pb_new_employees Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.pb_new_employees FOR SELECT USING (true);


--
-- Name: pb_research_log Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.pb_research_log FOR SELECT USING (true);


--
-- Name: public_comments Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.public_comments FOR SELECT USING (((EXISTS ( SELECT 1
   FROM public.meetings parent_meeting
  WHERE ((parent_meeting.id = public_comments.meeting_id) AND (parent_meeting.source_cancelled_at IS NULL)))) AND ((agenda_item_id IS NULL) OR (EXISTS ( SELECT 1
   FROM public.agenda_items ai
  WHERE ((ai.id = public_comments.agenda_item_id) AND (ai.agenda_source_retired_at IS NULL)))))));


--
-- Name: scan_runs Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.scan_runs FOR SELECT USING (true);


--
-- Name: topics Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.topics FOR SELECT USING (true);


--
-- Name: user_feedback Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.user_feedback FOR SELECT USING (true);


--
-- Name: votes Public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read" ON public.votes FOR SELECT USING ((EXISTS ( SELECT 1
   FROM (public.motions mo
     JOIN public.agenda_items ai ON ((ai.id = mo.agenda_item_id)))
  WHERE ((mo.id = votes.motion_id) AND (ai.agenda_source_retired_at IS NULL)))));


--
-- Name: filing_period_briefings Public read public-tier briefings; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Public read public-tier briefings" ON public.filing_period_briefings FOR SELECT USING ((((publication_tier)::text = 'public'::text) AND is_current));


--
-- Name: email_preferences Service role full access on email_preferences; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access on email_preferences" ON public.email_preferences TO service_role USING (true) WITH CHECK (true);


--
-- Name: email_subscribers Service role full access on email_subscribers; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access on email_subscribers" ON public.email_subscribers TO service_role USING (true) WITH CHECK (true);


--
-- Name: source_change_jobs Service role full access to source_change_jobs; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to source_change_jobs" ON public.source_change_jobs TO service_role USING (true) WITH CHECK (true);


--
-- Name: source_watch_state Service role full access to source_watch_state; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role full access to source_watch_state" ON public.source_watch_state USING ((auth.role() = 'service_role'::text));


--
-- Name: agenda_item_attachments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.agenda_item_attachments ENABLE ROW LEVEL SECURITY;

--
-- Name: agenda_items; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.agenda_items ENABLE ROW LEVEL SECURITY;

--
-- Name: agenda_items_embeddings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.agenda_items_embeddings ENABLE ROW LEVEL SECURITY;

--
-- Name: user_feedback anon_insert_feedback; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY anon_insert_feedback ON public.user_feedback FOR INSERT TO anon WITH CHECK (true);


--
-- Name: behested_payments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.behested_payments ENABLE ROW LEVEL SECURITY;

--
-- Name: behested_payments behested_payments_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY behested_payments_read ON public.behested_payments FOR SELECT USING (true);


--
-- Name: bodies; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.bodies ENABLE ROW LEVEL SECURITY;

--
-- Name: business_entities; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.business_entities ENABLE ROW LEVEL SECURITY;

--
-- Name: business_entity_officers; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.business_entity_officers ENABLE ROW LEVEL SECURITY;

--
-- Name: cities; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.cities ENABLE ROW LEVEL SECURITY;

--
-- Name: city_code_cases; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.city_code_cases ENABLE ROW LEVEL SECURITY;

--
-- Name: city_contracts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.city_contracts ENABLE ROW LEVEL SECURITY;

--
-- Name: city_employees; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.city_employees ENABLE ROW LEVEL SECURITY;

--
-- Name: city_expenditures; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.city_expenditures ENABLE ROW LEVEL SECURITY;

--
-- Name: city_licenses; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.city_licenses ENABLE ROW LEVEL SECURITY;

--
-- Name: city_permits; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.city_permits ENABLE ROW LEVEL SECURITY;

--
-- Name: city_projects; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.city_projects ENABLE ROW LEVEL SECURITY;

--
-- Name: city_service_requests; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.city_service_requests ENABLE ROW LEVEL SECURITY;

--
-- Name: closed_session_items; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.closed_session_items ENABLE ROW LEVEL SECURITY;

--
-- Name: comment_theme_assignments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.comment_theme_assignments ENABLE ROW LEVEL SECURITY;

--
-- Name: comment_themes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.comment_themes ENABLE ROW LEVEL SECURITY;

--
-- Name: commission_members; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.commission_members ENABLE ROW LEVEL SECURITY;

--
-- Name: commissions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.commissions ENABLE ROW LEVEL SECURITY;

--
-- Name: committees; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.committees ENABLE ROW LEVEL SECURITY;

--
-- Name: conflict_flags; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.conflict_flags ENABLE ROW LEVEL SECURITY;

--
-- Name: contributions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.contributions ENABLE ROW LEVEL SECURITY;

--
-- Name: court_case_matches; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.court_case_matches ENABLE ROW LEVEL SECURITY;

--
-- Name: court_case_parties; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.court_case_parties ENABLE ROW LEVEL SECURITY;

--
-- Name: court_cases; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.court_cases ENABLE ROW LEVEL SECURITY;

--
-- Name: cpra_requests; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.cpra_requests ENABLE ROW LEVEL SECURITY;

--
-- Name: data_sync_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.data_sync_log ENABLE ROW LEVEL SECURITY;

--
-- Name: document_references; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.document_references ENABLE ROW LEVEL SECURITY;

--
-- Name: documents; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

--
-- Name: donors; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.donors ENABLE ROW LEVEL SECURITY;

--
-- Name: economic_interests; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.economic_interests ENABLE ROW LEVEL SECURITY;

--
-- Name: election_candidates; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.election_candidates ENABLE ROW LEVEL SECURITY;

--
-- Name: elections; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.elections ENABLE ROW LEVEL SECURITY;

--
-- Name: email_preferences; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.email_preferences ENABLE ROW LEVEL SECURITY;

--
-- Name: email_subscribers; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.email_subscribers ENABLE ROW LEVEL SECURITY;

--
-- Name: entity_links; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.entity_links ENABLE ROW LEVEL SECURITY;

--
-- Name: entity_name_matches; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.entity_name_matches ENABLE ROW LEVEL SECURITY;

--
-- Name: external_references; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.external_references ENABLE ROW LEVEL SECURITY;

--
-- Name: extraction_runs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.extraction_runs ENABLE ROW LEVEL SECURITY;

--
-- Name: filing_period_briefings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.filing_period_briefings ENABLE ROW LEVEL SECURITY;

--
-- Name: form700_filings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.form700_filings ENABLE ROW LEVEL SECURITY;

--
-- Name: form_summary_cache; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.form_summary_cache ENABLE ROW LEVEL SECURITY;

--
-- Name: form_summary_cache form_summary_cache_anon_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY form_summary_cache_anon_read ON public.form_summary_cache FOR SELECT TO authenticated, anon USING (true);


--
-- Name: form_summary_cache form_summary_cache_service_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY form_summary_cache_service_all ON public.form_summary_cache TO service_role USING (true) WITH CHECK (true);


--
-- Name: friendly_amendments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.friendly_amendments ENABLE ROW LEVEL SECURITY;

--
-- Name: independent_expenditures; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.independent_expenditures ENABLE ROW LEVEL SECURITY;

--
-- Name: influence_patterns; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.influence_patterns ENABLE ROW LEVEL SECURITY;

--
-- Name: item_theme_narratives; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.item_theme_narratives ENABLE ROW LEVEL SECURITY;

--
-- Name: item_topics; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.item_topics ENABLE ROW LEVEL SECURITY;

--
-- Name: llm_cost_reservations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.llm_cost_reservations ENABLE ROW LEVEL SECURITY;

--
-- Name: llm_cost_reservations llm_cost_reservations_service_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY llm_cost_reservations_service_all ON public.llm_cost_reservations TO service_role USING (true) WITH CHECK (true);


--
-- Name: lobbyist_document_extractions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.lobbyist_document_extractions ENABLE ROW LEVEL SECURITY;

--
-- Name: lobbyist_document_extractions lobbyist_document_extractions_service_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY lobbyist_document_extractions_service_all ON public.lobbyist_document_extractions TO service_role USING (true) WITH CHECK (true);


--
-- Name: lobbyist_registrations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.lobbyist_registrations ENABLE ROW LEVEL SECURITY;

--
-- Name: lobbyist_registrations lobbyist_registrations_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY lobbyist_registrations_read ON public.lobbyist_registrations FOR SELECT USING (true);


--
-- Name: meeting_attendance; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.meeting_attendance ENABLE ROW LEVEL SECURITY;

--
-- Name: meetings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.meetings ENABLE ROW LEVEL SECURITY;

--
-- Name: meetings_embeddings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.meetings_embeddings ENABLE ROW LEVEL SECURITY;

--
-- Name: motions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.motions ENABLE ROW LEVEL SECURITY;

--
-- Name: motions_embeddings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.motions_embeddings ENABLE ROW LEVEL SECURITY;

--
-- Name: neighborhood_councils; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.neighborhood_councils ENABLE ROW LEVEL SECURITY;

--
-- Name: neighborhood_councils neighborhood_councils_public_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY neighborhood_councils_public_read ON public.neighborhood_councils FOR SELECT USING (true);


--
-- Name: neighborhood_councils neighborhood_councils_service_write; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY neighborhood_councils_service_write ON public.neighborhood_councils USING (true) WITH CHECK (true);


--
-- Name: nextrequest_documents; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.nextrequest_documents ENABLE ROW LEVEL SECURITY;

--
-- Name: nextrequest_requests; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.nextrequest_requests ENABLE ROW LEVEL SECURITY;

--
-- Name: officials; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.officials ENABLE ROW LEVEL SECURITY;

--
-- Name: officials_embeddings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.officials_embeddings ENABLE ROW LEVEL SECURITY;

--
-- Name: officials_embeddings officials_embeddings_anon_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY officials_embeddings_anon_read ON public.officials_embeddings FOR SELECT TO anon USING (true);


--
-- Name: opencorporates_api_usage; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.opencorporates_api_usage ENABLE ROW LEVEL SECURITY;

--
-- Name: operator_config; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.operator_config ENABLE ROW LEVEL SECURITY;

--
-- Name: operator_config operator_config_anon_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY operator_config_anon_read ON public.operator_config FOR SELECT TO anon USING (true);


--
-- Name: operator_config operator_config_service_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY operator_config_service_all ON public.operator_config TO service_role USING (true);


--
-- Name: organizations; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

--
-- Name: paper_filing_zero_results; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.paper_filing_zero_results ENABLE ROW LEVEL SECURITY;

--
-- Name: paper_filing_zero_results paper_filing_zero_results_service_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY paper_filing_zero_results_service_all ON public.paper_filing_zero_results TO service_role USING (true) WITH CHECK (true);


--
-- Name: pb_class_specs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pb_class_specs ENABLE ROW LEVEL SECURITY;

--
-- Name: pb_classification_actions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pb_classification_actions ENABLE ROW LEVEL SECURITY;

--
-- Name: pb_employee_compensation; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pb_employee_compensation ENABLE ROW LEVEL SECURITY;

--
-- Name: pb_job_postings; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pb_job_postings ENABLE ROW LEVEL SECURITY;

--
-- Name: pb_new_employees; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pb_new_employees ENABLE ROW LEVEL SECURITY;

--
-- Name: pb_research_log; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pb_research_log ENABLE ROW LEVEL SECURITY;

--
-- Name: pending_decisions; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pending_decisions ENABLE ROW LEVEL SECURITY;

--
-- Name: pending_decisions pending_decisions_service_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pending_decisions_service_all ON public.pending_decisions USING (true) WITH CHECK (true);


--
-- Name: pipeline_journal; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.pipeline_journal ENABLE ROW LEVEL SECURITY;

--
-- Name: pipeline_journal pipeline_journal_service_all; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY pipeline_journal_service_all ON public.pipeline_journal USING (true) WITH CHECK (true);


--
-- Name: public_comments; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.public_comments ENABLE ROW LEVEL SECURITY;

--
-- Name: rate_limit_buckets; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.rate_limit_buckets ENABLE ROW LEVEL SECURITY;

--
-- Name: rate_limit_buckets rate_limit_buckets_service; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY rate_limit_buckets_service ON public.rate_limit_buckets TO service_role USING (true);


--
-- Name: scan_runs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.scan_runs ENABLE ROW LEVEL SECURITY;

--
-- Name: search_queries; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.search_queries ENABLE ROW LEVEL SECURITY;

--
-- Name: search_queries search_queries_anon_insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY search_queries_anon_insert ON public.search_queries FOR INSERT TO anon WITH CHECK (true);


--
-- Name: search_queries search_queries_service_read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY search_queries_service_read ON public.search_queries TO service_role USING (true);


--
-- Name: user_feedback service_full_access_feedback; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY service_full_access_feedback ON public.user_feedback TO service_role USING (true) WITH CHECK (true);


--
-- Name: source_change_jobs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.source_change_jobs ENABLE ROW LEVEL SECURITY;

--
-- Name: source_watch_state; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.source_watch_state ENABLE ROW LEVEL SECURITY;

--
-- Name: topics; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.topics ENABLE ROW LEVEL SECURITY;

--
-- Name: user_feedback; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.user_feedback ENABLE ROW LEVEL SECURITY;

--
-- Name: votes; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.votes ENABLE ROW LEVEL SECURITY;

--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA public TO postgres;
GRANT USAGE ON SCHEMA public TO anon;
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT USAGE ON SCHEMA public TO service_role;


--
-- Name: FUNCTION check_and_increment_rate_limit(p_bucket_key text, p_window_secs integer, p_max_count integer); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.check_and_increment_rate_limit(p_bucket_key text, p_window_secs integer, p_max_count integer) TO anon;
GRANT ALL ON FUNCTION public.check_and_increment_rate_limit(p_bucket_key text, p_window_secs integer, p_max_count integer) TO authenticated;
GRANT ALL ON FUNCTION public.check_and_increment_rate_limit(p_bucket_key text, p_window_secs integer, p_max_count integer) TO service_role;


--
-- Name: TABLE source_change_jobs; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.source_change_jobs TO service_role;


--
-- Name: FUNCTION claim_due_source_change_jobs(p_change_id character varying, p_limit integer, p_lease_minutes integer); Type: ACL; Schema: public; Owner: -
--

REVOKE ALL ON FUNCTION public.claim_due_source_change_jobs(p_change_id character varying, p_limit integer, p_lease_minutes integer) FROM PUBLIC;
GRANT ALL ON FUNCTION public.claim_due_source_change_jobs(p_change_id character varying, p_limit integer, p_lease_minutes integer) TO service_role;


--
-- Name: FUNCTION claim_source_change_job(p_change_id character varying, p_source character varying, p_dispatch_generation integer, p_pipeline_run_id character varying, p_lease_minutes integer); Type: ACL; Schema: public; Owner: -
--

REVOKE ALL ON FUNCTION public.claim_source_change_job(p_change_id character varying, p_source character varying, p_dispatch_generation integer, p_pipeline_run_id character varying, p_lease_minutes integer) FROM PUBLIC;
GRANT ALL ON FUNCTION public.claim_source_change_job(p_change_id character varying, p_source character varying, p_dispatch_generation integer, p_pipeline_run_id character varying, p_lease_minutes integer) TO service_role;


--
-- Name: FUNCTION cleanup_rate_limit_buckets(); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.cleanup_rate_limit_buckets() TO anon;
GRANT ALL ON FUNCTION public.cleanup_rate_limit_buckets() TO authenticated;
GRANT ALL ON FUNCTION public.cleanup_rate_limit_buckets() TO service_role;


--
-- Name: FUNCTION complete_source_change_job(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer); Type: ACL; Schema: public; Owner: -
--

REVOKE ALL ON FUNCTION public.complete_source_change_job(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer) FROM PUBLIC;
GRANT ALL ON FUNCTION public.complete_source_change_job(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer) TO service_role;


--
-- Name: FUNCTION continue_source_change_job(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer, p_delay_seconds integer); Type: ACL; Schema: public; Owner: -
--

REVOKE ALL ON FUNCTION public.continue_source_change_job(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer, p_delay_seconds integer) FROM PUBLIC;
GRANT ALL ON FUNCTION public.continue_source_change_job(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer, p_delay_seconds integer) TO service_role;


--
-- Name: FUNCTION find_similar_items(p_item_id uuid, p_city_fips text, p_limit integer); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.find_similar_items(p_item_id uuid, p_city_fips text, p_limit integer) TO anon;
GRANT ALL ON FUNCTION public.find_similar_items(p_item_id uuid, p_city_fips text, p_limit integer) TO authenticated;
GRANT ALL ON FUNCTION public.find_similar_items(p_item_id uuid, p_city_fips text, p_limit integer) TO service_role;


--
-- Name: FUNCTION get_category_stats(p_city_fips text); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.get_category_stats(p_city_fips text) TO anon;
GRANT ALL ON FUNCTION public.get_category_stats(p_city_fips text) TO authenticated;
GRANT ALL ON FUNCTION public.get_category_stats(p_city_fips text) TO service_role;


--
-- Name: FUNCTION get_contested_votes(p_city_fips text, p_official_ids uuid[]); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.get_contested_votes(p_city_fips text, p_official_ids uuid[]) TO anon;
GRANT ALL ON FUNCTION public.get_contested_votes(p_city_fips text, p_official_ids uuid[]) TO authenticated;
GRANT ALL ON FUNCTION public.get_contested_votes(p_city_fips text, p_official_ids uuid[]) TO service_role;


--
-- Name: FUNCTION get_controversial_items(p_city_fips text, p_limit integer); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.get_controversial_items(p_city_fips text, p_limit integer) TO anon;
GRANT ALL ON FUNCTION public.get_controversial_items(p_city_fips text, p_limit integer) TO authenticated;
GRANT ALL ON FUNCTION public.get_controversial_items(p_city_fips text, p_limit integer) TO service_role;


--
-- Name: FUNCTION get_divergent_motions_detail(p_city_fips text, p_official_ids uuid[]); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.get_divergent_motions_detail(p_city_fips text, p_official_ids uuid[]) TO anon;
GRANT ALL ON FUNCTION public.get_divergent_motions_detail(p_city_fips text, p_official_ids uuid[]) TO authenticated;
GRANT ALL ON FUNCTION public.get_divergent_motions_detail(p_city_fips text, p_official_ids uuid[]) TO service_role;


--
-- Name: FUNCTION get_meeting_counts(p_city_fips text); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.get_meeting_counts(p_city_fips text) TO anon;
GRANT ALL ON FUNCTION public.get_meeting_counts(p_city_fips text) TO authenticated;
GRANT ALL ON FUNCTION public.get_meeting_counts(p_city_fips text) TO service_role;


--
-- Name: FUNCTION get_meeting_flag_counts(p_city_fips text); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.get_meeting_flag_counts(p_city_fips text) TO anon;
GRANT ALL ON FUNCTION public.get_meeting_flag_counts(p_city_fips text) TO authenticated;
GRANT ALL ON FUNCTION public.get_meeting_flag_counts(p_city_fips text) TO service_role;


--
-- Name: FUNCTION list_public_tables(); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.list_public_tables() TO anon;
GRANT ALL ON FUNCTION public.list_public_tables() TO authenticated;
GRANT ALL ON FUNCTION public.list_public_tables() TO service_role;


--
-- Name: FUNCTION mark_source_change_base_completed(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer); Type: ACL; Schema: public; Owner: -
--

REVOKE ALL ON FUNCTION public.mark_source_change_base_completed(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer) FROM PUBLIC;
GRANT ALL ON FUNCTION public.mark_source_change_base_completed(p_change_id character varying, p_pipeline_run_id character varying, p_dispatch_generation integer) TO service_role;


--
-- Name: FUNCTION merge_official_pair(p_keeper_id uuid, p_dupe_id uuid); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.merge_official_pair(p_keeper_id uuid, p_dupe_id uuid) TO anon;
GRANT ALL ON FUNCTION public.merge_official_pair(p_keeper_id uuid, p_dupe_id uuid) TO authenticated;
GRANT ALL ON FUNCTION public.merge_official_pair(p_keeper_id uuid, p_dupe_id uuid) TO service_role;


--
-- Name: FUNCTION parse_vote_tally(tally text); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.parse_vote_tally(tally text) TO anon;
GRANT ALL ON FUNCTION public.parse_vote_tally(tally text) TO authenticated;
GRANT ALL ON FUNCTION public.parse_vote_tally(tally text) TO service_role;


--
-- Name: FUNCTION reserve_llm_cost(p_reservation_id uuid, p_city_fips character varying, p_model text, p_caller text, p_projected_cost numeric, p_monthly_cap numeric, p_event_type text, p_metadata jsonb); Type: ACL; Schema: public; Owner: -
--

REVOKE ALL ON FUNCTION public.reserve_llm_cost(p_reservation_id uuid, p_city_fips character varying, p_model text, p_caller text, p_projected_cost numeric, p_monthly_cap numeric, p_event_type text, p_metadata jsonb) FROM PUBLIC;
GRANT ALL ON FUNCTION public.reserve_llm_cost(p_reservation_id uuid, p_city_fips character varying, p_model text, p_caller text, p_projected_cost numeric, p_monthly_cap numeric, p_event_type text, p_metadata jsonb) TO service_role;


--
-- Name: FUNCTION retry_source_change_job(p_change_id character varying, p_error text, p_dispatch_generation integer, p_pipeline_run_id character varying); Type: ACL; Schema: public; Owner: -
--

REVOKE ALL ON FUNCTION public.retry_source_change_job(p_change_id character varying, p_error text, p_dispatch_generation integer, p_pipeline_run_id character varying) FROM PUBLIC;
GRANT ALL ON FUNCTION public.retry_source_change_job(p_change_id character varying, p_error text, p_dispatch_generation integer, p_pipeline_run_id character varying) TO service_role;


--
-- Name: FUNCTION rls_auto_enable(); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.rls_auto_enable() TO anon;
GRANT ALL ON FUNCTION public.rls_auto_enable() TO authenticated;
GRANT ALL ON FUNCTION public.rls_auto_enable() TO service_role;


--
-- Name: FUNCTION search_hybrid(p_query text, p_query_embedding extensions.vector, p_city_fips text, p_result_type text, p_limit integer, p_offset integer); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.search_hybrid(p_query text, p_query_embedding extensions.vector, p_city_fips text, p_result_type text, p_limit integer, p_offset integer) TO anon;
GRANT ALL ON FUNCTION public.search_hybrid(p_query text, p_query_embedding extensions.vector, p_city_fips text, p_result_type text, p_limit integer, p_offset integer) TO authenticated;
GRANT ALL ON FUNCTION public.search_hybrid(p_query text, p_query_embedding extensions.vector, p_city_fips text, p_result_type text, p_limit integer, p_offset integer) TO service_role;


--
-- Name: FUNCTION search_site(p_query text, p_city_fips text, p_result_type text, p_limit integer, p_offset integer); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.search_site(p_query text, p_city_fips text, p_result_type text, p_limit integer, p_offset integer) TO anon;
GRANT ALL ON FUNCTION public.search_site(p_query text, p_city_fips text, p_result_type text, p_limit integer, p_offset integer) TO authenticated;
GRANT ALL ON FUNCTION public.search_site(p_query text, p_city_fips text, p_result_type text, p_limit integer, p_offset integer) TO service_role;


--
-- Name: FUNCTION settle_llm_cost_reservation(p_reservation_id uuid, p_actual_cost numeric, p_input_tokens integer, p_output_tokens integer, p_metadata jsonb); Type: ACL; Schema: public; Owner: -
--

REVOKE ALL ON FUNCTION public.settle_llm_cost_reservation(p_reservation_id uuid, p_actual_cost numeric, p_input_tokens integer, p_output_tokens integer, p_metadata jsonb) FROM PUBLIC;
GRANT ALL ON FUNCTION public.settle_llm_cost_reservation(p_reservation_id uuid, p_actual_cost numeric, p_input_tokens integer, p_output_tokens integer, p_metadata jsonb) TO service_role;


--
-- Name: FUNCTION update_meeting_agenda_item_count(); Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON FUNCTION public.update_meeting_agenda_item_count() TO anon;
GRANT ALL ON FUNCTION public.update_meeting_agenda_item_count() TO authenticated;
GRANT ALL ON FUNCTION public.update_meeting_agenda_item_count() TO service_role;


--
-- Name: TABLE agenda_item_attachments; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.agenda_item_attachments TO anon;
GRANT ALL ON TABLE public.agenda_item_attachments TO authenticated;
GRANT ALL ON TABLE public.agenda_item_attachments TO service_role;


--
-- Name: TABLE agenda_items; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.agenda_items TO anon;
GRANT ALL ON TABLE public.agenda_items TO authenticated;
GRANT ALL ON TABLE public.agenda_items TO service_role;


--
-- Name: TABLE agenda_items_embeddings; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.agenda_items_embeddings TO anon;
GRANT ALL ON TABLE public.agenda_items_embeddings TO authenticated;
GRANT ALL ON TABLE public.agenda_items_embeddings TO service_role;


--
-- Name: TABLE behested_payments; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.behested_payments TO anon;
GRANT ALL ON TABLE public.behested_payments TO authenticated;
GRANT ALL ON TABLE public.behested_payments TO service_role;


--
-- Name: TABLE bodies; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.bodies TO anon;
GRANT ALL ON TABLE public.bodies TO authenticated;
GRANT ALL ON TABLE public.bodies TO service_role;


--
-- Name: TABLE business_entities; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.business_entities TO anon;
GRANT ALL ON TABLE public.business_entities TO authenticated;
GRANT ALL ON TABLE public.business_entities TO service_role;


--
-- Name: TABLE business_entity_officers; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.business_entity_officers TO anon;
GRANT ALL ON TABLE public.business_entity_officers TO authenticated;
GRANT ALL ON TABLE public.business_entity_officers TO service_role;


--
-- Name: TABLE cities; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.cities TO anon;
GRANT ALL ON TABLE public.cities TO authenticated;
GRANT ALL ON TABLE public.cities TO service_role;


--
-- Name: TABLE city_code_cases; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.city_code_cases TO anon;
GRANT ALL ON TABLE public.city_code_cases TO authenticated;
GRANT ALL ON TABLE public.city_code_cases TO service_role;


--
-- Name: TABLE city_contracts; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.city_contracts TO anon;
GRANT ALL ON TABLE public.city_contracts TO authenticated;
GRANT ALL ON TABLE public.city_contracts TO service_role;


--
-- Name: TABLE city_employees; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.city_employees TO anon;
GRANT ALL ON TABLE public.city_employees TO authenticated;
GRANT ALL ON TABLE public.city_employees TO service_role;


--
-- Name: TABLE city_expenditures; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.city_expenditures TO anon;
GRANT ALL ON TABLE public.city_expenditures TO authenticated;
GRANT ALL ON TABLE public.city_expenditures TO service_role;


--
-- Name: TABLE city_licenses; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.city_licenses TO anon;
GRANT ALL ON TABLE public.city_licenses TO authenticated;
GRANT ALL ON TABLE public.city_licenses TO service_role;


--
-- Name: TABLE city_permits; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.city_permits TO anon;
GRANT ALL ON TABLE public.city_permits TO authenticated;
GRANT ALL ON TABLE public.city_permits TO service_role;


--
-- Name: TABLE city_projects; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.city_projects TO anon;
GRANT ALL ON TABLE public.city_projects TO authenticated;
GRANT ALL ON TABLE public.city_projects TO service_role;


--
-- Name: TABLE city_service_requests; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.city_service_requests TO anon;
GRANT ALL ON TABLE public.city_service_requests TO authenticated;
GRANT ALL ON TABLE public.city_service_requests TO service_role;


--
-- Name: TABLE closed_session_items; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.closed_session_items TO anon;
GRANT ALL ON TABLE public.closed_session_items TO authenticated;
GRANT ALL ON TABLE public.closed_session_items TO service_role;


--
-- Name: TABLE comment_theme_assignments; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.comment_theme_assignments TO anon;
GRANT ALL ON TABLE public.comment_theme_assignments TO authenticated;
GRANT ALL ON TABLE public.comment_theme_assignments TO service_role;


--
-- Name: TABLE comment_themes; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.comment_themes TO anon;
GRANT ALL ON TABLE public.comment_themes TO authenticated;
GRANT ALL ON TABLE public.comment_themes TO service_role;


--
-- Name: TABLE commission_members; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.commission_members TO anon;
GRANT ALL ON TABLE public.commission_members TO authenticated;
GRANT ALL ON TABLE public.commission_members TO service_role;


--
-- Name: TABLE commissions; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.commissions TO anon;
GRANT ALL ON TABLE public.commissions TO authenticated;
GRANT ALL ON TABLE public.commissions TO service_role;


--
-- Name: TABLE committees; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.committees TO anon;
GRANT ALL ON TABLE public.committees TO authenticated;
GRANT ALL ON TABLE public.committees TO service_role;


--
-- Name: TABLE conflict_flags; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.conflict_flags TO anon;
GRANT ALL ON TABLE public.conflict_flags TO authenticated;
GRANT ALL ON TABLE public.conflict_flags TO service_role;


--
-- Name: TABLE contributions; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.contributions TO anon;
GRANT ALL ON TABLE public.contributions TO authenticated;
GRANT ALL ON TABLE public.contributions TO service_role;


--
-- Name: TABLE court_case_matches; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.court_case_matches TO anon;
GRANT ALL ON TABLE public.court_case_matches TO authenticated;
GRANT ALL ON TABLE public.court_case_matches TO service_role;


--
-- Name: TABLE court_case_parties; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.court_case_parties TO anon;
GRANT ALL ON TABLE public.court_case_parties TO authenticated;
GRANT ALL ON TABLE public.court_case_parties TO service_role;


--
-- Name: TABLE court_cases; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.court_cases TO anon;
GRANT ALL ON TABLE public.court_cases TO authenticated;
GRANT ALL ON TABLE public.court_cases TO service_role;


--
-- Name: TABLE cpra_requests; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.cpra_requests TO anon;
GRANT ALL ON TABLE public.cpra_requests TO authenticated;
GRANT ALL ON TABLE public.cpra_requests TO service_role;


--
-- Name: TABLE data_sync_log; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.data_sync_log TO anon;
GRANT ALL ON TABLE public.data_sync_log TO authenticated;
GRANT ALL ON TABLE public.data_sync_log TO service_role;


--
-- Name: TABLE document_references; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.document_references TO anon;
GRANT ALL ON TABLE public.document_references TO authenticated;
GRANT ALL ON TABLE public.document_references TO service_role;


--
-- Name: TABLE documents; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.documents TO anon;
GRANT ALL ON TABLE public.documents TO authenticated;
GRANT ALL ON TABLE public.documents TO service_role;


--
-- Name: TABLE donors; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.donors TO anon;
GRANT ALL ON TABLE public.donors TO authenticated;
GRANT ALL ON TABLE public.donors TO service_role;


--
-- Name: TABLE donor_context; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.donor_context TO anon;
GRANT ALL ON TABLE public.donor_context TO authenticated;
GRANT ALL ON TABLE public.donor_context TO service_role;


--
-- Name: TABLE economic_interests; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.economic_interests TO anon;
GRANT ALL ON TABLE public.economic_interests TO authenticated;
GRANT ALL ON TABLE public.economic_interests TO service_role;


--
-- Name: TABLE election_candidates; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.election_candidates TO anon;
GRANT ALL ON TABLE public.election_candidates TO authenticated;
GRANT ALL ON TABLE public.election_candidates TO service_role;


--
-- Name: TABLE elections; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.elections TO anon;
GRANT ALL ON TABLE public.elections TO authenticated;
GRANT ALL ON TABLE public.elections TO service_role;


--
-- Name: TABLE email_preferences; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.email_preferences TO anon;
GRANT ALL ON TABLE public.email_preferences TO authenticated;
GRANT ALL ON TABLE public.email_preferences TO service_role;


--
-- Name: TABLE email_subscribers; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.email_subscribers TO anon;
GRANT ALL ON TABLE public.email_subscribers TO authenticated;
GRANT ALL ON TABLE public.email_subscribers TO service_role;


--
-- Name: TABLE entity_links; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.entity_links TO anon;
GRANT ALL ON TABLE public.entity_links TO authenticated;
GRANT ALL ON TABLE public.entity_links TO service_role;


--
-- Name: TABLE entity_name_matches; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.entity_name_matches TO anon;
GRANT ALL ON TABLE public.entity_name_matches TO authenticated;
GRANT ALL ON TABLE public.entity_name_matches TO service_role;


--
-- Name: TABLE external_references; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.external_references TO anon;
GRANT ALL ON TABLE public.external_references TO authenticated;
GRANT ALL ON TABLE public.external_references TO service_role;


--
-- Name: TABLE extraction_runs; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.extraction_runs TO anon;
GRANT ALL ON TABLE public.extraction_runs TO authenticated;
GRANT ALL ON TABLE public.extraction_runs TO service_role;


--
-- Name: TABLE filing_period_briefings; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.filing_period_briefings TO anon;
GRANT ALL ON TABLE public.filing_period_briefings TO authenticated;
GRANT ALL ON TABLE public.filing_period_briefings TO service_role;


--
-- Name: TABLE form700_filings; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.form700_filings TO anon;
GRANT ALL ON TABLE public.form700_filings TO authenticated;
GRANT ALL ON TABLE public.form700_filings TO service_role;


--
-- Name: TABLE form_summary_cache; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.form_summary_cache TO anon;
GRANT ALL ON TABLE public.form_summary_cache TO authenticated;
GRANT ALL ON TABLE public.form_summary_cache TO service_role;


--
-- Name: TABLE friendly_amendments; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.friendly_amendments TO anon;
GRANT ALL ON TABLE public.friendly_amendments TO authenticated;
GRANT ALL ON TABLE public.friendly_amendments TO service_role;


--
-- Name: TABLE independent_expenditures; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.independent_expenditures TO anon;
GRANT ALL ON TABLE public.independent_expenditures TO authenticated;
GRANT ALL ON TABLE public.independent_expenditures TO service_role;


--
-- Name: TABLE influence_patterns; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.influence_patterns TO anon;
GRANT ALL ON TABLE public.influence_patterns TO authenticated;
GRANT ALL ON TABLE public.influence_patterns TO service_role;


--
-- Name: SEQUENCE influence_patterns_id_seq; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON SEQUENCE public.influence_patterns_id_seq TO anon;
GRANT ALL ON SEQUENCE public.influence_patterns_id_seq TO authenticated;
GRANT ALL ON SEQUENCE public.influence_patterns_id_seq TO service_role;


--
-- Name: TABLE item_theme_narratives; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.item_theme_narratives TO anon;
GRANT ALL ON TABLE public.item_theme_narratives TO authenticated;
GRANT ALL ON TABLE public.item_theme_narratives TO service_role;


--
-- Name: TABLE item_topics; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.item_topics TO anon;
GRANT ALL ON TABLE public.item_topics TO authenticated;
GRANT ALL ON TABLE public.item_topics TO service_role;


--
-- Name: TABLE llm_cost_reservations; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.llm_cost_reservations TO anon;
GRANT ALL ON TABLE public.llm_cost_reservations TO authenticated;
GRANT ALL ON TABLE public.llm_cost_reservations TO service_role;


--
-- Name: TABLE lobbyist_document_extractions; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.lobbyist_document_extractions TO anon;
GRANT ALL ON TABLE public.lobbyist_document_extractions TO authenticated;
GRANT ALL ON TABLE public.lobbyist_document_extractions TO service_role;


--
-- Name: TABLE lobbyist_registrations; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.lobbyist_registrations TO anon;
GRANT ALL ON TABLE public.lobbyist_registrations TO authenticated;
GRANT ALL ON TABLE public.lobbyist_registrations TO service_role;


--
-- Name: TABLE meeting_attendance; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.meeting_attendance TO anon;
GRANT ALL ON TABLE public.meeting_attendance TO authenticated;
GRANT ALL ON TABLE public.meeting_attendance TO service_role;


--
-- Name: TABLE meetings; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.meetings TO anon;
GRANT ALL ON TABLE public.meetings TO authenticated;
GRANT ALL ON TABLE public.meetings TO service_role;


--
-- Name: TABLE meetings_embeddings; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.meetings_embeddings TO anon;
GRANT ALL ON TABLE public.meetings_embeddings TO authenticated;
GRANT ALL ON TABLE public.meetings_embeddings TO service_role;


--
-- Name: TABLE motions; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.motions TO anon;
GRANT ALL ON TABLE public.motions TO authenticated;
GRANT ALL ON TABLE public.motions TO service_role;


--
-- Name: TABLE motions_embeddings; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.motions_embeddings TO anon;
GRANT ALL ON TABLE public.motions_embeddings TO authenticated;
GRANT ALL ON TABLE public.motions_embeddings TO service_role;


--
-- Name: TABLE neighborhood_councils; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.neighborhood_councils TO anon;
GRANT ALL ON TABLE public.neighborhood_councils TO authenticated;
GRANT ALL ON TABLE public.neighborhood_councils TO service_role;


--
-- Name: TABLE nextrequest_documents; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.nextrequest_documents TO anon;
GRANT ALL ON TABLE public.nextrequest_documents TO authenticated;
GRANT ALL ON TABLE public.nextrequest_documents TO service_role;


--
-- Name: TABLE nextrequest_requests; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.nextrequest_requests TO anon;
GRANT ALL ON TABLE public.nextrequest_requests TO authenticated;
GRANT ALL ON TABLE public.nextrequest_requests TO service_role;


--
-- Name: TABLE officials; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.officials TO anon;
GRANT ALL ON TABLE public.officials TO authenticated;
GRANT ALL ON TABLE public.officials TO service_role;


--
-- Name: TABLE officials_embeddings; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.officials_embeddings TO anon;
GRANT ALL ON TABLE public.officials_embeddings TO authenticated;
GRANT ALL ON TABLE public.officials_embeddings TO service_role;


--
-- Name: TABLE opencorporates_api_usage; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.opencorporates_api_usage TO anon;
GRANT ALL ON TABLE public.opencorporates_api_usage TO authenticated;
GRANT ALL ON TABLE public.opencorporates_api_usage TO service_role;


--
-- Name: TABLE operator_config; Type: ACL; Schema: public; Owner: -
--

GRANT SELECT,REFERENCES,TRIGGER,TRUNCATE,MAINTAIN ON TABLE public.operator_config TO anon;
GRANT ALL ON TABLE public.operator_config TO authenticated;
GRANT ALL ON TABLE public.operator_config TO service_role;


--
-- Name: TABLE organizations; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.organizations TO anon;
GRANT ALL ON TABLE public.organizations TO authenticated;
GRANT ALL ON TABLE public.organizations TO service_role;


--
-- Name: TABLE paper_filing_zero_results; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.paper_filing_zero_results TO anon;
GRANT ALL ON TABLE public.paper_filing_zero_results TO authenticated;
GRANT ALL ON TABLE public.paper_filing_zero_results TO service_role;


--
-- Name: TABLE pb_class_specs; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.pb_class_specs TO anon;
GRANT ALL ON TABLE public.pb_class_specs TO authenticated;
GRANT ALL ON TABLE public.pb_class_specs TO service_role;


--
-- Name: TABLE pb_classification_actions; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.pb_classification_actions TO anon;
GRANT ALL ON TABLE public.pb_classification_actions TO authenticated;
GRANT ALL ON TABLE public.pb_classification_actions TO service_role;


--
-- Name: TABLE pb_employee_compensation; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.pb_employee_compensation TO anon;
GRANT ALL ON TABLE public.pb_employee_compensation TO authenticated;
GRANT ALL ON TABLE public.pb_employee_compensation TO service_role;


--
-- Name: TABLE pb_job_postings; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.pb_job_postings TO anon;
GRANT ALL ON TABLE public.pb_job_postings TO authenticated;
GRANT ALL ON TABLE public.pb_job_postings TO service_role;


--
-- Name: TABLE pb_new_employees; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.pb_new_employees TO anon;
GRANT ALL ON TABLE public.pb_new_employees TO authenticated;
GRANT ALL ON TABLE public.pb_new_employees TO service_role;


--
-- Name: TABLE pb_research_log; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.pb_research_log TO anon;
GRANT ALL ON TABLE public.pb_research_log TO authenticated;
GRANT ALL ON TABLE public.pb_research_log TO service_role;


--
-- Name: TABLE pending_decisions; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.pending_decisions TO anon;
GRANT ALL ON TABLE public.pending_decisions TO authenticated;
GRANT ALL ON TABLE public.pending_decisions TO service_role;


--
-- Name: TABLE pipeline_journal; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.pipeline_journal TO anon;
GRANT ALL ON TABLE public.pipeline_journal TO authenticated;
GRANT ALL ON TABLE public.pipeline_journal TO service_role;


--
-- Name: TABLE public_comments; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.public_comments TO anon;
GRANT ALL ON TABLE public.public_comments TO authenticated;
GRANT ALL ON TABLE public.public_comments TO service_role;


--
-- Name: TABLE rate_limit_buckets; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.rate_limit_buckets TO anon;
GRANT ALL ON TABLE public.rate_limit_buckets TO authenticated;
GRANT ALL ON TABLE public.rate_limit_buckets TO service_role;


--
-- Name: TABLE scan_runs; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.scan_runs TO anon;
GRANT ALL ON TABLE public.scan_runs TO authenticated;
GRANT ALL ON TABLE public.scan_runs TO service_role;


--
-- Name: TABLE search_queries; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.search_queries TO anon;
GRANT ALL ON TABLE public.search_queries TO authenticated;
GRANT ALL ON TABLE public.search_queries TO service_role;


--
-- Name: TABLE source_watch_state; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.source_watch_state TO anon;
GRANT ALL ON TABLE public.source_watch_state TO authenticated;
GRANT ALL ON TABLE public.source_watch_state TO service_role;


--
-- Name: TABLE topics; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.topics TO anon;
GRANT ALL ON TABLE public.topics TO authenticated;
GRANT ALL ON TABLE public.topics TO service_role;


--
-- Name: TABLE user_feedback; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.user_feedback TO anon;
GRANT ALL ON TABLE public.user_feedback TO authenticated;
GRANT ALL ON TABLE public.user_feedback TO service_role;


--
-- Name: TABLE v_appointment_network; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_appointment_network TO anon;
GRANT ALL ON TABLE public.v_appointment_network TO authenticated;
GRANT ALL ON TABLE public.v_appointment_network TO service_role;


--
-- Name: TABLE v_behested_by_official; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_behested_by_official TO anon;
GRANT ALL ON TABLE public.v_behested_by_official TO authenticated;
GRANT ALL ON TABLE public.v_behested_by_official TO service_role;


--
-- Name: TABLE v_body_meeting_counts; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_body_meeting_counts TO anon;
GRANT ALL ON TABLE public.v_body_meeting_counts TO authenticated;
GRANT ALL ON TABLE public.v_body_meeting_counts TO service_role;


--
-- Name: TABLE v_body_roster; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_body_roster TO anon;
GRANT ALL ON TABLE public.v_body_roster TO authenticated;
GRANT ALL ON TABLE public.v_body_roster TO service_role;


--
-- Name: TABLE v_code_enforcement_summary; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_code_enforcement_summary TO anon;
GRANT ALL ON TABLE public.v_code_enforcement_summary TO authenticated;
GRANT ALL ON TABLE public.v_code_enforcement_summary TO service_role;


--
-- Name: TABLE v_commission_staleness; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_commission_staleness TO anon;
GRANT ALL ON TABLE public.v_commission_staleness TO authenticated;
GRANT ALL ON TABLE public.v_commission_staleness TO service_role;


--
-- Name: TABLE v_court_entity_summary; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_court_entity_summary TO anon;
GRANT ALL ON TABLE public.v_court_entity_summary TO authenticated;
GRANT ALL ON TABLE public.v_court_entity_summary TO service_role;


--
-- Name: TABLE votes; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.votes TO anon;
GRANT ALL ON TABLE public.votes TO authenticated;
GRANT ALL ON TABLE public.votes TO service_role;


--
-- Name: TABLE v_donor_vote_crossref; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_donor_vote_crossref TO anon;
GRANT ALL ON TABLE public.v_donor_vote_crossref TO authenticated;
GRANT ALL ON TABLE public.v_donor_vote_crossref TO service_role;


--
-- Name: TABLE v_entity_connections; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_entity_connections TO anon;
GRANT ALL ON TABLE public.v_entity_connections TO authenticated;
GRANT ALL ON TABLE public.v_entity_connections TO service_role;


--
-- Name: TABLE v_feedback_ground_truth; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_feedback_ground_truth TO anon;
GRANT ALL ON TABLE public.v_feedback_ground_truth TO authenticated;
GRANT ALL ON TABLE public.v_feedback_ground_truth TO service_role;


--
-- Name: TABLE v_influence_pattern_summary; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_influence_pattern_summary TO anon;
GRANT ALL ON TABLE public.v_influence_pattern_summary TO authenticated;
GRANT ALL ON TABLE public.v_influence_pattern_summary TO service_role;


--
-- Name: TABLE v_license_summary; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_license_summary TO anon;
GRANT ALL ON TABLE public.v_license_summary TO authenticated;
GRANT ALL ON TABLE public.v_license_summary TO service_role;


--
-- Name: TABLE v_lobbyist_clients; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_lobbyist_clients TO anon;
GRANT ALL ON TABLE public.v_lobbyist_clients TO authenticated;
GRANT ALL ON TABLE public.v_lobbyist_clients TO service_role;


--
-- Name: TABLE v_permit_activity; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_permit_activity TO anon;
GRANT ALL ON TABLE public.v_permit_activity TO authenticated;
GRANT ALL ON TABLE public.v_permit_activity TO service_role;


--
-- Name: TABLE v_split_votes; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_split_votes TO anon;
GRANT ALL ON TABLE public.v_split_votes TO authenticated;
GRANT ALL ON TABLE public.v_split_votes TO service_role;


--
-- Name: TABLE v_staff_agenda_context; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_staff_agenda_context TO anon;
GRANT ALL ON TABLE public.v_staff_agenda_context TO authenticated;
GRANT ALL ON TABLE public.v_staff_agenda_context TO service_role;


--
-- Name: TABLE v_topic_stats; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_topic_stats TO anon;
GRANT ALL ON TABLE public.v_topic_stats TO authenticated;
GRANT ALL ON TABLE public.v_topic_stats TO service_role;


--
-- Name: TABLE v_vendor_spending_summary; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_vendor_spending_summary TO anon;
GRANT ALL ON TABLE public.v_vendor_spending_summary TO authenticated;
GRANT ALL ON TABLE public.v_vendor_spending_summary TO service_role;


--
-- Name: TABLE v_votes_with_context; Type: ACL; Schema: public; Owner: -
--

GRANT ALL ON TABLE public.v_votes_with_context TO anon;
GRANT ALL ON TABLE public.v_votes_with_context TO authenticated;
GRANT ALL ON TABLE public.v_votes_with_context TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR FUNCTIONS; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO service_role;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: -
--

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO service_role;


--
-- Name: ensure_rls; Type: EVENT TRIGGER; Schema: -; Owner: postgres
--
-- pg_dump --schema=public does not emit database-level event triggers even
-- when their function is in public. This definition was captured separately
-- from pg_event_trigger and is part of the reviewed Preview baseline.

CREATE EVENT TRIGGER ensure_rls ON ddl_command_end
    WHEN TAG IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
    EXECUTE FUNCTION public.rls_auto_enable();


--
-- PostgreSQL database dump complete
--
