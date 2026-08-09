# eSCRIBE Source Reconciliation Decision Packet

**Observed:** 2026-08-07
**Production project:** `ahrwvmizzykyyfavdvfv`
**Mode:** audit-only; public-source reads and Supabase read-only SQL only
**Decision:** **NO-GO for migration 134 and for an unbounded production full sync**

Migration 133 is working as the intended additive safety boundary. The next
cutover is not ready. The current draft would suppress material, valid public
history because it treats `legacy` (unclassified ownership) as if it meant
"owned and superseded by eSCRIBE." Those are not equivalent.

The exact production selectors used for this packet are preserved in
[`2026-08-07-escribe-reconciliation-readonly.sql`](./2026-08-07-escribe-reconciliation-readonly.sql).
They contain only `SELECT` statements and return every affected row, not just
the aggregates below.

## Executive evidence

The draft's own preflight predicates currently fail every material cutover
gate:

| Gate / candidate | Production result | Required before cutover |
|---|---:|---:|
| Complete, non-incomplete full sync in the last 48 hours | 0 | at least 1 |
| Meetings linked to an eSCRIBE GUID | 209 | context |
| GUID-linked meetings missing accepted sanitized raw proof | 209 | 0 |
| Active unsanitized eSCRIBE documents | 338 | reviewed replacements for all |
| Unsanitized documents without a replacement | 338 | 0 |
| Active agenda-owned items | 0 | nonzero, fully proven set |
| Active agenda-owned items missing revision proof | 0 | 0 |
| Active legacy items | 2,469 | not a safe global quarantine set |
| Active minutes-owned items | 9,514 | preserve |
| Active attachments with a NULL source revision | 7,945 | 0 or individually reviewed |
| Attachment quarantine candidates | 7,945 | not a safe global quarantine set |
| Proven current attachments missing DocumentId/hash | 0 | 0 |

If draft 134 ran against this snapshot, its expected public deltas would be:

| Public relation | Before | Draft loss | After | Loss rate |
|---|---:|---:|---:|---:|
| `documents` | 8,090 | 338 | 7,752 | 4.18% |
| `agenda_items` | 11,983 | 2,469 | 9,514 | 20.60% |
| `agenda_item_attachments` | 7,945 | 7,945 | 0 | **100%** |

The preflight correctly blocks this state. The issue is not a missing operator
confirmation; it is missing source proof.

The newest recorded full sync is from 2026-03-17, nearly five months outside
the gate. It fetched 243 meetings and skipped all 243 under the former
existence-based shortcut, so it supplied no migration-133 revision proof. The
2026-03-03 full run took 6,554.54 seconds (about 109 minutes) and recorded a
per-meeting timeout. A modern run needs bounded cohorts, durable progress, and
clone validation; historical `status='completed'` alone is not evidence of
authoritative coverage.

## Exact candidate-set identity

The ordered UUID fingerprints make snapshot drift visible while the companion
SQL returns the complete records:

| Set | Rows | Ordered-ID MD5 |
|---|---:|---|
| Active unsanitized eSCRIBE documents | 338 | `b7e1b648c1bc9d222446f405cc9a2764` |
| Active legacy agenda items | 2,469 | `0a1cc4ae8ed0ea1cb7ce010dfb963eff` |
| Active attachment candidates | 7,945 | `c4fe11aba71dbf2bb0354d352094cb78` |
| Clearly outside current full-reconciliation scope | 436 | `a4ceb6f6f37b7f879bea0809cfe60df8` |
| Plausibly within current eSCRIBE scope | 2,033 | `42747c0979da021c913a2389b287ea7a` |

These hashes identify the 2026-08-07 snapshot only. Re-run the read-only SQL
and record new counts/fingerprints immediately before any later clone or
production exercise.

## Three source cohorts

### 1. 2022+ loadable eSCRIBE agendas

The public calendar returned 257 meeting GUIDs: 232 `City Council`, 23
`Special City Council Meeting`, and 2 `Swearing In Ceremony`. An in-memory
structural parse made no attachment downloads and no database writes.

There are **160 structurally loadable agendas**, all from 2022 onward:

| Year | Loadable agendas |
|---|---:|
| 2022 | 36 |
| 2023 | 40 |
| 2024 | 31 |
| 2025 | 31 |
| 2026 | 22 |

