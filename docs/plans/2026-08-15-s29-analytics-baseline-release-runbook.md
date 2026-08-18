# S29 baseline and production release runbook

**Prepared:** 2026-08-16

**Status:** A0 is held. Vercel Hobby has no general billing-cycle reset, and
the latest authenticated snapshot reports about 289 of 240 included Active CPU
minutes in the rolling 30-day window. The committed measurement contract stays
`pending`; no measurement window has started. Do not record A0 until the exact
baseline deployment and soak, at least seven complete post-deploy UTC days,
the approved scoped crawler-containment rollout and verification,
rolling-CPU gate, resource-specific Usage snapshot, and apex operator-session
suppression check are all complete. This document authorizes no further
deploy, billing action, preview bootstrap, migration, email send, or
production-data change.

**Measurement:** 14 complete UTC days with the existing public experience,
followed by 14 complete UTC days with only the visible S29 treatment changed.
Analytics, subscription capture, email delivery, privacy, search, operator
session, and rate-limit behavior must be identical in both windows.

## Fixed starting state

- Current production remains deployment
  `dpl_3Fit9sx7D97BgAbA3iqsRfbjSfUp` at exact SHA
  `0ff9fd50443d8d13e15a4d83845b2997cfc1054a`.
- PR 101 / `fbb496b1c9988e0a7ec109089da5420565d2228b` is merged but
  undeployed. It is not the final baseline candidate. The final SHA and
  deployment remain pending the approved scoped crawler-containment rollout
  and its verified implementation. Before A0, confirm both `richmondcommons.org`
  and `www.richmondcommons.org` resolve to that eventual exact artifact, and
  retain `dpl_3Fit9sx7D97BgAbA3iqsRfbjSfUp` as the pinned rollback artifact.
- The later focused A0 measurement-config commit must not replace the verified
  application artifact or trigger another production deployment. Main-branch
  auto-deploy is disabled by
  `web/vercel.json` -> `git.deploymentEnabled.main = false`, and
  `tests/test_deploy_gate.py` enforces that guard. Do not request a preview for
  the config-only activation.
- Supabase remains **Pro**. Migrations 136 and 138 through 144 are live and
  postflight-verified.
- Migration 134 is byte-locked and a **HARD NO-GO**. Never apply or rewrite it.
- PR 92 owns migration **139** and is in `main`.
- PR 91's exact containment commit
  `325819f9a1f3c9768ff381bbfdc26829bc4dc473` owns migration **140** and is
  incorporated into PR 90. A separate PR 91 preview was intentionally
  not required.
- This baseline batch owns migration **141** for private subscription
  activations and email delivery. Migration **142** tightens its grants. Both
  sets of mirrors remain byte-identical.
- Migration **143** bounds and hardens the public search read paths. Migration
  **144** replaces the nested council-vote read with a bounded flat RPC. Their
  mirrors remain byte-identical, preview-generated types landed, and neither
  migration corrects, backfills, or deletes production rows.
- Similar Discussions uses the approved seven-day November-test cache.
  Related-topic reads propagate failures so ISR preserves the last successful
  page instead of caching a temporary empty state.
- Production model routing remains **DeepSeek-first**. Luna remains limited to
  the two benchmarked exceptions: failed negated-motion vote explainers and
  image-only Form 460 summary recovery.
- The public flag/count threshold remains **D2 = 0.50** and the repository
  remains **AGPL-3.0**.
- Vercel Web Analytics is enabled on the baseline production artifact. Before
  A0, verify sanitized public intake and reporting with operator and management
  routes absent. Pre-A0 traffic is excluded from the measurement window.

## A0 activation record

- Actual A0 capture time: **PENDING RUNTIME VERIFICATION**.
- Current Active CPU evidence: approximately 289/240 minutes in the rolling
  30-day window, with the recent observed rate around 7.9-8.4 minutes/day.
  That rate projects to 237-252 minutes over 30 days, from effectively no
  headroom to continued overage. There is no pending monthly reset that makes
  this start-safe.
