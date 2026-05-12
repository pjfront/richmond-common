# Re-Architecture Plan — 2026-05-09

**Trigger:** Operator paying for Vercel Pro + Supabase Pro on a hobby-budget project. Scope pivoted to Richmond-only, Richmond-complete. Five parallel architecture audits commissioned (cost × 2, multi-city overhead, backend, frontend, data, cross-cutting). This plan consolidates all five and sequences the work.

**Plan owner:** AI. Operator approval required before Phase 0 execution. Within each phase, AI executes without further approval unless an item is flagged as a judgment call.

---

## Convergent meta-findings (across all five audits)

These patterns appeared independently in multiple audits — when independent agents converge, the signal is real:

1. **Performative boundaries.** Stated invariants exist only in documentation, not in enforcement.
   - CLAUDE.md D3 ("every component uses shadcn/ui + Radix") — `web/src/components/ui/` doesn't exist.
   - CLAUDE.md D1 (provenance quartet on every record) — found in ~11 of 103 migrations, almost never NOT NULL.
   - "Operator vs public" tier system — at the wire layer, gated by an unsigned cookie + a `NEXT_PUBLIC_` "secret" baked into the client bundle.
   - "Scale by default" tenet — actively costs us; we are one city.
   - **Lesson:** Every architectural rule worth keeping needs tooling enforcement (CI, schema constraint, type check). Discipline-based rules decay.

2. **God objects on both sides of the language boundary.**
   - `src/db.py` — 2,382 LOC, 49 importers, mixes connection mgmt + 12 loaders + dedup + scanner persistence + queue + journal.
   - `web/src/lib/queries.ts` — 5,577 LOC, 102 exports, every page imports from it.
   - `src/conflict_scanner.py` — 5,153 LOC, 65 functions, 11 signals, no dedicated test.
   - `src/data_sync.py` — 3,941 LOC, 67 functions, single SYNC_SOURCES dispatch.
   - `web/src/lib/types.ts` — 1,582 LOC, hand-maintained from 50+ migrations.
   - **Lesson:** A single shared data-access surface that grew without subdivision is the dominant pattern. Splitting is now scary on both sides. Richmond-only pivot = permission to split aggressively.

3. **Cost is an architectural symptom, not a tuning problem.**
   - Hourly ISR × hundreds of slug pages = tens of thousands of background regenerations/day.
   - `select('*')` × inline `vector(1536)` columns = ~6 KB of vector shipped per row on every list query.
   - `documents.raw_content` BYTEA stores PDF bytes that are *also* stored decoded in `raw_text` — likely 200–500 MB of pure waste, plausibly the line item that pushed Supabase past 500 MB free tier.
   - **Lesson:** Fix architecture, cost falls out. Fix cost knobs, problem returns next quarter.

4. **The "AI-native self-monitoring" claim oversells reality.** `system_health.py`, `data_quality_checks.py`, `staleness_monitor.py` exist as CLIs running *next to* the pipeline, not *inside* it. Nothing in `data_sync.py` checks an expectation before declaring success. The system is **self-reporting, not self-monitoring**, and not self-healing. CLAUDE.md should be walked back to match.

---

## 🔴 Phase 0 — Stop the Bleeding (hours, not days)

These are exploitable security issues live in production AND the highest-leverage cost cuts. No architectural debate; ship today.

### Security (do not deploy anything else until done)

| # | Fix | Evidence | Effort |
|---|---|---|---|
| 0.1 | Revoke `GRANT ... TO anon` on `operator_config` UPDATE/INSERT/DELETE | `src/migrations/074_operator_config.sql:88-90` | 1 migration, 5 min |
| 0.2 | Add auth wrapper `withOperatorAuth(handler)` and apply to every route under `web/src/app/api/operator/**` | `settings/route.ts`, `sync-health/route.ts`, `decisions/route.ts`, `send-recap/route.ts` — currently no real auth | 1-2 hours |
| 0.3 | Replace `NEXT_PUBLIC_RTP_OPERATOR_SECRET` with server-only `RTP_OPERATOR_SECRET`. Issue an HMAC-signed httpOnly cookie from a `/api/operator/login` route after server-side secret check. Rotate the current secret — assume compromised. | `web/src/components/OperatorModeProvider.tsx:52` | 2-3 hours |
| 0.4 | Delete `api/operator/send-recap/route.ts` OR have it call `api/email/send-recap` server-side with the bearer token. One destructive code path, one auth model. | duplicate path with weaker auth | 30 min |
| 0.5 | Replace in-memory `Map()` rate limiter with Upstash Redis (`@upstash/ratelimit`). Apply to `subscribe`, `community-comments`, `feedback`, `revalidate`. | `subscribe/route.ts:61`, `community-comments/route.ts:10` | 2 hours |

