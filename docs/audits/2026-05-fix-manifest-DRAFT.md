# 2026-05 Audit Fix Manifest — DRAFT (operator review pending)

**Status:** Draft. AI compiled this from A+B+C findings; operator decides each row.
**Inputs:**
- [`2026-05-counter-audit.md`](2026-05-counter-audit.md) — Phase A (6 findings: A1-A6)
- [`2026-05-idempotency-audit.md`](2026-05-idempotency-audit.md) — Phase B (12 findings: B1-B12)
- [`2026-05-doc-drift-audit.md`](2026-05-doc-drift-audit.md) — Phase C (13 findings: C1-C13)

**Total findings:** 31, clustered into 9 fix bundles by root cause.

**How to use this:** Walk top to bottom. For each bundle, check the box for your decision (FIX / DEFER / ACCEPT / OTHER), or write a one-line note. AI executes only what you check. Save your edits in place — this doc becomes the Phase D execution input.

---

## Priority order (AI recommendation)

| # | Bundle | Cost to fix | Risk if unfixed | Compounding? |
|---|---|---|---|---|
| 1 | Budget lock leak (C8) | ~30 lines + 1 test | $-leak through 4 entry points | Yes — every Anthropic call through those paths bypasses cap |
| 2 | CAL-ACCESS IE write-amp (A3/B1) | 1 loader fn + cleanup migration | +4,300 dup rows/month | Yes — monthly cron |
| 3 | Data cleanup migrations (B3, B6, B7, B4, B5) | 1 migration file | UI serves dup data today | No — static; would not grow |
| 4 | Counter Contract Standard (A1, A4, B9-B12) | dataclass + linter + sweep | Counters lie; operator can't trust dashboards | No — wrong info, not wrong data |
| 5 | FIPS filtering contradiction (C1) | doc edit OR codebase sweep | Reader can't tell what's right | No — confusion only |
| 6 | Tag every CLAUDE.md rule (C6 + meta) | ~30 doc edits | Aspirational rules feel enforced; future drift hidden | Yes — every new rule will inherit the ambiguity |
| 7 | Donor-employer thrash root cause (A6, B2) | donor-upsert key widening | Wasted writes; thrash cycle every sync | Yes — 688 merges/run × 13 runs/wk |
| 8 | Stale doc cleanup (C3, C7, C11, C12, C13) | small doc commit | Reader follows old patterns | No — slow decay |
| 9 | Deferred/coverage gaps (B8, C2, C4, C9, C10) | varies | Latent | Varies |

Bundles 1-3 are the "stop the bleed + clean the wound" set. Bundles 4-6 are "make the structural standard explicit." Bundle 7 is its own root-cause investigation. Bundle 8 is housekeeping. Bundle 9 is "you said defer."

---

## Bundle 1 — Budget lock leak

**Decision:** ☐ FIX ☐ DEFER ☐ ACCEPT ☐ OTHER: _______________

**Findings:** C8

**What's broken:** 4 entry-point scripts call `messages.create` without importing `src/anthropic_budget_lock` — running them bypasses both the kill switch (`RICHMOND_API_BUDGET_LOCK=true`) and the auto-journaling. The cost rails added in PR #26/#27 don't cover these paths.

**Files to change if FIX:**
- Add `import anthropic_budget_lock  # noqa: F401` as first import in:
  - `src/correct_recap_names.py`
  - `src/extract_agenda.py`
  - `src/extract_transcript_votes.py`
  - `src/appointment_extractor.py`
- New test: `tests/test_anthropic_budget_lock_coverage.py` — AST scanner that asserts every `src/*.py` file importing `anthropic` (any path) also imports `anthropic_budget_lock`. Pattern from `tests/test_db_module_name_resolution.py`.

**Estimated effort:** 30 minutes including the test.

**AI recommendation:** FIX. Lowest effort + highest dollar impact on the audit board.

---

## Bundle 2 — CAL-ACCESS IE write amplification

**Decision:** ☐ FIX (+ cleanup migration) ☐ FIX (no cleanup yet) ☐ PAUSE SYNC ☐ DEFER

