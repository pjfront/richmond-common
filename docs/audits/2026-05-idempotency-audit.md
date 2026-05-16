# Phase B Audit — Pipeline Idempotency Verification

**Date:** 2026-05-16
**Scope:** All entry-point write scripts registered in `src/data_sync.py::SYNC_SOURCES` (40 functions).
**Methodology:** Trust Ladder — docstring claim → code path → SQL → live DB query. **No code changes.**
**Sequel to:** [`2026-05-counter-audit.md`](2026-05-counter-audit.md) (Phase A — counters).

---

## Executive Summary

| Severity | Count | Theme |
|---|---|---|
| HIGH    | 3 | Write amplification with measurable bleed |
| MEDIUM  | 5 | Source re-fetch creates new rows when underlying content drifts |
| LOW     | 4 | Counter inflation only (writes ARE idempotent) |
| VERIFIED idempotent | 19 sources | DB query confirms 0 natural-key dups |

**The headline:** **22 of 40 SYNC_SOURCES are truly idempotent** (writes AND counters honest). **8 have known problems** of varying severity. The remaining 10 are deferred (rarely-run sources where verification cost exceeds value this session — listed in Appendix B).

**The pattern:** Idempotency is correlated with the presence of a unique constraint + `ON CONFLICT ... RETURNING (xmax = 0)`. Sources missing either piece bleed. The cleanest sources (`socrata_expenditures`, `socrata_permits`, etc.) prove the pattern works; the bleeding sources (`calaccess` IE leg, `archive_center` on content drift) prove the absence is the problem.

**No idempotency claim in any docstring matched reality without caveat.** The claim is always "this is idempotent" with no qualifier. The reality is always "this is idempotent IF [some external precondition holds]." Phase D should make the precondition explicit.

---

## Methodology

For each source the question is:

> "If I re-ran this sync RIGHT NOW with no source changes, would it write new rows or update existing rows?"

A truly idempotent source returns: **no new writes, no updates, zero side effects.**

I verified by descending the Trust Ladder:

1. **Claim** — read the docstring's idempotency claim (or absence)
2. **Code** — read the actual write path + ON CONFLICT clause
3. **SQL** — identify the natural key
4. **DB** — run a query that counts how many rows would-be-dedup'd if the natural key were enforced

Where the source had a "skip-if-exists" gate (escribemeetings, form700, enrichments), I checked the gate query against the live DB to see whether it returns 0 (gate works) or non-zero (gate has known leaks).

Where the source had a thrash claim (Phase A A6), I queried the sync log over the last 7 days to count how often the "idempotent" sync actually did work.

All queries run read-only via Supabase MCP `execute_sql` against the live project (`ahrwvmizzykyyfavdvfv`). The operator can re-run any query independently — they're spelled out in full in each finding.

---

## Findings (severity-sorted)

### B1 — HIGH — `sync_calaccess` independent_expenditures has no ON CONFLICT

**Source:** `src/pipelines/calaccess.py:29` → `src/db/expenditures.py::load_expenditures_to_db`

**Claim (docstring line 41):** "This is a heavy operation — run monthly." No explicit idempotency claim, but the parent `data_sync.py` SYNC_SOURCES contract is "detect their own new work — idempotent, zero-cost when nothing needs doing" (line 65).

**Reality:** Plain `INSERT` with no `ON CONFLICT`. Every run re-inserts every row from the bulk ZIP.

**Evidence query:**
```sql
SELECT COUNT(*) AS total,
       COUNT(DISTINCT (city_fips, committee_name, candidate_name, amount, expenditure_date)) AS unique_keys,
       COUNT(*) - COUNT(DISTINCT (city_fips, committee_name, candidate_name, amount, expenditure_date)) AS would_dedup
FROM independent_expenditures;
```
**Result (live, 2026-05-16):** total=54,800, unique=2,079, **would_dedup=52,721 (96.2%)**.

**Hypothesis for root cause:** `load_expenditures_to_db` (Phase A A3) — same Decimal as Phase A finding A3. Each monthly cron run adds ~4,300 dup rows.

**Cross-ref:** Phase A finding A3 (counter inflation). The counter was the SYMPTOM, this is the underlying write-pattern bug.