### Cost (immediate burn rate cuts)

| # | Fix | Evidence | Magnitude |
|---|---|---|---|
| 0.6 | Bump root layout `revalidate` from `3600` → `86400`. Single line. | `web/src/app/layout.tsx:14` | **24× reduction** in background ISR fan-out |
| 0.7 | Add `export const revalidate = 86400` to `sitemap.ts` | `web/src/app/sitemap.ts` | Stops crawler-driven hourly regeneration of full slug enumeration |
| 0.8 | Drop `documents.raw_content` BYTEA column. PDFs are re-fetchable. | `src/db.py:114-147`, `src/migrations/014_backfill_raw_text.sql` | Plausibly **200–500 MB reclaimed** — single biggest Supabase storage win |
| 0.9 | Wrap `/api/health` table probes in `Promise.all`; bump `s-maxage` to 3600 | `web/src/app/api/health/route.ts:76-108` | ~25 sequential queries → 1 round-trip |
| 0.10 | Delete `opengraph-image.tsx` + `apple-icon.tsx` Edge routes; replace with static files in `public/` | `web/src/app/opengraph-image.tsx:3`, `apple-icon.tsx:3` | Stops Edge-invocation burn from social-share crawls |

**Phase 0 expected outcome:** security holes closed; Vercel ISR work cut ~24×; ~300+ MB Supabase storage reclaimed; cost trajectory compatible with free tier on both providers.

---

## Phase 1 — Architecture Foundation (week 1-2)

Rules that cost nothing once written, and that prevent the next round of debt from accumulating.

### 1.1 Documentation reconciliation (do BEFORE structural work)

The five audits found three documentation-vs-reality lies. Fix the docs first so the structural work has a true target to aim at.

- **CLAUDE.md tenet #2 ("Scale by default")** → rewrite to "Richmond-only, Richmond-complete. Scaling abstractions must justify themselves." (Memory `project_richmond_only_pivot.md` already captured this.)
- **CLAUDE.md D3 (shadcn/ui + Radix non-negotiable)** → either commit to installing shadcn this sprint and migrating 8 highest-leverage primitives, OR walk D3 back to "use Radix primitives where accessibility behavior is non-trivial; document custom-component justification per case." Operator chooses.
- **CLAUDE.md D1 (provenance quartet)** → keep the rule, add the enforcement mechanism in 1.2 below.
- **`.claude/rules/architecture.md` Multi-City + AI-native scaling sections** → delete (Richmond-only).
- **`.claude/rules/conventions.md` FIPS Enforcement** → keep "Richmond, California" disambiguation rule for external searches; drop "every query filters by city_fips" framing for internal queries (single-tenant DB).
- **CLAUDE.md "AI-native self-monitoring"** → walk back to "self-reporting + decision queue routing"; reserve "self-monitoring" framing for when expectations gate writes.

### 1.2 Schema-enforced D1 provenance

Define `CREATE DOMAIN provenance_url AS TEXT CHECK (...)`, etc., or add a CI check (extend `tests/test_pipeline_manifest.py`) that fails if any new migration creates a table touching public-facing data without `source_url`/`extracted_at`/`source_tier`/`confidence_score` NOT NULL. **No new public tables ship without this.** Backfill audit table tracking which existing tables already comply.

### 1.3 Migration discipline

- CI check: fail on duplicate numeric prefix in `src/migrations/`. Renumber the existing collisions (`068_community_voice` → `084`, `082_recap_emailed_at` → `085`, `077b` → `085`).
- Move SQL function definitions (`search_*`, stats RPCs, topic RPCs — currently `CREATE OR REPLACE`d across 6 migrations) out of `src/migrations/` into `src/db/functions/*.sql`. Single load step on deploy. Migrations stay schema-only.
- Generate `supabase/migrations/` from `src/migrations/` in CI; don't hand-maintain two copies.

