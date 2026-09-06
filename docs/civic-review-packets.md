# Automated source review packets

`src/civic_review_packets.py` turns new source evidence into a small operator inbox without a model call. It reads current immutable finance assertions and source-closest City Council agenda titles/URLs. It never reads generated recaps, topic labels, donor addresses, or legacy contribution totals. It does not publish, repair finance, send email, or change subscribers.

After migrations148 and149, run:

```sh
python src/civic_review_packets.py --section all
python src/civic_review_packets.py --section all --apply --max-packets 6 --report tmp/civic-packet-summary.json
```

The first command is a database-enforced read-only dry run. The report and stdout contain aggregate counts only. `--section finance` requires148+149; `--section stories` requires149 and the current agenda schema. Only2026 is supported by this initial election-focused producer. Dates use Richmond's timezone.

The daily finance job runs the second command only after `finance_sync.py --apply` succeeds. The existing serialized Data Sync workflow also covers the agenda packet scan; no second scheduler is needed. A failure preparing packets does not roll back the completed finance refresh. No live packet run was performed during implementation.

## What enters the inbox

Finance comparison packets show exact reported names, FPPC IDs, amounts, activity dates, forms and paired filing URLs. They explain ambiguous multiplicity, date disagreement, missing fields, or unverified independent-spending targets/stance. Comparison candidates require the same reported recipient ID, amount and amount kind, plus an exact donor ID or formatting-only reported name and dates within14days. That resemblance is a question to investigate, never proof of duplication. Approve/reject/defer records the judgment only. A tested extraction/reconciliation correction remains a separate engineering change; closing the note cannot change ledger totals.

Editorial drafts are deliberately narrow:

- The three reviewed story subjects receive exact agenda-title listings, bounded to14days before and21days after the run date. Retired, cancelled, non-council, unsafe-source and irrelevant listings are excluded. Agenda presence is never described as a vote or implementation outcome.
- `2026-general` may receive a small receipt note: at most five recently dated, positive monetary receipt events for a reported receiving committee/week. Exact matched report assertions count as one event. Loans, negative adjustments, noncash values and independent spending are excluded from this template. The text explains that it is a selection, not a campaign/election total or an affiliation claim. No minimum dollar threshold is applied.

Publication requires the existing operator approval RPC. Source-date fields in finance drafts are null because activity dates do not establish filing dates. The exact activity dates are shown in the proposed text and evidence.

## Bounds and persistence

The source scan stops rather than silently truncates beyond5000current finance assertions,100pending finance assertions, or1000agenda items. Each readable comparison/agenda packet displays at most8entries and states when more matched; its fingerprint includes all compared source versions. The default writes at most6changed packets, with a hard maximum of12per invocation and round-robin subject ordering.

Stable fingerprints exclude polling/extraction timestamps and generated database IDs. An unchanged packet stays suppressed after any decision status, including rejection. Changed pending/deferred drafts refresh in place in one advisory-locked transaction, advancing content and decision versions. Published and rejected candidates are preserved. If evidence reverts to a previously judged version, an intervening open publication proposal becomes an explicit engineering closure note rather than republishing that old judgment.

Every story run also rechecks the original source identity of all open story publication proposals, including older meetings outside the discovery window. Cancelled meetings, retired or removed agenda entries, unsafe sources and titles that no longer match the story cannot leave an unsupported proposal publishable. If no eligible agenda evidence remains, the proposal becomes an engineering closure note and its publish target is cleared. The previous private draft and readable source evidence are preserved. The existing decision-version trigger advances exactly once, blocking stale browser approval; repeated scans make no further change. Deferred decisions stay deferred. An already published candidate is never automatically withdrawn. If qualifying evidence returns while the closure note is still unjudged, a fresh private candidate requires another version-specific review; closed judgments remain suppressed.

Discovery and source rechecks share one repeatable-read snapshot. A failed fetch, malformed source identity, or truncated scan aborts before any packet writes. Rechecks are capped at100open proposals and1000source agenda rows and include cancelled/retired records. Safety withdrawals run before the new/changed proposal budget, so the six-packet discovery limit cannot leave the seventh unsupported draft publishable. Reports separately count `proposed_invalidations` and `invalidated`. This producer verifies the persisted source state; a failed upstream fetch must retain its last successful rows and must not pretend that an empty response is a confirmed deletion.

The producer writes only whitelisted draft and decision fields. Evidence cannot name SQL, a callback, or an action executor. If the decision insert fails, its new draft rolls back too. It does not alter migration149 or require migration150.

Validation: `pytest tests/test_civic_review_packets.py`; the real writer also runs through `tests/civic_review_packets.integration.py` against the same disposable PGlite0.5.8 runtime as the permission tests. That executable covers actual service grants, private drafts, refresh versions, stale approvals, publication, rejection suppression, transaction rollback and cancelled/retired/deleted evidence with unchanged polling timestamps. The database-permissions CI job runs it with Python and psycopg2-binary.

## Exact follow integration still required

The existing subscriber system is sufficient; no new accounts or authentication service are needed. Its bearer management link already identifies an active subscriber. However, saved district/candidate preferences currently do not affect delivery; only topic preferences filter the weekly digest and its recovery path. Orientation mail goes to all active subscribers. Adding a story checkbox alone would promise behavior the delivery system does not provide.

The remaining extension should be one coherent change:

1. Migration150 can extend `email_preferences.preference_type` with `subject`, restricted to the three story slugs above and `2026-general`. Add a versioned atomic replacement RPC with `p_subjects`; keep the existing four-argument RPC compatible so old clients cannot erase subject choices. Preserve service-only access and active-subscriber verification.
2. Extend `SubscriptionPreferences`, `PreferencesPanel`, `/api/subscribe/preferences`, and `/subscribe/manage` with these named subjects. Use the current management token. Do not let a public email-only signup overwrite an existing active subscriber's preferences.
3. Carry a whitelisted subject from `/subscribe?follow=<subject>` into the initial activation transaction for a new/reactivated subscriber. Use an atomic database contract, not a second best-effort insert. Existing subscribers use their email management link to confirm changes. Preserve generic public signup responses and unsubscribe-token rotation.
4. Add links to approved `civic_brief_candidates` in the existing weekly digest. Select only published versions and intersect subjects with the subscriber's selections. Keep existing topic-filtered meeting recaps as a separate preference category; an empty topic list must not unintentionally opt a subject-only follower into every meeting recap.
5. Apply the same selection contract to `send-digest` and `email-delivery` recovery. Bind content to the existing durable delivery/idempotency mechanism; do not add a second independent sender or send on every source poll. Test empty preferences, subject-only followers, withdrawn content, retries, and reactivation.
6. Only after that path is tested should a story/election CTA promise email updates. Until then, the site can link to the working general briefing without claiming story-specific delivery.