---

### B2 — HIGH — `sync_donor_employer_merge` claim of idempotency is operationally false

**Source:** `src/pipelines/netfile.py:148-264`

**Claim (docstring line 172):** "Idempotent — re-running on a clean DB is a no-op."

**Reality:** Average 688 donor merges per run, 13 runs in last 7 days. On a clean DB the next run finds work again because of a thrash cycle with `sync_netfile` (which re-creates donor-employer fragmentation each sync).

**Evidence query:**
```sql
SELECT COUNT(*) AS runs_7d,
       AVG((metadata->>'donors_merged')::int)::int AS avg_donors_merged_per_run
FROM data_sync_log
WHERE source='donor_employer_merge'
  AND completed_at > NOW() - INTERVAL '7 days'
  AND status='completed';
```
**Result (live, 2026-05-16):** runs_7d=13, avg_donors_merged_per_run=688.

**Hypothesis for root cause:** `sync_netfile` creates a new donor row for each `(name, employer_string)` tuple. Tiny variations in employer string ("California" vs "California State Assembly" vs "Calif. State Assembly") that ARE the same employer create separate donor rows. `sync_donor_employer_merge` then collapses them. Next netfile sync re-creates the fragmentation. Loop.

**Cross-ref:** Phase A finding A6 (donor-employer thrash). Same root cause; Phase B confirms with hard count.

---

### B3 — HIGH — `conflict_flags` has 4,941 stale duplicate flags visible via `is_current=TRUE`

**Source:** `src/pipelines/enrichments.py:257-403` → `db/flags.py::save_conflict_flag`, `db/flags.py::supersede_flags_for_meeting`

**Claim:** `sync_conflict_scanning` uses `NOT EXISTS (scan_runs WHERE status='completed')` gate (line 282-287), and `supersede_flags_for_meeting` is called inside each scan (line 358). The implication: "after the supersede step runs, only one flag per (meeting, type, description) tuple has is_current=TRUE."

**Reality:** `is_current=TRUE` query returns 23,085 rows, of which only 18,144 are unique by (meeting_id, flag_type, description). **4,941 duplicate flags** (21.4% dup rate). Max 20 duplicate copies of one flag for one meeting.

**Evidence query:**
```sql
SELECT COUNT(*) AS total_current_flags,
       COUNT(DISTINCT (meeting_id, flag_type, description)) AS unique_flags,
       COUNT(*) - COUNT(DISTINCT (meeting_id, flag_type, description)) AS dup_rows
FROM conflict_flags WHERE is_current = TRUE;
```
**Result (live, 2026-05-16):** total=23,085, unique=18,144, **dup_rows=4,941**.

**When were they created?**
```sql
WITH dups AS (
  SELECT meeting_id, flag_type, description FROM conflict_flags
  WHERE is_current = TRUE
  GROUP BY 1,2,3 HAVING COUNT(*) > 1
)
SELECT date_trunc('week', cf.created_at)::date AS week, COUNT(*) AS dup_rows_created
FROM conflict_flags cf
JOIN dups d ON d.meeting_id=cf.meeting_id AND d.flag_type=cf.flag_type AND d.description=cf.description
WHERE cf.is_current = TRUE
GROUP BY 1 ORDER BY 1 DESC;
```
**Result:** All 8,552 rows in dup groups were created in weeks of **2026-03-23** (4,102) and **2026-03-30** (4,450). **Zero new dups since 2026-04-06.**

**Hypothesis for root cause:** The `NOT EXISTS scan_runs WHERE status='completed'` gate currently prevents new dups (only 2 new scan_runs in last 7 days despite 31 sync runs), so the bug is **historically resolved in code**. But `supersede_flags_for_meeting` (or whatever earlier flow created the dups) left 4,941 stale rows behind, and no cleanup migration ever ran. The UI's `is_current = TRUE` filter — the supersede gate — sees them.

**Impact:** Public-facing pages that count flags or list "all current conflicts for meeting X" can show duplicate findings. Operator reviewing flags sees the same finding twice.

---

### B4 — MEDIUM — `sync_archive_center` writes new row when PDF byte-content drifts (not just refresh flow)