- The calendar is gate-driven. After the final approved CPU-affecting baseline
  release is live and soaked, collect at least seven complete UTC days. A0 may
  then be considered only when Usage is complete, rolling CPU is at most 180
  minutes, those seven complete days average at most four minutes/day, and each
  of the most recent three complete days is strictly below four minutes.
  Baseline day 1 is the first UTC midnight after the actual A0 capture.
- Derive every later date from actual gate passage: B7 and B14 are seven and 14
  complete baseline days; treatment begins only after B14 is frozen and the
  treatment is approved; T7 and T14 are seven and 14 complete treatment days.
  If any gate fails, leave the contract pending and move every boundary. Do not
  infer safety from a projected calendar or an account total alone. Create
  one-shot reminders only after A0 and T0 are final.
- September 18 A0 / September 19 baseline remains a conservative planning
  fallback if the rolling total does not fall quickly enough. In that example,
  B7 is September 26, B14 is October 3, treatment runs October 4 through
  October 18, T7 is October 11, and T14 is October 18. It is not a technical
  minimum: passing the actual gates may permit an earlier start, while failing
  them requires a later one. An operator may separately choose a full 30-day
  post-deploy observation period for additional conservatism.
- Scoped Amazonbot deep-item containment plus matching robots policy:
  **APPROVED BY THE OPERATOR ON 2026-08-18; NOT ACTIVE YET**. The bounded WAF
  log stage is still pending publish. No log, preview-deny, or production-deny
  stage may be described as active until its publish and runtime verification
  are complete.
- Exact production deployment/SHA and soak: **PENDING RUNTIME VERIFICATION**.
- Authenticated Vercel plan; rolling 30-day Active CPU total; recent daily CPU
  rate; Web Analytics allowance period, usage, and collection status; and every
  other displayed resource-specific hard quota: **PENDING RUNTIME
  VERIFICATION**.
- Apex logout/login/public-page operator suppression check:
  **PENDING RUNTIME VERIFICATION**.
- Private A0 packet under the gitignored
  `src/data/analytics_checkpoints/` directory: **PENDING**. Never commit its
  filled usage fields or any credential, event row, or full referrer URL.

The operator approved the donation-ask hold on 2026-08-18. Keep October 1
decision-only and hold every public homepage or email donation ask through the
actual T14 freeze. Under the conservative fallback above, the earliest
post-freeze date is October 19. This timing decision does not itself approve an
ask, its content, or its publication. Publishing before T14 would override the
approved hold, contaminate the defined test, and require a new operator
decision plus either a new window or an explicitly incomplete closeout.

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

The final baseline application also includes the already-reviewed, non-treatment
reliability work: PR 98's permanent canonical-host redirect; PR 100's bounded
search, official-voting-record, and Similar Discussions reads plus migrations
143 and 144; and PR 101's fail-closed related-topic ISR behavior. Freeze these
behaviors with the baseline. They do not authorize a data correction, expanded
sync, new analytics field, or visible treatment.

The baseline batch does **not** include a redesigned homepage, public
navigation/footer changes, new meeting/election subscription placements,
public SEO treatment, or public Richmond 101.

### Treatment batch: deploy only after baseline close

The treatment may contain only reviewed visible S29 changes in draft PR 99,
extracted from PR 88:

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

Before A0, `www.richmondcommons.org` permanently redirects to the apex host.
The two-host intake allowlist remains defense in depth and covers any request
that reaches client code before the redirect configuration is active. Do not
change canonical-host behavior during either measurement window.

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

1. Record completed baseline deployment, exact commit, migrations 138-144
   verification, Analytics verification, effective Vercel plan, the timestamped
   rolling 30-day Active CPU total and rate, each resource's own usage period,
   and current plan usage as `A0`.
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

