# Search-first Richmond Commons relaunch

Created October 3, 2026. Target: a reviewed public release by November 3, 2026, in the operator's America/Los_Angeles calendar. This is a release target, not a scheduled deployment or recurring automation.

## Accepted scope

The operator approved a narrower resident experience built around four connected kinds of records:

1. Agenda items, preserving their official title, plain-language explanation where supported, meeting context, and original documents.
2. Tags, using the existing categories and topic labels to filter and follow items.
3. Recorded votes on each item, preserving individual motions and vote sources. One item can have multiple motions; do not collapse them into a guessed single outcome.
4. Campaign donations and other reported financial activity, with date, committee identity, source filings, and coverage limits.

Search is the front door. Meetings remain a secondary browse path. The small navigation is Search / Meetings / Money. Broader profile directories, election-guide navigation, stories, commissions, scanner displays, and subscription features do not lead the relaunch interface. Retain their evidence and recoverable routes instead of deleting the underlying work.

Campaign money is reported about people and committees. A donation is not automatically related to an agenda item. Name similarity, a shared address, or nearby dates do not establish identity, control, or the reason for a vote. A source-backed relationship may be shown with its limits; speculative associations may not.

## Existing infrastructure and cost boundary

Use the current Python ingestion, PostgreSQL/Supabase records, Next.js frontend, and deliberate Vercel deployment path. No new database, Supabase branch, migration, hosting service, paid preview, provider account, plan upgrade, or increased inference cap is needed for the first staged slice. Do not silently drop retained source artifacts or downgrade an oversized database.

The private staging branch can read existing public data using only the public Supabase URL and anonymous key. It cannot receive a service-role key, database password, model-provider key, email credential, operator credential, or API write secret. Site access uses the project's own password-only form and a short-lived HttpOnly session cookie. The stage's site-access password is separate from operator authentication.

The normal preview guard continues to reject production resources. A separately explicit read-only mode must bind the exact staging branch and source SHA, admit only the existing public read configuration, and preserve credential denials. Runtime routing separately denies mutation methods and all unsupported API/operator paths. Automatic Git deployments stay disabled.

Password protection, private/no-store responses, noindex metadata, robots exclusion, and an empty staging sitemap serve different purposes. Verify all of them; a crawler directive does not protect access.

## Current staged slice

- Search-first home and search pages render the same explicitly submitted search component.
- The homepage selects the search-first design only in read-only staging mode. The existing resident home, including its sourced notices and calendar-outage fallback, remains available in the normal site configuration until an intentional public relaunch.
- A small shared header retains search on every allowed page; the footer offers a page-link copy action.
- Existing meeting inventory, meeting detail, and exact item-detail URLs remain the browse and evidence paths.
- `/money` uses the existing public finance snapshot, filters, source coverage, and original filing links. It does not compute a fundraising total from filtered transactions.
- The first search API uses existing public read paths and bounded question patterns. Supported interpretation and source-read failures are visible. No model-generated answer or arbitrary semantic understanding is implied.
- The staged layout omits analytics, operator-session probing, subscription and feedback providers. Meeting subscription actions are hidden in read-only mode; correction buttons are absent when their feedback provider is unavailable.
- No credits, accounts, checkout, payment webhooks, or monthly paid-query allowances are functional in this slice.

Implementation in a branch is not proof of a working hosted preview. Build, source, access, and browser verification must be recorded before declaring this slice ready.

## Delivery sequence

| Window | Work | Completion evidence |
|---|---|---|
| October 3–9 | Private staged shell; items/votes/money search; exact item links; meeting browse; same-data read-only environment. | Protected preview opens at the verified source SHA. Unauthorized requests cannot read page/API data. Supported searches and real source links work on mobile and desktop. No mutation, session probe, email, or model request is made. |
| October 10–16 | Natural-language retrieval and structured question coverage. Test topic/date/name parsing, vote questions, donation recipients, committee direction, and the distinction between contributions and outside spending. | A representative source-backed question set shows what is supported, correct, partial, missing, and ambiguous. Dates and identities are validated before query execution. Money/vote totals use exact structured evidence, never the top semantic matches. |
| October 17–23 | Search quality and source integrity; accessibility, navigation, failures, coverage, and operational costs. | Queries reproduce source records; unavailable reads remain distinct from empty results; the interface reflows at 320px and 200% zoom, supports keyboard navigation, and announces changing results. Costs are measured per successful generated answer if inference has been introduced within an authorized budget. |
| October 24–31 | Review the release candidate; resolve meaningful search failures; decide whether measured costs and use justify credits at launch. | Ready/held decisions are explicit. Production source/data/schema compatibility and the prior deployment are captured. No placeholder balance or checkout is presented as working. |
| By November 3 | Deliberate public relaunch when the evidence is ready. | Exact deployed source and public end-to-end behavior are verified; privacy settings change only in the intentional public release. If a core requirement remains unverified, report the hold and revised scope/date instead of opening automatically. |

The windows are targets, not elapsed-time authorization. Complete independent work while a genuine identity, source-claim, provider, or payment decision is pending. Use the existing delegation for implementation and verification; do not recreate repetitive exact-label or exact-SHA approval rituals that the active plan already superseded.