Those pages declare **10,651 attachments**. This is a declaration count, not a
download verification. Production currently has 7,945 active attachment rows,
all with extracted text but none with the migration-133 revision or downloaded
content hash. A clone reconciliation must prove declared = downloaded = hashed
for each complete agenda before any old attachment becomes ineligible.

### 2. 2020-2021 portal stubs

All **94 eSCRIBE entries from 2020-2021** are calendar stubs: 45 in 2020 and 49
in 2021. Each page parses as one unnumbered item titled `Details`, with no
attachments. `load_meeting_to_db()` correctly rejects an authoritative agenda
with no structured item numbers. Consequently, the current full sync would
report at least 94 per-meeting errors and `retryable_incomplete=true`; it cannot
satisfy migration 134's recent-complete-full-sync gate.

These rows need an explicit `legacy_portal_stub` observation state. A stub
should produce a sanitized Layer-1 observation but must not overwrite,
reclassify, or retire Layer-2 agenda/minutes history.

Three additional source entries explicitly report no agenda:

| Date | GUID | Meeting |
|---|---|---|
| 2022-06-14 | `563b7bf8-ccbf-4021-909e-c8e7721be2b9` | City Council |
| 2024-08-13 | `bb3e2170-59bb-4687-af4c-f1be875d83f0` | Special City Council Meeting |
| 2025-01-14 | `ad235794-a743-4493-8950-ac987ee79f15` | Swearing In Ceremony |

`HasAgenda=false` without a cancellation is not, by itself, proof that a
previously unclassified historical item was withdrawn. The existing writer's
"awaiting agenda" behavior is the safe default unless a prior managed revision
exists.

### 3. Records the current source cannot blanket-quarantine

The 2,469 `legacy` items span **2005-2026** and 272 meetings. At least **436
rows (17.66%)** are clearly outside what the current full eSCRIBE run could
establish because one or more of these is true:

- the meeting predates 2022, including records back to 2005;
- the body is not City Council (96 Personnel Board, Design Review Board, or
  Richmond Rent Board rows); or
- the meeting's current document is not eSCRIBE (228 Archive Center or NULL
  meeting-document rows).

The categories overlap, which is why 436 is the union rather than their sum.
Meeting-level document provenance is only a scope warning, not proof of
row-level ownership. Even the remaining 2,033 rows cannot be retired merely
because their meeting currently points to an eSCRIBE document.

The full legacy distribution is:

| Year | Legacy rows | Year | Legacy rows |
|---|---:|---|---:|
| 2005 | 6 | 2020 | 93 |
| 2006 | 19 | 2021 | 136 |
| 2008 | 5 | 2022 | 542 |
| 2009 | 5 | 2023 | 523 |
| 2011 | 2 | 2024 | 457 |
| 2012 | 3 | 2025 | 297 |
| 2014 | 1 | 2026 | 350 |
| 2015 | 6 | | |
| 2016 | 3 | | |
| 2017 | 15 | | |
| 2018 | 6 | | |

## Raw-document and identity findings

The 338 active unsanitized document rows represent 249 distinct GUIDs. None
has a current sanitized accepted replacement. There are no NULL GUIDs, but 16
GUIDs have duplicate active rows (105 rows total). The largest leak is **44
active rows for the 2026-06-09 special meeting**
(`9030cd00-8f58-4a20-8e76-591b9dec7c29`). The next largest are 14 rows for
2026-07-28 and 13 for 2026-07-21. A successful GUID-based reconciliation
should leave exactly one current sanitized raw revision per GUID and retain all
older rows only for service-role audit.

The source has 257 GUIDs; production active documents cover 249 (96.89%). The
eight exact source GUIDs without an active production document are:

| Date | GUID | Meeting |
|---|---|---|
| 2021-03-23 | `bbd17186-799a-4134-9239-bf37b944459a` | City Council |
| 2021-07-20 | `1f29e092-b454-4e46-9509-9a5e7be610ce` | City Council |
| 2021-07-20 | `68291464-f066-4281-b17d-09ce95d681fe` | City Council |
| 2021-09-14 | `eaec43e4-4f72-4cd8-9d7b-b0c989e8531a` | City Council |
| 2022-07-19 | `6caff046-a09b-406f-a35d-7fcfea201792` | Special City Council Meeting |
| 2023-01-10 | `cbb3cbbd-c691-4890-a2f7-04258141e60e` | Special City Council Meeting |
| 2023-01-17 | `ab57dcf7-5a72-478a-88b1-415b63d8ae88` | Special City Council Meeting |
| 2026-08-11 | `c3c39254-53cc-4461-9b85-041288171803` | Special City Council Meeting |