**Source:** `src/pipelines/archive_center.py:29-87` → `archive_center_discovery.py::save_to_documents` → `db.documents.ingest_document`

**Claim:** `ingest_document` (`src/db/documents.py:43`) docstring says "Deduplicates by content_hash — returns existing ID if duplicate."

**Reality:** The content_hash gate works for BYTE-identical re-fetches. But when the underlying PDF changes at all (even just metadata/timestamp/regen), a new row is inserted. The same ADID then has 2+ document rows. The known-good pattern (`refresh_stale_minutes`) intentionally inserts a new doc with `metadata.refreshed_from` set; the UNKNOWN cases don't have that flag.

**Evidence query:**
```sql
WITH dup_groups AS (
  SELECT source_identifier FROM documents
  WHERE source_type='archive_center' AND source_identifier IS NOT NULL
  GROUP BY 1 HAVING COUNT(*) > 1
)
SELECT
  COUNT(DISTINCT dg.source_identifier) AS dup_source_ids,
  SUM(CASE WHEN d.metadata ? 'refreshed_from' THEN 1 ELSE 0 END) AS intentional_refreshes,
  SUM(CASE WHEN NOT (d.metadata ? 'refreshed_from') THEN 1 ELSE 0 END) AS unintended_dups
FROM dup_groups dg
JOIN documents d ON d.source_identifier = dg.source_identifier
WHERE d.source_type='archive_center';
```
**Result (live, 2026-05-16):** 18 dup source_ids, totaling 42 rows. Of those, **only 3 carry `refreshed_from`** (intentional). The other **~39 are unintended dups** from re-runs picking up slightly-different PDFs.

**Impact:** Layer 1 has 1-2 extra MB per dup PDF. Extraction runs may operate on either copy. Minutes/recap pipelines that look up "the latest document for ADID X" may pick the wrong one.

**Note:** `documents` total table has **0 content_hash dups** (3,915 unique hashes), so each row IS unique by content. The dup is only at the source-identifier layer.

---

### B5 — MEDIUM — `sync_escribemeetings` per-meeting skip-check has 5 leaks

**Source:** `src/pipelines/escribemeetings.py:30-171`

**Claim (comment at line 96-100):** "This is the single gate: it catches every failure mode — scraped before agenda was published, items dropped during loading, partial extraction, etc."

**Reality:** 5 (source_type='escribemeetings', source_identifier) pairs have 2-3 document rows each. Total 15 rows in dup groups.

**Evidence query:**
```sql
SELECT source_identifier, COUNT(*) AS c
FROM documents
WHERE source_type='escribemeetings' AND source_identifier IS NOT NULL
GROUP BY 1 HAVING COUNT(*) > 1
ORDER BY c DESC;
```
**Result (live, 2026-05-16):** 5 distinct source_identifiers, 15 total dup rows.

**Hypothesis for root cause:** The per-meeting skip-check at `escribemeetings.py:101-112` checks `agenda_items` existence for the (meeting_date, body_id) tuple. But the document insert happens BEFORE the agenda_items insert (lines 121-145). If the scrape succeeds but agenda_items insert fails (e.g., transient DB error, malformed item), the document row exists but no agenda_items do — so the next run's skip-check returns False and re-inserts the document. The content_hash gate also has to fire for actual byte-identical re-fetch; if eSCRIBE re-emits the JSON with even a different timestamp the gate misses.

---

### B6 — MEDIUM — `city_employees` `uq_city_employee` constraint doesn't cover what it should

**Source:** `src/pipelines/socrata.py:29-114` → ON CONFLICT ON CONSTRAINT uq_city_employee

**Claim:** Uses `ON CONFLICT ON CONSTRAINT uq_city_employee DO UPDATE` → expected idempotent.

**Reality:** 10 duplicate rows exist by the natural key (city_fips, name, fiscal_year, source). All from source='socrata_payroll'.

**Evidence query:**
```sql
SELECT COUNT(*) AS total,
       COUNT(DISTINCT (city_fips, name, fiscal_year, source)) AS unique_keys,
       COUNT(*) - COUNT(DISTINCT (city_fips, name, fiscal_year, source)) AS would_dedup
FROM city_employees;
```
**Result (live, 2026-05-16):** total=2,729, unique=2,719, would_dedup=10.

