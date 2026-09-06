# Subject follows and delivery activation

Status, September 6, 2026: implemented for the next release using migration150; weekly subscriber broadcasts remain disabled. Implementation and verification used disposable PostgreSQL, mocked providers, and a local browser without form submission. No live migration, signup, provider send, schedule activation, or billing change was performed.

## Resident choices

The existing email subscription and private bearer management link are reused. Four subject IDs are accepted in the UI, API, database, and digest selector:

| Subject | Destination |
| --- | --- |
| `chevron-settlement-and-city-budget` | `/stories/chevron-settlement-and-city-budget` |
| `fire-stations-and-emergency-response` | `/stories/fire-stations-and-emergency-response` |
| `flock-cameras-and-data-privacy` | `/stories/flock-cameras-and-data-privacy` |
| `2026-general` | `/elections/2026-general` |

The story and election CTAs carry their subject to `/subscribe?follow=<subject>`. The page and management form explain the intended weekly cadence: send when a followed subject has a newly published reviewed update. They explicitly say weekly delivery has not started. There is no email for every source poll or each operator approval.

`receive_council_updates` is a separate, explicit preference. Existing subscribers retain `true`; a new follow-only subscription starts with `false`.

| Council updates | Topics | Subjects | Delivery selection |
| --- | --- | --- | --- |
| On | Empty | Empty | Existing pre-meeting/recap mail; all meeting recaps in the planned weekly digest |
| On | Selected | Selected | Existing pre-meeting/recap mail; topic-matched weekly recaps plus matching reviewed subject updates |
| Off | Any | Selected | Only matching reviewed subject updates in the planned weekly digest |
| Off | Any | Empty | No update emails |

Topics filter weekly recap content; they do not filter the existing individual orientation/recap paths. Turning council updates off excludes those paths entirely, including signup orientation, broadcasts, and durable recovery. Welcome and management links remain available. District and candidate selections are saved context, not delivery filters; their form labels say this.

## Atomic signup and management

`activate_email_subscription_v2` validates and locks the email, then creates or reactivates the subscription, activation history, pending welcome, and requested subject in one transaction. Any preference failure rolls everything back. A follow-only reactivation replaces old choices with the requested subject and council updates off. General reactivation retains prior saved choices and enables council updates. Reactivation rotates the bearer token; old management links cannot update the new activation.

An email-only request for an already active subscription returns the same generic public success as any signup without changing its name, token, or choices or sending another welcome. Existing subscribers must use the management link already in their email. An inactive subscription belonging to another city is not reactivated by this Richmond endpoint.

`replace_email_preferences_v2` rechecks the active status and current bearer token while holding the subscriber lock and atomically replaces all supplied categories. Omitted new fields preserve their current values; an empty subject array explicitly clears subjects. The previous four-argument RPC replaces only the legacy categories, preserving subjects and council consent. All mutation RPCs remain service-only; anonymous/authenticated clients cannot read subscriber preferences or call them directly.

## Reviewed content and retry behavior

`loadPublishedDigestBriefs` and `selectSubscriberDigest` are shared by `/api/email/send-digest` and durable delivery recovery. They use the already completed Monday–Sunday UTC week, matching the existing digest contract. Eligibility is based on the brief's publication timestamp, not an agenda date, source filing date, or finance activity date. Only currently published, whitelisted, source-linked briefs are eligible, and subjects must match the recipient's current selections. No matching meetings or briefs means no update email.

Both email formats contain the exact reviewed text, publication timestamp, content version, source URLs/titles/tiers/dates, and a version-aware `/updates/<id>` link. That public detail page checks the exact current publication without using the six-item story feed or its cache, and links back to the continuing story/election page. Withdrawn or superseded versions show an explicit unavailable notice; a query failure gets a separate temporary-error notice. The email itself retains its quoted text and original source links. Public pages and emails label explanations “AI-written; checked against linked sources.” This describes the work performed without implying that a human, rather than an authorized AI delegate, checked it. Private publication actor values are not selected or rendered. Source/query failures stop delivery rather than become an empty successful week. Reads fail closed above 40 briefs per week or 200 briefs across recovery periods; existing subscriber, preference, meeting, retry, and provider-attempt caps are retained.

The consent-aware claim RPC checks active status, council consent, and each brief's exact ID, content version, publication timestamp, and current followed subject under database locks. Mixed digests explicitly declare whether they contain council content, preventing a council opt-out between selection and claim from receiving those recaps. Withdrawal, republication, or a changed version invalidates an earlier publication reference, even if the text itself did not change.

The existing durable delivery ledger, payload hash, provider idempotency key, and retry limits remain authoritative. Recovery reloads current approved sources and consent; if none remain, it cancels the attempt. If rebuilt content differs after a payload has been bound, the existing hash guard sends the attempt to manual review instead of substituting different content under the old key. This includes changed sources, publication identity, or recipient choices. An unchanged valid retry uses the same content key and provider identity. A pending welcome from before this release may similarly require review if its already-bound template differs.

**The database claim is the authorization boundary.** An unsubscribe, preference change, or withdrawal after that transaction commits cannot recall an already in-flight provider send. Delivered email cannot be withdrawn. This implementation does not claim otherwise.

## Rollback behavior

Migration150 requires the existing migration141 delivery system and migration149 reviewed briefs. Its mirrored Supabase filename is `20260906015000_subscription_subject_follows.sql`. It does not replace the delivery ledger or remove existing columns.

The original claim implementation is renamed `claim_email_delivery_v141` and made private, including revoking direct service-role execution. Its old public signature remains as a service-only consent-aware wrapper. This preserves council opt-outs if the frontend rolls back to the prior tracked-mail application: old orientation/recap/digest senders cannot bypass the new consent by omitting the new column. Such an old sender may report failed or skipped batches for follow-only residents; it cannot deliver their new subject updates. A rollback to an application predating the tracked delivery system is outside this compatibility contract.

## Verification and activation

Local checks include executable PGlite assertions for service grants, anonymous denial, transaction rollback, active-email idempotence, token rotation, legacy preference preservation, council opt-outs, private claim enforcement, publication identity, withdrawal/republication, and payload changes. Vitest covers API signup/management, shared selection, source caps/failures, source/version rendering, brief-only canary composition, and durable recovery. Provider calls in tests are mocked. The database-permissions CI job runs `tests/subscription_subject_follows.integration.mjs` using its existing pinned PGlite0.5.8 installation.

Before enabling real weekly delivery:

1. Apply migration150 through the trusted migration/preview process after141/149, regenerate `web/src/lib/database.types.ts` from the resulting schema, and deploy the application with `DIGEST_BROADCAST_ENABLED = false`.
2. Verify new general signup, follow-only signup, existing-active signup, management, unsubscribe/reactivation, and retries in an isolated preview. Confirm follow-only accounts are excluded from individual orientation/recap sends and the old tracked-mail rollback path. Use only test recipients/providers during this stage.
3. Run the existing explicitly authorized operator canary workflow against a reviewed completed-week fixture, including a brief-only week and verified source links. Confirm the provider result; an ambiguous outcome requires review and must not be blindly rerun. No such canary was sent during implementation.
4. Review a separate, paired activation change: deliberately enable the digest broadcast code gate, add the weekly schedule to the existing email workflow, and replace the rollout-not-started copy in `web/src/lib/subscription-subjects.ts`. Verify no duplicate scheduler or independent sender is introduced. This document does not authorize or perform that activation.

Public story pages work independently of mail activation. Saving choices is useful before launch, but no current CTA promises that weekly emails are already arriving.