Only 209 of 257 source GUIDs (81.32%) are currently linked on `meetings`.
That is not itself a reason to attach the remaining GUIDs by date: eSCRIBE has
three same-date/type collision groups that the current
`(city_fips, meeting_date, meeting_type, body_id)` unique key cannot represent:

| Date | Source sessions |
|---|---|
| 2021-03-23 | 18:30 `bbd17186-799a-4134-9239-bf37b944459a`; 18:45 `e4f93958-234f-4f18-b0d2-aa150b715a53` |
| 2021-07-20 | 09:15 `1f29e092-b454-4e46-9509-9a5e7be610ce`; 10:00 `68291464-f066-4281-b17d-09ce95d681fe`; 18:30 `3c672b4f-1a6f-4362-98fc-fcfdaf6c42f6` |
| 2021-09-14 | 13:00 `eaec43e4-4f72-4cd8-9d7b-b0c989e8531a`; 18:30 `4081cc6c-04d2-432b-bc9f-f1f1fa616310` |

These seven are stubs, so the smallest immediate repair is to keep them at the
Layer-1 observation boundary. Longer term, source GUID must be the primary
eSCRIBE identity and the date/body fallback must not merge distinct sessions.

## Public derivative impact if the draft were forced

Retiring the 2,469 legacy parents would also remove these rows from anonymous
reads through migration-133 child policies:

| Derivative | Rows affected |
|---|---:|
| Conflict flags | 2,777 |
| Topic assignments | 1,944 |
| Public comments linked to an item | 805 |
| Theme narratives | 247 |
| Votes | 35 |
| Motions | 5 |
| Agenda-item embeddings | 2,469 |

The attachment loss is especially unsafe: 3,769 of the 7,945 attachments have
minutes-owned parents, and 4,176 have legacy parents. Draft 134 would hide both
groups solely because their newly added revision/hash columns have not been
backfilled.

## False-positive and false-negative risks

### False positives (valid history hidden)

- Blanket `legacy` retirement suppresses records the source never observed,
  including pre-eSCRIBE history and non-council bodies.
- NULL attachment revision currently means "not backfilled," not "source
  removed." Treating NULL as a tombstone candidate hides every attachment.
- A meeting's current `document_id` does not prove every child item's source.
- Minutes-owned agenda outcomes can legitimately retain eSCRIBE source packets;
  agenda mutability must not erase adopted outcomes or their useful evidence.

### False negatives (stale or merged history survives)

- Existing stale eSCRIBE rows remain `legacy`, so the current writer only
  retires later omissions from rows already proven `agenda`-owned.
- Date/body fallback identity can merge multiple source GUIDs into one meeting.
- A failed full run commits per meeting. Later failure leaves a partially
  reconciled database even though the run is correctly marked incomplete.
- A transient attachment download failure cannot prove upstream removal.
- A long full run does not observe one global source snapshot; each accepted
  page needs its own revision and observed-at proof, plus an inventory hash for
  the run.

## Smallest safe repair sequence

1. **Keep migration 133 as the public boundary.** Do not apply or promote draft
   134, and do not run the current unbounded full sync against production.
2. **Make source observation complete without pretending stubs are agendas.**
   Record one sanitized current Layer-1 observation for every discovered GUID.
   Classify each as `complete_agenda`, `legacy_portal_stub`, or
   `no_current_agenda`. Only `complete_agenda` may enter authoritative Layer 2.
3. **Make eSCRIBE ownership row-specific.** Add durable source meeting/document
   identity to agenda-owned rows (separate from the `agenda`/`minutes`
   authority field). Backfill only exact source matches. Never infer ownership
   from meeting date, current meeting document, title similarity, or NULL.
4. **Fence the same-day identity collision.** Prefer stable source GUID for
   eSCRIBE rows and make the date/body uniqueness fallback apply only where a
   stable source identity is absent. Any minutes linkage that is ambiguous
   across same-day sessions must be explicitly resolved, not guessed.
