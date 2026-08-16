# S29 baseline and production release runbook

**Prepared:** 2026-08-16

**Status:** Draft release sequence. This document authorizes no merge, deploy,
billing action, preview bootstrap, migration, email send, or production-data
change.

**Measurement:** 14 complete UTC days with the existing public experience,
followed by 14 complete UTC days with only the visible S29 treatment changed.
Analytics, subscription capture, email delivery, privacy, search, operator
session, and rate-limit behavior must be identical in both windows.

## Fixed starting state

- `richmondcommons.org` is intentionally pinned to PR 83 / `3be0709`.
- Current `main` is `c27c594d57e86c815074cc0cf57570606bceccaa`.
  It includes PR 92 / migration 139 and PR 94's preview-aware schema-drift
  gate. Moving production from the pin releases the full reviewed delta, not
  just PR 90.
- Supabase remains **Pro**. Migration 136 is live. Migration 138 is preserved
  on `main` and remains separately approval-gated.
- Migration 134 is byte-locked and a **HARD NO-GO**. Never apply or rewrite it.
- PR 92 owns migration **139** and is in `main`.
- PR 91's exact containment commit
  `325819f9a1f3c9768ff381bbfdc26829bc4dc473` owns migration **140** and is
  incorporated into draft PR 90. A separate PR 91 preview is intentionally
  not required.
- This baseline batch owns migration **141** for private subscription
  activations and email delivery. Both mirrors must remain byte-identical.
- Production model routing remains **DeepSeek-first**. Luna remains limited to
  the two benchmarked exceptions: failed negated-motion vote explainers and
  image-only Form 460 summary recovery.
- The public flag/count threshold remains **D2 = 0.50** and the repository
  remains **AGPL-3.0**.
- Vercel Web Analytics is dashboard-enabled, but pinned production does not
  render Analytics. No valid instrumented pre-treatment baseline exists.

## Exact baseline/treatment split

### Baseline batch: live before `A0`, then frozen

PR 90 contains the non-visible behavior needed in both windows:

- pageview-only Vercel Analytics, without custom events or persistent IDs;
- query/fragment stripping, private-path exclusion, sensitive-referrer
  suppression, and fail-closed operator-session gating;
- no search-query or stable search-client persistence;
- daily secret-HMAC operational log identifiers, with raw request IP,
  user-agent, and stable unsalted email hashes removed from existing log calls;
- daily HMAC rate-limit keys and bounded cleanup of only expired, versioned
  pseudonymous buckets;
- migration 141's private `subscription_activations` and
  `email_deliveries` ledgers and service-role-only RPCs;
- automated pruning of per-cycle activation rows after 90 days through the
  scheduled bounded recovery path;
- one identical unauthenticated success status/body for active duplicates,
  races, initial subscriptions, and reactivations;
- management-token rotation on reactivation, so old-cycle links stop
  authorizing;
- atomic activation capture, atomic preference replacement, and topic-filtered
  digest delivery;
- per-recipient welcome, orientation, recap, and digest idempotency;
- at most three delivery attempts within 23 hours, a 500-recipient broadcast
  cap, concurrency 10, and a shared 50-row recovery budget; and
- accurate public privacy disclosure and operator runbook/manifest copy.

Delivery disposition remains in structured logs and operator-only views; the
public subscribe response does not reveal it.

The baseline batch does **not** include a redesigned homepage, public
navigation/footer changes, new meeting/election subscription placements,
public SEO treatment, or public Richmond 101.

### Treatment batch: deploy only after baseline close

The treatment may contain only reviewed visible S29 changes extracted from
PR 88:

- homepage/front-door treatment;
- public navigation and footer treatment;
- public meeting/election acquisition placements and their coarse labels;
- public SEO treatment; and
- Richmond 101 only after separate public publication approval.

It must not change migration 141, activation semantics, delivery/retry
behavior, preference filtering, search persistence, logging, rate limiting,
operator-session suppression, analytics, privacy disclosure, or measurement
definitions.

## Privacy and reporting boundary

Analytics records automatic pageviews only. It:

- rejects custom events;
- strips destination query strings and fragments in the browser;
- excludes `/operator` and `/subscribe/manage`, including descendants;
- remains unmounted unless the session probe succeeds and proves a public
  session;
- drops a pageview when the browser-visible referrer is a private management
  route or contains a token/secret parameter;