### 1.4 Observability for the web tier

- Sentry on `web/` (free tier) — captures the operator-config-mutation alert that today fires nowhere.
- Structured `console.log({event, ...})` JSON for destructive routes (subscribe, send-recap, operator/settings).

### 1.5 Schema/code lockstep

- Move `supabase db push` into the CI deploy job with `SUPABASE_ACCESS_TOKEN` as a GitHub secret, OR add a pre-deploy migration-drift check that fails the Vercel build if `supabase/migrations/` is ahead of deployed schema.
- Add Vitest + 5–10 route handler tests covering: auth presence, validation rejection, happy path. (One afternoon. Catches the entire class of Phase 0.2 bugs forever.)

---

## Phase 2 — Structural Refactor (week 3-6)

The big one. Same anti-pattern (god-file with too many importers) on both sides of the language boundary. Same fix shape: split by aggregate, introduce repository / domain-grouped boundary.

### 2.1 Backend: split `db.py` into repositories

- New layout: `src/db/connection.py`, `src/db/migrations.py`, `src/db/repos/{meetings,votes,contributions,officials,conflicts,documents,journal}.py`.
- Each repo function returns `models.py` dataclasses (which today are dead code — make them the boundary type).
- Pydantic optional but recommended for validation at the boundary.
- Migration path: incremental. New code goes through repos. Existing 49 importers migrate one at a time when touched. No big-bang.
- Side benefit: introduces a `Connection` Protocol so the 11 critical untested modules (`db`, `conflict_scanner`, `data_sync`, `cloud_pipeline`, `pipeline`, `system_health`, `embedding_generator`, etc.) become unit-testable with an in-memory fake.

### 2.2 Backend: extract `conflict_scanner.py` signals