**Findings:** A3, B1, partial B9

**What's broken:** `src/db/expenditures.py::load_expenditures_to_db` uses plain `INSERT` with no `ON CONFLICT`. Every CAL-ACCESS monthly cron run adds the entire IE dataset again. Current state: 54,800 rows, 52,540 dups (96.2%), 2,260 unique. Per Phase A migration 102 did this cleanup once (dropping ~120K → ~2,252); the table grew back to 54,800.

**Files to change if FIX:**
- `src/db/expenditures.py::load_expenditures_to_db` → add `ON CONFLICT (city_fips, committee_name, candidate_name, amount, expenditure_date) DO UPDATE ... RETURNING (xmax = 0) AS inserted` pattern (copy from `src/pipelines/socrata.py::sync_socrata_expenditures`, the reference impl)
- Migration `src/migrations/NNN_dedup_independent_expenditures_v2.sql` — DELETE dups based on the same natural key (one-off; same shape as migration 102 but should land WITH the loader fix)
- Counter fix in `src/pipelines/calaccess.py:75-84` (use `inserted`/`updated` from the loader instead of `loaded += 1`)

**Estimated effort:** 90 minutes including test.

**AI recommendation:** FIX + cleanup migration in same commit. The "fix code without cleaning data" pattern is exactly the B3/B7 pitfall — don't repeat it.

---

## Bundle 3 — Stale dup-data cleanup (one-off migrations)

**Decision:** ☐ FIX (all together) ☐ FIX (per-finding, pick which) ☐ DEFER

**Findings:** B3 (4,941 conflict_flag dups), B6 (10 city_employee dups), B7 (25 scan_run dups), B4 (~39 archive_center dup docs), B5 (15 escribemeetings dup docs)

**What's broken:** Historical write-amplification bugs. Code-level gates have stopped new dups in B3 (since 2026-03-30) and B7 (same era). B4/B5/B6 are smaller. None are actively growing today. But the rows ARE visible to `is_current=TRUE` queries (B3) or as duplicate documents downstream.

