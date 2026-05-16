# web/CLAUDE.md — Frontend Conventions

## Stack

Next.js 16 (app router), React 19, TypeScript (strict, no `any`), Tailwind CSS v4, Supabase client. Deployed on Vercel with ISR (1hr revalidation).

## Deployment Gating (as of 2026-05-16)

**`web/vercel.json` disables Vercel auto-deploy from `main` git pushes.** Pushes to main do NOT trigger a Vercel build or deployment at all — the branch is fully ignored from Vercel's automatic pipeline. The operator triggers production deploys manually.

Why: this is the production-side companion to T0.4's data-anomaly hold. CI's `next build` check (`.github/workflows/build-check.yml`) still runs on main pushes and catches compile errors; the manual gate prevents *successful builds* from going live without an operator-in-the-loop step. A passing build doesn't prove the live site works — RLS regressions visible only via the anon role, ISR cache poisoning, and content mistakes that only manifest after deploy all slip through. Manual promote inserts one human eyeball between "code merged" and "richmondcommons.org reflects the change."

**What's wired automatically:**
- `web/vercel.json` ships `"git": { "deploymentEnabled": { "main": false } }`. Vercel reads this on every push and does nothing with main commits — no preview, no production, no build.
- PR pushes (any branch other than main) still trigger Vercel preview deploys as normal — the gate only applies to main. Use those preview URLs to spot-check changes before merging.
- GitHub Actions `.github/workflows/build-check.yml` still runs `next build` on main pushes, so compile-time errors and missing env vars surface fast even though Vercel itself is dormant.

**What the operator does manually (per production release):**
1. Wait for the Build Check workflow to succeed on the latest `main` commit (catches compile errors)
2. Trigger the Vercel production deploy via either:
   - **CLI (recommended):** `cd web && vercel --prod` — requires one-time `npx vercel link` to associate the local directory with the Vercel project
   - **Dashboard:** Promote a recent preview deployment to production via the Deployments tab
3. Spot-check the live site (visit `/` and one recently-changed page)

**To revert the gate (emergency only):**
- Delete `web/vercel.json` or change `"deploymentEnabled"` to `{ "main": true }`, push to main. Auto-deploy resumes on the next push. `tests/test_deploy_gate.py` will go red until the file is restored or the test updated — that's intentional, so a removal can't slip through silently.

**The trade-off (be honest about the cost):** every production release now requires an operator action. For a one-person project this is acceptable friction in exchange for a hard gate against bad data going live during election week. After June 2 the gate can be revisited — options include re-enabling auto-deploy with a stronger pre-deploy assertion suite, or moving to a `production` branch model where main auto-deploys to preview and the operator merges `main → production` to release.

## Directory Structure

```
web/src/
  app/           # Pages (app router)
    about/       # Mission, methodology, source tiers, disclaimers
    api/         # API routes (feedback, health, data-freshness, public-records)
    council/     # Grid + [slug] profiles with stats, donors, voting record
    meetings/    # List (grouped by year) + [id] detail with agenda/votes
    public-records/  # CPRA compliance dashboard
    reports/     # Financial contribution reports + [meetingId] flag detail
  components/    # 28+ React components (incl. CivicTerm, SourceBadge, DonorOverlapSelector)
  lib/           # queries/ (barrel + 12 domain files), types.ts, supabase.ts, useFeedback.ts
```

## Design System

> **Before creating or modifying any component**, read `docs/design/DESIGN-RULES-FINAL.md` (enforceable rules U1-U14, C1-C8, T1-T6, A1-A6). Before modifying a component with known violations, check `docs/design/DESIGN-DEBT.md`. If a rule seems wrong, check `docs/design/DESIGN-POSITIONS.md` for the reasoning before proposing changes.

**Civic palette** defined in `globals.css` via `@theme inline`:
- `--color-civic-navy: #1e3a5f` / `civic-navy-light: #2d5a8e` — headers, nav, primary
- `--color-civic-slate: #475569` — body text
- `--color-civic-amber: #d97706` / `amber-light: #fbbf24` — accents, CTAs, highlights
- Vote colors: `vote-aye: #059669` (green), `vote-nay: #dc2626` (red), `vote-abstain: #6b7280`, `vote-absent: #9ca3af`
- Typography: Inter font (`--font-sans`), body on `#f8fafc` background

