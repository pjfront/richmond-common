# Pipeline Counter & Gate Audit — Phase A

**Date:** 2026-05-16
**Auditor:** Claude (under operator-directed skeptical-verification protocol)
**Scope:** Tier 1 sites identified in `~/.claude/plans/steady-crafting-island.md`
**Methodology:** Trust Ladder — code → SQL → DB ground truth. **No code changes** in this phase.

---

## Executive summary

Six findings on six Tier-1 sites. Two are HIGH severity (data correctness, ongoing damage). Two are MEDIUM (counter framing misleads the operator). One is the reference implementation. One is low-risk-but-future-fragile.

| ID | Site | Severity | One-line verdict |
|---|---|---|---|
| **A1** | `src/db/contributions.py` counter | MEDIUM | After my fix, still ~6% drift (1589 reported vs 1492 actual). Pre-commit accounting; see hypothesis. |
| **A2** | `src/db/entities.py` counters | LOW | Correct as written. Untested at outcome layer. Latent fragility if WHERE is added. |
| **A3** | `src/db/expenditures.py` no ON CONFLICT | **HIGH** | `independent_expenditures` table is **96% duplicates** (54,800 rows, 2,260 unique). Frontend PAC pages show inflated numbers. Migration 102 was one-time mop-up; bleed continues. |
| **A4** | `src/pipelines/socrata.py` payroll counter | MEDIUM | `records_new` counter labels every UPSERT as "new." Yesterday's sync produced 0 actual inserts but counter would have reported ~2,700. |
| **A5** | `src/pipelines/socrata.py` expenditures counter | NONE | Reference implementation. Counter correct, table clean. **Use this pattern everywhere.** |
| **A6** | `src/pipelines/netfile.py` `donor_employer_merge` "idempotent" | **HIGH** | Function has run 10 times in 5 days, EACH RUN merging ~655 donors and dropping ~1,500 duplicate contributions. The "idempotent" docstring is operationally false. This is the root cause of the contributions gate's 6% miss rate (Finding A1). |

**The pattern.** Three of six counters are misleading. Two of six tables have idempotency claims that aren't backed by data. **No site I audited had a test that verified the counter against an outcome-layer query before this audit.** Every drift was findable in <5 minutes with a single SQL query the audit just ran for the first time.

---

## Trigger

On 2026-05-16 the contributions sync reported `records_new: 1591` as "verified live end-to-end." A direct DB query showed only 6 actually-new rows in the first window and 1,492 in the second — neither matched the counter. The operator caught the drift by being skeptical of the number.

Three other sites with similar shape were surfaced by `Agent`-based exploration. This audit verifies each at the outcome layer.

---

## Verdict format

Each finding has:

- **Claim** — what the code (counter name, docstring, surrounding comment) tells the operator
- **Code path** — file:line of the counter increment
- **Outcome-layer query** — the SQL that establishes ground truth
- **Observed drift** — counter vs. ground truth
- **Hypothesis** — most likely root cause (not a fix; just a hypothesis)
- **Operator decision required** — fix code / remove claim / defer

---

## Finding A1: `contributions` counter overstates inserts by ~6%

**Claim.** After my counter fix (`dcebd20`), the docstring at `src/db/contributions.py:117-122` says:
> `contributions` = rows ACTUALLY INSERTED as new (xmax = 0 on RETURNING)
> `updated` = rows that existed and got DO UPDATE'd
> `conflict_noop` = rows that hit ON CONFLICT but DO UPDATE WHERE was false

The netfile sync result dict at `src/pipelines/netfile.py:128-141` then exposes these as `records_new / records_updated / records_unchanged` to the operator log.

**Code path.** `src/db/contributions.py:296-329` — `INSERT ... ON CONFLICT ... RETURNING (xmax = 0)`, then `result = cur.fetchone()` increments `stats["contributions"]` when `result[0]` is True.

