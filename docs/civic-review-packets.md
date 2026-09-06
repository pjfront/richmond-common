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

The producer writes only whitelisted draft and decision fields. Evidence cannot name SQL, a callback, or an action executor. If the decision insert fails, its new draft rolls back too. It does not alter migration149 or require migration150.

Validation: `pytest tests/test_civic_review_packets.py`; the real writer also runs through `tests/civic_review_packets.integration.py` against the same disposable PGlite0.5.8 runtime as the permission tests. That executable covers actual service grants, private drafts, refresh versions, stale approvals, publication, rejection suppression and transaction rollback. The database-permissions CI job runs it with Python and psycopg2-binary.

## Follow integration: implemented, delivery activation pending

The original September 6 plan required one coherent extension of the subscriber system: atomic subject signup and management, explicit council-email consent, and identical selection in initial and recovered weekly delivery. Migration150 and the accompanying application change now implement that contract. No new accounts, authentication service, sender, or polling schedule were added.

New story/election followers select a named subject with general council mail off. Existing subscribers retain their council defaults and use their private management link to change them. Public email-only signup cannot overwrite an active subscriber's choices. Saved district/candidate choices remain local context and are explicitly labeled as not affecting delivery.

The story and election CTAs say that choices can be saved and that weekly delivery has not started. The broadcast code gate remains false. See [Subject follows and delivery activation](subject-follows.md) for consent semantics, exact publication checks, rollback behavior, validation, and the remaining activation steps. The packet producer itself still requires only migrations148 and149.
