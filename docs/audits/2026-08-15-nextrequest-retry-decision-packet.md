# NextRequest retry-exhaustion decision packet — 2026-08-15

## Decision recorded — retain for manual reconciliation

On August 16, 2026, the operator approved **retain**: when a durable
NextRequest source-change job exhausts its automated attempts, Richmond Commons
keeps the job and its evidence in `dead_letter` for manual reconciliation. It
does not automatically replay or acknowledge/drop the obligation.

No production-data correction, replay, requeue, migration, or deployment was
performed while preparing this packet.

## Read-only incident evidence

The evidence was captured from GitHub Actions and Supabase's enforced
`database/query/read-only` endpoint on August 15, 2026. No credentials or
request contents are included.

- The first directly correlated failure was detector run
  [31841238553](https://github.com/pjfront/richmond-common/actions/runs/31841238553),
  which observed a NextRequest document-fingerprint change and dispatched Data
  Sync run
  [31841329935](https://github.com/pjfront/richmond-common/actions/runs/31841329935).
  That sync fetched 3,032 requests, recorded pagination-change failures and
  HTTP 429s, encountered a Supabase statement timeout, and remained explicitly
  retryable.
- A later five-run retry wave began from detector run
  [31861691162](https://github.com/pjfront/richmond-common/actions/runs/31861691162).
  The retained sync artifacts show another 3,035-row replay per change while
  the same request-level failures remained unresolved.
- The last correlated failed run was
  [31877347120](https://github.com/pjfront/richmond-common/actions/runs/31877347120),
  dispatch generation 5 for change
  `4b618b7d5ce861b7f841bcf063accbec5876c293ba1c0710d2565c94b2119263`.
- Eight NextRequest jobs created in the Aug. 14–15 UTC incident window each
  reached `attempt_count=5` and `status=dead_letter`: 40 charged dispatch
  attempts. Eleven retained detector sync-log rows fetched and updated 33,373
  request rows in aggregate and recorded 263 scrape failures; all eleven were
  `retryable_incomplete`.
- At capture time, all 38 historical NextRequest outbox jobs were
  `dead_letter`, none were `succeeded`, and no source-change job of any source
  remained active. The watcher itself had continued advancing and was healthy.

`data_sync_log` is upserted by change ID, so its eleven retained rows are a
lower-bound artifact summary, not a count of every GitHub attempt. GitHub run
history is authoritative for dispatch attempts.

## Root cause and contained behavior

The durable job was bounded to five claims, but its retry artifact was erased
before reuse. Each retry therefore restarted the broad authoritative listing,
rewrote roughly 3,035 local rows, hit the same volatile document-pagination
boundary, and added load during existing Supabase read timeouts. Generic
1/2/4/8-minute retry delays also all fell inside the detector's 15-minute
cadence. Unsupported `queue: max` workflow keys incorrectly implied an
unbounded GitHub queue; GitHub concurrency actually retains at most one pending
run per group.

The proposed containment keeps the durable obligation while changing future
behavior:

1. New NextRequest events receive three automated attempts.
   Nested in-process retries are disabled for detector events; each durable
   claim can touch its bounded portal scope only once.
   The detector drains only one due retry job per poll, so a backlog cannot
   fan out into another dispatch wave.
2. The first detector attempt uses a fixed 14-day listing window plus existing
   bounded recent-document and oldest-first reconciliation slices. It never
   performs the daily global deletion-proof sweep.
3. Later attempts reuse only the concrete `failed_request_ids` already stored
   in the same sync-log artifact, with a hard 100-request safety bound. They do
   not run a broad listing, global document index, or rotation.
4. NextRequest retry delays become 30 then 60 minutes (exponential, capped at
   six hours); other source behavior remains unchanged.
5. Exhaustion remains terminal for automation and is labeled
   `Manual reconciliation required` while retaining the job and evidence in
   `dead_letter`.

## Approved policy: retain

Keep exhausted work in `dead_letter`, do not auto-replay it, and require an
operator to reconcile the recorded request IDs before any explicit requeue or
acknowledgement.

- Preserves the durable civic-data obligation and audit trail.
- Prevents unattended portal and database load.
- Requires a later, separately reviewed manual-reconciliation procedure.
- This recorded policy is implemented by migration 140 and the containment
  code; it does not decide whether or how the 38 existing rows should be
  reconciled.
- Any action on those existing rows remains a separate production-reviewed
  task. This decision authorizes neither replay nor correction.

## Scope invariants

This containment does not change Supabase Pro, AGPL licensing, D2=$0.50,
DeepSeek-first routing or its two benchmarked Luna exceptions, S26/S28, live
migration 136, or the migration 134 HARD NO-GO.