5. **Reconcile attachments on a production clone.** For each complete agenda,
   require declared count = downloaded count, stable DocumentId, and byte hash.
   Upsert exact `(source GUID, item number, DocumentId)` matches. Retire an old
   attachment only when a complete later revision for that exact managed parent
   proves omission. Preserve all other NULL-revision rows for review.
6. **Define and test a genuinely complete full sync** using the contract below.
   Run it first on a fresh production clone. Then run the read-only selectors
   and the cutover draft with `COMMIT` replaced by `ROLLBACK`.
7. **Rewrite migration 134 around proven source scope.** Remove the global
   `agenda_source_authority = 'legacy'` quarantine. Snapshot exact reviewed
   source-scoped candidates and abort on any extra public loss. A nonzero
   attachment loss must be individually explained; a 100% loss is an automatic
   abort.
8. **Update migration 135 atomically with any later policy change.** Its two
   `SECURITY DEFINER` statistics functions intentionally reproduce the live
   migration-133 predicates because they bypass RLS. If a later cutover adds an
   authority/source predicate, both function bodies and their security test
   must adopt the exact same predicate in the same migration/PR, or the RPCs
   will bypass the new public boundary.
9. **Only after the clone packet is clean:** run the bounded reconciliation in
   production, re-run the snapshot, obtain the operator's cutover decision,
   and regenerate only derivatives whose source inputs actually changed.

The source scan and reconciliation use no LLM tokens. The expensive part is
downloading and hashing 10,651 declared files plus later derivative
regeneration; keep the latter behind the existing event/monthly cost caps.

## Complete-full-sync contract

Counts are a snapshot and may change as Richmond publishes meetings. A full
run is complete only when all of these hold for the inventory it observed:

- public calendar discovery succeeded and the run stored an inventory hash and
  observation timestamp;
- every discovered GUID has exactly one classified current sanitized
  observation;
- every `complete_agenda` has an accepted page revision and every numbered item
  has exact source GUID + revision ownership;
- for every complete agenda, all declared attachments were downloaded and
  hashed before its revision was accepted;
- stubs and no-agenda entries are explicit covered outcomes, not generic
  errors, and did not mutate Layer 2 without prior managed source proof;
- no two source GUIDs were merged through the date/body fallback;
- there is exactly one active sanitized raw document per current GUID; older
  revisions remain service-role-readable and are not hard-deleted;
- the source result has zero unclassified errors and
  `retryable_incomplete=false`; and
- `data_sync_log` records the classified cohort counts and completes inside the
  cutover's recency window.

For the 2026-08-07 inventory, that means 257 classified observations: 160
complete agendas, 94 legacy stubs, and 3 no-current-agenda entries. It does not
mean forcing all 257 through the agenda loader.

## Rollback considerations

The current cutover plan says rollback before migration 134 is code-only. That
is too optimistic for a full reconciliation: the writer commits each meeting
independently and can set document/item/attachment tombstones before a later
meeting fails. A code rollback does not reverse those persisted facts.

Before any production reconciliation, retain:

- a fresh production clone or equivalent recoverable database snapshot;
- the exact candidate IDs and prior authority/revision/retirement values;
- the run inventory hash and every accepted source revision; and
- generated restoration SQL that clears only tombstones introduced by that
  run and restores prior metadata values.

No source artifact should be hard-deleted. Migration 134 itself remains a
single serializable transaction, so a pre-commit failure can roll it back. Once
an enforcement cutover commits, rollback must restore its RLS policies,
source-scoped tombstones, and the matching migration-135 `SECURITY DEFINER`
predicates together.

## Verification performed

- Production queries used Supabase's read-only database query endpoint.
- Public eSCRIBE discovery and all 257 page parses ran in memory; no attachment
  files were downloaded.
- No production rows, environment variables, Vercel settings, or source files
  were mutated during evidence collection.
- `tests/test_source_freshness_reconciliation.py` and
  `tests/test_rollout_source_boundaries.py`: **23 passed**. The focused unit
  suites validate revision/tombstone and authoritative-identity mechanics but
  currently lack the live historical-stub, full-run completeness, same-day
  GUID collision, and global-legacy-cutover regressions identified here.
