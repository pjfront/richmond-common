# Migration Health Check — Implementation Plan

**Date:** 2026-02-22
**Estimated vibe-coding time:** 10–15 min
**Context:** After Phase D, we discovered that Supabase migrations must be run manually but nothing in the system detects when they haven't been. The `/public-records` page silently renders zeros, `/api/data-freshness` returns 500, and data sync hard-fails — all without surfacing the root cause (missing tables).

## Problem

Code deploys via `git push` → Vercel. Database migrations require manual SQL Editor runs in Supabase. This gap means:
- Frontend pages silently degrade to empty/zero states
- API routes return 500s that look like bugs, not missing migrations
- Data sync pipelines fail without explaining why
- The freshness endpoint (`/api/data-freshness`) itself fails if migration 001 hasn't been run

## Solution: Two complementary fixes

### Task 1: `/api/health` endpoint (~5-10 min)

**File:** `web/src/app/api/health/route.ts` (new)

**What it does:**
- Queries `information_schema.tables` (or attempts lightweight SELECTs) against a list of expected tables
- Reports which tables exist and which are missing
- Groups results by migration (001, 002, 003) so you know exactly which SQL script to run
- Returns overall status: `healthy` | `degraded` (some missing) | `unhealthy` (core tables missing)

**Expected tables list:**
```
Migration 001 (cloud pipeline):  scan_runs, data_sync_log
Migration 002 (user feedback):   user_feedback
Migration 003 (NextRequest):     nextrequest_requests, nextrequest_documents
Core schema:                     cities, officials, meetings, agenda_items, motions, votes, contributions, documents, conflict_flags
```

**Response shape:**
```json
{
  "status": "healthy",
  "migrations": {
    "001_cloud_pipeline": { "applied": true, "tables": ["scan_runs", "data_sync_log"] },
    "002_user_feedback": { "applied": true, "tables": ["user_feedback"] },
    "003_nextrequest": { "applied": false, "missing": ["nextrequest_requests", "nextrequest_documents"] }
  },
  "core_schema": { "applied": true, "tables": [...] }
}
```

**Cache:** `s-maxage=300` (5 min) — short enough to detect fixes quickly.

**Pattern:** Follow the existing `data-freshness/route.ts` structure. Use the anon key Supabase client (already initialized in `web/src/lib/supabase.ts`). Query each table with `.select('*').limit(0)` and catch errors — simpler and more reliable than querying `information_schema` through PostgREST.

### Task 2: Staleness monitor schema check (~3-5 min)

**File:** `src/staleness_monitor.py` (modify)

**What it does:**
- Add a `check_schema_health()` function that runs before the freshness check
- Uses the existing `conn` (direct Postgres via `db.get_connection()`) to query `information_schema.tables`
- Reports missing tables in both text and JSON output formats
- When `--check` flag is used, exit code 1 if any tables are missing (same as stale sources)

**Expected tables:** Same list as Task 1.

**Integration point:** The existing `--alert-only` and `--check` flags should include schema health. Text output prepends a "Schema Health" section before "Data Freshness."

### Task 3: Commit and verify

- Run test suite
- Commit: `Phase 2: add migration health check endpoint and schema verification`
- Verify `/api/health` works locally with `npm run dev`

## Why not Option 1 (plan template checklist)?

Options 2+3 make Option 1 redundant. If the system detects missing migrations automatically, there's no need to tax human attention with a checklist item. Aligns with the AI-native principle: "treat human attention as a scarce resource."

## Future extensions (not in scope now)

- Frontend banner component that calls `/api/health` and shows warnings to admin
- Vercel deploy hook that hits `/api/health` post-deploy and alerts via Slack/n8n
- n8n pre-pipeline check that verifies schema health before running data sync
