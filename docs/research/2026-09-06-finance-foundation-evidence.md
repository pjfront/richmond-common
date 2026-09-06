# Finance foundation — September 6, 2026

This change preserves Richmond, California finance reports before deriving a public money view. It does not silently rebuild or overwrite the legacy contribution table.

## Verified defects and current source scope

Read-only production inspection found 11 reversed 2026 Form 497 Part 2 records and one source assertion missing from the legacy table. The missing record is the May 18 $30,000 gift from Richmond Police Officers Association PAC (951606) to Safe Richmond Neighborhoods (1490887), filing 216787856. The original May 12, May 18 and May 29 reports each disclose a separate $30,000 gift and have unchecked amendment boxes. The three reports total $90,000; the legacy table retained $60,000 pointing in the wrong direction. No production data was changed by this audit.

- [May 12 report](https://netfile.com/Connect2/api/public/image/216765092)
- [May 18 report](https://netfile.com/Connect2/api/public/image/216787856)
- [May 29 report](https://netfile.com/Connect2/api/public/image/216841017)

The official [Connect2 transaction enum](https://netfile.com/Connect2/api/public/campaign/list/transaction/types?format=json) identifies 21 as F497P2 (contributions **made**), 20 as F497P1 (received), 19 as S496 (independent expenditures) and 4 as F496P3 (new funders received). The unrelated legacy-upload enum has different values and must not be substituted.

The bounded source acquisition requests non-superseded transactions explicitly and validates pagination counts and unique original transaction IDs. It fetches filing metadata with explicit `amends`, `amendedBy` and amendment sequence, preserving metadata and original transaction payloads in an immutable private assertion ledger. Local Form 496 PDFs are stored deterministically. A recognized PDF checkbox layout verifies candidate support/opposition; unrecognized or ambiguous layouts remain pending, without model calls.

The first acquisition returned 1,265 electronic assertions across 1108 Schedule A receipts, 3 noncash records, 7 Form 496 funder records, 19 Schedule B1 loan records, 32 independent spending records, 84 received late reports and 12 made late reports. The 32 independent spending records came from 13 PDFs. Coverage remains explicitly **partial** because paper reports, disclosures filed only with other agencies and periodic independent expenditure schedules are outside this first acquisition. Form 496 has no election-date field: no election is inferred from a committee name or activity date.

## Public contract and reconciliation

`finance_public_events` exposes event key, scope, source, kind, reported donor/recipient names and FPPC IDs, reporting filer name/ID, signed amount and amount kind, activity date, verified target/stance, nullable election date, description, filing IDs, source links, reconciliation status and D1 provenance. It excludes raw payloads, addresses and assertion IDs. The reporting filer is the spender on an IE; donor fields remain null because the spender is not necessarily the original funder.

`finance_public_coverage` exposes source, form, stable scope `0660620:calendar-2026`, checked time, covered activity dates, counts, pending count and explicit limitations. A zero matching amount must not be presented as evidence of zero undisclosed activity. Never add legacy contributions to these events as though they were separate money.

Unique exact cross-report claims may form one event; same-role repeated gifts survive. Exact reported names can bridge a missing donor ID only where the retained assertions supply one unambiguous ID for that name. Multiple possible matches are held for review. Near-date disagreement never authorizes deletion: the periodic recipient statement remains visible and the unmatched rapid/outgoing assertion waits for review. Negative adjustments stay signed and are not automatically described as cash refunds. Noncash and Schedule B1 values stay separate from monetary receipts; B1 is not a net-new-loan total.

Known mayor committee IDs are Ahmad Anderson 1481105 and Claudia Jimenez 1488504. Safe Richmond Neighborhoods is 1490887. The legacy database already has that committee under its exact legal name with a `Pending` identifier. The targeted repair updates that existing row from verified source identity; it does not create a duplicate committee.

## Run and verify

Apply migration 148 and its byte-identical timestamp mirror through the project migration workflow. The CLI defaults to read-only acquisition:

```sh
python src/finance_sync.py --year 2026 --through 2026-09-06 --dry-run --report tmp/finance/summary.json
python src/finance_sync.py --year 2026 --through 2026-09-06 --apply
python src/finance_repair_audit.py --year 2026 --through 2026-09-06 --report tmp/finance/repair.json
```

The import writes document evidence, assertions, projection and coverage in one transaction. Incomplete pagination or metadata/PDF acquisition aborts before replacing a prior snapshot. Raw finance documents also have restrictive public RLS so addresses cannot escape through the document lake. ACLs revoke public mutations and TRUNCATE, which bypasses RLS. Even service_role cannot delete/truncate assertions or rewrite raw evidence. The original near-date deletion entry point is retired, including its CLI.

Validation: 110 targeted Python tests pass, covering source direction, repeated gifts, exact and ambiguous matching, explicit amendment amount changes, negative/noncash/loan distinctions, PDF stance verification, incomplete acquisition, original source identity, November dates and manifest contracts. A separate PGlite run executes actual PostgreSQL DDL twice and passes 41 access, replay, immutable-evidence and public-projection assertions. It begins with broad Supabase-style default grants and checks anon/authenticated cannot mutate or truncate any finance table. Production checks were read-only and printed no personal donor/address fields.

November activity/deadline pairs are July 1–September 19 / September 24, September 20–October 17 / October 22, and October 18–December 31 / February 1, 2027. Rapid reporting runs August 5–November 3. [FPPC official local candidate schedule](https://www.fppc.ca.gov/siteassets/documents/tad/filing_schedules/2026/2026_local_nov_01_cand_final.pdf).

## Bounded compatibility repair and daily refresh

`repair_2026_part2.py` covers exactly twelve identified, unamended Form 497 Part 2 transactions. It requires the retained source ledger first. The read-only production simulation found 11 reversed legacy rows, one missing recipient-backed May 18 receipt, and one exact committee identity update from `Pending` to 1490887. Safe Richmond Neighborhoods already exists under its exact reported name; its identifier needs correction. The script uses both the source FPPC ID and exact committee name where historical cycles share an identifier (Bana's 2022 and 2026 committee records are an example).

The source-evidence proof hash, computed from sorted `(record_key, content_hash)` pairs for the twelve original assertions, is:

`33357d66c6995b1e419e489ca40efb29e8cbc526200a7a2735b29ba7230f6fbb`

After migration and the bounded finance import, run a fresh preview against the persisted ledger. Its `source_evidence_hash` should match that proof; its `state_hash` additionally includes actual database UUIDs, all relevant legacy values and proposed actions. The local simulation used placeholder assertion UUIDs, so its state hash must not be used to apply a live repair.

```sh
python src/repair_2026_part2.py --report tmp/finance/part2-preview.json
python src/repair_2026_part2.py --apply --expected-state-hash <state_hash-from-that-preview> --report tmp/finance/part2-applied.json
python src/repair_2026_part2.py --report tmp/finance/part2-after.json
```

Expected first preview: 11 reversed projections, 1 missing receipt, 1 committee identifier update. Expected post-repair preview: zero remaining changes. Apply holds a serializable transaction, source advisory lock and legacy-table write locks. Original legacy rows and the committee identity are archived into immutable private `finance_assertions` before their projections change. An altered source, ambiguous identity, changed preview or database constraint failure aborts the transaction. Outgoing-only and pending reports stay in the dedicated ledger; they do not become additional candidate receipts. The regular legacy loader rejects Form 497 Part 2 to prevent recurrence.

These are the precise changes to **legacy 2026 row sums**, not newly certified campaign totals:

| Committee | Before | Change | After |
|---|---:|---:|---:|
| Safe Richmond Neighborhoods | $305,000 | +$30,000 | $335,000 |
| Richmond Police Officers Association PAC | $220,675 | −$102,500 | $118,175 |
| Independent PAC Local 188 IAFF | $10,000 | −$7,500 | $2,500 |
| United Teachers of Richmond PAC | $116,500 | −$2,500 | $114,000 |

Candidate committee row sums remain unchanged. Other legacy defects, paper-summary adjustments and historical reconciliation are outside this twelve-record repair. The three source-verified RPOA-to-Safe-Richmond gifts total $90,000 after restoration.

The final electronic snapshot produced 1,178 public events and 12 pending assertions: nine ambiguous cross-report multiplicity cases and three date disagreements. Source-verified 2026 Form 496 activity totals $155,000 supporting Ahmad Anderson from Safe Richmond Neighborhoods, $92,456.14 supporting Claudia Jimenez from East Bay Working Families, and $36,712.90 supporting Doria Robinson from that same committee. These are rapid-report activity sums, not November-attributed or complete independent-spending totals.

`Data Sync` now includes an independent daily finance ledger job on the existing daily schedule. It receives only the database credential, calls no model provider, logs metadata/PDF request counts and byte volume, and preserves prior coverage on failure. Initial acquisition downloads 13 PDFs; content hashes deduplicate stored evidence. Cross-run HTTP caching is a later optimization, not a correctness dependency. API responses that lack valid pagination metadata, include superseded reports, or return incomplete pages cannot replace a snapshot. Neither an incomplete form set nor an earlier coverage cutoff can replace a current calendar projection.

The guarded repair has five focused Python tests plus a second isolated PostgreSQL test that executes the Python writer's actual parameterized SQL. It verifies all 11 removals, the one restoration, all 12 immutable before-state backups, the identifier update, and complete rollback when the final receipt insertion is forced to fail a foreign key constraint. Nothing in this worktree has applied the repair or migration to production.

The import uses 250-row batches for documents, source assertions, public events and coverage. It looks up document hashes and retained assertion versions in bulk, skips unchanged immutable evidence entirely, and only deactivates superseded selection state. A third PostgreSQL proof executes the Python batch writer's actual parameterized SQL on 503 assertions and 504 documents: 17 database roundtrips on first import, 11 on an unchanged replay, and 13 with an amendment. It verifies unchanged bytes, all document/assertion references, preserved original and amended amounts, correct public row selection, and complete rollback when the final coverage batch fails. The 1,265-assertion current source snapshot requires approximately 25 database roundtrips rather than thousands. Concurrent identical document inserts resolve through the existing content-hash uniqueness constraint.