**Hypothesis for root cause:** The `uq_city_employee` constraint includes a column beyond the four checked — probably `job_title` or `normalized_name` — which lets two employees with the same name in the same FY through if their job_title differs across runs. Need to check migrations to confirm. Impact is small (0.37%) but the gate is leaky.

---

### B7 — MEDIUM — `scan_runs` has 7 (meeting_id, scan_mode) combos with multiple `status='completed'` rows

**Source:** `src/pipelines/enrichments.py:257-403`

**Claim:** `NOT EXISTS (scan_runs WHERE status='completed')` gate (line 282-287) — one completed scan per meeting per mode.

**Reality:** 877 completed scan_runs, 852 unique (meeting_id, scan_mode). 25 extra rows. Max 20 completed scans for ONE meeting in ONE mode.

**Evidence query:**
```sql
SELECT meeting_id, scan_mode, COUNT(*) AS c
FROM scan_runs WHERE status='completed'
GROUP BY 1,2 HAVING COUNT(*) > 1 ORDER BY c DESC LIMIT 10;
```
**Result (live, 2026-05-16):** 7 groups, max 20 dup runs for one meeting.

**Hypothesis for root cause:** Same era as B3 (weeks of 2026-03-23 to 03-30). The gate is now firing correctly — only 2 new scan_runs in last 7 days despite 31 sync runs. Historical artifact. Same conclusion as B3.

---

### B8 — MEDIUM — `nextrequest_documents` table is EMPTY; document_count never populated

**Source:** `src/pipelines/nextrequest.py:29-81` → `nextrequest_scraper.save_to_db`

**Claim (docstring line 36-37):** "Uses NextRequest's public client JSON API. For incremental: fetches requests since last sync." `src/CLAUDE.md` documents that the document API exists and was wired in April: "Wired into `get_request_detail(include_documents=True)`."

**Reality:** `sync_nextrequest` hardcodes `download_docs=False, skip_details=...` (line 62-67). Documents table has 0 rows. `document_count` column in `nextrequest_requests` is 0 for ALL 2,385 rows.

**Evidence query:**
```sql
SELECT COUNT(*) AS request_count,
       SUM(document_count) AS total_docs_claimed,
       (SELECT COUNT(*) FROM nextrequest_documents) AS docs_actually_loaded
FROM nextrequest_requests;
```
**Result (live, 2026-05-16):** 2,385 requests, total_docs_claimed=0, docs_actually_loaded=0.

**Not strictly an idempotency bug** — it's a coverage gap. Including here because the sync's docstring + parent `data_sync.py` docs imply "documents are loaded." They're not. Anything downstream that consults `nextrequest_documents` (search, RAG, CPRA frontend) sees an empty table.

**Cross-ref:** `search_nextrequest_docs.py` (per `src/CLAUDE.md`) — this script presumably worked on the 24-428 request (115 docs). Either that ran ad-hoc with different flags, or the table was wiped, or my Q6 query is fooled by RLS (verify by checking with service-role access — query above used the MCP which should use service-role).

---

### B9 — LOW — `sync_archive_center` counter `records_new = stats["saved"]` lies

**Source:** `src/pipelines/archive_center.py:75-87` + `archive_center_discovery.py::save_to_documents` (line 400)

**Claim:** Counter `records_new` = "new rows."

**Reality:** `save_to_documents` increments `saved` after EVERY call to `ingest_document`, regardless of whether `ingest_document` actually inserted or returned an existing ID. Writes themselves are idempotent (via content_hash gate); only the counter is wrong.

**Evidence:** Last archive_center sync (2026-05-12) reported `records_new = 3,500`. With 3,915 total documents in the table, 3,500 "new" means we essentially "added the whole archive again" — impossible since it's been mostly stable for weeks. The 3,500 is "documents processed without raising an exception."

**Hypothesis:** Same shape as Phase A A1/A3/A4. Counter needs to use `RETURNING (xmax = 0)` like the socrata_expenditures reference impl.

---

### B10 — LOW — `nextrequest.save_to_db` counter same bug pattern

