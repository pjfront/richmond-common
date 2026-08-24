# Bounded Official-Minutes Repair Plan

**Status:** Prepared only — not executed

**Publication tier:** Operator-only (pipeline repair)

**Production writes in this change:** None

## Purpose

Repair four proven 2026 City Council minutes records after the loader fix that
persists `documents.source_url` into `meetings.minutes_url`. The repair must use
the already persisted Tier 1 Archive Center artifact, remain allowlisted to the
four records below, and stop before touching any other meeting.

## Fixed cohort and current evidence

| Meeting | Meeting ID | Archive document | ADID | Current state | Planned treatment |
|---|---|---|---:|---|---|
| 2026-04-07 | `d91e5def-d612-41cf-9708-cac35b363f31` | `ed04cd05-c02b-409f-9db8-8bcbc85513e0` | 17484 | Official minutes loaded; URL was not copied to the meeting | Reload the existing current extraction through `load_meeting_to_db`; no LLM call |
| 2026-04-21 | `555c2fd6-a0f0-440c-9a81-639d00d38a1f` | `1de70571-df7f-4b75-8a89-bc6f9286a9b6` | 17532 | Official minutes loaded; URL was not copied to the meeting | Reload the existing current extraction through `load_meeting_to_db`; no LLM call |
| 2026-04-28 | `38be49b9-7bab-410a-a08f-4e797d4a516a` | `ee9f7149-5720-406d-b3c2-d2229f4fb603` | 17546 | City minutes artifact exists, but the current extraction lacks meeting identity and never loaded; meeting still has transcript motions | Re-extract this one persisted raw document with DeepSeek V4 Pro, validate, then load atomically |
| 2026-06-16 | `44f652b6-d6f9-4225-a01c-a1fb2162c02f` | `33a4930c-d149-4a1c-885d-0292fdd2321b` | 17676 | Official minutes loaded; URL was not copied to the meeting | Reload the existing current extraction through `load_meeting_to_db`; no LLM call |

The source URL for each row is
`https://www.ci.richmond.ca.us/Archive.aspx?ADID=<ADID>` as persisted in
`documents.source_url`. Do not reconstruct or hand-enter it during repair; the
loader now derives it from the document row in the same transaction.

## Execution packet for a later session

1. Start from the merged loader fix and open a read-only transaction. Select
   only the four meeting IDs and four document IDs above. Abort unless every
   document is `source_type='archive_center'`, `credibility_tier=1`,
   `metadata->>'amid'='31'`, has the expected ADID/source URL, and has minutes
   structural markers in `raw_text`.
2. For April 7, April 21, and June 16, read the current
   `extraction_runs.extracted_data` for the exact document ID. Abort if its
   `meeting_date`, `meeting_type`, or target meeting ID differs from the table.
   In one transaction per record, call `load_meeting_to_db(...,
   official_minutes=True, document_id=<allowlisted-id>, commit=False)`, assert
   the returned meeting ID, verify `meetings.minutes_url` equals the persisted
   `documents.source_url`, then commit. This path performs no paid extraction.
3. For April 28 only, read the source-closest persisted
   `documents.raw_text` for document
   `ee9f7149-5720-406d-b3c2-d2229f4fb603`. Run the established minutes
   extractor on DeepSeek V4 Pro with `RICHMOND_EVENT_BUDGET_USD=0.05`. Abort
   unless the result says `meeting_date='2026-04-28'` and
   `meeting_type='regular'`. In one transaction, save the new extraction run
   and call the same official-minutes loader; assert that it returns meeting
   `38be49b9-7bab-410a-a08f-4e797d4a516a` before committing.
4. Re-run the one liveness expectation
   `past_meetings_have_minutes_within_45_days`. The repaired four must be
   absent. As of this plan, June 23 and July 7 must remain failures because no
   authoritative published/loaded minutes evidence exists for them; those are
   genuine City publication delays, not repair targets.
5. Run only meeting-scoped downstream verification for the repaired cohort.
   Do not launch a full minutes sync, a historical backfill, or a broad
   enrichment cascade. Any recap regeneration belongs to its separately
   bounded repair task.

## Stop conditions

- More or fewer than the four allowlisted records are selected.
- A document ID, ADID, meeting date/type, source URL, or returned meeting ID
  differs from the table.
- April 28 extraction exceeds the `$0.05` event cap or lacks a valid meeting
  identity.
- The operation would require a schema migration, migration 134, a broad
  S26/S28 expansion, an unbounded sync, or correction of any other production
  record.

This plan intentionally leaves production unchanged until a later bounded
repair is explicitly in scope.
