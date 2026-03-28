-- Migration 068: Community Voice — theme-based public comment display
-- Adds source tracking to public_comments, creates theme tables for S21.
-- Idempotent: safe to re-run.

-- ── Enhanced columns on public_comments ─────────────────────────
ALTER TABLE public_comments ADD COLUMN IF NOT EXISTS source VARCHAR(30) DEFAULT 'minutes';
ALTER TABLE public_comments ADD COLUMN IF NOT EXISTS confidence REAL DEFAULT 1.0;
ALTER TABLE public_comments ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ;
ALTER TABLE public_comments ADD COLUMN IF NOT EXISTS city_fips VARCHAR(7) DEFAULT '0660620';
ALTER TABLE public_comments ADD COLUMN IF NOT EXISTS name_confidence VARCHAR(10) DEFAULT 'high';

-- Index for source-based queries (e.g., "all transcript-sourced comments")
CREATE INDEX IF NOT EXISTS idx_comments_source ON public_comments(source);
CREATE INDEX IF NOT EXISTS idx_comments_city_fips ON public_comments(city_fips);

-- ── Comment Themes catalog ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS comment_themes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips VARCHAR(7) NOT NULL DEFAULT '0660620',
    slug VARCHAR(100) NOT NULL,
    label VARCHAR(200) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'merged', 'archived'
    merged_into_id UUID REFERENCES comment_themes(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_theme_slug_city UNIQUE (city_fips, slug)
);

-- ── Comment ↔ Theme assignments (many-to-many) ─────────────────
CREATE TABLE IF NOT EXISTS comment_theme_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    comment_id UUID NOT NULL REFERENCES public_comments(id) ON DELETE CASCADE,
    theme_id UUID NOT NULL REFERENCES comment_themes(id) ON DELETE CASCADE,
    confidence REAL NOT NULL DEFAULT 0.9,
    source VARCHAR(30) NOT NULL DEFAULT 'llm',  -- 'llm', 'manual'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_comment_theme UNIQUE (comment_id, theme_id)
);

CREATE INDEX IF NOT EXISTS idx_theme_assignments_comment ON comment_theme_assignments(comment_id);
CREATE INDEX IF NOT EXISTS idx_theme_assignments_theme ON comment_theme_assignments(theme_id);

-- ── Per-item theme narratives ───────────────────────────────────
CREATE TABLE IF NOT EXISTS item_theme_narratives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agenda_item_id UUID NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
    theme_id UUID NOT NULL REFERENCES comment_themes(id) ON DELETE CASCADE,
    narrative TEXT NOT NULL,
    comment_count INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0.9,
    model VARCHAR(50),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_item_theme_narrative UNIQUE (agenda_item_id, theme_id)
);

CREATE INDEX IF NOT EXISTS idx_theme_narratives_item ON item_theme_narratives(agenda_item_id);
CREATE INDEX IF NOT EXISTS idx_theme_narratives_theme ON item_theme_narratives(theme_id);