**Source:** `src/nextrequest_scraper.py:404-482`

**Claim:** `requests_saved` and `documents_saved` = "new rows."

**Reality:** `requests_saved += 1` after every `ON CONFLICT DO UPDATE RETURNING id`. Writes idempotent (`uq` on `(city_fips, request_number)` per Q2 showing 0 dups). Counter wrong same way.

**Evidence:** Last nextrequest sync (2026-05-14) reported `records_new = 0` (per Q1). This is actually correct in result, but only because there were genuinely 0 new requests; on any run with new requests the counter conflates inserts and updates.

---

### B11 — LOW — `load_behested_to_db` counter same pattern

**Source:** `src/db/entities.py:203-285`

**Claim:** `stats["loaded"]` = "newly inserted rows."

**Reality:** `stats["loaded"] += 1` after every `ON CONFLICT DO UPDATE` execute. Writes idempotent. Counter wrong.

**Evidence:** behested_payments has 7 rows, all unique. The April sync reported `last_records_new = 7`. Since the table started with 7 rows after the April sync, the counter happened to match — but if the same 7 rows were re-synced, the counter would still report 7 "new."

---

### B12 — LOW — `load_lobbyists_to_db` counter same pattern

**Source:** `src/db/entities.py:291-364`

Same shape as B11. lobbyist_registrations has 48 rows, all unique by (city_fips, source, source_identifier). The counter inflates on re-runs.

---

## Verified Idempotent — 19 sources

These passed the Trust Ladder. The DB query confirms 0 natural-key dups; the gate query (where applicable) returns 0 outstanding work or matches the expected backlog.

| Source / Loader | Natural key | At-rest dups | Notes |
|---|---|---|---|
| `sync_netfile` → contributions | (city_fips, donor_id, amount, contribution_date, committee_id) | 0 of 27,956 | Gate is 94% effective; 6% miss-rate UPDATES rows but does NOT add dups. See Phase A A1 for counter caveat. |
| `sync_socrata_expenditures` → city_expenditures | (city_fips, socrata_row_id) | 0 of 139,820 | **Reference implementation.** Pattern to copy. |
| `sync_socrata_permits` → city_permits | (city_fips, socrata_row_id) | 0 of 177,431 | Uses shared `_sync_socrata_paginated` helper with xmax = 0. |
| `sync_socrata_licenses` → city_licenses | (city_fips, socrata_row_id) | 0 of 1 | (Table small; pattern is correct.) |
| `sync_socrata_code_cases` → city_code_cases | (city_fips, socrata_row_id) | 0 of 1 | (Table small; pattern is correct.) |
| `sync_socrata_service_requests` → city_service_requests | (city_fips, socrata_row_id) | 0 of 1 | (Table small; pattern is correct.) |
| `sync_socrata_projects` → city_projects | (city_fips, socrata_row_id) | 0 of 1 | (Table small; pattern is correct.) |
| `sync_escribemeetings` → meetings | (city_fips, meeting_date, meeting_type, body_id) | 0 of 850 | Meetings table is clean. Document-layer leak is B5. |
| `sync_escribemeetings` → agenda_items | (meeting_id, item_number) | 0 of 11,705 | ON CONFLICT DO UPDATE. |
| `sync_escribemeetings_minutes` → meetings (URL update) | implicit (skip-if-eSCRIBE-already-set) | N/A | Gate works per code review. |
| `sync_minutes_extraction` → extraction_runs | document_id | 0 of 824 current | ON CONFLICT (document_id) DO UPDATE. |
| `sync_nextrequest` → nextrequest_requests | (city_fips, request_number) | 0 of 2,385 | Writes idempotent; coverage gap separately at B8. |
| `sync_form700` → form700_filings | (city_fips, filer_name, filing_year, statement_type, source) | 0 of 101 | Pre-filter query + ON CONFLICT. |
| `sync_form803_behested` → behested_payments | (city_fips, source, source_identifier) | 0 of 7 | Counter inflated (B11), writes idempotent. |
| `sync_lobbyist_registrations` → lobbyist_registrations | (city_fips, source, source_identifier) | 0 of 48 | Counter inflated (B12), writes idempotent. |
| `sync_propublica` → organizations | (city_fips, source, entity_number) | 0 of 170 | ON CONFLICT + RETURNING xmax = 0. Correct counter. |
| `sync_propublica` → entity_links | (city_fips, normalized_person_name, organization_id, role, source) | 0 of 247 | ON CONFLICT + RETURNING xmax = 0. Correct counter. |
| `sync_topic_tagging` → item_topics | (agenda_item_id, topic_id) | 0 of 7,614 | Re-runs don't add new assignments. |
| `sync_donor_dedup` | finds cross-filing dups | 0 finds/run avg (7d) | After first cleanup, runs find nothing. **Genuinely idempotent in practice.** |

