# web/CLAUDE.md — Frontend Conventions

**Active plan:** The [September 6 implementation delegation](../docs/CURRENT-PLAN.md) supersedes the historical S29 and repeated human-approval requirements below within its accepted scope. Retain technical release and source-quality checks.

## Stack

Next.js 16 (app router), React 19, TypeScript (strict, no `any`), Tailwind CSS v4, Supabase client. Deployed on Vercel with ISR (1hr revalidation).

## Deployment Gating (as of 2026-05-16, tightened 2026-08-23)

**`web/vercel.json` disables every automatic Vercel Git deployment.** Pushes to main and PR branches do not trigger a Vercel build or deployment. Production deploys and bounded PR Previews are intentional, exact-source operations.

Why: this is the production-side companion to T0.4's data-anomaly hold. CI's `next build` check (`.github/workflows/build-check.yml`) still runs on main pushes and catches compile errors; the gate prevents *successful builds* from going live without an explicit deploy step. A passing build doesn't prove the live site works — RLS regressions visible only via the anon role, ISR cache poisoning, and content mistakes that only manifest after deploy all slip through. The explicit deploy step inserts one eyeball between "code merged" and "richmondcommons.org reflects the change."

**What's wired automatically:**
- `web/vercel.json` ships the documented global `"git": { "deploymentEnabled": false }` switch. Vercel does nothing with automatic Git pushes from any branch — no Preview, Production deployment, clone, install, or build. Explicit REST API, CLI, and Deploy Hook paths remain available.
- A live PR Preview is requested only by the trusted-main bounded Supabase Preview controller, which sends the exact approved branch and full Git SHA to Vercel's REST API. Production remains an explicit CLI deployment.
- GitHub Actions `.github/workflows/build-check.yml` still runs `next build` on main pushes, so compile-time errors and missing env vars surface fast even though Vercel itself is dormant.

**Automation and preview isolation (added 2026-08-06, tightened 2026-08-23):**
- Global `git.deploymentEnabled: false` contains `heartbeat`, `automation/**`, `automation-*`, main, and every PR branch before a deployment is created. Do not substitute `gitProviderOptions.createDeployments`; it is not a build-disable control and did not stop clone/install/build in the live probe.
- `ignoreCommand` rejects `heartbeat` and both automation-ref forms before any Production exception. It is automation-only defense in depth, not the Preview approval boundary. A deployment canceled here still counts as a full Vercel deployment and briefly occupies a concurrent-build slot; the global Git switch is what avoids that usage for ordinary pushes.
- Vercel runs `web/scripts/assert-preview-env.mjs` before every build. On `VERCEL_ENV=preview`, the build fails if the production Supabase project URL or any server-only production credential is in scope.
- A live PR Preview is provisioned explicitly through `.github/workflows/supabase-preview.yml`; see `docs/supabase-preview-branches.md`. The workflow creates a data-less, non-persistent Supabase branch, proves its native deletion deadline, writes five exact-git-branch identity variables plus PR/creation/parent/deployment lifecycle markers, and requests exact H0 only after its type comparison passes (or exact H1 only after the separately verified type-only rebind). It explicitly targets Preview, attests the immutable returned deployment through terminal `READY`, and never uses a production database password or service-role key.
- `assert-preview-env.mjs` is the branch-owned last guard: it requires the branch-scoped Git branch, exact approved Git SHA, and Supabase project-ref markers to match Vercel's actual Git ref, commit SHA, and Supabase URL. A generic Preview variable, a marker copied from another branch, or a later commit on the same branch therefore fails closed even if its key names look correct. The trusted-main controller and its exact REST request—not this branch-owned script—are the approval boundary.
- Preview must never receive `DATABASE_URL`, a Supabase service-role key, email/API secrets, model API keys, or operator/session secrets. Environment scope is configured in the Vercel project control plane; the build guard makes scope drift fail closed.
- GitHub PR Build Check uses an inert loopback Supabase URL and performs no production read. The production-connected anon-role integration build runs only on a push to `main`.