## Data Layer

- **`lib/supabase.ts`** — Supabase client instance
- **`lib/database.types.ts`** — Auto-generated from Supabase via `npm run gen:types`. Source of truth for row/insert/update shapes of every public table. Regenerate in the same commit as any migration that changes a column. Do not edit by hand.
- **`lib/types.ts`** — Hand-curated composite/view types that narrow on top of the generated Row types. Re-exports `Database`, `Tables<>`, `Inserts<>`, `Updates<>`, `Views<>` helpers. As of Phase 2.5 (2026-05-11), every interface that mirrors a public-schema table is anchored to its generated row via `extends Omit<Tables<'tablename'>, ...>` (or `Pick<>` / type alias when no narrowing is needed). The `lib/types.drift.test.ts` safeguard fails CI if anyone adds a new freestanding mirror; freestanding DTOs (no matching table) opt out via `EXEMPT_INTERFACES` with a one-line reason.
- **`lib/queries/`** — All Supabase queries, split by domain in Phase 2.4 (2026-05-11). Domain files: `meetings.ts`, `council.ts`, `elections.ts`, `donors.ts`, `conflicts.ts`, `commissions.ts`, `pacs.ts`, `comments.ts`, `search.ts`, `topics.ts`, `influence.ts`, `public_records.ts`. Barrel `index.ts` re-exports everything for back-compat (`import { getMeetings } from '@/lib/queries'` still works). Shared column-projection constants (`COLS_MEETING_LIST`, etc.) live in `_shared.ts`. Every query filters by `city_fips` (constant `RICHMOND_FIPS = '0660620'`).
- **`lib/useFeedback.ts`** — Client-side state machine hook for feedback submission

## Component Patterns

- **Server components by default** (app router). Client components only for interactivity (`"use client"` directive).
- **ISR via root layout:** `layout.tsx` exports `revalidate = 3600`. Pages inherit — don't add per-page revalidate unless overriding. `force-dynamic` is used for `/search` (per-request input), and for `/council/analytics`, `/financial-connections`, and `/influence` (heavy multi-table queries that exceed the anon statement_timeout under concurrent build prerenders). Adding a new page that calls `getAllFinancialConnectionSummaries` or other heavy joins → make it `force-dynamic` too. Never use `select('*')` in listing queries — use `COLS_*` constants from `queries/_shared.ts`.
- **Layout:** `FeedbackModalProvider` wraps app -> `Nav` -> `main` -> `Footer`
- **Feedback system:** `FeedbackButton` (per-flag accuracy voting), `FeedbackModal` (global tips via React context), `ReportErrorLink` (per-vote errors), `SubmitTipButton` (footer), `SuggestCorrectionLink` (council profiles)
- **Conflict display:** Three-tier confidence system. Tier 1 "Potential Conflicts" + Tier 2 "Financial Connections" shown in reports. Tier 3 suppressed. `ConflictFlagCard` shows amber "X days after vote" badge for temporal correlations.

## Operator Auth (server-enforced as of 2026-05-09)

- Operator-only routes are gated by **iron-session** (sealed httpOnly cookie). Login at `/operator/login`; secret in `OPERATOR_PASSWORD` (server-only env). Cookie sealed with `IRON_SESSION_PASSWORD` (≥32 chars).
- API: wrap operator-only handlers with `withOperatorAuth(handler)` from `@/lib/operator-auth`. Returns 401 on missing session.
- Pages: `web/src/middleware.ts` redirects unauthenticated `/operator/*` requests to `/operator/login` (whitelist: `/operator/login` itself).
- Client side: `OperatorModeProvider` queries `/api/operator/session` on mount. The cookie is httpOnly so JS cannot read it directly.
- Logout: `POST /api/operator/logout`.
- **Never use `NEXT_PUBLIC_*` for any operator secret.** That prefix bakes the value into the browser bundle.