**Outcome-layer query.**
```sql
SELECT COUNT(*) FROM contributions
WHERE created_at >= '2026-05-16 12:15:00+00'
  AND created_at <  '2026-05-16 12:25:00+00';
```

**Observed drift (run 25961678509, sha dcebd20).**
| Source | Value |
|---|---|
| `records_new` in summary log | 1589 |
| `records_updated` in summary log | 0 |
| Rows actually inserted (`COUNT(*)` in window) | **1492** |
| Drift | **+97 (counter overstates by 6.5%)** |
| Total contributions before sync | 26,464 |
| Total contributions after sync | 27,956 |
| Delta | 1,492 (matches `actually_inserted`) |

**Hypothesis.** Three candidates, ordered by likelihood:
1. **Batch-commit rollback.** Code commits every 1000 successful operations; on a mid-batch exception, the partial transaction is rolled back but the in-memory counter is not decremented.
2. **Unique-constraint silent recovery.** A separate UNIQUE constraint (e.g., a different partial index) may abort the INSERT but `RETURNING (xmax = 0)` still returns True before the row is rejected at commit time.
3. **Counter increment happens before commit confirms.** psycopg2 `fetchone()` reflects the in-transaction outcome; if the transaction aborts later, the count is already booked.

**Separate finding (gate effectiveness).** The gate prevented 22,378 of 23,967 INSERT attempts (93%). The remaining 1,492 are mostly NOT amendments (per earlier investigation in this session — 0 of 1,492 had collisions on existing natural keys). They appear to be donor-employer thrash: same person, different employer string across filings, creates new donor_id, breaks the gate's natural-key match. **This is a separate audit item logged in Finding A6 below.**

**Operator decision required:** fix code (add commit-aware counter) / remove "INSERT" framing from records_new and acknowledge it's "INSERTs counted-as-new pre-commit" / defer (97 rows out of 23,967 is small in absolute terms).

---

## Finding A2: `organizations` + `entity_links` counters are correct-as-written but unverified at the outcome layer

**Claim.** `src/db/entities.py:84-88` and `:145-149` use the standard `RETURNING (xmax = 0)` pattern to split inserts from updates. This is the same idiom I added to `contributions.py` in `dcebd20`.

**Code path.**
```python
# lines 84-88 (organizations)  and  145-149 (entity_links)
row = cur.fetchone()
if row and row[0]:
    stats["inserted"] += 1
else:
    stats["updated"] += 1
```

**Read-the-SQL analysis.** Neither ON CONFLICT clause has a WHERE filter — they always fire DO UPDATE on conflict. So `cur.fetchone()` always returns a row, `row` is never None in practice, and the counter is logically correct.

**Outcome-layer query.**
```sql
SELECT 'organizations', COUNT(*), MAX(created_at) FROM organizations
UNION ALL
SELECT 'entity_links',  COUNT(*), MAX(created_at) FROM entity_links;
```

**Observed state.**
| Table | Total rows | Last 7 days | Latest write |
|---|---|---|---|
| organizations | 170 | 0 | 2026-03-16 |
| entity_links | 247 | 0 | 2026-03-16 |

Both tables have been dormant for 2 months. There's no recent sync to compare a counter against.

**Test coverage.** `grep -rln "load_organizations_to_db|load_entity_links_to_db" tests/` returns **zero tests**. Callers: `src/pipelines/external.py` only.

**Hypothesis.** The exploration agent flagged a hypothetical "ON CONFLICT WHERE false → row is None → falls to else → falsely counts as updated" bug. That bug pattern would be real if a WHERE clause is ever added to either DO UPDATE statement. Today, no WHERE → no bug.

**Risk.** Two latent risks:
1. **No regression guard.** If someone adds a WHERE to the DO UPDATE (e.g., to prevent overwriting newer data), the counter silently mis-counts and no test fails.
2. **Counter never live-verified.** With 417 total rows and 2-month-old writes, no one has ever cross-checked the counter against `SELECT COUNT(*)` at the outcome layer.

