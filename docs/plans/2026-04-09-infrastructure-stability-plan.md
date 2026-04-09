# Strategic Infrastructure Plan: Stability & Automation

## Context

The platform has solid foundations: idempotent pipelines, 15-min change detection, triple-trigger workflows, multi-tier monitoring (staleness, completeness, journal, self-assessment, data quality), a decision queue for human gating, and runtime operator config. The question is: what are the highest-leverage investments to make the system more stable and more hands-off?

After auditing the full pipeline (`data_sync.py`, `change_detector.py`, `pipeline_journal.py`, `data_quality_checks.py`, `staleness_monitor.py`, `completeness_monitor.py`, `self_assessment.py`, `cloud_pipeline.py`, `operator_config.py`, `decision_queue.py`, all GitHub Actions workflows), three strategic themes emerge.

---

## Theme A: Pipeline Resilience — Make It Harder to Break

### A1. Circuit Breaker Pattern
**Problem:** When an external API (NetFile, eSCRIBE, Socrata) is down, every scheduled job retries 3x with exponential backoff (210s total), then fails. During multi-day outages, this burns CI minutes and generates noise without preventing downstream effects.

**Solution:** Track consecutive failures per source in `source_watch_state` (or new table). After N consecutive failures within a time window, skip retries entirely ("open circuit"). Auto-reset after cooldown period. Decision queue entry on circuit open.

**Files:** `src/data_sync.py` (retry loop ~lines 1660-1700), migration for circuit state

### A2. Pre-Enrichment Data Validation Gate
**Problem:** This is the scariest failure mode. If NetFile API returns 0 records (500 error, silent failure), sync logs "completed" with 0 records. The enrichment sweep then runs conflict scanning on empty contributions — all conflict flags vanish. Published silently.

**Solution:** Before running enrichments (`--enrich` or `--enrich-only`), check that upstream source syncs either (a) loaded >0 records, or (b) explicitly confirmed "source is genuinely empty." Block enrichment if any critical source has a suspicious zero-count sync.

**Files:** `src/data_sync.py` (enrichment logic), potentially `src/pipeline_journal.py` for sync result tracking

### A3. Structured Error Classification
**Problem:** `data_sync_log.error_message` is unstructured exception text. Operator can't distinguish "API temporarily down" from "config broken" from "data corrupt" from "timeout." Auto-escalation is impossible without classification.

**Solution:** Add `error_category` enum (`api_transient`, `api_permanent`, `config_error`, `data_validation`, `timeout`, `auth_failure`) to sync log entries. Classify in exception handlers. Decision queue auto-escalation rules keyed on category + consecutive count.

**Files:** `src/data_sync.py` (exception handling), migration for `error_category` column

### A4. Sync Heartbeat for Hung Detection
**Problem:** Long-running syncs (CAL-ACCESS 3hrs, minutes extraction 6hrs) have no heartbeat. If a sync hangs (playwright timeout, DB lock, network stall), the log entry never completes. Operator has no visibility into "sync running for >6 hours."

**Solution:** Lightweight heartbeat — update `data_sync_log.updated_at` every 5 minutes during long syncs. Staleness monitor checks for stale heartbeats. Alert if sync started >2x expected duration with no recent heartbeat.

**Files:** `src/data_sync.py` (background heartbeat thread), `src/staleness_monitor.py` (heartbeat staleness check)

---

## Theme B: Observability — Know When It's Breaking

### B1. Post-Sync ISR Revalidation
**Problem:** Data syncs update the database, but frontend pages serve stale ISR cache (1hr TTL). If revalidation fails silently, pages can be stale indefinitely.

**Solution:** After successful data sync, call the ISR revalidation API for affected paths (already planned as S24.12). Use `pipeline_map.py` to trace sync → tables → queries → pages for surgical revalidation.

**Files:** `.github/workflows/data-sync.yml` (post-sync step), `web/src/app/api/revalidate/` route, `src/pipeline_map.py` (trace logic already exists)

**Note:** Already on roadmap as S24.12. Calling it out here because it's a high-leverage stability win.

### B2. RPC Health Probes
**Problem:** Frontend uses Supabase RPCs (`get_meeting_counts`, `find_similar_items`, `search_site`). If an RPC regresses (wrong return type, missing function after migration), the health check doesn't catch it — users discover it first.

**Solution:** Add lightweight RPC probes to `/api/health` — call each RPC with known-good minimal input, verify non-error response. Already tracked as I117/S24.11.

**Files:** `web/src/app/api/health/route.ts`

### B3. Monthly Trend Assessment
**Problem:** `self_assessment.py` runs with `--days 1` daily and `--days 7` weekly. Slow degradation (extraction quality declining, record counts drifting) over weeks/months is invisible.

**Solution:** Add `--days 30` monthly assessment to the quarterly schedule. Optional: lightweight trend detection (is this month's average worse than last month's?).

**Files:** `.github/workflows/data-sync.yml` (add monthly cron step), `src/self_assessment.py` (minor)

### B4. Sync Results Dashboard Data
**Problem:** Sync results (records fetched, new, updated) are logged to stdout in GitHub Actions but not persisted structurally. Operator can't see "NetFile synced 0 records for the 3rd time this week" without reading CI logs.