- New layout: `src/scanner/signals/{donor_match,recusal,address,coalition,...}.py` — one file per detector.
- `src/scanner/scoring.py`, `src/scanner/fetch.py` (or push fetches into 2.1's repos).
- Each signal independently testable. Today the whole 5,153-LOC module is untestable as a unit.

### 2.3 Backend: `data_sync.py` → pipeline registry

- Existing `SYNC_SOURCES` dict already proves the dispatcher pattern; it's just inlined. Extract `Pipeline` Protocol, one file per source under `src/pipelines/`, register via decorator.
- Replace the 40+ `except Exception` blocks with typed exception classes routed through `pipeline_journal`. Today's bare-except hides the very pipeline failures `system_health` was built to detect.

### 2.4 Frontend: split `queries.ts` by domain

- New layout: `web/src/lib/queries/{meetings,council,elections,donors,conflicts,commissions,pacs,comments,search}.ts` with a barrel `index.ts`.
- Move `COLS_*` projections next to their domain.
- Replace all 20 `select('*')` calls with explicit projections (CLAUDE.md already mandates this; convention is just unenforced).

### 2.5 Frontend: generate `types.ts` from Supabase ✅ (2026-05-11)

- ~~Add `npm run gen:types` invoking `supabase gen types typescript`. Commit `database.types.ts`. Hand-curated composite types narrow on top of generated row types.~~
- ~~Eliminates the 1,582-line manual mirror of a 103-migration schema. Drift becomes impossible by construction.~~

Closed 2026-05-11. Three independent gates now make schema drift a compile error:
1. `.github/workflows/schema-drift.yml` — regenerates `database.types.ts` on any PR touching migrations or the file itself; `git diff --exit-code` fails if stale.
2. `web/src/lib/types.drift.test.ts` — scans `types.ts` for `export interface X` whose name maps to a public-schema table and fails CI if the interface doesn't reference `Tables<'tablename'>`. Genuinely freestanding interfaces opt out via `EXEMPT_INTERFACES` with a one-line reason.
3. `tsc --noEmit` — interfaces that anchor via `extends Omit<Tables<'x'>, ...>` stop compiling if any column they reference gets dropped or renamed.

29 hand-rolled table interfaces refactored across five batches; one truly freestanding (`CommunityComment` — no matching DB table). Real divergences surfaced and fixed during the sweep: `meetings.body_id` typed nullable but DB enforces NOT NULL; `meeting_attendance.body_id` and `economic_interests.{document_id, created_at}` previously omitted from query result builders. Convention documented at `.claude/rules/conventions.md` "Frontend Type Drift" and `web/CLAUDE.md`.

### 2.6 Frontend: routing canonicalization

- Pick one canonical agenda-item URL: `/meetings/[id]/items/[itemNumber]`. Make `/influence/item/[id]` and `/reports/[meetingId]` 301 to it.
- Consolidate `/council/patterns`, `/council/voting-patterns`, `/council/stats` into `/council/analytics` with tabs.
- Pick one slug convention: `[slug]` for human-readable, `[id]` for opaque IDs. Rename violators.

### 2.7 Frontend: form validation at the trust boundary

- Add `zod` (small dep). Define request schemas once, share between client and route handler.
- Apply to `/api/subscribe`, `/api/feedback`, `/api/community-comments`, `/api/operator/settings`. (Stacks with Phase 0.2 auth.)

### 2.8 Frontend: card consolidation

- Introduce `Card` shell (or shadcn's, if Phase 1.1 chose to install shadcn). Single `MeetingCard` with `variant="list"|"latest"|"next"` props. Estimate: −300 LOC across `MeetingCard`, `MeetingListCard`, `LatestMeetingCard`.

### 2.9 Frontend: RSC boundary discipline

- Audit `*Client.tsx` files. Data must be server-fetched and passed as props unless user-interactive. Today several `Client` components re-fetch via `queries.ts` from the browser, bundling Supabase into the client and bypassing ISR.

### 2.10 Data: embeddings sidecar

- Migrate `embedding vector(1536)` off `agenda_items`, `meetings`, `officials`, `motions` into `*_embeddings` sidecar tables. HNSW index lives on the sidecar.
- Eliminates accidental ~6 KB-per-row egress on every `select('*')` and removes Layer 3 bleed into Layer 2.
- Pairs naturally with 2.4 (queries.ts split) — embedding fetches become explicit JOINs only when similarity search is needed.

---

## Phase 3 — Richmond-only Cleanup (week 7, parallel-safe)

Per the multi-city overhead audit. Ordered low-risk → high-risk.

### 3.1 Drop dead indexes (low risk, immediate Supabase win)

Drop ~30 single-column `(city_fips)` indexes (zero selectivity in single-city DB; pure write amplification). Re-key 8 composite indexes that lead with `city_fips` to drop the leading column.

### 3.2 Inline `city_config.py` constants

Replace `get_city_config()`, `get_data_source_config()`, `get_council_member_names()` with module constants. ~30 call sites simplify by ~3 LOC each. Removes `copy.deepcopy` per scraper invocation. Removes `inspect.signature` reflection in `data_sync.run_sync`.

### 3.3 Drop `cityFips` parameter plumbing in `web/src/lib/queries.ts`

~40 query functions drop a useless arg. Inline `RICHMOND_FIPS` constant; queries still filter on `city_fips` (cheap; the column stays).

### 3.4 Delete dead test files

9 dedicated `test_*city_config*.py` files (717 LOC) test the abstraction itself, not behavior.

### 3.5 Delete confirmed dead Python modules

Per backend audit: `models.py` (paradoxically — turn into boundary type instead), `pipeline.py`, `dev_structured_explainer.py`, `escribemeetings_to_agenda.py`, `post_meeting_recap.py`, `prepare_census_data.py`, `self_assessment.py`, `change_detector.py`, `deploy_schema.py`. Verify no imports first.

### 3.6 Keep these (NOT overhead)

- `cities` table itself (one row, FK target — ripping it out cascades through 24 tables for no benefit).
- `city_fips` column (7 bytes, harmless, useful for resilience).
- "Richmond, California" web-search qualifier (real disambiguation against 27 actual Richmonds).
- NetFile MCP on PyPI (external; doesn't constrain Richmond code).

---

## Phase 4 — Operational Maturity (week 8+)

### 4.1 Soft-deletes on entity tables

`deleted_at TIMESTAMPTZ` on `officials`, `meetings`, `agenda_items`, `motions`, `contributions`. Rewrite dedup as `UPDATE child SET official_id = canonical_id` then soft-delete the dup row. Today's hard-delete cascades destroy historical vote attribution — unacceptable for a civic-record platform.

### 4.2 Append-only retention

Range-partition by month (`pg_partman`) the high-volume ops tables: `pipeline_journal`, `scan_runs`, `data_sync_log`, `search_queries`, `decision_queue`. Daily `pg_cron` prune for the rest with explicit retention windows. Today these grow forever.

### 4.3 Wire expectations *into* the pipeline

`data_sync.py` should check liveness expectations (already defined in `pipeline-manifest.yaml`) BEFORE declaring success. Convert "self-reporting" to "self-monitoring" honestly. Then re-earn the CLAUDE.md framing.

### 4.4 On-demand revalidation

Wire the Python data-sync pipeline to call `web/src/app/api/revalidate/route.ts` after each successful load, with a path scope (e.g., the specific meeting that changed). Then set `revalidate = false` on slug pages and let on-demand drive freshness. Civic data has strong write-time signals — ISR-by-time was always wrong here.

### 4.5 CSP header

Start with `default-src 'self'; img-src 'self' data: https://*.tile.openstreetmap.org; style-src 'self' 'unsafe-inline'`. Tighten over time.

### 4.6 Frontend test pyramid

Vitest + Playwright. Cover: every API route handler, the OperatorGate enforcement, every form's validation rejection path, golden-path render of each main page.

---

## Phase 4.5 — Launch-readiness gate (before FB public release)

The operator's stated goal is shipping to the Facebook public where they can personally vouch for donation numbers and content. Until this gate passes, the launch button stays grey.

- **Donation-number provenance:** every page displaying a donation total traces cleanly to NetFile / CAL-ACCESS source via the D1 quartet. CI test loads each page, asserts non-null `source_url` + `confidence_score >= 0.9` on every dollar figure rendered.
- **Spot-check protocol:** AI samples 10 random items per donation-displaying page, traces each to original source (PDF, API call), confirms exact match. Generates a `docs/launch-readiness/{date}-spot-check.md` report. Operator countersigns.
- **Top-100 content review:** AI samples 100 highest-traffic-likely content items (recent meetings, prominent council members, current candidates), checks for: confidently-wrong claims, inherited editorial omissions (the Flock pattern), source-label honesty.
- **Security re-audit:** repeat the cross-cutting audit specifically against shipped surface. No anon writes anywhere; no `NEXT_PUBLIC_` secrets; CSP in place; rate limits validated end-to-end.
- **Operator dry run:** operator clicks through every public page from a clean browser (no OperatorGate cookie), confirms nothing operator-only leaks, nothing 500s.

If any check fails, the gate halts launch. AI files findings to `decision_queue` with severity `launch_blocker`.

---

## Phase 5 — Self-knowledge system (the original vision, made structural)

The CLAUDE.md "AI-native self-monitoring" claim is currently aspirational — `system_health.py` and friends are post-hoc surveillance, not pre-commit gating. This phase makes the tenet honest by giving the system a model of itself and the ability to notice when reality diverges.

Reframe the tenet from "self-monitoring" to **"self-knowledge: the system carries a model of itself and detects when reality diverges from that model."** That's truthful and still aspirational.

### 5.1 Baselines + expectation-gated writes

- **New table:** `baselines (source_id, metric_name, mean, stddev, sample_count, updated_at, city_fips)` with rolling-window updates.
- **New helper:** `assert_within_baselines(source_id, metrics: dict) -> Result[OK | Quarantine(reason)]`.
- **Wire into** the five most-failure-prone loaders first (contributions, escribe, propublica, netfile, recap_generation — the ones already failing per current SessionStart report).
- **Failure mode:** anomalous batch writes to `quarantine_<table>` instead of main table. Operator triages from decision_queue with one-click promote-or-discard.
- **Side effect:** "contribution count dropped 62% during load_contributions" stops being a passive medium-priority finding and starts being a refuse-to-commit gate.

### 5.2 Reflective digest

- After every pipeline run: a Haiku-class AI prompt reads the run's journal entries + baseline deltas + any quarantine writes, and writes a 3–5 sentence "what just happened, does it look right" summary into `pipeline_journal.reflection`.
- Anomalies escalate to `decision_queue` with the *reasoned* summary, not just a row-count delta. The operator gets "X dropped 62% because the upstream API returned a different schema for filings dated after 2026-04-01" instead of "anomaly: load_contributions below baseline."
- Cheap (~$0.001 per run with Haiku 4.5).

### 5.3 Drift sentinel (monthly meta-audit)

- Cron-triggered Sonnet-class agent runs claims-vs-code checks. Concretely:
  - For each "non-negotiable" in CLAUDE.md, locate the enforcement (CI check, schema constraint, type, test). If none exists, file a decision_queue item.
  - For each rule in `.claude/rules/`, sample 10 PRs from the past month, check compliance.
  - For each documented architectural pattern, scan for violations (e.g., new `select('*')` calls, new tables without provenance quartet, new modules without test files).
  - Output: `docs/audits/{yyyy-mm}-drift-sentinel.md`.
- This is what would have caught the shadcn lie, the D1 provenance gap, the dead `models.py`, the 20 `select('*')` violations — *before* a commissioned audit had to surface them.
- The drift sentinel is itself the answer to "how do we get to the original vision" — it's the structural mechanism that prevents documentation-vs-reality divergence going forward.

### 5.4 Self-audit cadence in the operator workflow

- Quarterly the AI runs the kind of multi-agent architecture audit we just ran (cost, security, backend, frontend, data, cross-cutting) and writes consolidated findings.
- Today this requires the operator asking. After 5.4, it's automatic.
- Existing `judgment-boundaries.md` quarterly audit process expands to cover this; the cadence already exists, the scope grows.

### 5.5 The honest tenet rewrite

- Replace CLAUDE.md tenet on "AI-native self-monitoring" with: **"AI-native self-knowledge. The system carries an explicit model of itself — baselines, expectations, claims-vs-code mappings — and detects when reality diverges. Anomalies are caught at write time (gated commits), summarized at run time (reflective digest), and meta-audited monthly (drift sentinel)."**
- This is achievable, falsifiable, and matches what 5.1–5.4 actually implement.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Phase 2 refactors are large and could regress production | Each refactor is incremental; new code through new structure, old code migrates when touched. Add tests before refactoring (Phase 1.5). |
| Phase 0 security fixes lock the operator out of their own dashboard | Issue the new operator cookie via `/api/operator/login` immediately after rotating the secret. Operator UX unchanged. |
| Dropping `documents.raw_content` (Phase 0.8) loses re-extractability | False — `raw_text` already exists. Re-extraction reads text. Original PDFs re-fetchable from Archive Center / eSCRIBE. |
| Migration renumbering (Phase 1.3) breaks already-applied DBs | Renumber forward only (assign next free slot). Already-applied dups stay applied; new slot is a no-op `IF NOT EXISTS`. |
| Walking back CLAUDE.md self-monitoring claim feels like admitting failure | It's not. It's matching docs to truth so the next decision is grounded. The audit caught it; the operator should hear it from us, not from a future incident. |

---

## Effort summary (rough)

| Phase | Wall time (single dev) | Risk | Blocking |
|---|---|---|---|
| 0 | 1 day | LOW (security wins are surgical; cost wins are 1-line edits) | None |
| 1 | 1 week | LOW | Phase 0 |
| 2 | 3-4 weeks | MEDIUM (large surface, incremental migration) | Phase 1.5 (tests) |
| 3 | 2-3 days | LOW | Phase 2.1 (so we know which paths still matter) |
| 4 | Ongoing | MEDIUM | Phase 2 |

---

## Open judgment calls (require operator decision)

These are the only items in this plan that require human judgment per `.claude/rules/judgment-boundaries.md`:

1. **D3 disposition (Phase 1.1):** install shadcn/ui this sprint, OR walk D3 back to per-component justification?
2. **Operator auth mechanism (Phase 0.2):** simplest solid choice is HMAC-signed httpOnly cookie issued by a server route. Acceptable, or prefer NextAuth / Vercel Password Protection?
3. **Documents storage (Phase 0.8):** confirmed safe to drop `raw_content` BYTEA? (Re-fetch from Archive Center on demand. Loses speed of in-DB lookup, gains hundreds of MB.)
4. **Self-monitoring framing (Phase 1.1):** walk back the CLAUDE.md "AI-native self-monitoring" claim to "self-reporting + decision queue routing"? Accurate but less inspiring.
5. **Phase ordering:** anything you want done first that I have ranked low? Anything you want skipped?

Once these five are answered, every remaining item in Phases 0–4 is AI-delegable and I will execute end-to-end.
