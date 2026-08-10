# S29 November demand test

**Status:** Implementation runbook; results remain operator-only
**Window:** Two bounded 14-day observations after the S29 production deploy
**Public experiment surfaces:** Homepage, the upcoming November election page,
and existing subscription forms

## Question

Does making the current election and meeting record easier to find lead Richmond
residents to use the public record and subscribe for future briefings?

This is a demand test, not a traffic-growth program. It does not authorize paid
promotion, automated outreach, new tracking identifiers, or broader S26/S28
work.

## Privacy boundary

Vercel Web Analytics supplies aggregate page views, daily visitors, routes,
referrer domains, and same-day session behavior without cookies. Richmond
Commons strips query strings and fragments before analytics events leave the
browser, and does not send search text, addresses, email addresses, preference
tokens, or operator activity.

Vercel resets its anonymous visitor hash every day. The test therefore does not
claim to measure cross-day returning residents. Bounce rate and multi-page
sessions are reported only as a **same-day engagement proxy**. Adding a durable
browser identifier or fingerprint is outside S29.

Subscription attribution is a coarse allow-listed placement stored with the
subscriber record (`homepage`, `meeting`, `november_election`, `subscribe_page`,
`nav`, or `footer`). It never stores a raw referrer or page URL.

## Test A — front-door exposure

Compare the first 14 complete days after the S29 production deploy with the 14
complete days immediately before it.

Measure:

- homepage, meeting-index, council-index, district-finder, and upcoming-election
  page views;
- Vercel daily visitors, labeled exactly as daily visitors rather than weekly
  uniques;
- referrer domains and direct traffic;
- bounce rate and multi-page sessions as the same-day engagement proxy; and
- new active subscriptions, split by coarse acquisition placement.

The code change is the treatment: search-first homepage, three direct civic
paths, and subscription access from the main acquisition surfaces. There is no
random assignment and no attempt to identify a person across visits.

## Test B — November election subscription path

For the same post-deploy window, measure visits to the upcoming November
election page and new subscriptions attributed to `november_election`.

Report the descriptive conversion ratio:

`new november_election subscriptions / November election page views`

At Richmond Commons' current traffic, do not present the ratio without its raw
numerator and denominator. If the page has fewer than 50 views, label the result
"insufficient exposure" and extend observation instead of inferring that the
page or subscription offer failed.

External posting is not part of this code test. A future Nextdoor, Facebook,
partner-newsletter, or direct-email distribution test requires the operator to
choose and publish the message. Its results must remain a separate source cohort
rather than being blended into this organic baseline.

## Operator-only results packet

Copy this section for the closeout note.

| Field | Baseline 14 days | S29 14 days | Notes |
|---|---:|---:|---|
| Homepage views | — | — | |
| November election views | — | — | |
| Meeting-index views | — | — | |
| Council-index views | — | — | |
| District-finder views | — | — | |
| Daily visitors (sum; not deduplicated across days) | — | — | |
| Same-day multi-page sessions | — | — | Engagement proxy only |
| Bounce rate | — | — | |
| New active subscriptions | — | — | |
| Homepage subscriptions | — | — | |
| November-election subscriptions | — | — | |
| Meeting subscriptions | — | — | |
| Top referrer domains | — | — | Aggregate domains only |

Record the production deploy commit, exact UTC window boundaries, any outage,
and any external coverage or link that materially affected traffic.

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
- **Residents reach several record pages in one day but do not subscribe:**
  preserve free browsing; investigate whether email is the wrong retention
  surface before building donation conversion.

Every conclusion must cite the raw counts above. No production-data correction,
unbounded sync, broad S26/S28 expansion, or donation ask is authorized by this
runbook.
