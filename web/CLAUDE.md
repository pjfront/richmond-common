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
    reports/     # Transparency reports + [meetingId] flag detail
  components/    # 25 React components
  lib/           # queries.ts, types.ts, supabase.ts, useFeedback.ts
```

## Design System

**Civic palette** defined in `globals.css` via `@theme inline`:
- `--color-civic-navy: #1e3a5f` / `civic-navy-light: #2d5a8e` — headers, nav, primary
- `--color-civic-slate: #475569` — body text
- `--color-civic-amber: #d97706` / `amber-light: #fbbf24` — accents, CTAs, highlights
- Vote colors: `vote-aye: #059669` (green), `vote-nay: #dc2626` (red), `vote-abstain: #6b7280`, `vote-absent: #9ca3af`
- Typography: Inter font (`--font-sans`), body on `#f8fafc` background

## Data Layer

- **`lib/supabase.ts`** — Supabase client instance
- **`lib/types.ts`** — All TypeScript interfaces matching `src/schema.sql` (18 types + 6 composite types + feedback + freshness + CPRA)
- **`lib/queries.ts`** — All Supabase queries. Every query filters by `city_fips` (constant `RICHMOND_FIPS = '0660620'`). Functions: `getMeetings`, `getMeetingsWithCounts`, `getMeeting`, `getOfficials`, `getOfficialBySlug`, `getOfficialVotingRecord`, `getTopDonors`, `getMeetingStats`, `getConflictFlags`, `getConflictFlagsDetailed`, `getMeetingsWithFlags`, plus CPRA queries.
- **`lib/useFeedback.ts`** — Client-side state machine hook for feedback submission

## Component Patterns

- **Server components by default** (app router). Client components only for interactivity (`"use client"` directive).
- **ISR on all pages:** `export const revalidate = 3600` (1 hour)
- **Layout:** `FeedbackModalProvider` wraps app -> `Nav` -> `main` -> `Footer`
- **Feedback system:** `FeedbackButton` (per-flag accuracy voting), `FeedbackModal` (global tips via React context), `ReportErrorLink` (per-vote errors), `SubmitTipButton` (footer), `SuggestCorrectionLink` (council profiles)
- **Conflict display:** Three-tier confidence system. Tier 1 "Potential Conflicts" + Tier 2 "Financial Connections" shown in reports. Tier 3 suppressed. `ConflictFlagCard` shows amber "X days after vote" badge for temporal correlations.

## API Routes

- `POST /api/feedback` — User feedback with in-memory rate limiting (5/IP/hr, 10/session lifetime)
- `GET /api/health` — Migration health check, probes 18 tables across 5 groups. 5-min cache.
- `GET /api/data-freshness` — Per-source freshness status. 1hr cache.
- `GET /api/public-records` — CPRA compliance stats. Graceful fallback for missing migration.

## Key Conventions

- **No `any` types.** Every Supabase response is cast to typed interfaces.
- **FIPS filtering everywhere.** Even with single-city data, every query uses `.eq('city_fips', cityFips)`.
- **Graceful degradation.** CPRA pages handle missing migration 003. Health endpoint returns degraded (not error) for missing optional tables.
- **Publication tiers in UI.** Reports page shows Tier 1 + Tier 2 flags only. Tier 3 count disclosed in methodology ("Additional matches tracked internally: N").
- **Source credibility displayed.** About page has color-coded tier cards. Richmond Standard always tagged "funded by Chevron Richmond."