**Operator decision required:** add a defensive `cur.fetchone() if row is None: stats["conflict_noop"] += 1` branch as future-proofing / leave as-is and add a comment "DO NOT add WHERE without updating counter logic" / defer (low volume, low risk today).

---

## Finding A3: `independent_expenditures` is 96% duplicates — counter is accurate, semantic is misleading, frontend reads inflated data

**Severity: HIGH.** This is the biggest finding in the audit.

**Claim.** `src/db/expenditures.py:30-80` (`load_expenditures_to_db`) returns `{"loaded": N, "skipped": M}` and the function docstring says it "Follows same pattern as load_contributions_to_db." It does not.

**Code path.**
```python
# lines 56-74 — NO ON CONFLICT, NO RETURNING, NO IDEMPOTENCY
cur.execute(
    """INSERT INTO independent_expenditures
       (city_fips, committee_name, candidate_name, ...)
       VALUES (%s, %s, %s, ...)""",
    (...)
)
stats["loaded"] += 1   # plain INSERT; every call creates a new row
```

The counter is technically accurate (it counts INSERT statements executed) but the SEMANTIC IMPLIED ("loaded" reads as "loaded for the first time") is misleading. Each sync re-loads every record as a duplicate.

**Outcome-layer query.**
```sql
SELECT
  COUNT(*) AS total_rows,
  COUNT(*) FILTER (...HAVING COUNT(*) > 1) AS duplicate_groups,
  SUM(dup_count - 1) AS extra_rows_from_duplicates
FROM independent_expenditures;
```

**Observed state.**
| Metric | Value |
|---|---|
| Total rows | **54,800** |
| Distinct logical records | **2,260** |
| Extra rows from duplicates | **52,540** |
| Duplication factor | **24× average** |
| Latest write | 2026-05-16 |
| Daily growth rate | ~4,379 rows/day (all duplicates of the same 2,260 records) |

**Insertion-over-time evidence.**
| Day | Rows inserted | Unique logical |
|---|---|---|
| 2026-05-16 | 4,379 | 2,260 |
| 2026-05-15 | (no IE sync this day) | — |
| 2026-05-11 | 4,379 | 2,260 |
| 2026-05-10 | 4,379 | 2,260 |
| 2026-05-09 | 4,379 | 2,260 |
| 2026-05-08 | 8,758 | 2,260 |

The CAL-ACCESS sync (or whatever invokes `load_expenditures_to_db`) runs almost daily. Each run inserts ~4,379 rows. None of them are new logical records; all are duplicates of the same 2,260.

**Frontend impact.**
- `web/src/lib/queries/pacs.ts:491` `getPACIndependentExpenditures()` reads this table directly with a 10-year date window.
- Called from `web/src/app/pac/[slug]/page.tsx:68`.
- Returned rows have **24× the actual count**. If the page sums `amount` it reports ~24× the real spend.
- The comment at `pacs.ts:485` says "dedup'd in migration 102" — this is **stale and misleading**. Migration 102 ran ONCE on 2026-04-29 to clean up a backlog. There is no permanent dedup mechanism. The table re-duplicated within days.

**Existing dedup mechanism.** `src/migrations/102_dedup_independent_expenditures.sql` is a one-time DELETE that goes from 122,326 → ~2,252 rows. It has no permanent enforcement. From migration comment line 29: "Idempotent: re-running the migration is a no-op once the table is deduped." Yes, but nothing PREVENTS re-duplication on the next sync.

**Root cause.** `src/db/expenditures.py` was written without ON CONFLICT, contradicting its own docstring claim that it "follows same pattern as load_contributions_to_db." The contributions loader has a unique index + ON CONFLICT DO UPDATE; the expenditures loader has neither. Schema lacks a unique constraint on the natural key `(committee_name, payee_name, amount, expenditure_date, support_or_oppose, candidate_name)`.

**Hypothesis.** When `load_expenditures_to_db` was extracted from the old monolithic `db.py` in Phase 2.1, the ON CONFLICT clause was either never written or got lost. Migration 102 was a manual mop-up, not a permanent fix.