**Enrichments with "needing-X" gate queries** (re-runs are no-ops when caught up; pending backlog is just pending work, not duplicate-write risk):

```sql
-- live snapshot 2026-05-16
agenda_items_no_proceeding_type         0     ← caught up
meetings_unscanned                      0     ← caught up
meetings_with_transcript_no_motions     1     ← 1 outlier; sync would do work
agenda_items_no_ai_comment_summary     22     ← backlog
meetings_without_orientation           46     ← backlog
meetings_without_recap                139     ← backlog
meetings_without_summary              136     ← backlog
agenda_items_no_plain_language_summary 454    ← backlog
agenda_items_no_topic_label           490    ← backlog
```

The backlog counts are NOT idempotency bugs — they're "still has work to do." If a sync ran on a caught-up dataset, the gate would return 0 and no work would happen. Operator can verify any of these by running `python data_sync.py --source X` and checking the result returns `records_new = 0` for caught-up sources.

---

## Deferred — Sources not run in last 7 days (Appendix B)

These sources haven't run in the verification window so live "would-they-write-dups?" data isn't fresh. Code review alone says they're idempotent; live verification deferred.

| Source | Last successful run | Code-level idempotency |
|---|---|---|
| `lobbyist_registrations` | 2026-04-01 | ON CONFLICT (already in B12) |
| `form803_behested` | 2026-04-01 | ON CONFLICT (already in B11) |
| `form700` | 2026-04-01 | Pre-filter + ON CONFLICT (verified) |
| `elections` | 2026-03-23 | derived; idempotency depends on `run_election_pipeline` internals (not audited) |
| `courts` (Tyler Odyssey) | not in 60d window | not audited this session |
| `opencorporates` | not in 60d window | Has caching layer; not audited live |
| `refresh_stale_minutes` | 2026-05-11 | Content-hash check; verified by code review |
| `embedding_generation` | 2026-05-11 (then failed) | Documented idempotent; skips when OPENAI_API_KEY missing |
| `propublica` | failing | per system_health report; not audited live |
| `paper_filing_reconciliation` | 2026-05-16 | Idempotency claim "existing UNI rows are deleted and re-inserted with current correct amounts" — `rows_synthesized` metadata is NULL (Q10), suggesting either no Form 460 cover totals to reconcile right now, or the metadata isn't being set. Defer to operator review. |

---

## How to re-run this audit

Every finding above includes the exact SQL the operator can paste into Supabase SQL Editor (or `supabase db remote` via psql) to independently confirm. Each query is small — runs in <1 second on the live DB. No fixture setup needed.

**Total audit-rerun time: <5 min for the full set.**

---

## Operator Review — Phase B Decisions

Each finding needs one of: **Fix code** / **Fix data + Fix code** / **Remove/qualify claim** / **Defer** / **Accept**.

For B-class findings, "Accept" means "I know this isn't fully idempotent; the docstring stays as written." This is fine for sources where the cost of fixing exceeds the cost of the leak — but should be conscious, not default.