**Production deploy is now AI-delegable** (as of 2026-05-18; previously operator-manual). Windows execution starts through `web/scripts/deploy-prod.ps1`, which pins Git for Windows instead of the operator machine's unusable bare-`bash`/WSL resolution, then hands off to `web/scripts/deploy-prod.sh`. The shell gate:
1. Requires the operator-approved full 40-character SHA as its only argument
2. Pins canonical GitHub repository `pjfront/richmond-common`, queries its `main` ref through `gh api --hostname github.com`, and refuses a fork origin, non-`main` branch, mismatched HEAD, or dirty checkout
3. Requires a successful `Build Check` main-push run for that exact repository and SHA; lookup errors, missing/stale runs, pending runs, and every non-success conclusion fail closed
4. Creates a temporary upload solely from `git archive <approved-sha>` with Git replacement objects and caller Git indirection disabled. System/global archive attributes are disabled, repository-local `.git/info/attributes` is refused, archive permissions are pinned, symlinks and non-example env files are rejected, and the 50 MB/2,000-file caps apply to that artifact
5. Pins Vercel CLI `59.1.4` to its reviewed JavaScript path (native-binary override disabled), official npm registry `https://registry.npmjs.org/`, official API origin `https://api.vercel.com`, team scope `phillips-projects-1f180556`, and the tracked, non-secret Richmond Commons org/project IDs. It explicitly overrides ambient npm offline/prefer-offline settings to refresh and version-prove that CLI from the official registry before final checks, disables its update notifier and telemetry, then requires strict offline package resolution for every Vercel read/deploy/API call. It refuses conflicting ambient IDs and never trusts `.env`, `.vercel`, or mutable per-user npm/Vercel routing configuration for the deployment target
6. Captures the exact current READY production deployment before mutation, then repeats CI and checkout checks and makes one final canonical-main query immediately before the pinned Vercel invocation
7. Deploys only the immutable artifact with explicit approved-SHA/ref metadata, then requires the returned deployment to be READY production at that SHA and `main`, and requires `richmondcommons.org` to resolve to that exact deployment ID
8. Prints a literal `ACTION:` smoke check plus the captured prior deployment ID. It never auto-rolls back

**Boundary split** (per `.claude/rules/judgment-boundaries.md`):
- **AI-delegable:** running `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\web\scripts\deploy-prod.ps1 <full-sha>` after exact-SHA operator approval. The launcher selects `C:\Program Files\Git\bin\bash.exe` explicitly; do not substitute bare `bash`, which resolves to unconfigured WSL on the operator machine. The mechanics — prove Git/CI, construct the immutable artifact, invoke `vercel --prod`, confirm — are mechanical. Passing a SHA to the script is not itself evidence of approval.
- **Judgment call (unchanged):** deciding *whether* a batch with public-facing changes is ready to ship. AI provides the full 40-character SHA, complete included-change list, and user-visible impact; operator approval is valid only for that SHA. Any later `main` commit requires a new packet and approval.

**Per-release workflow:**
1. Merge to main (existing workflow — AI-delegable)
2. AI provides a decision packet with the full 40-character current-main SHA, every change since the last production deploy, and the user-visible impact
3. Operator approves that exact SHA (judgment call); if main advances, return to step 2
4. From the clean Windows `main` checkout root, AI runs `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\web\scripts\deploy-prod.ps1 <operator-approved-full-sha>` (mechanical)
5. AI verifies the wrapper's deployment/alias/SHA attestation, opens the homepage and `/api/health`, and reports back
6. If either smoke check fails, AI first prepares a bounded rollback compatibility packet naming the exact prior `dpl_...` ID, resolving it to an exact full Git SHA (or returning `UNSAFE/UNKNOWN`), and listing every committed Supabase migration plus any explicitly approved schema-contract or manual data-correction operation between that SHA and the current approved SHA. It verifies the live Supabase migration ledger and schema metadata read-only, but never scans, queries, or corrects production table rows; ordinary content sync/ingestion is excluded. A Vercel rollback changes frontend/runtime code only; it never reverses Supabase migrations or data. The packet must preserve live migration 136, keep migration 134 HARD NO-GO, and must not propose production-data correction. Immediately before approval, AI re-checks read-only that the captured deployment remains the immediately previous target and is rollback-eligible on the current Vercel plan; an upgrade is not a rollback remedy. Only if exact source, eligibility, and code/schema compatibility are proven may the operator separately reply `APPROVE PRODUCTION ROLLBACK: <exact-prior-dpl-id>`. AI then re-checks current production and eligibility immediately before command execution and invokes the pinned CLI strictly offline. If the package cache is missing, AI may prefetch `59.1.4` from the pinned official registry, but it must then repeat the current-state and eligibility proof; any changed state or intervening target/control-plane action invalidates approval and requires a new packet and approval