**Files to change if FIX:**
- Single migration `src/migrations/NNN_cleanup_audit_dups.sql` covering:
  - `conflict_flags`: collapse (meeting_id, flag_type, description) groups, keep MIN(id)
  - `scan_runs`: keep latest by (meeting_id, scan_mode), mark others superseded (don't delete — audit trail)
  - `documents`: keep latest by (source_type, source_identifier) where `metadata->'refreshed_from'` is NULL
  - `city_employees`: collapse (city_fips, name, fiscal_year, source) keep highest annual_salary
- Test: `tests/test_dup_cleanup_migration.py` — runs migration on a fixture DB, asserts row counts match expected post-cleanup

**Estimated effort:** 2 hours including test.

**AI recommendation:** FIX all together as one migration. Same pattern, same effort to ship one as five.

---

## Bundle 4 — Counter Contract Standard

**Decision:** ☐ ADOPT (Phase D refactor) ☐ FIX FINDINGS NOW (no standard) ☐ DEFER

**Findings:** A1 (contributions), A4 (payroll), B9 (archive_center), B10 (nextrequest), B11 (behested), B12 (lobbyist)

**What's broken:** Six loaders increment `stats["X"] += 1` after every execute, regardless of whether the row actually inserted vs DO-UPDATEd vs no-opped. The counter is "calls that didn't raise," not "rows changed." Operator dashboard reads the counters; they lie systematically.

**ADOPT the standard:** Phase D refactor target (audit plan principle 1):
```python
@dataclass(frozen=True)
class XSyncStats:
    fetched_from_api: int
    inserted: int          # MUST come from cur.fetchone()[0] on RETURNING (xmax = 0)
    updated: int           # MUST come from same path; xmax != 0
    conflict_noop: int     # ON CONFLICT WHERE matched but condition false
    skipped_malformed: int
    def invariant(self) -> None: ...  # raises if counters don't sum
```
- Lint rule: any loader returning `dict` instead of `XSyncStats` fails CI
- Apply to all 6 affected loaders + 14 untouched-but-vulnerable loaders

**FIX FINDINGS NOW alternative:** Patch each of the 6 loaders to use `RETURNING (xmax = 0)` directly (the reference pattern from `socrata_expenditures` and the netfile contributions counter fix from commit `dcebd20`). No dataclass yet, no linter — just consistent counter logic.

**Estimated effort:**
- ADOPT: 1-2 days for dataclass + linter + sweep
- FIX FINDINGS NOW: 3-4 hours total

**AI recommendation:** FIX FINDINGS NOW for the 6 affected loaders, then ADOPT (dataclass + linter) in a second pass once the pattern is consistent. Bundle 4 then becomes "the standard already lives in 6 loaders; promote to enforced."

---

## Bundle 5 — FIPS filtering contradiction (C1)

**Decision:** ☐ A: Keep filtering (revert root rule) ☐ B: Stop filtering (deprecate the column filter) ☐ C: Stop for new, keep for old ☐ OTHER

**Findings:** C1 (contradiction between web/CLAUDE.md:96 and conventions.md:6)

**What's broken:** Two docs say opposite things. 115 active uses follow web/CLAUDE.md. Phase 3 of the rearchitecture plan only makes sense under option B.

**Files to change by option:**
- (A) Update root CLAUDE.md + conventions.md + architecture.md to revert "no city_fips filter" claim. ~5-line edit.
- (B) Update web/CLAUDE.md to remove FIPS-filtering rule. Tag the 115 current uses with a `// TODO(phase-3): drop city_fips filter` comment. Phase 3 of the rearchitecture sweeps them.
- (C) Update both docs to say "new queries drop the filter; existing ones stay until touched." 4-line edit each.

**AI recommendation:** (C) is the path of least resistance and matches the actual practice. The rearchitecture plan still gets to land Phase 3 someday; we don't have to enforce it now.

---

## Bundle 6 — Tag every CLAUDE.md rule with enforcement status

**Decision:** ☐ ADOPT (sweep all rule files) ☐ ADOPT (per-rule as touched) ☐ DEFER

**Findings:** C6 (meta-rule violation), plus the 8 aspirational rules surfaced by Phase C

**What's broken:** CLAUDE.md L34 says every rule worth keeping needs tooling enforcement. The audit found 8 rules that don't have enforcement but read as if they do. New contributors (or future-me) follow the rules, believe they're checked, and don't notice when they're violated.

**Standard:** Each "must / always / never / every / no" rule gets a parenthetical tag:
- `[enforced by tests/test_xxx.py]` — automated check exists
- `[advisory]` — judgment-call zone, not mechanizable
- `[aspirational — Phase D]` — claim is correct, enforcement is planned

Example transformation:
```
- "Every Anthropic API call must set temperature explicitly."
→ "Every Anthropic API call must set temperature explicitly.
    [convention only — no automated check; aspirational]"
```

**Files to edit if ADOPT:** All 8 rule files. Per-rule sweep. ~30 rules to tag.

**Estimated effort:** 1 hour.

**AI recommendation:** ADOPT (sweep all). This is the cheapest single thing we can do that closes the "rules that lie" gap. It doesn't fix any rule — it makes which-ones-lie discoverable.

---

## Bundle 7 — Donor-employer thrash root cause

**Decision:** ☐ FIX (widen donor upsert key) ☐ FIX (drop merge job from cron) ☐ DOCUMENT only ☐ DEFER

**Findings:** A6, B2

**What's broken:** Each `sync_netfile` run creates donor rows fragmented by tiny employer-string variations ("California" vs "California State Assembly"). `sync_donor_employer_merge` then collapses them (avg 688 merges/run, 13 runs/wk). On a clean DB the NEXT netfile sync re-fragments. Loop. Wasted writes, churning indexes.

**Options:**
- **FIX (widen donor upsert key):** Change donor upsert in `src/db/contributions.py` to upsert on `(normalized_name)` only, ignoring employer string. Promote employer onto existing donor if currently empty. Eliminates the thrash at the source. Risk: cross-donor collisions for same-named different people (need handling).
- **FIX (drop merge job from cron):** Stop running `sync_donor_employer_merge` automatically. Run manually only when cleanup needed. Saves the wasted writes; accepts continuous fragmentation (uglier `donors` table, won't hurt downstream queries that use `normalized_name`).
- **DOCUMENT only:** Update the docstring at `src/pipelines/netfile.py:172` to remove "Idempotent — re-running on a clean DB is a no-op" and replace with the truth: "Operates as a thrash partner to `sync_netfile`; merges ~688 donor rows per run; runs after every netfile sync via the manifest DAG."

**AI recommendation:** DOCUMENT now (1-line change). Defer real fix to Phase D — needs the donor-key-widening design discussion, which is a judgment call about how to handle same-name-different-person.

---

## Bundle 8 — Stale doc cleanup (housekeeping)

**Decision:** ☐ FIX ALL ☐ FIX SELECTED: _______________ ☐ DEFER

**Findings:** C3 (visual-verification stale), C7 (visual-verification contradiction), C11 (Upstash reference stale), C12 (system_health stale-doc detector wrong), C13 (VS Code extension claim)

**Files to edit if FIX ALL:**
- `web/CLAUDE.md` line 77: change "Upstash-rate-limited" → "Postgres-rate-limited (`@/lib/rate-limit`)"
- `web/CLAUDE.md` lines 82-91: replace "Visual Verification" section with the operator's `next build` flow (or delete entirely)
- `src/system_health.py` (or wherever the stale-doc detector lives): fix the path it scans for queries/*.ts
- `.claude/rules/conventions.md` line 160: verify VS Code extension claim with operator; either keep, qualify, or remove

**Estimated effort:** 30 minutes.

**AI recommendation:** FIX ALL. Trivial, removes confusion.

---

## Bundle 9 — Deferred coverage gaps

**Decision:** Each row individually:
- B8 (nextrequest_documents empty) — ☐ Wire documents API ☐ Document the choice ☐ Defer
- C2 (no NEXT_PUBLIC secret scan) — ☐ Add scan ☐ Defer
- C4 (canonical_names enforcement) — ☐ Add test ☐ Defer
- C9 (Richmond/California codebase scan) — ☐ Add test ☐ Demote to advisory
- C10 (hardcoded lists) — ☐ Demote to advisory

These are all "claim exists, drift not actively causing damage, fix is non-trivial." Reasonable to defer.

**AI recommendation:** Defer all five except B8. For B8, document the "we deliberately don't load nextrequest documents" choice in the sync_nextrequest docstring; that's a 1-line change.

---

## What Phase D looks like after operator approval

The fix manifest above produces a Phase D scope. Once bundles are decided:

1. **Bundles 1-3 (stop bleed + clean wound)** — Sprint 1 of Phase D. Single-purpose commits. Each ships with a test that verifies at the outcome layer (`SELECT COUNT(*)` queries the operator can re-run).
2. **Bundle 4 (Counter Contract Standard)** — Sprint 2. Loader-by-loader migration. Lint goes on at the end.
3. **Bundles 5-6 (FIPS + rule tags)** — Sprint 3. Doc-heavy work, low code risk.
4. **Bundle 7 (donor thrash)** — Sprint 4 if not deferred. Needs design conversation first.
5. **Bundle 8 (stale doc cleanup)** — Bundled into one commit during whichever sprint touches the most files.
6. **Bundle 9 (deferred)** — Backlog. Re-audit in 3 months.

Each Phase D commit follows the audit plan's principles:
- Test FIRST, fix SECOND
- Counter from `RETURNING (xmax = 0)`, never increment-then-execute
- Cleanup migration in same commit as the bug fix
- Docstring + `[enforced by tests/test_xxx.py]` cross-reference

---

## Operator sign-off

When done reviewing, mark the file:

```
Reviewed: <YOUR DATE>
Approved bundles for Phase D: [list bundle numbers]
Deferred bundles: [list]
Notes: [any]
```

Once sign-off lands, AI proceeds against the approved bundles in priority order with no further prompts unless a fix uncovers something not anticipated in the manifest.