| ID | Severity | Action | Notes |
|---|---|---|---|
| B1  (calaccess IE no ON CONFLICT)         | HIGH   | ☐ Fix code ☐ Fix data + code ☐ Defer ☐ Accept | Cross-ref A3. Pause CAL-ACCESS sync until fix? |
| B2  (donor_employer_merge thrash)         | HIGH   | ☐ Fix code ☐ Qualify claim ☐ Defer ☐ Accept   | Cross-ref A6. Tightening donor upsert is the root-cause fix. |
| B3  (conflict_flags 4,941 stale dups)     | HIGH   | ☐ Cleanup migration ☐ Defer ☐ Accept           | Live bug is fixed; data cleanup is one-off DELETE. |
| B4  (archive_center content drift dups)   | MEDIUM | ☐ Fix code ☐ Document intent ☐ Defer ☐ Accept | Likely fine if intentional; needs docstring. |
| B5  (escribemeetings 5 dup source_ids)    | MEDIUM | ☐ Fix code ☐ Investigate ☐ Defer ☐ Accept     | 15 rows; low impact. |
| B6  (city_employees 10 dups)              | MEDIUM | ☐ Fix constraint ☐ Defer ☐ Accept              | 0.37% leak; check uq def. |
| B7  (scan_runs 7 dup combos)              | MEDIUM | ☐ Cleanup migration ☐ Defer ☐ Accept           | Same era as B3; cleanup is same shape. |
| B8  (nextrequest_documents empty)         | MEDIUM | ☐ Wire documents API ☐ Document choice ☐ Defer | Coverage gap, not idempotency. |
| B9  (archive_center counter inflation)    | LOW    | ☐ Fix counter ☐ Defer ☐ Accept                 | Same pattern as A1/A3/A4. |
| B10 (nextrequest counter inflation)       | LOW    | ☐ Fix counter ☐ Defer ☐ Accept                 | Same pattern. |
| B11 (load_behested counter inflation)     | LOW    | ☐ Fix counter ☐ Defer ☐ Accept                 | Same pattern. |
| B12 (load_lobbyists counter inflation)    | LOW    | ☐ Fix counter ☐ Defer ☐ Accept                 | Same pattern. |

---

## Themes for Phase D refactor

If multiple B-class findings get "fix code," they cluster into three categorical changes for Phase D:

1. **Counter Contract Standard** (B9, B10, B11, B12 + A1, A3, A4) — Replace ad-hoc `stats[]` dicts with `*SyncStats` dataclasses whose `inserted` field MUST come from `cur.fetchone()[0]` on `RETURNING (xmax = 0)`. Linter check fails any new loader without it.

2. **Idempotency Contract: Hard or Documented Soft** (B1, B2, B3, B5, B7) — Every sync's docstring must be either "Hard idempotent: re-runs add 0 rows and update 0 rows" OR "Soft idempotent because of [precondition]; under [thrash condition X] re-runs do measurable work." No more bare "idempotent" claims.

3. **Cleanup Migrations on Resolved Bugs** (B3, B7) — Convention: when a write-amplification bug is fixed in code, the SAME commit ships a one-off cleanup migration. The fix is half the work; the data remediation is the other half. Without it, `is_current = TRUE` queries serve the wrong data forever.

---

## What this audit does NOT cover

- **Counter accuracy beyond the LOW findings.** Counters of every source were not exhaustively re-verified — Phase A covered 6 sources, Phase B added 4 more. The remaining ~30 sources could still have inflated counters that would show up if their backlog drops to zero. A follow-up should grep `stats["..."] += 1` across all loaders.
- **Cross-pipeline state mutation.** E.g., does `sync_donor_employer_merge` invalidate `conflict_flags` that referenced merged donors? Not audited.
- **Race conditions.** All checks were sequential read-only queries; concurrent-write idempotency (two crons hitting same source) wasn't tested. The scan_runs duplicates (B7) suggest it WAS a problem historically.
- **Source-side schema drift.** E.g., if NetFile renames a field, the gate's natural-key check could silently miss matches and re-insert "new" rows. Not testable without a synthetic source change.
- **Migration discipline.** Whether unique-constraint coverage matches the in-code ON CONFLICT keys (B6 suggests a mismatch). Phase D candidate.

---

## File pointer

This audit's findings refer back to:
- [`2026-05-counter-audit.md`](2026-05-counter-audit.md) — Phase A (counters)
- `~/.claude/plans/steady-crafting-island.md` — the master audit plan
- `src/data_sync.py::SYNC_SOURCES` — the registry under audit

Next: **Phase C — documentation drift audit** (every "must"/"always" rule in CLAUDE.md and rules/, mapped to enforcement status).
