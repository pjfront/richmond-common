# Code Conventions & Standards

## FIPS Enforcement

- **Every database table** has a `city_fips` column
- **Every query** filters by `city_fips`
- **Every web search** includes "Richmond, California" — never just "Richmond"
- **Every API response** includes city context
- Richmond CA = `0660620`. There are 27 Richmonds in the US.

## Python (Backend/Pipeline)

- Type hints on all functions
- Extraction prompts in dedicated files, not inline strings
- `python-dotenv` required — `.env` is in repo root, not `src/`
- Load with `load_dotenv(Path(__file__).parent.parent / ".env", override=True)`
- Run pipeline scripts from `src/` directory
- NULL-safe field access: `(row.get("FIELD") or "").strip()` pattern
- **Anthropic API calls must set `temperature` explicitly.** The SDK default is 1.0, which produces non-deterministic output. Structured extraction (JSON, classifications) → `temperature=0`. Creative generation (recaps, summaries, bios) → `temperature=0` for reproducible regeneration unless the operator has explicitly opted into stylistic variation. Reference pattern: `src/extract_transcript_votes.py` (with the canonical "why, with evidence" comment).

## TypeScript (Frontend)

- Strict TypeScript, no `any` types
- Next.js 16 app router with ISR (1hr revalidation)
- Supabase queries in `web/lib/queries.ts`, types in `web/lib/types.ts`

## Branching

- **Feature branches for all work.** Each session (or parallel session) works on its own branch.
- **Check before first edit.** Before writing, editing, or deleting any file, verify you're on a feature branch (not `main`). If on `main`, create a feature branch first. This is AI-delegable — do it automatically, don't ask.
- Branch naming: sprint or feature prefix, e.g. `s9-search`, `s8-commission-meetings`, `fix-donor-dedup`.
- Merge locally to `main` when done. Always push to GitHub after merging.
- **Parallel sessions** use Claude Code's built-in worktree support. Each session gets an isolated branch and working copy.
- No PRs unless explicitly requested. This is a solo project.

## Commit Messages

- Imperative mood, reference the phase: "Phase 2: add coalition tracking"
- AI drafts all messages; most are AI-delegable. See `team-operations.md` for when commit message framing is a judgment call requiring human review.

## Progress Tracking Sync

- **Every commit that completes or substantially advances a PARKING-LOT.md item must update the parking lot in the same commit.** Mark items ✅, add status lines, update descriptions. This is AI-delegable.
- Same applies to `CLAUDE.md` "What's Built" section when sprint status changes (e.g., an entire sprint completing).
- If a commit touches multiple tracked items, update all of them.

## Pipeline Manifest Sync

- **Every commit that adds, modifies, or removes a sync source, db loader function, query function, or frontend page must update `docs/pipeline-manifest.yaml` in the same commit.** This is AI-delegable — same enforcement pattern as PARKING-LOT sync.
- The manifest is validated by `src/pipeline_map.py validate` and `tests/test_pipeline_manifest.py`. Drift is also reported in the SessionStart health check.
- When adding a new data pipeline: add entries to `sources`, `tables`, and wire through `enrichments` → `queries` → `pages` as applicable.
- Use `python src/pipeline_map.py impact <module>` to check downstream effects before making changes.
- This is not optional. The parking lot is the project's source of truth for progress. If it's stale, the operator wastes time re-discovering what's done.

## Source-Closest Artifact

Every generator and every debug investigation must identify what data artifact it is reading and verify that artifact is the closest-to-source persisted form. Derivative artifacts (summaries, recaps, embeddings, theme narratives, labels, bullet lists) inherit any editorial omissions of their input. Downstream consumers that read derivatives inherit those omissions in turn — and amplify them when summarizing.

**The rule, two ways.**

When **writing a generator or extractor** (any `src/*.py` script that reads from one place and writes to another), the first design question is: "what's the source-closest artifact for this input?" Read from raw persisted data when available. Examples of source-closest artifacts:

