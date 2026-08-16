# S29 analytics baseline and production release runbook

**Prepared:** 2026-08-15

**Status:** Ready for review; no deploy, billing change, preview bootstrap,
migration, merge, or production mutation is authorized by this document.

**Measurement:** 14 complete UTC days of analytics-only baseline, followed by
14 complete UTC days of front-door treatment.

## Fixed starting state

- `richmondcommons.org` is intentionally pinned to PR 83 / `3be0709`.
- `main` is `c433783` and contains PRs 84-87. A production deploy of this
  analytics branch after merge would therefore release that whole reviewed
  code delta, not only the analytics component.
- Migration 136 is already live. Verify its ledger/grants; do not reapply it.
- Migration 138 is committed on `main`, privilege-only, and still requires its
  own operator approval and post-apply checks.
- Migration 134 is byte-locked and a **HARD NO-GO**. Never apply it or rewrite
  it in place.
- Supabase stays **Pro**. The public flag/count threshold stays **D2 = 0.50**.
- Production model routing stays **DeepSeek-first**. Luna remains limited to
  exactly the two benchmarked exceptions: failed negated-motion vote
  explainers and image-only Form 460 summary recovery.
- The repository stays **AGPL-3.0**.
- Vercel Web Analytics is enabled in the dashboard, but production does not
  yet render an Analytics component. There is no valid pre-treatment baseline
  before the analytics-only production release.
- PR 88 mixes analytics, email-delivery migration 137, and public front-door
  treatment. It must not be merged or deployed as the baseline artifact.

## Measurement boundary

The analytics-only change records automatic page views and nothing else. It:

- rejects custom events;
- removes query strings and fragments before a page view leaves the browser;
- excludes `/operator` and `/subscribe/manage`, including descendants;
- drops a page view when its browser referrer is a private management path or
  contains a token/secret parameter;
- adds `Referrer-Policy: no-referrer` to the subscription-management surface;
  and
- creates no cookie, local-storage value, fingerprint, custom visitor ID, or
  person-level join.