If deployment/alias attestation is ambiguous, the packet must first resolve the actual current production deployment ID and exact full Git SHA; it must not assume the approved SHA went live. If actual current source cannot be proven, the verdict is `UNSAFE/UNKNOWN`; any diagnostic output showing rollback syntax remains explicitly `NOT AUTHORIZED` and must not be executed.

**Residual concurrency (do not overclaim):** Vercel and GitHub do not offer one atomic transaction spanning main, CI, source upload, and alias promotion. `main` could advance just after the final canonical query, or another authorized control-plane action could move the production alias after attestation. Automatic Git deployment remains disabled and this wrapper is the sole approved normal production path, which removes ordinary competing deploys. The wrapper also re-queries main after its final CI request and verifies the alias after deploy. Any external/manual deployment must be coordinated as a separate operator-approved action.

**One-time setup (already done as of 2026-05-18):**
- On the operator machine, use only `env NO_UPDATE_NOTIFIER=1 VERCEL_TELEMETRY_DISABLED=1 VERCEL_CLI_USE_NATIVE_BINARY=0 npx --registry=https://registry.npmjs.org/ --offline=false --prefer-online --yes vercel@59.1.4 --api https://api.vercel.com login` (auth lives outside the repository; no team scope is needed for login)
- No Vercel project link or `.env` setup is needed. The non-secret Richmond org/project IDs and CLI version are pinned in the tracked wrapper; credentials remain external
- Guard tests fail if target binding, exact-SHA/CI checks, immutable artifact rules, rollback capture, or post-deploy attestation regress

**To revoke AI-runnable deploys:**
- Run `env NO_UPDATE_NOTIFIER=1 VERCEL_TELEMETRY_DISABLED=1 VERCEL_CLI_USE_NATIVE_BINARY=0 npx --registry=https://registry.npmjs.org/ --offline=false --prefer-online --yes vercel@59.1.4 --api https://api.vercel.com logout` on the operator machine or revoke that CLI session in Vercel. Do not substitute an unguarded manual `vercel --prod`; restoring the authenticated exact-SHA wrapper is the approved path.

**To revert the gate entirely (emergency only):**
- Delete `web/vercel.json` or change `"deploymentEnabled"` to `true`, then publish that configuration intentionally. Automatic Git deployments resume for every branch. `tests/test_deploy_gate.py` will go red until the file is restored or the test updated — that's intentional, so a removal can't slip through silently.

**The trade-off (be honest about the cost):** the gate still requires an explicit deploy step per release. The 2026-05-18 change moved WHO runs the command (AI now) but kept WHAT triggers it (intentional decision per batch). For a one-person project this is the right point on the speed/safety curve — the operator's attention is the constrained resource, and reviewing diffs is more valuable than running CLI commands.

## Directory Structure

