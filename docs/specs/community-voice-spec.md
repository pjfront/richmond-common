# Community Voice: Theme-Based Public Comment Display

**Sprint:** S21 (revised) | **Status:** Specced, not started | **Depends on:** S18 (Go Live), S20 (transcript pipeline)
**Publication tier:** Graduated (operator-only until validated)
**Spec date:** 2026-03-27

## Problem

Public comments are currently reduced to speaker counts ("54 public comments") with no substance visible. The original S21 scope called for sentiment classification (support/oppose/neutral), but sentiment labels destroy nuance. A resident who says "I want safety but I remember what surveillance did to this community" is not "mixed" — they're saying something that only works as a whole. Sentiment extraction plays into the same reductive dynamics as social media.

## Reframe

**Theme extraction, not sentiment extraction.** Group comments by substantive points raised, describe them in narrative, and let visitors read individual comments threaded under those themes. This makes civic participation legible without reducing it to sides.

## Design Principles

- **Themes are topics, not positions.** "Privacy & Data Retention" is a theme. "Opposition" is not.
- **Speakers can belong to multiple themes.** Someone who raises both privacy and cost concerns appears under both.
- **Narrative over numbers.** Primary display is 1-2 sentence description of what speakers said, not a count chart.
- **Names preserved as spoken.** LLM corrects obvious auto-caption mangling using context (chair announcements, self-introductions). Confidence flagged per name.
- **AI always marked.** Theme grouping and narrative summaries are AI-generated and labeled as such.

## Current State

- **80 YouTube transcripts** exist in `data/transcripts/*_clean.txt`
- Current extraction prompt (`src/prompts/youtube_comments_system.txt`) only asks for speaker counts
- `public_comments` table schema supports rich data but is mostly empty for transcript-sourced meetings
- `agenda_items.public_comment_count` has integer counts from S20

## Architecture

### Phase A: Enhanced Transcript Extraction

**Goal:** Extract individual speaker names, methods, and comment summaries from transcripts.

1. **New prompt** (`src/prompts/community_voice_system.txt`) — extracts per-speaker: LLM-corrected name, name confidence (high/medium/low), delivery method, agenda item, 1-3 sentence summary of what they said
2. **Pipeline script** (`src/community_voice_extractor.py`) — modeled on `youtube_comments.py`, writes individual `public_comments` rows with `source = 'youtube_transcript'`
3. **Schema migration** (`src/migrations/060_community_voice.sql`) — adds `source`, `confidence`, `extracted_at`, `city_fips` columns to `public_comments`; creates `comment_themes`, `comment_theme_assignments`, `item_theme_narratives` tables

### Phase B: Theme Extraction Pipeline

**Goal:** Given individual comments on an agenda item, cluster by theme and generate narratives.

1. **Theme prompt** (`src/prompts/theme_extraction_system.txt`) — classifies by substantive topic, NOT sentiment. Reuses existing theme labels for consistency (seed pattern from `topic_tagger.py`). Speakers can belong to multiple themes.
2. **Theme extractor** (`src/theme_extractor.py`) — queries comments per item, calls Claude, creates/reuses theme catalog entries, writes assignments + narratives
3. **Batch wrapper** (`src/batch_theme_extract.py`) — follows `batch_summarize.py` pattern for bulk processing

### Phase C: Frontend — Community Voice Component

**Goal:** Replace `CommentBreakdownSection` with theme-grouped narrative display.

1. **Types** — `CommentTheme`, `ThemeNarrative`, `CommunityVoiceData` in `web/src/lib/types.ts`
2. **Query** — `getCommunityVoice()` in `web/src/lib/queries.ts` with graceful fallback
3. **Component** — `web/src/components/CommunityVoiceSection.tsx`:

```
Community Voice (54 speakers, 12 written)

  Privacy & Data Retention (23 comments)
  "Several speakers raised concerns about how long camera data is stored,
   who can access it, and whether data-sharing policies are adequate."
  > Show individual comments
    - Ahmad Anderson · In person
      "Argued that public safety is foundational to economic development..."
    - Claudia Citra · In person
      "Described car thefts in her neighborhood and urged the council..."

  Public Safety & Policing (18 comments)
  "Residents described specific incidents where cameras aided investigations..."
  > Show individual comments

  Cost & Contract Terms (13 comments)
  ...

  AI-generated themes from meeting transcript · Source: KCRT YouTube
```

4. **Page integration** — graceful degradation: themes → raw comments → count only
5. **Meeting-level** — compact indicator: "54 speakers across 5 themes"

### Phase D: Backfill

- Transcript extraction: 80 meetings via Batch API (~$8-15)
- Theme extraction: items with 3+ comments via Batch API (~$2-5)
- Validation benchmark: Flock Safety meeting (2026-03-03), 54 speakers

**Total backfill cost: ~$10-20**

## Design Rule Compliance

| Rule | How |
|------|-----|
| D6/T7 (Narrative over numbers) | Primary display is narrative text, not counts or charts |
| U8 (AI marking) | Theme narratives + individual summaries labeled AI-generated |
| U1 (Source attribution) | Transcript source + extraction date shown |
| U13 (Low confidence excluded) | Themes <90% confidence only in expanded detail view |
| T4 (Hedged language) | "Speakers raised..." not "Community opposes..." |
| T6 (Non-adversarial) | Themes are topics, not sides |
| C8 (Confidence indicators) | Name confidence flags; theme confidence scores |

## Schema

```sql
-- New tables
comment_themes (id, city_fips, slug, label, description, status, merged_into_id, created_at, updated_at)
comment_theme_assignments (id, comment_id, theme_id, confidence, source, created_at)
item_theme_narratives (id, agenda_item_id, theme_id, narrative, comment_count, confidence, model, generated_at)

-- Enhanced columns on public_comments
source VARCHAR(30) DEFAULT 'minutes'  -- 'minutes', 'youtube_transcript', 'granicus_transcript'
confidence REAL DEFAULT 1.0
extracted_at TIMESTAMPTZ
city_fips VARCHAR(7) DEFAULT '0660620'
```

## What This Replaces

The original S21 scope (sentiment classification + vote alignment) is replaced by:
- **Sentiment → Themes** — substantive clustering instead of support/oppose/neutral
- **Vote alignment deferred** — can still be built later using theme data, but not in initial scope
- **Comment counts → individual speakers** — enhanced extraction fills the `public_comments` table gap

## Files

### New
- `src/prompts/community_voice_system.txt` — speaker extraction prompt
- `src/prompts/theme_extraction_system.txt` — theme clustering prompt
- `src/community_voice_extractor.py` — transcript → individual comments
- `src/theme_extractor.py` — comments → themes + narratives
- `src/batch_theme_extract.py` — batch API wrapper
- `src/migrations/060_community_voice.sql` — schema
- `web/src/components/CommunityVoiceSection.tsx` — frontend component
- `tests/test_community_voice_extractor.py`
- `tests/test_theme_extractor.py`

### Modified
- `web/src/lib/types.ts` — new interfaces
- `web/src/lib/queries.ts` — new query + fallback logic
- `web/src/app/meetings/[id]/items/[itemNumber]/page.tsx` — swap component
- `web/src/app/meetings/[id]/page.tsx` — update compact indicator
- `src/schema.sql` — add tables
- `docs/pipeline-manifest.yaml` — add pipeline lineage