| Domain | Source-closest | Common derivatives that should NOT be the input |
|---|---|---|
| Council meeting transcripts | `data/transcripts/{date}_clean.txt`, official minutes PDFs | `meetings.transcript_recap`, `meetings.meeting_recap`, `meetings.meeting_summary` |
| Vote / motion data | `motions` + `votes` (filtered by `source='minutes'` for ground truth) | `vote_explainer`, `meeting_recap`, narratives |
| Public comments | `public_comments` rows | `item_theme_narratives`, `comment_summary`, theme narratives |
| Officials & staff | `officials`, `city_employees` tables | bio summaries, `canonical_names.md` (regenerable from those tables) |
| Campaign finance | `contributions` (NetFile API direct), CAL-ACCESS bulk | aggregated totals, top-donor lists |
| Conflicts | `conflict_flags` rows | flag-count badges, summary cards |
| Agendas | `data/agendas/` PDFs, `agenda_items` | `orientation_preview`, `meeting_summary` |

If you must read a derivative because the source isn't persisted, **document why** in the script's docstring and **log the choice** at runtime so the operator can see which path fired.

When **debugging incorrect generated output**, the first question is "what artifact is this reading?" — NOT "what's wrong with what it produced?" The most common cause of confidently-wrong AI output is reading a derivative artifact that already had editorial license. The fix is to read the source-of-truth artifact, not to fix the prompt.

**Generator docstring convention.** Every Python script in `src/` that reads input data must declare its input artifact in the module docstring. A single sentence: "Reads from X. Does NOT read from Y (derivative)." Example from `src/extract_transcript_votes.py`:

> Reads raw auto-captioned transcripts from `data/transcripts/{date}_clean.txt` when available (preferred), falling back to `meetings.transcript_recap` otherwise.

Adding or updating this declaration is AI-delegable.

**Why this matters.** The 2026-04-26 Flock incident (JOURNAL.md Entry 51): the 3/17 meeting page confidently asserted "the council did not vote on any action items, including a Flock Safety contract extension" — for a 4-3 vote that was right there in the raw auto-caption file the whole time. The bug looked like a prompt failure; it was actually an input-source failure. `extract_transcript_votes.py` had been reading `transcript_recap` (a curated 3KB summary that had editorially omitted Flock) when it should have been reading the raw 60KB transcript persisted at `data/transcripts/2026-03-17_clean.txt`. Two days of confident assertion that no one had noticed because the attribution looked authoritative.

**The cascade risk.** Multi-stage AI pipelines amplify omissions. The 3/17 chain was raw transcript → `transcript_recap` → `meeting_recap` → user-facing display. Each summarization step had editorial license. When `transcript_recap` omitted Flock, `meeting_recap` inherited the omission and amplified it ("did not vote on any action items"). Generally: when summarizing a summary, every step away from raw is a step closer to confidently asserting something the raw never said. Where multi-stage chains exist, downstream stages should reach back to the raw artifact for verification, not just trust the immediately-upstream summary.