```
web/src/
  app/           # Pages (app router). Top-level segments:
                 #   Public:    about, council, commissions, elections,
                 #              meetings, topics, financial-connections,
                 #              influence, pac, public-records, reports,
                 #              data-quality, search, subscribe
                 #   Operator:  operator/ (login + dashboards; middleware-gated)
                 #   API:       api/ (see "API Routes" section below)
  components/    # React components, one per file. Notable:
                 #   - OperatorGate (registry: docs/operator-review-queue.yaml)
                 #   - CivicTerm, SourceBadge (design system)
                 #   - CandidateCard, RaceSection, CandidateContributionBuckets
                 #     (elections cascade — graduated 2026-05-22, see I163)
                 #   - ConflictFlagCard (three-tier display)
                 #   - FeedbackButton, FeedbackModal, SubmitTipButton
                 #     (feedback system)
  lib/           # Data, queries, auth, observability, formatting:
                 #   - supabase.ts, types.ts, database.types.ts (generated)
                 #   - queries/ (barrel + 11 domain files; see Data Layer)
                 #   - operator-auth.ts, operator-session.ts, rate-limit.ts
                 #   - logger.ts (structured JSON; see Observability)
                 #   - format.ts, format-agenda-text.ts, geo.ts, provenance.ts
                 #   - Per-domain helpers: electionNarrative.ts,
                 #     contributionBuckets.ts, district-colors.ts,
                 #     topic-label-colors.ts, local-issues.ts, significance.ts,
                 #     thresholds.ts
                 #   - Hooks: useFeedback.ts, useRecentlyVisited.ts
```

When the structure here diverges from reality, the filesystem wins. Add a missing top-level segment here when you ship one; don't enumerate every individual component (the directory listing is the source of truth).

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
- **`lib/queries/`** — All Supabase queries, split by domain in Phase 2.4 (2026-05-11). Current domain files (11): `meetings.ts`, `council.ts`, `elections.ts`, `donors.ts`, `conflicts.ts`, `commissions.ts`, `pacs.ts`, `search.ts`, `topics.ts`, `influence.ts`, `public_records.ts`. (A short-lived comments domain file was created in 2.4 and retired with D60 community_comments — see parking lot.) Barrel `index.ts` re-exports everything for back-compat (`import { getMeetings } from '@/lib/queries'` still works). Shared column-projection constants (`COLS_MEETING_LIST`, etc.) live in `_shared.ts`. The `city_fips` filter is no longer required on new queries (~76 existing queries keep it; see Key Conventions below).
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
- Privacy/retention: client addresses are HMAC-pseudonymized with the existing
  server-only `IRON_SESSION_PASSWORD` and rotate at each UTC day boundary. The
  limiter opportunistically prunes only versioned pseudonymous buckets older
  than 1 day; legacy raw-IP rows require a separately approved cleanup.

## Observability (structured logs)

- **Destructive routes emit structured JSON events** via `@/lib/logger`. The Vercel runtime captures stdout into queryable logs, so JSON lines stay greppable after the fact.
- Pattern: `logEvent('<surface>.<action>[.<outcome>]', { ...requestContext(request), ...fields })`. Severity defaults to `info`; use `warn` for rate-limit / validation rejections, `error` for unexpected failures.
- Never log raw passwords, emails, request IPs, or user agents.
  `requestContext(request)` omits user-agent and emits a daily secret-HMAC
  client pseudonym only when the required server secret is available.
  `emailHash(email)` is also a daily secret-HMAC and returns `omitted` rather
  than falling back to a stable unsalted identifier.
- Currently wired into: `operator/login`, `operator/logout`, `operator/settings`, `operator/send-recap`, `subscribe`. Extending the pattern to new destructive routes (revalidate, feedback, community-comments, etc.) is AI-delegable.
- No paid observability add-on or external alerting sink is assumed.

## API Routes

Grouped by audience and write/read shape. New routes belong here; if you ship one and forget to add it, the structured-log wiring check (when extended) or the public-write rate-limit audit will catch it.

**Public read (cached or live data, no auth):**
- `GET /api/health` — Migration health check, probes tables in parallel. 1hr cache.
- `GET /api/data-freshness` — Per-source freshness status. 1hr cache.
- `GET /api/data-quality` — Aggregated data-quality signals for the public dashboard.
- `GET /api/public-records` — CPRA compliance stats. Graceful fallback for missing migration.
- `GET /api/search` — Hybrid FTS + semantic search (falls back to FTS-only when `OPENAI_API_KEY` is unset on Vercel). Postgres-rate-limited.
- `GET /api/flag-details` — Conflict flag detail payloads for the reports drill-down.
- `GET /api/geocode` — Address → district lookup for "Find my district."

