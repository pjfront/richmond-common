-- Migration 019: Deduplicate records from repeated batch collection
--
-- The --collect-batch command re-processed all 706 documents multiple times,
-- inserting duplicate motions (each with their own duplicate votes) and
-- duplicate public_comments. The motions table lacks a unique constraint,
-- so each re-collection inserted fresh copies.
--
-- Strategy: keep the earliest-inserted record per unique group, delete the rest.
-- Run each step sequentially (votes depend on motions, etc.)

-- ============================================================
-- Step 1: Delete votes attached to duplicate motions
-- ============================================================
-- Identify one "keeper" motion per unique group (earliest created_at).
-- Delete all votes whose motion_id is NOT a keeper.

DELETE FROM votes
WHERE motion_id NOT IN (
    SELECT DISTINCT ON (
        agenda_item_id,
        motion_type,
        COALESCE(motion_text, ''),
        COALESCE(result, '')
    ) id
    FROM motions
    ORDER BY
        agenda_item_id,
        motion_type,
        COALESCE(motion_text, ''),
        COALESCE(result, ''),
        created_at ASC
);
-- Expected: ~83K votes deleted

-- ============================================================
-- Step 2: Delete duplicate motions (keep earliest per group)
-- ============================================================

DELETE FROM motions
WHERE id NOT IN (
    SELECT DISTINCT ON (
        agenda_item_id,
        motion_type,
        COALESCE(motion_text, ''),
        COALESCE(result, '')
    ) id
    FROM motions
    ORDER BY
        agenda_item_id,
        motion_type,
        COALESCE(motion_text, ''),
        COALESCE(result, ''),
        created_at ASC
);
-- Expected: ~14.7K motions deleted

-- ============================================================
-- Step 3: Deduplicate public_comments
-- ============================================================
-- Group by meeting + agenda item + speaker + summary text.

DELETE FROM public_comments
WHERE id NOT IN (
    SELECT DISTINCT ON (
        meeting_id,
        COALESCE(agenda_item_id::text, ''),
        COALESCE(speaker_name, ''),
        COALESCE(summary, '')
    ) id
    FROM public_comments
    ORDER BY
        meeting_id,
        COALESCE(agenda_item_id::text, ''),
        COALESCE(speaker_name, ''),
        COALESCE(summary, ''),
        created_at ASC
);
-- Expected: ~34K comments deleted

-- ============================================================
-- Step 4: Deduplicate extraction_runs (keep latest per document)
-- ============================================================

DELETE FROM extraction_runs
WHERE id NOT IN (
    SELECT DISTINCT ON (document_id) id
    FROM extraction_runs
    ORDER BY document_id, extracted_at DESC
);
-- Expected: ~2.2K runs deleted

-- ============================================================
-- Step 5: Add unique constraint to motions to prevent future dupes
-- ============================================================
-- Uses a partial unique index with COALESCE for nullable columns.
-- This prevents the same motion from being inserted twice for the
-- same agenda item, even across multiple extraction runs.

CREATE UNIQUE INDEX IF NOT EXISTS uq_motions_natural_key
ON motions (
    agenda_item_id,
    motion_type,
    COALESCE(motion_text, ''),
    COALESCE(result, '')
);

-- ============================================================
-- Step 6: Add unique constraint to public_comments
-- ============================================================

CREATE UNIQUE INDEX IF NOT EXISTS uq_public_comments_natural_key
ON public_comments (
    meeting_id,
    COALESCE(agenda_item_id::text, ''),
    COALESCE(speaker_name, ''),
    COALESCE(summary, '')
);

-- ============================================================
-- Step 7: Add unique constraint to extraction_runs
-- ============================================================
-- One extraction_run per document. Re-extractions should UPDATE,
-- not INSERT a second row.

CREATE UNIQUE INDEX IF NOT EXISTS uq_extraction_runs_document
ON extraction_runs (document_id);