## Rate Limiting (Postgres-backed as of 2026-05-11)

- All rate limiting goes through `@/lib/rate-limit`. In-memory `Map()` rate limiters do not work on Vercel serverless (per-warm-instance, resets on cold start).
- Backend: `rate_limit_buckets` table + `check_and_increment_rate_limit(bucket_key, window_secs, max_count)` RPC (migration 106). Fixed-window counters, atomic INSERT/UPDATE.
- Limits (defined in `rate-limit.ts`): `login` (5/15m), `subscribe` (5/h), `comments` (10/h), `feedback` (10/h), `revalidate` (60/m).
- Pattern: `await enforceRateLimit('login', clientKey(request))` → returns `{allowed, response?}`. If denied, return the 429 response directly.
- Falls open on RPC error so a Supabase blip doesn't lock the site. Login route is the one place this matters; it has its own 750ms artificial delay.
- Retention: `cleanup_rate_limit_buckets()` RPC prunes rows older than 1 day. Wire to a daily cron or pipeline post-step.

## Observability (structured logs)

- **Destructive routes emit structured JSON events** via `@/lib/logger`. The Vercel runtime captures stdout into queryable logs, so JSON lines stay greppable after the fact.
- Pattern: `logEvent('<surface>.<action>[.<outcome>]', { ...requestContext(request), ...fields })`. Severity defaults to `info`; use `warn` for rate-limit / validation rejections, `error` for unexpected failures.
- Never log raw passwords or full email addresses. Use `emailHash(email)` from the logger for stable, non-recoverable identifiers.
- Currently wired into: `operator/login`, `operator/logout`, `operator/settings`, `operator/send-recap`, `subscribe`. Extending the pattern to new destructive routes (revalidate, feedback, community-comments, etc.) is AI-delegable.
- External alerting (Sentry, etc.) is not yet wired. The structured-log layer is the foundation; an alerting sink can layer on later without changing call sites.

## API Routes

- `POST /api/feedback` — User feedback. Postgres-rate-limited via `@/lib/rate-limit` (see "Rate Limiting" above; migration 106 replaced the old Upstash dependency).
- `GET /api/health` — Migration health check, probes tables in parallel. 1-hr cache.
- `GET /api/data-freshness` — Per-source freshness status. 1hr cache.
- `GET /api/public-records` — CPRA compliance stats. Graceful fallback for missing migration.

## Visual Verification

**After visual changes, prefer `next build` over preview tools.** Supabase statement_timeouts hit hard under concurrent build prerenders so the `preview_*` browser-automation tools end up testing failure paths more than the actual UI; running `npm run build` from `web/` exercises the real ISR/SSR code paths and surfaces routing/data issues fastest. Operator memory `feedback_skip_preview.md` is the source of truth on this.

If you do need pixel-level checks (rare — usually a design-debt audit or a screenshot for review), `docs/design/VISUAL-VERIFICATION.md` documents the `preview_snapshot` / `preview_screenshot` workflow.

## Key Conventions

- **No `any` types.** Every Supabase response is cast to typed interfaces.
- **FIPS filtering: new queries can skip it.** Per the 2026-05-09 single-city pivot (`.claude/rules/conventions.md`), internal queries no longer need `.eq('city_fips', cityFips)` — the DB has one city's data. **Existing queries keep their filter** (~115 across this directory) until Phase 3 of the rearchitecture plan drops the indexes wholesale; rewriting them all now is churn without benefit. Pattern for new queries: omit the filter, leave the column in the SELECT for provenance.
- **Graceful degradation.** CPRA pages handle missing migration 003. Health endpoint returns degraded (not error) for missing optional tables.
- **Publication tiers in UI.** Reports page shows Tier 1 + Tier 2 flags only. Tier 3 count disclosed in methodology ("Additional matches tracked internally: N").
- **Source credibility displayed.** About page has color-coded tier cards. Richmond Standard always tagged "funded by Chevron Richmond."
