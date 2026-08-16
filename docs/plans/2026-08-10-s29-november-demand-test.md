# S29 November demand test

**Status:** Implementation runbook; results remain operator-only
**Window:** One 14-day instrumented baseline, followed by one 14-day treatment
window
**Public treatment surfaces:** Homepage, the upcoming November election page,
and existing subscription forms

## Question

Does making an official meeting record, the current election, and the district
finder easier to reach change use of those public records or acquisition of
meeting-briefing subscriptions?

This is a demand test, not a traffic-growth program. It does not authorize paid
promotion, automated outreach, new tracking identifiers, or broader S26/S28
work.

## Privacy boundary

Vercel Web Analytics supplies aggregate page views, daily visitors, routes,
referring pages, and bounce rate without analytics cookies. Richmond Commons
strips query strings and fragments from its own page URLs before analytics
events leave the browser and does not send search text, addresses, email
addresses, preference tokens, or operator activity. Analytics waits for the
operator-session check before mounting, so an operator page view cannot race
ahead of that check.

Vercel can receive the full external referring-page URL when the source site
chooses to send it; Richmond Commons cannot sanitize that field through the
analytics `beforeSend` hook. Modern browser defaults usually reduce a cross-site
referrer to its origin. The operator report groups referrers to source domains
and never republishes referring paths. Whether accepting Vercel's underlying
full-referrer intake is appropriate remains an explicit privacy judgment before
the baseline starts.

Vercel resets its anonymous visitor hash every day. The test therefore does not
claim to measure cross-day returning residents. Adding a durable browser
identifier or fingerprint is outside S29. Search-query logging is disabled;
the legacy `search_queries` table is not a November measurement source.

Subscription attribution is a coarse allow-listed placement recorded in the
private `subscription_activations` ledger (`homepage`, `meeting`,
`november_election`, `subscribe_page`, `nav`, or `footer`). Each row identifies
an `initial` or `reactivation` event and stores its explicit activation time; it
never stores an email address, name, unsubscribe token, raw referrer, or page
URL. The subscriber row carries only the current activation marker.

Count both windows from `subscription_activations.activation_at`, split by
`activation_kind` and `acquisition_surface`. `email_subscribers` has no
`created_at`, and its `subscribed_at` is overwritten on reactivation, so neither
is a valid history source. Migration 140 deliberately does not backfill the two
legacy subscribers. Record the application cutover timestamp: subscriptions
made by old code between migration deployment and application deployment are
"not measured," never reconstructed or reported as zero.

## Required deployment sequence

This combined implementation must become two deployable production batches. A
single deployment cannot provide a valid pre-treatment baseline.

1. **Baseline batch:** deploy migration 140, then the activation recorder,
   dedicated bounded welcome/orientation recovery endpoint, privacy safeguards, and aggregate
   Vercel page-view integration. Record the migration and application cutover
   times. Keep the existing production homepage, navigation, CTA placement, and
   public metadata unchanged.
2. Observe exactly **14 complete UTC days**. Record the baseline commit and UTC
   boundaries before starting the treatment.
3. **Treatment batch:** deploy the S29 front door, sourced SEO, and coarse
   acquisition placement changes. Do not change promotion or public messaging
   during the observation window.
4. Observe exactly **14 complete UTC days**, then close the test.

If either window has a material outage, document the affected dates and report
both the full-window counts and a same-number-of-complete-days sensitivity view.
Do not silently move a boundary.

## Test A — front-door exposure

Compare the 14 complete treatment days with the 14 complete instrumented
baseline days.

Measure:

- homepage, meeting-index, council-index, district-finder, and upcoming-election
  page views;
- Vercel daily visitors, labeled exactly as daily visitors rather than weekly
  uniques;
- referrer domains and direct traffic;
- bounce rate; and
- subscription activations, split into first-time subscriptions and
  re-subscriptions, then by coarse acquisition placement.

The code change is the treatment: a truthful search prompt, three direct civic
paths, and subscription access from the main acquisition surfaces. A
re-subscription counts as a new activation for this demand test, but it must be
reported separately from first-time subscriptions. An already-active duplicate
signup is not a new activation. There is no random assignment and no attempt to
identify a person across visits.

## Test B — meeting-briefing acquisition from the November election page

For the treatment window, measure visits to the upcoming November election page
and meeting-briefing activations attributed to `november_election`. The CTA does
not promise election alerts, so this test must not be described as demand for an
election-alert product.

Report the descriptive conversion ratio:

`new or reactivated meeting-briefing subscriptions from november_election / November election page views`

At Richmond Commons' current traffic, do not present the ratio without its raw
numerator and denominator, including separate first-time and re-subscription
counts. If the page has fewer than 50 views, label the result "insufficient
exposure" and close the 14-day test without inferring that the page or offer
failed. Any later operator-chosen distribution test is a new, separately bounded
14-day cohort; it does not extend or overwrite this organic observation.

External posting is not part of this code test. A future Nextdoor, Facebook,
partner-newsletter, or direct-email distribution test requires the operator to
choose and publish the message. Its results must remain a separate source cohort
rather than being blended into this organic baseline.

## Operator-only results packet

Copy this section for the closeout note.

| Field | Baseline 14 days | Treatment 14 days | Notes |
|---|---:|---:|---|
| Homepage views | — | — | |
| November election views | — | — | |
| Meeting-index views | — | — | |
| Council-index views | — | — | |
| District-finder views | — | — | |
| Daily visitors (sum; not deduplicated across days) | — | — | |
| Bounce rate | — | — | |
| Subscription activations | — | — | First-time + re-subscriptions |
| First-time subscriptions | — | — | |
| Re-subscriptions | — | — | Report separately; count in activation total |
| Homepage briefing activations | — | — | Baseline may be not measured |
| November-election briefing activations | — | — | Treatment CTA offers meeting briefings |
| Meeting-page briefing activations | — | — | Baseline may be not measured |
| November briefing conversion ratio | — | — | Always include raw numerator and denominator |
| Top referrer domains | — | — | Aggregate domains only |

Record the production deploy commit, exact UTC window boundaries, any outage,
and any external coverage or link that materially affected traffic.

## Approved bounded C7 exception

Approved by the operator on 2026-08-15 for S29:

- General search covers meetings, topics, and council members; address entry is
  a separate, explicit link to the existing Find My District route.
- The homepage remains limited to three paths: a current/latest meeting with an
  official agenda, an upcoming election with trusted provenance, and the
  district finder. It does not carry forward an unsourced AI meeting summary or
  a flagged-item card.
- No top-level **Explore** link is added because Richmond Commons does not yet
  have the faceted overview route described by C7. Adding a label that points to
  a non-equivalent page would create false information scent. Revisit this
  exception only when that real route exists; it does not authorize broader
  S26/S28 work.

## Following-sprint decision

- **Visits and subscriptions both increase:** continue the acquisition and
  dependable-delivery path; do not expand the scanner or entity surface merely
  because traffic arrived.
- **Visits increase but subscriptions do not:** improve the subscription value
  explanation and delivery cadence before adding more acquisition channels.
- **Election traffic grows but other civic paths do not:** keep November work
  bounded to election entry, voting records, and dependable briefings.
- **Exposure is insufficient:** run one operator-chosen distribution test and
  repeat the same packet. Do not treat low exposure as product rejection.
- **Page use grows but subscriptions do not:** preserve free browsing;
  investigate whether meeting briefings are the wrong retention surface before
  building donation conversion.

Every conclusion must cite the raw counts above. No production-data correction,
unbounded sync, broad S26/S28 expansion, or donation ask is authorized by this
runbook.