**Public write (rate-limited, no auth):**
- `POST /api/feedback` — User feedback. Postgres-rate-limited via `@/lib/rate-limit` (see "Rate Limiting" above; migration 106 replaced the old Upstash dependency).
- `POST /api/subscribe`, `POST /api/subscribe/preferences` — Email subscribe + preference center. Rate-limited.

**Email delivery (API_SECRET bearer auth):**
- `POST /api/email/retry-deliveries` — Shared 50-row recovery budget for due welcome, orientation, recap, and digest deliveries. Rebuilds persisted content in grouped bounded queries; it does not initiate new broadcasts.
- `POST /api/email/send-orientation` — Pre-meeting agenda previews (idempotent per meeting).
- `POST /api/email/send-recap` — Post-meeting recaps.
- `GET /api/email/send-digest` — Read-only deployed-capability handshake.
- `POST /api/email/send-digest` — Explicit canary or weekly digest mode. The
  current `subscriber-weekly-digest.yml` release uses a typed trusted-main
  repository event and is canary-only; a separate post-canary change adds the
  Monday broadcast schedule and deliberately enables broadcast in code.

**Operator-only (iron-session cookie, see Operator Auth):**
- `POST /api/operator/login`, `POST /api/operator/logout`, `GET /api/operator/session` — Auth lifecycle.
- `GET/POST /api/operator/settings` — Operator preferences.
- `POST /api/operator/send-recap` — Manual recap broadcast (separate from the GH Actions automated route).
- `GET /api/operator/decisions` — Pending decisions queue.
- `GET /api/operator/sync-health` — Pipeline freshness diagnostics.
- `GET /api/operator/meeting-context` — Conflict scanner detail for a meeting page.
- `GET /api/operator/agenda-item-context` — Influence-map detail for an agenda item page.
- `GET /api/operator/council-context` — Unreviewed Form 700 detail for a council profile.

**Cache invalidation (API_SECRET bearer auth):**
- `POST /api/revalidate` — On-demand ISR revalidation (called by pipeline post-sync to refresh changed pages).

## Visual Verification

**After visual changes, prefer `next build` over preview tools.** Supabase statement_timeouts hit hard under concurrent build prerenders so the `preview_*` browser-automation tools end up testing failure paths more than the actual UI; running `npm run build` from `web/` exercises the real ISR/SSR code paths and surfaces routing/data issues fastest. Operator memory (feedback: skip preview) is the source of truth on this.

If you do need pixel-level checks (rare — usually a design-debt audit or a screenshot for review), `docs/design/VISUAL-VERIFICATION.md` documents the `preview_snapshot` / `preview_screenshot` workflow.

## Key Conventions

- **No `any` types.** Every Supabase response is cast to typed interfaces.
- **FIPS filtering: new queries can skip it.** Per the 2026-05-09 single-city pivot (`.claude/rules/conventions.md`), internal queries no longer need `.eq('city_fips', cityFips)` — the DB has one city's data. **Existing queries keep their filter** (~76 across `lib/queries/` as of 2026-05-23, down from ~115 as query rewrites have organically dropped it) until Phase 3 of the rearchitecture plan drops the indexes wholesale; rewriting them all now is churn without benefit. Pattern for new queries: omit the filter, leave the column in the SELECT for provenance.
- **Graceful degradation.** CPRA pages handle missing migration 003. Health endpoint returns degraded (not error) for missing optional tables.
- **Publication tiers in UI.** Reports page shows Tier 1 + Tier 2 flags only. Tier 3 count disclosed in methodology ("Additional matches tracked internally: N").
- **Source credibility displayed.** About page has color-coded tier cards. Richmond Standard always tagged "funded by Chevron Richmond."