Vercel identifies an anonymous visitor with a hash that resets daily. A count
of “visitors” is therefore unique only within one day. Summing 14 daily visitor
counts produces **visitor-days**, not 14-day unique people: one resident who
visits on five days can count five times. The experiment must not label these
counts “returning residents,” “repeat residents,” or cross-day retention.
Vercel documents the daily reset and cookie-free aggregation in its
[Web Analytics guide](https://vercel.com/docs/analytics) and
[privacy documentation](https://vercel.com/docs/analytics/privacy-policy).

Allowed reporting fields are:

- page views by sanitized path;
- daily visitors, reported per day or explicitly summed as visitor-days;
- referrer hostnames/direct traffic, never raw token-bearing URLs;
- Vercel bounce rate and same-day page depth; and
- total new active subscriptions from the existing database timestamps.

Baseline acquisition placement is unavailable and must be shown as `N/A`, not
inferred. A later treatment may store an allow-listed coarse placement in the
existing subscriber metadata, but it must never store a raw URL or referrer.

## Window definitions

Use complete UTC days so partial deploy days are not compared.

1. Record the analytics production deployment ID, commit, and completion time
   as `A0`.
2. Baseline day 1 is the first `00:00:00Z` after `A0`. Baseline is days 1-14,
   ending at `00:00:00Z` after day 14.
3. Export and freeze the baseline packet before any public front-door change.
4. Record the treatment production deployment ID, commit, and completion time
   as `T0`.
5. Treatment day 1 is the first `00:00:00Z` after `T0`. Treatment is days 1-14,
   ending at `00:00:00Z` after day 14.

Do not start a window until a manual network check confirms that a public page
sends one sanitized page-view request and operator/manage paths send none. Any
analytics outage, collection pause, major site outage, external media link, or
release during a window must be recorded. If a release can affect navigation,
subscriptions, page rendering, or measurement, either defer it or restart the
affected 14-day window.

This is a sequential observation, not a randomized causal experiment.
Election-season timing, news coverage, weekday mix, and other external changes
can explain differences. Report raw counts and descriptive changes; do not
claim that the treatment caused them.

## Baseline and treatment packet

Select **Production** only and filter to `richmondcommons.org`. Save the exact
UTC query boundaries and export each panel at baseline close, then again at
treatment close.

| Field | Baseline 14 days | Treatment 14 days | Reporting rule |
|---|---:|---:|---|
| Total public page views | - | - | Sanitized paths only |
| Homepage views | - | - | `/` |
| November election views | - | - | Record the exact route |
| Meeting-index views | - | - | `/meetings` |
| Council-index views | - | - | `/council` |
| District-finder views | - | - | `/elections/find-my-district` |
| Daily visitors by date | - | - | Daily-reset counts |
| Visitor-days | - | - | Sum of daily visitors; not unique residents |
| Bounce rate | - | - | Vercel definition; same-day context |
| Same-day page depth | - | - | Engagement proxy, not retention |
| New active subscriptions | - | - | Raw numerator required |
| Subscriptions by coarse placement | N/A | - | Treatment metadata only |
| Top referrer hostnames | - | - | Hostnames/direct only |
| Analytics event usage | - | - | Confirm collection did not pause |

For any conversion ratio, show the raw numerator and denominator. If the
November route has fewer than 50 treatment page views, label the result
`insufficient exposure` and do not infer rejection or success.

## Vercel Hobby to Pro decision packet

**Decision deadline:** before approving the analytics production release, and
in all cases before the November observation. Billing changes remain operator
only.

Current Vercel documentation gives Hobby 50,000 Web Analytics events and a
one-month reporting window. Hobby pauses collection after its limit/grace
behavior rather than billing overages. Pro gives a 12-month reporting window,
billable event capacity, Spend Management, longer runtime-log retention, and
optional drains; it does not require Web Analytics Plus for this pageview-only
test. See Vercel's current
[analytics limits and pricing](https://vercel.com/docs/analytics/limits-and-pricing),
[Hobby comparison](https://vercel.com/docs/plans/hobby), and
[Pro plan](https://vercel.com/docs/plans/pro-plan). Confirm the dashboard
checkout quote immediately before approval because pricing can change.

### Option H - remain on Hobby for the bounded test

Choose only if the operator confirms all of the following:

- forecast usage across every project on the account stays safely below 50,000
  events for the collection cycle;
- baseline exports will be frozen immediately on day 14 and treatment exports
  immediately on day 28, avoiding reliance on the one-month retention edge;
- collection-paused notifications and Usage are checked daily;
- one-hour runtime-log retention is acceptable for release diagnosis; and
- the operator is satisfied that the project's use fits Vercel's current Hobby
  terms, which Vercel describes as personal/non-commercial.

This is the lowest-cost option, but a 28-complete-day sequence plus deploy and
closeout margins leaves little retention slack.

### Option P - upgrade to Pro before `A0`

Choose if the operator values a durable audit trail, billing/spend controls,
longer runtime diagnosis, or clearer plan fit more than the recurring cost.
Configure a conservative Spend Management alert/hard action before release,
keep custom events disabled, and do not buy Web Analytics Plus. The analytics
privacy boundary and daily-reset visitor semantics do not change on Pro.

**Recommendation:** choose Pro before `A0` if its dashboard quote is acceptable.
The 12-month reporting window materially reduces the risk of losing the
baseline during a 28-day sequence. Otherwise Option H is viable only with the
day-14/day-28 export discipline above. Do not start a 14-day Pro trial as a
substitute for a decision; it would expire halfway through the experiment.

Record the decision, approver, timestamp, checkout quote, spending cap, and
effective plan in the release packet. This document does not make the change.

## Release and migration ordering checklist

Every numbered gate requires a fresh operator approval for the exact artifact
named. No approval carries forward to another gate.

### 1. Prepare the analytics baseline artifact

- [ ] Merge only the focused analytics PR after CI is green and review confirms
      it has no migration, treatment UI, custom event, or persistent ID.
- [ ] Do not require a Vercel/Supabase PR Preview. The repository's preview
      environment fails closed without the explicit Supabase-preview bootstrap;
      this runbook does not authorize that billable bootstrap.
- [ ] Reconfirm the resulting `main` SHA and list the full PR83-to-target delta
      (PRs 84-87 plus analytics) for production approval.
- [ ] Resolve Option H or Option P. If P is selected, operator upgrades billing
      and configures spend controls before `A0`.

### 2. Stabilize already-merged operations work

- [ ] Verify migration 136 is present/live and migration 134 is absent. Do not
      apply either.
- [ ] Decide migration 138 separately. If approved before the experiment, apply
      only the mirrored forward migration, run its exact grant checks, and
      finish stabilization before `A0`.
- [ ] If migration 138 is not approved before `A0`, defer it until after the
      treatment window. Do not change grants mid-window.
- [ ] Do not run the NextRequest catch-up, an eSCRIBE replay/full sync, the
      42-row contribution cleanup, an unbounded rescan, or any other production
      correction as part of this release.

### 3. Release analytics and run baseline

- [ ] Operator approves the exact target SHA and acknowledges that production
      moves from PR83 to the full PR84-87-plus-analytics batch.
- [ ] Record the current production deployment ID for rollback.
- [ ] Execute the repository production-deploy procedure and no other mutation.
- [ ] Spot-check `/`, `/meetings`, `/search?q=private`, `/operator/login`, and
      `/subscribe/manage?token=test` without using a real token.
- [ ] Confirm public analytics URLs contain no query/fragment, and operator,
      manage, custom-event, and token-referrer cases send nothing.
- [ ] Record `A0`; run and freeze the 14-complete-day baseline packet.

### 4. Split PR 88 before treatment

Do not cherry-pick PR 88's single commit. Rebase its branch on the analytics
baseline `main`, then construct explicit commits/PRs by path:

1. **Analytics:** drop PR 88's analytics package hunk,
   `PrivacyAnalytics.tsx`, `analytics-privacy*`, layout analytics hunk, and old
   two-window runbook; they are superseded by the focused baseline PR and this
   runbook.
2. **Front-door treatment (no migration):** homepage/navigation/SEO and coarse
   subscription-placement UI/API changes, their focused tests, and only the
   query/provenance changes those public surfaces require. Keep Richmond 101
   operator-only or split it again for voice/publication review.
3. **Email reliability (migration-dependent):** mirrored migration 137,
   `email-delivery*`, email route changes, and generated type/manifest/docs
   updates. This is not required for the front-door comparison.

The treatment diff must be reviewed against the analytics baseline commit, not
against PR83 or PR 88's old base.

### 5. Release treatment and run treatment window

- [ ] Verify the baseline export is complete and immutable.
- [ ] Operator approves the exact front-door treatment SHA. It must contain no
      migration and must not change the analytics privacy component.
- [ ] Deploy the treatment artifact; record `T0`.
- [ ] If rollback is required, restore the exact analytics-baseline deployment,
      not PR83, so measurement continues under the same analytics code.
- [ ] Run 14 complete UTC days, export the treatment packet, and report only
      descriptive differences with raw counts.

### 6. Handle migration 137/email reliability outside the windows

- [ ] Prefer deferring this slice until treatment close. If the operator needs
      it earlier, release it before `A0`, verify it, and restart the baseline
      clock after stabilization.
- [ ] Apply migration 137 only after its own approval and preflight. Verify the
      private table, service-role-only grants, functions, and mirrored hashes.
- [ ] Deploy dependent email code only after the schema verification succeeds.
- [ ] Treat migration 137 as forward-only: rollback the application artifact if
      needed, but do not drop the ledger/functions ad hoc.

## Stop conditions

Stop and request operator direction if the target SHA changes, CI is not green,
analytics collection pauses, the Hobby event forecast approaches its cap, a
preview asks for production credentials, any real management token appears in
telemetry, a proposed release contains migration 134, migration 136 appears
absent, or a migration/treatment is proposed during an active window.
