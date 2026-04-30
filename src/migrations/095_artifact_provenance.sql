-- Migration 095: Provenance metadata for auto-generated text artifacts.
--
-- Background. Entry 50/51 in JOURNAL.md exposed a class of bug: an
-- auto-generated artifact (meeting_recap) carried a fixed UI label
-- ("from official minutes and vote records") that became dishonest when
-- the underlying input source changed (transcript-extracted motions
-- counted as "votes" without the label adapting). The 72480e6 fix added
-- a render-side prop (hasMinutesMotions) for one branch. The audit on
-- 2026-04-27 found the same dishonest-attribution risk in 6 more sites.
--
-- Architectural fix: provenance is a property of the artifact, not of
-- the renderer. Every auto-generated text column gets a sibling JSONB
-- column written by the generator in the SAME UPDATE that writes the
-- text. The frontend reads provenance and renders attribution from it
-- via a single <SourceAttribution> component. Zero desync window.
--
-- Provenance struct shape (TypeScript discriminated union mirrored in
-- web/src/lib/types.ts):
--
--   { kind: 'official_minutes',  minutes_url, as_of, generator?, backfilled? }
--   { kind: 'meeting_recording', channel: 'kcrt'|'granicus', as_of, generator?, backfilled? }
--   { kind: 'agenda_packet',     agenda_url, as_of, generator?, backfilled? }
--   { kind: 'mixed',             from_minutes, from_transcript, as_of, generator?, backfilled? }
--
-- Storage strategy:
--   - Generated text artifacts (recaps, summaries, bios): JSONB column
--     written by the Python generator. This migration.
--   - Aggregate-derived artifacts (theme groupings): provenance is
--     computed at query time from public_comments.source. No column
--     needed; the existing comment_source path handles that case.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS. Backfill happens in a separate
-- script (src/backfill_artifact_provenance.py) so this migration stays
-- pure-DDL and re-runnable.

-- ── meetings: 4 generated text columns ─────────────────────────────────
ALTER TABLE meetings
  ADD COLUMN IF NOT EXISTS meeting_recap_provenance       JSONB,
  ADD COLUMN IF NOT EXISTS transcript_recap_provenance    JSONB,
  ADD COLUMN IF NOT EXISTS meeting_summary_provenance     JSONB,
  ADD COLUMN IF NOT EXISTS orientation_preview_provenance JSONB;

COMMENT ON COLUMN meetings.meeting_recap_provenance IS
  'Provenance struct for meeting_recap. Written by generate_meeting_recaps.py '
  'in the same UPDATE as meeting_recap. Discriminated union — see migration '
  '095 header for the kind variants.';

COMMENT ON COLUMN meetings.transcript_recap_provenance IS
  'Provenance struct for transcript_recap. Written by post_meeting_recap.py / '
  'correct_recap_names.py. Replaces the flat transcript_recap_source column '
  'with the unified Provenance shape.';

COMMENT ON COLUMN meetings.meeting_summary_provenance IS
  'Provenance struct for meeting_summary. Written by generate_meeting_summaries.py. '
  'May be ''mixed'' when summary aggregates both minutes-source and transcript-source '
  'motions (Entry 51 dishonest-attribution risk).';

COMMENT ON COLUMN meetings.orientation_preview_provenance IS
  'Provenance struct for orientation_preview. Written by generate_orientation_previews.py. '
  'Always kind=''agenda_packet''; column exists for schema consistency and to enable '
  'the unified <SourceAttribution> render path.';

-- ── officials: bio_summary ──────────────────────────────────────────────
ALTER TABLE officials
  ADD COLUMN IF NOT EXISTS bio_summary_provenance JSONB;

COMMENT ON COLUMN officials.bio_summary_provenance IS
  'Provenance struct for bio_summary. Written by generate_bios.py. Carries '
  '{from_minutes, from_transcript} vote counts so the bio UI can disclose '
  'when stats include transcript-extracted votes (which are pre-minutes '
  'and may revise). Highest-stakes provenance in the catalog: per-person '
  'attribution carries the most credibility weight.';

-- ── agenda_items: plain_language_summary ────────────────────────────────
ALTER TABLE agenda_items
  ADD COLUMN IF NOT EXISTS plain_language_summary_provenance JSONB;

COMMENT ON COLUMN agenda_items.plain_language_summary_provenance IS
  'Provenance struct for plain_language_summary. Written by generate_summaries.py / '
  'plain_language_summarizer.py. Always kind=''agenda_packet'' (title + description + '
  'staff_report attachment, all from eSCRIBE agenda packet).';

-- ── Indexes ─────────────────────────────────────────────────────────────
-- GIN on the kind field for "find all artifacts of source X" queries.
-- Useful for liveness checks and the backfill script.
CREATE INDEX IF NOT EXISTS meetings_meeting_recap_provenance_kind_idx
  ON meetings ((meeting_recap_provenance->>'kind'))
  WHERE meeting_recap_provenance IS NOT NULL;

CREATE INDEX IF NOT EXISTS meetings_meeting_summary_provenance_kind_idx
  ON meetings ((meeting_summary_provenance->>'kind'))
  WHERE meeting_summary_provenance IS NOT NULL;

CREATE INDEX IF NOT EXISTS officials_bio_summary_provenance_kind_idx
  ON officials ((bio_summary_provenance->>'kind'))
  WHERE bio_summary_provenance IS NOT NULL;