**Solution:** Persist sync result counts in `data_sync_log` (some of this exists but inconsistently). Surface in operator sync-health dashboard alongside staleness data.

**Files:** `src/data_sync.py` (ensure all sync functions write result counts to log), `web/src/app/operator/sync-health/` (display)

---

## Theme C: Automation Expansion — Make It More Hands-Off

### C1. Auto-Escalation Rules in Decision Queue
**Problem:** Decision queue entries are created but require manual operator discovery. Persistent failures (same source failing 3+ times) and cascading issues (stale → quality regression → user impact) aren't auto-escalated.

**Solution:** Add severity auto-promotion rules: if a `low` decision isn't resolved within 7 days, promote to `medium`. If the same `dedup_key` fires 3+ times, promote to `high`. If a `critical` decision isn't resolved in 24h, add to a "needs attention" flag visible on the frontend operator bar.

**Files:** `src/decision_queue.py` (escalation logic), potentially a lightweight cron job or post-sync hook

### C2. Change Detector Dispatch Retry
**Problem:** If `trigger_dispatch()` fails (GitHub API timeout, auth error), the change is detected but the sync never fires. No retry. Next check will see the same fingerprint and skip.

**Solution:** On dispatch failure, persist a "pending dispatch" in `source_watch_state`. Next change_detector run checks for pending dispatches and retries. After 3 failed dispatches, create decision queue entry.

**Files:** `src/change_detector.py` (dispatch logic + retry state)

### C3. Migration Validation in CI
**Problem:** Schema migrations aren't validated in CI. A breaking migration could reach production without early warning. Test suite uses fixtures, not live schema.

**Solution:** Add `supabase db push --dry-run` to the PR CI workflow. Catches syntax errors, constraint violations, and missing dependencies before merge.

**Files:** `.github/workflows/ci.yml` (add migration validation step)

### C4. Pipeline Cost Tracking
**Problem:** Claude API costs per pipeline run aren't tracked systematically. As extraction volume grows (more cities, more meetings), cost surprises are possible.

**Solution:** Track token usage per pipeline step in `pipeline_journal`. Monthly cost summary in self-assessment. Alert if monthly cost exceeds threshold (operator-configurable).

**Files:** `src/cloud_pipeline.py` and `src/batch_extract.py` (token counting), `src/pipeline_journal.py` (cost entry type), `src/self_assessment.py` (cost summary)

---

## Priority Ranking

| # | Item | Impact | Effort | Why This Order |
|---|------|--------|--------|----------------|
| 1 | **A2** Pre-enrichment validation | Critical | Small | Prevents the worst failure mode (data silently disappearing) |
| 2 | **A1** Circuit breaker | High | Medium | Stops retry storms, enables auto-skip of broken sources |
| 3 | **A3** Error classification | High | Medium | Foundation for all auto-escalation logic |
| 4 | **B1** Post-sync ISR revalidation | High | Medium | Already planned (S24.12), closes the data-stale-in-UI gap |
| 5 | **C1** Auto-escalation rules | High | Small | Multiplier on existing decision queue — makes monitoring proactive |
| 6 | **C2** Dispatch retry | Medium | Small | Closes a real gap in the change detection loop |
| 7 | **A4** Sync heartbeat | Medium | Medium | Important for CAL-ACCESS/extraction but less frequent |
| 8 | **B2** RPC health probes | Medium | Small | Already planned (S24.11), quick win |
| 9 | **C3** Migration CI | Medium | Small | Safety net, low effort |
| 10 | **B3** Monthly trend assessment | Medium | Tiny | 30-min add to existing cron |
| 11 | **B4** Sync results dashboard | Low | Medium | Nice-to-have, most data exists in logs |
| 12 | **C4** Cost tracking | Low | Medium | Insurance policy, not urgent at current scale |

## Recommended Implementation Approach

**Batch 1 (immediate, 1 session):** A2 + C2 + B3 — the most critical safety gate, the dispatch reliability fix, and the trivial cron add. These are independent and can be done in parallel.

**Batch 2 (next session):** A1 + A3 — circuit breaker + error classification. These build on each other (circuit breaker uses error classification to decide when to open).

**Batch 3 (following session):** C1 + B2 + C3 — auto-escalation, RPC probes, migration CI. All independent, all quick wins.

**Batch 4 (when S24.12 is active):** B1 — post-sync ISR revalidation. Already scoped.

**Batch 5 (as needed):** A4 + B4 + C4 — heartbeat, dashboard, cost tracking. Lower urgency.

## Verification

- **A1/A2/A3:** Unit tests simulating API failures, zero-count syncs, classified errors
- **B1:** Trigger sync, verify ISR revalidation fires for affected pages
- **B2:** Break an RPC (e.g., drop function), verify health check catches it
- **C1:** Create a low-severity decision, wait for auto-promotion (or simulate with timestamp manipulation)
- **C2:** Mock GitHub API failure in change_detector, verify pending dispatch persisted and retried
- **C3:** Introduce a syntax error in a migration, verify CI fails
- **All:** Existing test suite (`pytest tests/`) passes after each change