## Search design and quality

Use the raw source and structured data as the evidence. Existing full-text and vector indexes can retrieve candidate items. Topic similarity does not establish a vote tally, an accounting total, a complete history, or a donor's identity. Route those questions to exact structured read paths and show the covered period.

Start with representative Richmond questions, including housing decisions, Point Molate motions, an official's recorded votes, contributions to a named campaign, a committee printed on a mailer, and a question with no supported result. Include multiple motions on one item, amendments, signed adjustments, loans, ambiguous names, missing records, and failed source reads. Verify expected answers against official minutes or filings rather than comparing one derived summary with another.

Generated research answers, when implemented, must cite the particular records supporting each factual claim, expose the query's coverage, identify generated content, and decline unsupported conclusions. Avoid unbounded chat sessions or arbitrary SQL execution. Keep a defined read-only query contract and request/response bounds.

The preview's deterministic question patterns are useful for testing this flow, but do not satisfy unrestricted natural-language search. Do not announce that unrestricted capability until representative retrieval and answer tests support it.

## Item-specific vote source-review hold

Read-only QA on October 3 found a source conflict for agenda item `9cf375c8-edc1-413c-8ee0-6485348fbc6f`, meeting `5f560013-daea-499a-8ecd-ca1a089c8a0c`, March 2, 2010, item J-2. The working [official minutes PDF, page 9](https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809#page=9) records the original motion approved: ayes Bates, Butt, Lopez and Rogers; nay McLaughlin; abstentions Ritterman and Viramontes; no absent members. Stored extraction rows instead attribute an abstention to Beckles and an aye to Tom Bates, omit Lopez and Viramontes, and assign a failed result to a second motion without a recorded failed vote in the minutes. Do not invent replacement identities or infer a vote on that substitute proposal. The legacy `Archive.aspx?ADID=2809` link returned 404 in earlier bounded QA but 200 in a later check; treat its availability as intermittent and use the working ArchiveCenter PDF for this hold.

Both stored motions are held on staging search, meeting browse and item detail, including their outcomes, tallies, individual votes and generated explanations. This item's generated `summary_headline` and `plain_language_summary` are suppressed as well. Its official title, meeting context and source links remain available with a visible source-review reason. The shared guard at `web/src/lib/stage-vote-source-review.ts` uses `stageVoteSourceReviewForItem` and `holdStageVoteSourceRecords`, matches the exact item ID, meeting ID and item number, and exposes `reason`, `checkedAt` and `sourceUrl` through `voteSourceReview`. It applies before search results or `getMeeting`/`getAgendaItemDetail` data reach page props. Vote-search totals are withheld when a returned item has held records.

This is a read-only presentation hold, not a database repair or a new verified vote record. Minutes-derived records are labelled "Extracted from official minutes" with an automated-extraction accuracy caveat; a minutes origin alone does not establish verified accuracy. The current extraction schema's motion-result enum permits only `passed|failed`; future source repair requires explicit unknown, withdrawn or unvoted states rather than forcing unsupported outcomes into that enum. No schema change, extraction rerun or database write is authorized by this QA.

## Credits proposal to validate

The proposed allowance is five free successful generated research queries per person per month, with additional use bought as prepaid credits. Treat this as a policy experiment, not a proven price or financial forecast. Record browsing, meeting navigation, tags, ordinary filters, and original source access remain free.

Define a chargeable unit before implementation: one completed, useful generated research response. Do not charge for typing, pagination, retries caused by a failure, denied/unsupported questions, or opening a source. Keep the allowance and remaining credits visible before a paid submission. Consider whether follow-ups belong to the same research request; do not surprise residents by charging for interface exploration.

Measure production inference costs, background ingestion costs, hosting costs, payment fees, and operator support time separately. Cached or deterministic record search may cost much less than a generated answer. Older business-plan estimates are historical assumptions, not the current operating baseline.

Only add accounts, a credit ledger, payment processing, and fulfillment after the price, payment-account ownership, fee impact, abuse handling, refund policy, and quota behavior are concrete and justified by use. No automatic credit reloads. Payment secrets and model secrets never enter the read-only staging environment. If credits are not ready, a bounded free pilot can launch with an honest limit; do not imitate a paid feature.

## Release evidence

- Preserve current raw records, ingestion contracts, public source permissions, and provenance-bearing exports. No migration is planned; migration 134 remains prohibited.
- Record exact source SHA, prior production deployment, included changes, required configuration, CI/build proof, and a rollback-compatible path. A successful merge does not establish a deployed site.
- Verify page and API access while signed out and signed in; method/path denial, cookie behavior, noindex/robots/sitemap, credential isolation, and the absence of writes/model/email calls.
- Verify the full resident path: search → correct item or money record → particular motion/vote or filing → original official source; repeat through meeting browse.
- Review empty, unavailable, incomplete, stale, and ambiguous data. Maintain visible source dates and coverage rather than promising complete history.
- Verify keyboard access, labels, result announcements, touch targets, contrast, and mobile/zoom reflow. Preserve correction/context handling before the public relaunch if the private preview intentionally omits feedback.
- Keep launch manual and intentional. Do not create a future automation that makes the site public merely because the target date arrived.