- uses `Referrer-Policy: no-referrer` on management responses/pages; and
- creates no analytics cookie, local-storage value, fingerprint, custom
  visitor ID, or person-level join.

The browser also rejects every destination hostname except exact HTTPS
`richmondcommons.org` and `www.richmondcommons.org`. This is required because
Vercel's public aggregate API cannot filter or group by request hostname; the
intake allowlist keeps project-level API results from including the Vercel
alias, previews, or lookalike hosts.

The operator accepts bounded Vercel referrer intake: an external source may
send Vercel its full referring-page URL, and `beforeSend` cannot transform
that separate field. Disclosure must say this accurately. Analysis and
closeout use only aggregate referrer hostnames/`missing_or_direct` traffic. Do
not export, retain, quote, or republish referring paths or full referring URLs.
Named referrer hostnames require at least five visitor-days in the selected
window. This is a small-cell reduction rule, not person-level k-anonymity.
Lower-frequency names, IP literals, single-label hosts, and
special-use/private hostnames are combined into a suppressed tail without
their names. A missing referrer is reported as `missing_or_direct`, not
`Direct`, because client-side soft navigations also omit referrers.

Vercel's anonymous visitor hash resets daily. “Visitors” therefore means
**daily-reset visitors**, unique only within one day. The 14-day sum is
**visitor-days**, not unique or returning residents. One resident visiting on
five days may count five times. Never label these figures returning residents,
repeat residents, cross-day retention, or 14-day unique people.

Subscription measurement comes from private
`subscription_activations.activation_at`, split by `activation_kind` and
`acquisition_surface`. Already-active duplicates do not create activations.
Initial subscriptions and reactivations are both activations but must be
reported separately. The ledger contains a subscriber foreign key and coarse
facts, not duplicated email/name/token, raw URL, or referrer.

Migration 141 does not backfill legacy subscribers. Record migration and
application cutovers. Activations made by old code between cutovers are **not
measured**; never reconstruct them or report them as zero.

Per-cycle activation rows are retained for 90 days, then the scheduled bounded
recovery path calls a service-role-only pruning RPC. It fails closed if
retention cannot be enforced. The existing schema has no clean aggregate-only
destination, so PR 90 retains no activation data beyond 90 days. Preserving
daily/acquisition-surface aggregates beyond that would require a separate
aggregate table and migration judgment; none is added here. This policy never
deletes or rewrites legacy subscriber rows.

This design uses ordinary runtime logs and does not require or assume Vercel
Observability Plus, a log drain, or another paid observability add-on.

## Window definitions

Use complete UTC days:

1. Record completed baseline deployment, exact commit, migration-141
   verification, Analytics verification, effective Vercel plan, current
   billing-cycle boundaries, and current plan usage as `A0`.
2. Baseline day 1 starts at the first `00:00:00Z` after `A0`; observe 14
   complete UTC days.
3. Freeze the baseline packet before changing public treatment.
4. Record completed visible-treatment deployment and commit as `T0`.
5. Treatment day 1 starts at the first `00:00:00Z` after `T0`; observe 14
   complete UTC days.

Do not start until a network check confirms one sanitized public pageview and
none on operator/manage pages. Record analytics pauses, email-delivery outages,
site outages, media links, or releases. Defer changes affecting capture,
delivery, privacy, navigation, subscriptions, or rendering; otherwise restart
the affected window after stabilization.

This is sequential observation, not a randomized causal experiment. Election
interest naturally changes between the two windows, SEO indexing may lag past
the 14-day treatment window, and the treatment bundles the front door,
navigation, placements, SEO, and any separately approved Richmond 101 release.
Report raw counts and descriptive changes only; do not attribute lift to one
component or causally separate the treatment from calendar effects.

## Results packet

Select **Production** and the same exact two-host scope used at intake:
`richmondcommons.org` plus `www.richmondcommons.org`. Save exact UTC
boundaries. Do not use an apex-only dashboard filter, which could omit a
pre-redirect `www` pageview and make bounce/collection fields disagree with
the API packet. If the dashboard cannot select both hosts together, use the
unfiltered Production view only after verifying that intake contains no other
hostname; otherwise record the two hosts separately without averaging their
bounce rates.