Vercel's official [Hobby plan
documentation](https://vercel.com/docs/plans/hobby) says Hobby has no billing
cycles, includes four Active CPU hours, and generally requires usage to fall
out of the prior 30 days after a limit is exceeded. Active CPU is therefore a
rolling 30-day constraint; a date-picker boundary or a separate product's
allowance period is not a CPU reset. Vercel's [Web Analytics limits and
pricing](https://vercel.com/docs/analytics/limits-and-pricing) separately
defines its own 50,000-event monthly allowance, one-month reporting window,
three-day overage grace period, and seven-day wait after Hobby collection
pauses. Apply those semantics only to Analytics.

The dashboard is not the durable system of record for this 28-day test. Use
Vercel's aggregate count/aggregate views or dashboard only; never export
event-level rows, referring paths, or full referring URLs. Filled packets may
be saved only under the gitignored `src/data/analytics_checkpoints/` directory
and never committed. A later public summary requires separate review and
contains only approved aggregates.

The 2026-08-18 authenticated evidence proves the dominant CPU surface in the
observed Production interval and supplies a narrower crawler hypothesis:

- the recent Production table showed about 1,400 invocations and four Active
  CPU minutes;
- `/meetings/[id]/items/[itemNumber]` accounted for about 1,200 invocations and
  three of those CPU minutes;
- in the bounded sampled hour, the retained Hobby log slice contained 147
  detail-route cache `MISS` requests and an exact sampled Amazonbot request;
- Firewall observations in that sampled hour attributed 142 requests directly
  to Amazonbot and 146 to an Amazon ASN; and
- ISR usage showed 449 unique item paths and 902 writes, while only three
  time-based revalidations appeared sitewide.

The Production table proves that agenda-item detail was the dominant CPU
surface: about 1,200 of 1,400 invocations and three of four CPU minutes. The
bounded log and Firewall views make Amazonbot a high-confidence, likely
dominant material contributor to cold-path enumeration in the sampled hour.
They do **not** quantify Amazonbot's share of the broader 1,200-invocation /
three-minute interval. The three time-based revalidations show that TTL churn
was not the primary mechanism in the observed interval. Vercel also displayed
an incident notice that some Usage and Observability data may be missing for
August 17, so that affected interval cannot prove a stable post-change rate.

### Approved crawler containment; rollout pending

On 2026-08-18, the operator approved containment of only `Amazonbot/0.1` on
deep `/meetings/.../items/...` routes, plus a matching Amazonbot-only
`robots.txt` instruction. Google, Bing, `Amzn-SearchBot`, `Amzn-User`, humans,
APIs, meeting-level pages, and every other route remain outside the block. No
broader crawler block, generic bot challenge, IP block, or GET rate limit is
authorized.

The bounded Vercel WAF log stage is still **PENDING PUBLISH** and no WAF stage
is active as of this record. After it is published, compare its count with the
same route's request and CPU evidence over a declared short interval; this is
an attribution test, not proof assumed in advance. If the evidence continues
to support the hypothesis, proceed through the approved preview-deny and
production-deny stages and publish the matching robots policy, verifying each
stage before advancing. The policy/SEO judgment is approved, but each external
publish remains an explicit operator action and the eventual application SHA
remains pending review and verification.

The operator also approved a rolling 24-month agenda-item sitemap on
2026-08-18. Keep it in PR 99's visible treatment by default. Older item pages
remain live, indexable, and internally linked; only their sitemap enumeration
changes. Move this bounded sitemap change into the pre-A0 baseline only if the
scoped containment is published and verified but the post-containment CPU
gates still fail, then re-review and soak the resulting exact baseline SHA.
Extending the approved Similar Discussions TTL remains useful cache hygiene,
but it does not eliminate unique cold renders.

`src/s29_vercel_analytics.py` is a compact, one-checkpoint-at-a-time collector;
it is not a scheduled monitor. The exact contract is
`docs/s29-measurement.json`. Its committed `measurement_status` remains
`pending`, with null phase dates and SHAs. Only after every A0 runtime gate
passes may a focused activation change the status to `active`, set baseline day
1's exact midnight, and record the verified 40-character production SHA. That
config-only commit must not request a Preview; once merged to `main`,
`web/vercel.json` -> `git.deploymentEnabled.main = false` prevents a production
deployment and `tests/test_deploy_gate.py` guards the setting. Set the treatment
start/SHA only after the full joined baseline freeze and treatment approval.
After the joined T14 freeze, change the status to `complete`; the collector
refuses capture unless the status is `active`. Richmond 101 remains absent from
the exact route allowlist unless its route receives separate publication and
measurement approval.

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
| `A0` | Baseline deploy verified | Plan; timestamped rolling 30-day CPU total and recent rate; each resource's own usage period; Analytics events used; each hard-quota percentage; exact UTC/query filters |
| `B7` | After 7 complete baseline days | Aggregate packet; collection status; account-wide plan usage and projections |
| `B14` | After 14 complete baseline days, before treatment | Final baseline packet; collection status; account-wide plan usage and projections |
| `T7` | After 7 complete treatment days | Aggregate packet; collection status; account-wide plan usage and projections |
| `T14` | After 14 complete treatment days | Final treatment packet; collection status; account-wide plan usage and projections |

Every aggregate packet records its capture timestamp, exact UTC start/end,
production deployment SHA, and the allow-listed Vercel result fields above.
It does not attempt to infer quota consumption. Web Analytics usage is shared
account-wide across projects and follows its own allowance period. Active CPU
uses the rolling 30-day window. The authenticated Vercel Usage dashboard is the
authoritative quota and collection source. Record the snapshot time, exact
scope, resource-specific window, actual usage, collection status, and any
Vercel projection at `A0` and every checkpoint.

Apply the following account-wide CPU gates. The seven-day rate uses complete
UTC days after the final CPU-affecting deployment; do not extrapolate a partial
day or an interval covered by a Vercel data incident.

| Active CPU gate | Rolling 30-day total | Trailing seven-day average | Required action |
|---|---:|---:|---|
| Start-safe | At most 180 minutes (75%) | At most 4 minutes/day | A0 or T0 may start only if the three-day stability proof and every other gate also pass |
| Warning | More than 180 minutes | More than 4 minutes/day | Capture the state, diagnose, and continue daily checks; do not treat it as green |
| Action | At least 216 minutes (90%) | At least 7.2 minutes/day | Hold any phase start and check twice daily until below the action gate |
| Hard stop | At least 240 minutes (100%) | More than 8 minutes/day, or Vercel pauses the project | Do not start or continue a window unattended; record any outage and obtain an operator decision |

The start-safe row is conjunctive: after at least seven complete post-deploy UTC
days, the total and seven-day rate must pass, and each of the three most recent
complete days must be strictly below four minutes. A full 30-day post-change
wait is optional operator conservatism, not a technical requirement. The other
rows are disjunctive: crossing either threshold escalates. At the current
approximately 289-minute total and 7.9-8.4-minute recent rate, A0 is blocked.
No calendar date is pre-authorized; actual complete-day evidence must pass.

Continue the bounded aggregate checkpoints and check CPU once daily at a
consistent UTC time before and during both windows. At the action gate, check
twice daily. At a hard stop, preserve the public site's recoverable state, do
not manufacture replacement data, and follow the existing outage/restart rule.

| Other resource | Warning threshold | Action threshold |
|---|---|---|
| Account-wide Web Analytics events in its documented monthly allowance period | Actual or projected use reaches 40,000 (80% of the current Hobby allowance) | Actual reaches 45,000, projected reaches 50,000 in that Analytics period, or the dashboard cannot be checked promptly |
| Any other Hobby hard quota shown by Vercel | Actual reaches 70%, or projected reaches 80% | Actual reaches 80%, or projected reaches 100% within that resource's documented window |
| Analytics collection or aggregate reporting | Any unexplained gap or failed checkpoint | Collection pauses, or `B14`/`T14` cannot be frozen with the defined aggregates |

At a warning threshold, capture a checkpoint and diagnose the source. At an
action threshold, do not start the next window or continue the current window
unattended. The operator chooses among a valid restart after a bounded
architecture fix or closing the test as incomplete; a future paid-plan action
remains a separate judgment and is not the S29 default. Do not introduce
sampling, custom events, new route filters, or another analytics provider
mid-window: each changes the measurement contract and requires a fresh window.

Ordinary Pro is not an analytics-architecture prerequisite here. It would add
retention and usage headroom, but it would not change daily visitor semantics
or the privacy boundary. Keep custom events off; do not buy Web Analytics Plus,
Observability Plus, or a drain for this test, and do not upgrade solely to clear
the S29 CPU gate. Revisit the plan only for a separately justified need, longer
raw dashboard retention, or changed commercial-use facts. Current Vercel plan
limits remain an external dependency and must be rechecked against the official
links above at `A0`.

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
resource-specific usage periods, rolling Active CPU, other hard limits, and
collection continuity.
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
- [x] Apply and verify 138 -> 139 -> 140 -> 141; the postflight identified
      excess default `service_role` privileges before application deployment.
- [x] Land and apply migration 142's privilege-only forward correction, then
      rerun the exact grant and trigger-function postconditions.
- [x] Confirm fresh CI for the combined 138 -> 139 -> 140 -> 141 -> 142
      repository candidate.
- [x] Keep PR 90 draft and unmergeable until its one clean-room preview and
      generated-type gates are complete.

### 2. Generate DB types only from clean-room preview

- [x] After fresh combined-candidate CI, obtain separate approval for the one
      explicit Supabase-preview bootstrap allowed for this release candidate.
- [x] Build one clean-room preview from the trusted baseline through migrations
      138, 139, 140, 141, and 142. Do not create a separate PR 91 preview. Never
      generate types from production.
- [x] Generate and commit `web/src/lib/database.types.ts` exactly from that
      preview; pass schema-drift/type checks.
- [x] On failure, stop. Never hand-edit generated DB types or use production
      credentials.
- [x] Delete the approved ephemeral preview and its branch-scoped environment
      after the exact-head gates pass.
- [x] Use the separately approved PR 100 Micro preview to validate migrations
      143 and 144 and regenerate types from that clean-room schema only; delete
      it after the exact-head gates pass (completed in 22 minutes 13 seconds).

### 3. Approve and merge baseline prerequisites; final candidate pending

- [x] Confirm PR 90 has all baseline mechanics and no named treatment.
- [x] Confirm CI, mirror hashes, manifest, type drift, focused tests, lint, and
      production build are green.
- [x] Merge in a maintenance window before the `17 */4 * * *` recovery
      schedule; a call against the old app can only fail and is not cutover.
- [x] Reconfirm the reviewed application delta through merged PR 101 / exact
      SHA `fbb496b1c9988e0a7ec109089da5420565d2228b`; that SHA remains undeployed
      and is not the final baseline candidate.
- [x] Record the operator's 2026-08-18 approval of the scoped Amazonbot
      deep-item containment policy and matching robots instruction.
- [ ] Publish and verify the bounded WAF log stage, complete the approved
      staged containment rollout, then validate and reconfirm the complete
      delta and exact final baseline SHA. No WAF stage is active merely because
      the policy is approved.

### 4. Production preflight and migrations

- [ ] Confirm the noncommercial facts above are still unchanged and record the
      effective Vercel plan, rolling 30-day Active CPU total and rate, each
      resource's usage period, Analytics events used, and every displayed
      hard-usage quota percentage. Confirm both CPU start-safe thresholds and
      every other release gate before A0.
- [x] Verify that the aggregate API can reproduce the defined pageview,
      route, daily-reset visitor, and referrer-hostname fields without
      event-level or full-referrer export. The authenticated Usage dashboard
      remains required for resource-specific windows, authoritative collection
      status, bounce rate, and every displayed hard-usage quota percentage.
      Prepare the operator-only checkpoint packet; the current start-safety
      decision remains the unchecked item above.
- [x] Verify migration 136 live and migration 134 absent.
- [x] Approve/apply/verify forward migrations in order: 138, PR 92's 139,
      incorporated PR 91 migration 140, PR 90 migration 141, then the bounded
      postflight correction in migration 142.
- [x] Verify 141 and 142 mirror hashes, private tables, RLS/grants, trigger,
      and RPCs. `service_role` must have only `SELECT`, `INSERT`, and `UPDATE`
      on `email_deliveries`; no API role may directly execute the activation
      trigger function. Confirm the 90-day pruning RPC is service-role-only
      and invoked by the scheduled recovery route. Do not backfill or correct
      data.
- [x] Approve/apply/verify migrations 143 then 144, their mirror hashes,
      explicit API-role grants, bounded public-read behavior, and generated
      types. Neither migration performs a production-data correction.
- [x] Do not run NextRequest catch-up, eSCRIBE replay/full sync, contribution
      cleanup, unbounded rescan, or another production correction.

### 5. Deploy baseline application and start measurement

- [x] Record current production
      `dpl_3Fit9sx7D97BgAbA3iqsRfbjSfUp` /
      `0ff9fd50443d8d13e15a4d83845b2997cfc1054a` as the pinned rollback;
      the previously approved delta through PR 101 does not approve a crawler
      policy.
- [ ] After the crawler judgment and exact-delta review, approve the final
      baseline SHA and full production delta.
- [ ] Deploy that exact final SHA after schema verification; soak it and retain
      `dpl_3Fit9sx7D97BgAbA3iqsRfbjSfUp` as the exact rollback target.
- [x] Verify anti-enumerating subscribe responses, token rotation using test
      data only, ledger health, bounded recovery, topic filtering, search
      non-persistence, daily-HMAC/no-raw-client logging, and retention pruning.
- [x] Verify sanitized pageviews and operator/manage/custom/sensitive-referrer
      suppression.
- [ ] Deploy and soak the permanent `www` -> apex redirect, then verify that
      path and query are preserved and Analytics still records only public
      apex traffic.
- [ ] Log out and back in on the apex operator route after the redirect is
      live, then verify an authenticated visit to a public apex page remains
      suppressed. The host-only operator cookie must not be assumed to move
      from `www` across the redirect.
- [ ] Record `A0`; baseline day 1 begins at the first UTC midnight afterward.
- [ ] Run daily quota checks plus `B7`, then freeze `B14` before
      the treatment deploy.

### 6. Extract/release visible treatment

- [ ] Rebase draft PR 99 after baseline and keep every PR-90-owned backend file
      out of its extracted PR-88 treatment delta.
- [ ] Include the approved rolling 24-month agenda-item sitemap in PR 99 by
      default, while keeping older item pages live, indexable, and internally
      linked. Move it into the baseline only if verified post-containment CPU
      gates still fail, then re-review and soak the new exact baseline SHA.
- [ ] Review against exact baseline deployment.
- [ ] Confirm no migration or capture/delivery/privacy/search/logging/rate-limit/
      operator-session/analytics change.
- [ ] Freeze baseline, approve treatment SHA, deploy, and record `T0`.
- [ ] Roll back to exact baseline deployment if needed, not PR83.
- [ ] Run daily quota checks plus `T7`, then freeze `T14` and close with
      descriptive raw counts.

## Stop conditions

Stop if the release does not preserve exact migration order 138 -> 139 -> 140
-> 141 -> 142 -> 143 -> 144, clean-room types are absent, schema drift is not
preview-aware, CI is not green, the Vercel plan/commercial-use facts are
unresolved, a Hobby
action threshold is reached without an operator decision, a required aggregate
checkpoint cannot be captured, analytics pauses, preview asks for production
credentials, a real token appears in telemetry, migration 134 is present,
migration 136 appears absent, the 90-day retention job fails, or backend/
measurement behavior changes during a window.