**Operator decision required:** **STRONGLY RECOMMEND FIX (HIGH PRIORITY).** Options:
1. Add `ON CONFLICT (committee_name, payee_name, amount, expenditure_date, support_or_oppose, candidate_name) DO NOTHING` + a unique index migration. Stops the bleed.
2. Run migration 102 manually now to clean up the 52,540 dup rows, then do (1).
3. Defer (but acknowledge: PAC pages display inflated numbers; CAL-ACCESS sync wastes Supabase quota daily; table will hit row limits eventually).

**Adjacent risk.** This is the cleanest example of "claim said X, code does Y, no test catches the drift." The docstring claim ("follows same pattern as load_contributions_to_db") was never enforced. A pre-commit or CI lint that diffs the SQL shapes of loaders in `src/db/` against each other could have caught this.

---

## Finding A4: `sync_socrata_payroll` counter labels every UPSERT as `records_new`

**Claim.** `src/pipelines/socrata.py:109-114` returns `{"records_new": total_loaded, "records_updated": 0, ...}`. The "records_new" naming, plus the hardcoded `records_updated: 0`, tells the operator "all loaded rows are new." That's not what's happening.

**Code path.** `src/pipelines/socrata.py:74-103`:
```python
loaded = 0
for rec in records:
    cur.execute(
        """INSERT INTO city_employees ...
           ON CONFLICT ON CONSTRAINT uq_city_employee
           DO UPDATE SET ..."""  # NO RETURNING
        ...
    )
    loaded += 1  # increments on every execute, regardless of INSERT vs UPDATE
```

The ON CONFLICT clause is correct (it has a unique constraint, so dedup happens). But the COUNTER doesn't reflect what happened. `loaded` counts INSERT attempts, not new rows.

**Outcome-layer query.**
```sql
SELECT COUNT(*) AS total, COUNT(DISTINCT (normalized_name, fiscal_year)) AS unique_employee_years,
       MAX(created_at) AS latest_insert, MAX(updated_at) AS latest_update
FROM city_employees WHERE city_fips = '0660620';
```

