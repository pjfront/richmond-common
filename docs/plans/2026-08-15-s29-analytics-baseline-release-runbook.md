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
- Current `main` contains PRs 84-87. Moving production from the pin releases
  the full reviewed delta, not just PR 90.
- Supabase remains **Pro**. Migration 136 is live. Migration 138 is preserved
  on `main` and remains separately approval-gated.
- Migration 134 is byte-locked and a **HARD NO-GO**. Never apply or rewrite it.
- Draft PR 92 owns migration **139**.
- Draft PR 91 must move its retry-containment migration to **140**. Its fetched
  head still used 139 on 2026-08-16, so PR 90 is blocked until corrected.
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

The operator accepts bounded Vercel referrer intake: an external source may
send Vercel its full referring-page URL, and `beforeSend` cannot transform
that separate field. Disclosure must say this accurately. Analysis and
closeout use only aggregate referrer domains/direct traffic. Do not export,
retain, quote, or republish referring paths or full referring URLs.

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
   verification, Analytics verification, and effective Vercel plan as `A0`.
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

This is sequential observation, not a randomized causal experiment. Report raw
counts and descriptive changes, not causal claims.

## Results packet

Select **Production** and `richmondcommons.org`. Save exact UTC boundaries.

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
| Top referrer domains | - | - | Domains/direct only; no path export |
| Analytics collection status | - | - | Confirm no pause |

Every conversion ratio includes its raw numerator and denominator. Fewer than
50 November-route treatment pageviews is `insufficient exposure`, not success
or rejection.

## Vercel decisions: resolved, execution still gated

The operator approves **Vercel Pro before baseline** and accepts the bounded
referrer intake under the disclosure/domain-only/no-path-export rules above.
This task changes neither billing nor production.

Before `A0`, the operator separately executes the dashboard upgrade, confirms
the checkout quote, configures conservative Spend Management alerts/actions,
and records the effective timestamp. Keep custom events off; do not buy Web
Analytics Plus or Observability Plus for this test. Pro changes retention and
headroom, not daily visitor semantics or privacy.

## Dependency and release ordering

Every mutation requires approval for the exact artifact.

### 1. Resolve repository dependencies; no production action

- [ ] Land **Make schema drift preview-aware**.
- [ ] Correct PR 91 so both retry-containment mirrors use migration 140.
- [ ] Merge PR 92 (139) and PR 91 (140) in reviewed order.
- [ ] Rebase draft PR 90 onto resulting `main`; confirm 138 -> 139 -> 140 ->
      141 and rerun all gates.
- [ ] Keep PR 90 draft and unmergeable until complete.

### 2. Generate DB types only from clean-room preview

- [ ] After the preview-aware fix and dependency rebase, obtain separate
      approval for explicit Supabase-preview bootstrap.
- [ ] Build clean-room preview from trusted baseline through migration 141.
      Never generate types from production.
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

- [ ] Operator separately upgrades Vercel to Pro and records spend controls.
- [ ] Verify migration 136 live and migration 134 absent.
- [ ] Approve/apply/verify forward migrations in order: 138, PR 92's 139,
      PR 91's 140, PR 90's 141.
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
- [ ] Record `A0`; run and freeze 14 complete UTC days.

### 6. Extract/release visible treatment

- [ ] Rebase PR 88 after baseline and remove every PR-90-owned backend file.
- [ ] Review against exact baseline deployment.
- [ ] Confirm no migration or capture/delivery/privacy/search/logging/rate-limit/
      operator-session/analytics change.
- [ ] Freeze baseline, approve treatment SHA, deploy, and record `T0`.
- [ ] Roll back to exact baseline deployment if needed, not PR83.
- [ ] Run 14 complete UTC days and close with descriptive raw counts.

## Stop conditions

Stop if PR 91 still conflicts with 139, dependency rebase is incomplete,
clean-room types are absent, schema drift is not preview-aware, CI is not
green, analytics pauses, Vercel Pro is not effective before `A0`, preview
asks for production credentials, a real token appears in telemetry, migration
134 is present, migration 136 appears absent, the 90-day retention job fails,
or backend/measurement behavior changes during a window.
