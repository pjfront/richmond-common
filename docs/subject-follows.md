# Subject follows and delivery activation

This revision contains the paired weekly activation: the broadcast gate, Monday workflow and resident-facing cadence copy. It must remain held until the authorized representative canary is verified. See the [launch record](weekly-digest-launch.md) for current activation state and the [release evidence](research/2026-09-06-release-evidence.md) for deployed-source verification. Migrations 150 and 151 were already applied together from committed source `8db732ff3f3b92f2b875396da31ca6d9d9b3907b`; replay and production access/data-preservation checks passed. Activation needs no new migration or change to existing subscriber choices.

## Resident choices

The existing email subscription and private bearer management link are reused. Four subject IDs are accepted in the UI, API, database, and digest selector:

| Subject | Destination |
| --- | --- |
| `chevron-settlement-and-city-budget` | `/stories/chevron-settlement-and-city-budget` |
| `fire-stations-and-emergency-response` | `/stories/fire-stations-and-emergency-response` |
| `flock-cameras-and-data-privacy` | `/stories/flock-cameras-and-data-privacy` |
| `2026-general` | `/elections/2026-general` |

The story and election CTAs carry their subject to `/subscribe?follow=<subject>`. The page, management form and welcome email explain the conditional weekly cadence: Mondays at 16:30 UTC (9:30 a.m. PDT / 8:30 a.m. PST), when a followed subject has a newly published reviewed update. A scheduler may run late. There is no email for every source poll or each operator approval.

`receive_council_updates` is a separate, explicit preference. Existing subscribers retain `true`; a new follow-only subscription starts with `false`.

| Council updates | Topics | Subjects | Delivery selection |
| --- | --- | --- | --- |
| On | Empty | Empty | Existing pre-meeting/recap mail; all meeting recaps in the weekly digest |
| On | Selected | Selected | Existing pre-meeting/recap mail; topic-matched weekly recaps plus matching reviewed subject updates |
| Off | Any | Selected | Only matching reviewed subject updates in the weekly digest |
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

Migration 150 requires the existing migration 141 delivery system and migration 149 reviewed briefs. Its mirrored Supabase filename is `20260906015000_subscription_subject_follows.sql`. It does not replace the delivery ledger or remove existing columns. Migration 151 (`20260906015100_restrict_subscriber_table_access.sql`) removes public/API-role table privileges from subscriber records and preferences while preserving service grants, row policies, and RPCs. Both remain compatible with the existing server-backed tracked-mail rollback path.

The original claim implementation is renamed `claim_email_delivery_v141` and made private, including revoking direct service-role execution. Its old public signature remains as a service-only consent-aware wrapper. This preserves council opt-outs if the frontend rolls back to the prior tracked-mail application: old orientation/recap/digest senders cannot bypass the new consent by omitting the new column. Such an old sender may report failed or skipped batches for follow-only residents; it cannot deliver their new subject updates. A rollback to an application predating the tracked delivery system is outside this compatibility contract.

## Verification and activation

Local checks include executable PGlite assertions for service grants, anonymous denial, transaction rollback, active-email idempotence, token rotation, legacy preference preservation, council opt-outs, private claim enforcement, publication identity, withdrawal/republication, and payload changes. Vitest covers API signup/management, shared selection, source caps/failures, source/version rendering, brief-only canary composition, and durable recovery. Provider calls in tests are mocked. The database-permissions CI job runs `tests/subscription_subject_follows.integration.mjs` and `tests/subscriber_table_security.integration.mjs` using pinned PGlite 0.5.8. The latter starts with broad hosted-style defaults and checks all table privileges, including TRUNCATE, across anonymous, authenticated, PUBLIC-only and service roles.

Production application and replay preserved existing subscriber, preference, delivery and activation records. All seven API table privileges are denied on private subscription tables, service table grants are unchanged, service-only RPC access is verified, and direct access to the legacy claim core is denied. The initial subject-follow deployment kept `DIGEST_BROADCAST_ENABLED=false`; this paired activation changes it only after the exact canary check.

Before enabling real weekly delivery:

1. Verify the signup, management, unsubscribe/reactivation and retry contracts with the existing executable API/database tests and mocked providers. Confirm follow-only accounts remain excluded from individual orientation/recap sends and the old tracked-mail rollback path. These tests are not an actual subscriber signup or live provider delivery.
2. Complete the explicitly authorized canary against the reviewed completed-week fixture using the one-attempt procedure in the launch record. Verify the exact provider ID, configured destination, stored subject/body hashes and provider-reported delivery state. The authenticated proof endpoint exposes no email body, recipient address or provider key. An ambiguous or unavailable result holds activation; it must not cause another send.
3. Review and deploy this paired code/workflow/copy change after the canary passes. The existing workflow retains an owner-only empty canary event and adds a separate original-repository, trusted-main Monday job. Shared non-cancelling concurrency, an activated-capability check and one bounded broadcast request preserve the existing durable delivery path. Partial/uncertain results fail for ledger review; the scheduler does not blindly resend.

Public story pages work independently of mail delivery. A resident with no new matching content receives no weekly email. For a full delivery stop, disable the broadcast gate and schedule and handle any queued digest recovery through the existing guarded ledger; those first two switches cannot recall an in-flight provider send.
