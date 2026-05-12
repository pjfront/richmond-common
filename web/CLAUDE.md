# web/CLAUDE.md — Frontend Conventions

## Stack

Next.js 16 (app router), React 19, TypeScript (strict, no `any`), Tailwind CSS v4, Supabase client. Deployed on Vercel with ISR (1hr revalidation).

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
  lib/           # queries.ts, types.ts, supabase.ts, useFeedback.ts
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
- **`lib/queries.ts`** — All Supabase queries. Every query filters by `city_fips` (constant `RICHMOND_FIPS = '0660620'`). Functions: `getMeetings`, `getMeetingsWithCounts`, `getMeeting`, `getOfficials`, `getOfficialBySlug`, `getOfficialVotingRecord`, `getTopDonors`, `getMeetingStats`, `getConflictFlags`, `getConflictFlagsDetailed`, `getMeetingsWithFlags`, plus CPRA queries.
- **`lib/useFeedback.ts`** — Client-side state machine hook for feedback submission

## Component Patterns

- **Server components by default** (app router). Client components only for interactivity (`"use client"` directive).
- **ISR via root layout:** `layout.tsx` exports `revalidate = 3600`. Pages inherit — don't add per-page revalidate unless overriding (e.g., `/council/patterns` uses 1800). Only `/search` uses `force-dynamic`. Never use `select('*')` in listing queries — use `COLS_*` constants from `queries.ts`.
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

- `POST /api/feedback` — User feedback. Upstash-rate-limited.
- `GET /api/health` — Migration health check, probes tables in parallel. 1-hr cache.
- `GET /api/data-freshness` — Per-source freshness status. 1hr cache.
- `GET /api/public-records` — CPRA compliance stats. Graceful fallback for missing migration.

## Visual Verification

**After every visual change, before committing:** Use Claude Preview tools to verify your work against design rules. Full workflow and checklist at `docs/design/VISUAL-VERIFICATION.md`.

Quick reference:
1. `preview_snapshot` — check DOM structure (Tier A: heading hierarchy, ARIA, touch targets)
2. `preview_screenshot` at 1280px — check visual quality (Tier B: KPIs, source badges, composition)
3. `preview_resize` to 375px + `preview_screenshot` — check mobile layout
4. Fix violations or add to `docs/design/DESIGN-DEBT.md`
5. Flag Tier C items (tone, framing, publication readiness) for human review

## Key Conventions

- **No `any` types.** Every Supabase response is cast to typed interfaces.
- **FIPS filtering everywhere.** Even with single-city data, every query uses `.eq('city_fips', cityFips)`.
- **Graceful degradation.** CPRA pages handle missing migration 003. Health endpoint returns degraded (not error) for missing optional tables.
- **Publication tiers in UI.** Reports page shows Tier 1 + Tier 2 flags only. Tier 3 count disclosed in methodology ("Additional matches tracked internally: N").
- **Source credibility displayed.** About page has color-coded tier cards. Richmond Standard always tagged "funded by Chevron Richmond."