**The honest-source-label corollary.** If a generator reads from a derivative, the UI label that displays the generator's output must say so honestly. Don't claim "Auto-summarized from official minutes" when the actual input was `transcript_recap` + agenda items + public comments. Branched/conditional source labels (per `MeetingNarrative.tsx`'s `hasMinutesMotions`) are the pattern — they reflect the actual input source at render time, not a hopeful fixed string. Initial source-label choices and their phrasing are judgment calls; making the label conditional once the data path is clear is AI-delegable.

## Canonical Names

- **Auto-generated transcripts misspell names phonetically.** YouTube/Granicus auto-captions transcribe "Gioia" as "Joya," "Aleshire" as "Alshshire," etc. Without correction, those misspellings leak into public-facing recaps.
- **`src/prompts/canonical_names.md`** is the authoritative spelling reference. It's appended to the system prompt of every transcript-derived generation: `transcript_recap`, `meeting_recap`, `comment_summary`, `theme_extraction`. The model is instructed to use canonical spellings even when the input spells phonetically.
- **When you see a misspelled name in a recap:** add the canonical spelling to `canonical_names.md` in the same commit that triggers regeneration. AI-delegable — same enforcement pattern as PARKING-LOT and pipeline-manifest sync.
- **Don't invent spellings.** If a name isn't in `canonical_names.md` or in the `officials`/`city_employees` DB tables, use a generic role descriptor in the recap. Never guess.
- **Auto-sync from DB:** `python src/sync_canonical_names.py` regenerates the "Richmond City Council" and "Richmond Municipal Staff" sections from `officials` and `city_employees`. "Often misheard as:" alias lines are preserved across regenerations — the sync only rewrites the canonical headers. Run after any council change, role transition, or department-head update. Idempotent. Hand-curated sections (former officials, county supervisors, retained counsel, recurring orgs) are not touched.
- **Apply to existing recaps:** `python src/correct_recap_names.py --all` runs already-generated recaps through Claude with the updated canonical list, replacing phonetic misspellings without re-fetching transcripts. ~$0.05 per recap. Use after any canonical-name addition that affects historical recaps.

## Liveness Expectations

- **Every new source or enrichment in the manifest must declare at least one `expectations:` entry.** Static lineage answers "where could data go?" — expectations answer "did the latest record actually flow through?" Both layers are required to catch silent pipeline failures.
- Expectations live in `docs/pipeline-manifest.yaml` under the top-level `expectations:` block. Each is a SQL `SELECT` that returns ROWS WHERE THE EXPECTATION FAILS (empty result = passing).
- Required fields: `id` (snake_case, used as decision_queue dedup key), `owner` (a source or enrichment name), `severity` (high/medium/low/info), `description`, `check` (SQL).
- Run locally: `python src/pipeline_map.py liveness`. Surface failures into the operator decision queue: `python src/pipeline_map.py liveness --create-decisions`.
- Failures appear in the SessionStart health report under "Pipeline Liveness." Critical owners (escribemeetings, netfile, recap_generation, orientation_generation, conflict_scanning, topic_tagging) are enforced by `tests/test_pipeline_manifest.py::TestLivenessExpectations`.
- **Anon visibility (Layer 3):** `tests/test_anon_visibility.py` queries each public-facing table via the anon Supabase client. Catches the "data exists but RLS blocks the public from seeing it" pattern. When adding a new public table, add it to `PUBLIC_TABLES` in that test.

## AI Parking Lot

- **Every session:** Note ideas, research topics, improvement suggestions, and technical debt observations in `docs/AI-PARKING-LOT.md`.
- AI has full autonomy over this file. No approval needed to add, edit, or reorganize.
- Commit/push with regular session work.
- Categories: Research Topics (R#), Improvement Suggestions (I#), Technical Debt (D#), Validation Checkpoints (V#).
- This is distinct from `docs/PARKING-LOT.md` (sprint execution tracking, human-managed).

## Human Action Callouts

- **Migrations are AI-executable.** Run `supabase db push` directly after writing migrations — don't list as a human action. Requires `SUPABASE_ACCESS_TOKEN` in `.env`.
- **Genuinely non-AI-executable steps** (e.g., DNS changes, external account registrations) must be called out as a human action at the point the work ships, not buried in a summary.
- Include the exact URL, SQL, or command inline. No "run this in Supabase" without the link.
- If multiple human actions accumulate during a session, list them all explicitly before signing off.

## Testing

- pytest for Python, 400+ tests in `tests/`
- Dict-dispatched functions: use `patch.dict(SYNC_SOURCES, ...)` not `@patch("data_sync.sync_netfile")`
- Lazy imports in sync functions: patch at source module level

## Database Migrations

- **Source of truth:** `src/migrations/` with sequential naming (`00N_description.sql`)
- **Supabase CLI copies:** `supabase/migrations/` with timestamp naming — auto-generated from `src/migrations/`
- All migrations are idempotent (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `DROP POLICY IF EXISTS` before `CREATE POLICY`)
- **Running migrations:** `supabase db push` from repo root (AI-delegable). Requires `SUPABASE_ACCESS_TOKEN` in `.env`.
- **Creating migrations:** Write in `src/migrations/` first, then copy to `supabase/migrations/` with timestamp prefix
- **Dry run:** `supabase db push --dry-run` to preview what would be applied
- Health check: `/api/health` probes tables across all migration groups

## Documentation

- Log decisions in `docs/DECISIONS.md` with date and rationale
- Research output goes to `docs/research/{topic}.md`
- Plans go to `docs/plans/{date}-{topic}.md`
- Specs go to `docs/specs/{feature}-spec.md`

## Environment

- Use Claude Code through the Claude desktop app, NOT VS Code extension
- Parallel sessions: use built-in worktree checkbox or sibling directories (NOT `.worktrees/`)
- No `sudo npm install` — ever
- Secrets in `.env` only, `.env.example` gets placeholder values like `sk-ant-...`