| Field | Baseline 14 days | Treatment 14 days | Reporting rule |
|---|---:|---:|---|
| Total public pageviews | - | - | Sanitized paths only |
| Homepage views | - | - | `/` |
| November election views | - | - | Record exact route |
| Meeting-index views | - | - | `/meetings` |
| Council-index views | - | - | `/council` |
| District-finder views | - | - | `/elections/find-my-district` |
| Daily-reset visitors | - | - | Daily only |
| Visitor-days | - | - | Not unique people |
| Bounce rate | - | - | Vercel definition |
| Initial subscriptions | - | - | Private activation ledger |
| Reactivations | - | - | Separate from initial |
| Total activations | - | - | Initial + reactivations |
| Activations by coarse surface | - | - | Allow-listed values only |
| Welcome/orientation delivery health | - | - | Same definitions both windows |
| Top referrer hostnames | - | - | Hostnames/`missing_or_direct`; no path export |
| Analytics collection status | - | - | Confirm no pause |

Every conversion ratio includes its raw numerator and denominator. Fewer than
50 November-route treatment pageviews is `insufficient exposure`, not success
or rejection.

## Vercel Hobby decision and checkpoint contract

The operator confirmed that Richmond Commons is presently volunteer-run: no
one is paid to build or operate it; it sells or advertises no product or
service; and it has no paid sponsorship or affiliate offering. On those facts,
the November test remains on **Vercel Hobby**. The donation-only Ko-fi link does
not by itself make the project commercial under Vercel's published
[fair-use guidance](https://vercel.com/docs/limits/fair-use-guidelines). If any
of those facts changes, stop and obtain a new plan/hosting judgment before the
next production release. This runbook does not make that future legal or
billing decision.

Hobby currently includes 50,000 Web Analytics events per month and a one-month
reporting window. The dashboard is therefore not the durable system of record
for this 28-day test. Use Vercel's aggregate count/aggregate views or dashboard
only; never export event-level rows, referring paths, or full referring URLs.
Filled packets may be saved only under the gitignored
`src/data/analytics_checkpoints/` directory and never committed. A later
public summary requires separate review and contains only approved aggregates.

`src/s29_vercel_analytics.py` is a compact, one-checkpoint-at-a-time collector;
it is not a scheduled monitor. The exact contract is
`docs/s29-measurement.json`. Its committed `measurement_status` is `pending`,
so merging it makes no Vercel call. At `A0`, change it to `active`, set the
baseline `start_utc` to baseline day 1's exact midnight, and record the
verified 40-character production SHA. Set the treatment start/SHA only after
the full joined baseline freeze and treatment approval. After the joined T14
freeze, change the status to `complete`; the collector refuses capture unless
the status is `active`. Richmond 101 remains absent from the exact route
allowlist unless its route receives separate publication and measurement
approval.

The collector calls only `visits/count` and `visits/aggregate`, with aggregate
groups `day`, the five-route allow-listed `requestPath`, and the top ten
`referrerHostname` rows. Every request includes `teamId`, `projectId`, an
explicit production filter, and date-only inclusive-last-day boundaries. The
collector asserts the API's normalized half-open UTC response window and
cross-checks count totals against daily aggregates. It accepts omitted
`groupBy` metadata only for an empty aggregate response. It never writes raw
API responses, event rows, query strings, referrer paths, full referrer URLs,
tokens, or project/team identifiers.

Capture these bounded checkpoints:

| Checkpoint | When | Required capture |
|---|---|---|
| `A0` | Baseline deploy verified | Plan and billing-cycle boundaries; Analytics events used; each hard-usage quota percentage; exact UTC/query filters |
| `B7` | After 7 complete baseline days | Aggregate packet; collection status; account-wide plan usage and projections |
| `B14` | After 14 complete baseline days, before treatment | Final baseline packet; collection status; account-wide plan usage and projections |
| `T7` | After 7 complete treatment days | Aggregate packet; collection status; account-wide plan usage and projections |
| `T14` | After 14 complete treatment days | Final treatment packet; collection status; account-wide plan usage and projections |

Every aggregate packet records its capture timestamp, exact UTC start/end,
production deployment SHA, and the allow-listed Vercel result fields above.
It does not attempt to infer quota consumption. Hobby Web Analytics usage is
shared account-wide across projects and follows the account billing cycle, so
the Vercel Usage dashboard remains the authoritative quota and collection
source. Record its actual usage, billing boundaries, collection status, and
Vercel projection at `A0` and every checkpoint; check it daily during both
windows.

| Resource | Warning threshold | Action threshold |
|---|---|---|
| Account-wide Web Analytics events in one billing cycle (dashboard; authoritative) | Actual or projected use reaches 40,000 (80% of the current Hobby allowance) | Actual use reaches 45,000, projected use reaches 50,000 before reset, or the dashboard cannot be checked promptly |
| Any other Hobby hard-usage quota shown by Vercel | Actual use reaches 70%, or projected use reaches 80% | Actual use reaches 80%, or projected use reaches 100% before reset |
| Analytics collection or aggregate reporting | Any unexplained gap or failed checkpoint | Collection pauses, or `B14`/`T14` cannot be frozen with the defined aggregates |

At a warning threshold, capture a checkpoint, diagnose the source, and check
usage daily. At an action threshold, do not start the next window or continue
the current window unattended. The operator chooses among a paid-plan billing
action, a valid restart after a bounded architecture fix, or closing the test
as incomplete. Do not introduce sampling, custom events, new route filters, or
another analytics provider mid-window: each changes the measurement contract
and requires a fresh window.

Ordinary Pro is not an analytics-architecture prerequisite here. It would add
retention and usage headroom, but it would not change daily visitor semantics
or the privacy boundary. Keep custom events off; do not buy Web Analytics Plus,
Observability Plus, or a drain for this test. Revisit Pro only if a threshold
above is reached, longer raw dashboard retention becomes necessary, or the
project's commercial-use facts change. Current Vercel plan limits remain an
external dependency and must be rechecked against the official
[Web Analytics limits](https://vercel.com/docs/analytics/limits-and-pricing)
and [Hobby plan limits](https://vercel.com/docs/plans/hobby) at `A0`.

### Capture and private delivery

Checkpoint reminders are created separately at `A0` and `T0`; this repository
adds no schedule, rolling proxy, heartbeat state, receipt, or automatic retry.
For a local capture, load the existing `VERCEL_TOKEN`, `VERCEL_PROJECT_ID`, and
`VERCEL_ORG_ID`, then run:

```text
python src/s29_vercel_analytics.py --checkpoint B7
```

Replace `B7` with the due checkpoint. The CLI refuses an early, pending,
complete, unconfigured, expanded, or out-of-directory capture and writes only
to `src/data/analytics_checkpoints/s29-<checkpoint>.json`.

The manual-only **S29 analytics checkpoint** Actions workflow is the bounded
one-button equivalent. Choose `main` and exactly one of `B7`, `B14`, `T7`, or
`T14`. It reuses the existing project-scoped `VERCEL_TOKEN`,
`VERCEL_PROJECT_ID`, `VERCEL_ORG_ID`, `RESEND_API_KEY`, and `OPERATOR_EMAIL`;
no new repository setting is required. It creates no artifact or branch state,
does not print the packet, and sends the canonical JSON once as a Base64 Resend
attachment. Resend and the mailbox provider process and may retain that packet.
The separately approved `pjfront+canary@gmail.com` remains reserved for
subscription-delivery verification and is not the analytics recipient.

There is deliberately no delivery deduplication or automatic retry. After a
run, inspect the Resend log, verify the operator inbox received the message,
and open the expected attachment. If the run becomes ambiguous, do those checks
before pressing Run workflow again; a retry may send a duplicate. API success
does not prove collection stayed enabled, and Resend acceptance does not prove
mailbox delivery.

The attachment is only the Vercel aggregate portion. Before freezing `B14` or
`T14`, join it with the private Supabase activation/delivery aggregates and
manual dashboard fields, including two-host bounce rate, account-wide usage,
billing-cycle boundaries, other hard limits, and collection continuity.
Treatment remains blocked on that complete baseline packet and explicit
approval, not merely a successful workflow. After the joined `T14` packet is
verified, preserve both phase dates/SHAs and change `measurement_status` from
`active` to `complete`.

Reviewing token expiry/scope and optionally rotating to a shorter-lived
project-scoped token or sending-only Resend key after `T14` is a
least-privilege follow-up, not an `A0` blocker.

## Dependency and release ordering

Every mutation requires approval for the exact artifact.

### 1. Validate the combined repository candidate; no production action

- [x] Land **Make schema drift preview-aware** through PR 94.
- [x] Land PR 92 / migration 139 on `main`.
- [x] Rebase draft PR 90 onto `c27c594` and incorporate PR 91's exact single
      containment commit as migration 140.
- [x] Order the Supabase mirrors as `20260815013900`, `20260816014000`, then
      `20260816014100`, while preserving source migration number 141.
- [ ] Confirm fresh CI for the combined 138 -> 139 -> 140 -> 141 candidate.
- [ ] Keep PR 90 draft and unmergeable until its one clean-room preview and
      generated-type gates are complete.

### 2. Generate DB types only from clean-room preview

- [ ] After fresh combined-candidate CI, obtain separate approval for the one
      explicit Supabase-preview bootstrap allowed for this release candidate.
- [ ] Build one clean-room preview from the trusted baseline through migrations
      138, 139, 140, and 141. Do not create a separate PR 91 preview. Never
      generate types from production.
- [ ] Generate and commit `web/src/lib/database.types.ts` exactly from that
      preview; pass schema-drift/type checks.
- [ ] On failure, stop. Never hand-edit generated DB types or use production
      credentials.
- [ ] This task performs none of these billable preview actions.

### 3. Approve and merge complete baseline artifact

- [ ] Confirm PR 90 has all baseline mechanics and no named treatment.
- [ ] Confirm CI, mirror hashes, manifest, type drift, focused tests, lint, and
      production build are green.
- [ ] Merge in a maintenance window before the `17 */4 * * *` recovery
      schedule; a call against the old app can only fail and is not cutover.
- [ ] Reconfirm full PR83-to-target production delta.

### 4. Production preflight and migrations

- [ ] Confirm the noncommercial facts above are still unchanged and record the
      effective Vercel plan, billing-cycle boundaries, Analytics events used,
      and every displayed hard-usage quota percentage.
- [ ] Verify that the aggregate dashboard/API can reproduce every Vercel-side
      result field without event-level or full-referrer export. Prepare the
      operator-only checkpoint packet and confirm usage is below the warning
      thresholds.
- [ ] Verify migration 136 live and migration 134 absent.
- [ ] Approve/apply/verify forward migrations in order: 138, PR 92's 139,
      incorporated PR 91 migration 140, then PR 90 migration 141.
- [ ] Verify 141 mirror hash, private tables, RLS/grants, trigger, and RPCs.
      Confirm the 90-day pruning RPC is service-role-only and invoked by the
      scheduled recovery route. Do not backfill or correct data.
- [ ] Do not run NextRequest catch-up, eSCRIBE replay/full sync, contribution
      cleanup, unbounded rescan, or another production correction.

### 5. Deploy baseline application and start measurement

- [ ] Approve exact SHA and full production delta; record pinned rollback.
- [ ] Deploy immediately after schema verification.
- [ ] Verify anti-enumerating subscribe responses, token rotation using test
      data only, ledger health, bounded recovery, topic filtering, search
      non-persistence, daily-HMAC/no-raw-client logging, and retention pruning.
- [ ] Verify sanitized pageviews and operator/manage/custom/sensitive-referrer
      suppression.
- [ ] Record `A0`; run daily quota checks plus `B7`, then freeze `B14` before
      the treatment deploy.

### 6. Extract/release visible treatment

- [ ] Rebase PR 88 after baseline and remove every PR-90-owned backend file.
- [ ] Review against exact baseline deployment.
- [ ] Confirm no migration or capture/delivery/privacy/search/logging/rate-limit/
      operator-session/analytics change.
- [ ] Freeze baseline, approve treatment SHA, deploy, and record `T0`.
- [ ] Roll back to exact baseline deployment if needed, not PR83.
- [ ] Run daily quota checks plus `T7`, then freeze `T14` and close with
      descriptive raw counts.

## Stop conditions

Stop if the combined branch does not preserve exact migration order 138 -> 139
-> 140 -> 141, clean-room types are absent, schema drift is not preview-aware,
CI is not green, the Vercel plan/commercial-use facts are unresolved, a Hobby
action threshold is reached without an operator decision, a required aggregate
checkpoint cannot be captured, analytics pauses, preview asks for production
credentials, a real token appears in telemetry, migration 134 is present,
migration 136 appears absent, the 90-day retention job fails, or backend/
measurement behavior changes during a window.