**Observed state.**
| Metric | Value |
|---|---|
| Total rows | 2,729 |
| Unique (normalized_name, fiscal_year) pairs | 2,719 |
| Latent duplicate drift | **10 rows** (very low) |
| Latest insert | 2026-05-06 |
| Latest update (post-UPSERT touch) | 2026-05-15 (yesterday's sync did UPSERT-as-UPDATE on existing rows) |
| Rows inserted last 7 days | **0** |

**Verdict.** Yesterday's payroll sync produced ZERO new rows in the DB (latest insert is from 5/6) but the counter would have reported `records_new: ~2700`. Same misleading-counter shape as the contributions bug.

**Small secondary finding.** 10 rows of duplicate drift on the `(normalized_name, fiscal_year)` natural key. Investigate whether `uq_city_employee` covers exactly that key or a slightly different one (maybe `(normalized_name, fiscal_year, source)` or similar that allows benign duplicates from multiple sources).

**Operator decision required:** apply the `RETURNING (xmax = 0)` pattern (same as contributions/expenditures) to split inserted vs updated / leave counter and rename `records_new` → `records_processed` to remove the misleading framing / defer.

---

## Finding A5: `sync_socrata_expenditures` counter is correct AND outcome-layer-clean

**Claim.** `src/pipelines/socrata.py:124-262` returns `{"records_new": total_new, "records_updated": total_updated, ...}` where both come from `RETURNING (xmax = 0)` distinguishing INSERT from UPDATE.

**Code path.** Lines 213-247 use the standard pattern correctly.

**Outcome-layer query.**
```sql
SELECT COUNT(*) AS total, COUNT(DISTINCT socrata_row_id) AS unique_ids,
       (SELECT COUNT(*) FROM ... HAVING COUNT(*) > 1) AS natural_key_dup_groups
FROM city_expenditures;
```

**Observed state.**
| Metric | Value |
|---|---|
| Total rows | 139,820 |
| Unique socrata_row_id | 139,820 (zero drift) |
| Natural-key duplicate groups | **0** |
| Rows inserted last 7 days | 922 (genuine new) |
| Latest insert | 2026-05-14 |

**Verdict.** The counter is correct, the dedup is working, and the table is clean. **This is the reference implementation for what the others should look like.**

**Operator decision required:** None — flag this as the pattern to extend everywhere.

---

## Finding A6: `donor_employer_merge` "idempotent" claim is operationally false — the netfile↔merge thrash root cause

**Severity: HIGH.** This is the root cause of the contributions gate's 6% miss rate identified in Finding A1.

**Claim.** `src/pipelines/netfile.py:172` docstring:
> "Reads from `donors` and `contributions`. Writes only the rows that need to change. Idempotent — re-running on a clean DB is a no-op."

**The "on a clean DB" weasel.** This is technically true and operationally meaningless. The DB is never clean because the netfile sync (`load_contributions_to_db`) keeps re-introducing the duplicates the merge function just removed.

**Code path.** `src/pipelines/netfile.py:148-264` (sync_donor_employer_merge). The function clusters donor rows by `normalized_name`, picks one keeper per cluster, repoints contributions, and deletes the loser. Returns `{"donors_merged": N, "contributions_repointed": M, "duplicate_contribs_dropped": K}`.

**Outcome-layer query.**
```sql
SELECT source, records_fetched, records_new, records_updated, metadata
FROM data_sync_log WHERE source = 'donor_employer_merge'
ORDER BY completed_at DESC LIMIT 10;
```

**Observed state — 10 runs in 5 days, EVERY ONE finds ~700 clusters to merge:**

| Completed at | donors_merged | contribs_repointed | duplicate_contribs_dropped | execution_secs |
|---|---|---|---|---|
| 2026-05-16 10:39 | 657 | 6 | 1,490 | 16.1 |
| 2026-05-16 09:25 | 657 | 8 | 995 | 335.3 |
| 2026-05-16 07:19 | 655 | 6 | 1,491 | 18.7 |
| 2026-05-16 05:01 | 655 | 3 | 1,489 | 499.6 |
| 2026-05-15 23:41 | 656 | 7 | 1,489 | 313.0 |
| 2026-05-12 01:33 | 713 | 8 | 1,581 | 148.4 |
| 2026-05-11 12:39 | 721 | 25 | 1,124 | 477.5 |
| 2026-05-11 10:33 | 710 | 1 | 1,579 | 17.6 |
| 2026-05-11 08:19 | 711 | 7 | 1,588 | 194.3 |
| 2026-05-10 23:53 | 714 | 10 | 1,591 | 404.6 |

**Pattern.** Every merge run does ~655 merges + drops ~1,500 duplicate contributions. If the function were truly idempotent against the working state, the second run should find ZERO work. Instead, each run finds **the same ~655 merges and ~1,500 duplicates** because the netfile sync re-creates them between runs.

**The thrash cycle:**
1. NetFile API returns 23,946 records (some with employer "Stanford Health", some with "Stanford Health Care" for the same donor)
2. `load_contributions_to_db` creates new donor rows for each employer variant (case-sensitive lookup on `COALESCE(employer, '')`)
3. New contributions get new donor_ids, gate doesn't match, INSERT runs → ~1,492 "new" rows
4. `donor_employer_merge` runs as a `--enrich` cascade
5. Merges ~655 employer variants down to canonical rows, drops ~1,500 duplicate contributions
6. NetFile sync runs again, API still returns the original employer variants
7. New donor rows created again. Goto 2.

**The exact number** of duplicate_contribs_dropped (~1,490) matches the ~1,492 actually-inserted rows from the post-fix sync in Finding A1. They are the same rows. This is the loop.

**Cost impact.** Each iteration:
- Netfile sync: 23,946 INSERT attempts → ~1,492 actual inserts (Supabase writes)
- Donor merge: ~700 UPDATEs (re-pointing) + ~1,500 DELETEs + ~655 donor DELETEs
- All this work undoes itself. Net data change per day = ~0 (logical), Supabase writes per day = ~3,000-4,000.

**Hypothesis (root cause).** The donor upsert query at `src/db/contributions.py:117-122` uses `COALESCE(employer, '') = %s` for the conflict key — case-sensitive, no normalization for trivial differences. NetFile's API returns whatever employer string the donor wrote on each filing form, so the same person commonly has 2-6 employer variants. The merge function normalizes them post-hoc instead of preventing them at insert.

**Operator decision required:** **STRONGLY RECOMMEND FIX.** Three plausible paths:
1. **Tighten donor upsert** — normalize employer (lowercase + strip + collapse "n/a" variants) BEFORE the conflict key lookup. The merge function becomes a no-op once this lands.
2. **Use canonical_employer instead of employer for the unique constraint** — add a generated column on donors that holds the normalized form, change unique index to use it.
3. **Defer + acknowledge** — the data is correct after each merge run, just expensive. Operationally fine if Supabase quota holds.

**The misleading claim.** The "Idempotent" framing in the docstring is doing more harm than good — it implies the system has converged when it's in a steady-state loop. Even if option 3 is chosen, the docstring should be updated to: "Merges fresh thrash from each netfile sync. NOT idempotent across sync cycles because netfile re-introduces employer variants. See audit docs/audits/2026-05-counter-audit.md Finding A6."

---

## Methodology notes for the operator (so you can re-verify any finding)

Every finding above is independently re-verifiable in <5 minutes using only the **Outcome-layer query** block. Steps:

1. Open Supabase SQL editor at https://supabase.com/dashboard/project/ahrwvmizzykyyfavdvfv/sql
2. Paste the SQL from the finding's "Outcome-layer query" section
3. Compare against the "Observed state" table

If you get different numbers from what I documented, **the audit is wrong and needs to be redone.** The whole point of Phase A is that you don't have to take my word for any of this.

The findings DO NOT include any code changes. Phase A's hard rule is no fixes; everything above is information for you to decide what to fix and what to defer.

---

## What this audit did NOT verify

To prevent the same "trust an intermediate signal" failure that triggered this audit, here's what's still UNVERIFIED:

1. **Tier 2 audit (idempotency).** Phase B will check whether each entry-point script can be re-run with no DB writes. Today's audit only covered the 6 Tier 1 sites.
2. **Tier 3 audit (documentation drift).** Phase C will check every "must" rule in CLAUDE.md against actual enforcement. Not done in Phase A.
3. **Frontend-visible impact of Finding A3.** I confirmed `getPACIndependentExpenditures` reads the inflated table, but did NOT load a PAC page in a browser and measure what the operator/public sees. The page MIGHT do client-side dedup or hide the section. Worth a manual check before any public-facing communication.
4. **Other counter sites in src/pipelines/*.py.** Phase A focused on the 5 sites flagged by the Tier 1 inventory plus contributions. The Tier 2 sweep will check the remaining 6+ pipeline files for similar shape.

---

## Operator review form

For each finding, please mark:

- [ ] **A1** contributions counter 6% drift — fix code / remove "INSERT" framing / defer
- [ ] **A2** entities counters latent fragility — add defensive branch / leave + comment / defer
- [ ] **A3** independent_expenditures 96% dup — **HIGH PRIORITY**: rerun migration 102 + add ON CONFLICT / add ON CONFLICT only / defer
- [ ] **A4** payroll counter misleading — apply RETURNING (xmax=0) pattern / rename records_new → records_processed / defer
- [ ] **A5** expenditures counter — no action; flag as reference pattern
- [ ] **A6** donor_employer_merge thrash — **HIGH PRIORITY**: normalize employer in donor upsert / generated column / defer + update docstring

Once decided, write decisions to `docs/audits/2026-05-fix-manifest.md` and the Phase D refactor uses that as input.

