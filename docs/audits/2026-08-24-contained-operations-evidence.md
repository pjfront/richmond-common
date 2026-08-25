# Contained-operations evidence — 2026-08-24

This dated, read-only checkpoint supports the short operator manual. It is not
a live dashboard, a production approval, or permission to replay/correct data,
apply a migration, increase cost, deploy, or publish a firewall draft.

## Repository and deployment controls

- `origin/main` after PR #131 is `7db7a4b5fdc97e266c925b0166ecd5625c5d43ec`.
- PR #116 changed Vercel Git deployment control from a main-only deny to the
  documented global `deploymentEnabled: false` setting. Its independent
  exact-head review and all three required GitHub checks passed before merge.
- A disposable Git branch pointing to that exact main SHA produced zero Vercel
  deployments in two read-only observations. The branch was then deleted; the
  commit remains on `main`.
- The trusted `Supabase Preview Expiry` controller was dispatched from that
  exact main SHA after merge. Run `32705565208` completed green and reported
  `cleaned=0`, confirming the real credentials/controller path without creating
  or deleting a Preview branch.
- The public site still points to the previously verified READY production
  deployment at source SHA `0ff9fd50443d8d13e15a4d83845b2997cfc1054a`
  (PR #100). A merge is not evidence that a website change is live.
- PR #126 merged the six owner-only manual-workflow containment changes after
  exact-head Linux CI (3,220 passed, 64 skipped) and independent review. No
  typed event was dispatched as part of that merge.
- PR #128 merged the bounded local Form 497 OCR fallback after exact-head CI
  and independent review. It has not been run against production and no filing
  row was corrected.
- PR #130 merged a bounded 30-minute timeout for the daily Archive Center job
  after the prior run completed its useful work just before the old 20-minute
  job ceiling. It did not replay the failed run and has not been explicitly
  production-deployed; the next natural schedule is the verification path.
- PR #131 merged a bounded orientation-preview generator that considers only
  non-cancelled, upcoming regular Richmond City Council agendas within 14 days,
  caps source input, and keeps DeepSeek V4 Pro as its only model route. It did
  not generate previews, change production data, or explicitly deploy the
  application.
- A recurring NextRequest detector/retry loop was confirmed after the source
  repeatedly produced the same failing incremental work. Focused containment
  is implemented, tested, and committed locally: the scheduled watcher becomes
  observation-only, fallback/detail work is capped, HTTP 429 stops later work,
  and migration 145 excludes NextRequest from unscoped outbox leases while
  preserving exact-ID claims. Focused draft PR #132 records the tested commit,
  but neither that code nor migration 145 is merged or live at this checkpoint.
  No sync was replayed, cancelled, or corrected as part of the containment
  work.

## Operator notification channel

- The Richmond-owned alert workflow is active and its latest observed run was
  green.
- The repository did not have a `HEALTHCHECKS_PING_URL` Actions secret at the
  checkpoint, so the external dead-man's switch was not armed. Raw GitHub
  Actions failure mail must remain enabled until the documented channel test
  passes.
- Open alert issue #93 records the bounded July three-meeting recap gap. It is
  not a current site outage and does not authorize production-data correction.
- The issue's copy-ready handoff has now been completed read-only. The official
  Richmond eSCRIBE calendar and meeting pages confirm regular City Council
  meetings on July 7, July 21, and July 28, and each meeting exposes an official
  standalone video player. The current recap path still lacks a proven bounded
  way to turn those eSCRIBE/ISI recordings into source-grounded transcript
  recaps without a replay or a new transcription path. Do not renew the expired
  broad suppression and do not replay these meetings under S29. After its
  one-time monitor-only refresh, the exact reviewed July cohort appears only in
  weekly/monthly status and has no action-reminder cadence while unchanged. The
  issue closes automatically when the rolling liveness check passes. A newly
  failing later meeting or malformed monitor state becomes actionable
  immediately; bounded reminder milestones apply again only after that alert.

## Email and DNS

- Aggregate subscription telemetry reported two active subscriptions and one
  inactive subscription. One active row is an initial activation and the other
  is a reactivation; a reactivation counts as a new subscription cycle.
- The originally approved canary plus-address appeared in a tracked runbook.
  The current-tree reference is being removed, but Git history is durable; use
  a fresh private plus-address in Vercel before the canary deployment.
- DMARC was publicly observed at `p=none`. The private `hello` forwarding target
  could not be rechecked without the operator's Cloudflare sign-in.

## Vercel Firewall

The read-only, pinned Vercel CLI `firewall diff` command was repeated after PR
#128 and still showed exactly two unpublished changes:

1. Add `S29 Amazonbot production observation`.
2. Modify `S29 Amazonbot item containment` from production Log to Preview Deny.

The draft remains mutable. The operator must rerun the read-only diff and verify
those exact changes before using the operator-only publish command.

## Capacity and spend

The prior authenticated provider snapshot recorded:

- Vercel Hobby: 5.1/100 GB transfer, 3.54/10 GB origin transfer, 265K/1M
  requests, 143K/1M ISR reads, 102K/200K ISR writes, 129K/1M function calls,
  201.3/360 GB-hours memory, 4h04 build CPU, and 3,501/50,000 analytics events.
- Vercel rolling Active CPU was the exception at about 5h13m against the Hobby
  four-hour allowance; recent observed days were still above the runbook's
  four-minutes/day start-safe gate. No Vercel Pro upgrade was justified.
- A bounded production log query found no error-level entries and no HTTP 500s
  in the prior 24 hours. This is an application-health check, not a billing
  total.
- Vercel listed 89 Preview deployments that failed closed from August 7 through
  the checkpoint across 38 branches. Their build phases totaled about 476.9
  seconds. A sampled run proved that deployment stopped at the intentional
  `assert-preview-env.mjs` gate because no approved isolated Supabase Preview
  URL/key/ref was present. That sampled red row demonstrates fail-closed
  containment rather than a production failure; the audit did not individually
  attribute all 89 rows.
- Authenticated `vercel metrics` queries returned `payment_required` for
  Observability Plus. That limitation does not justify Vercel Pro or the paid
  add-on; the monthly dashboard check remains the supported low-cost path.
- Supabase Pro: about 1.08/8 GB database size and 8.6/250 GB organization
  egress. No Preview branch was active. Historical Preview compute in the
  current billing period was about 261 hours / $3.51.
- The unattended application LLM cap was $5/month. That database-backed figure
  does not include Vercel or Supabase plan usage.

Provider usage windows and values change. These figures establish why the
current architecture/cost decision was made; they must not be copied forward as
a current monthly check.

## Standing boundaries

Supabase Pro; DeepSeek-first with only the two benchmarked Luna exceptions;
AGPL-3.0; D2=0.50; migration 136 live; migration 134 HARD NO-GO; no broad
S26/S28 expansion, unbounded sync, or production-data correction/replay.
