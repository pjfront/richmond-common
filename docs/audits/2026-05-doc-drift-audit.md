# Phase C Audit — Documentation Drift

**Date:** 2026-05-16
**Scope:** Every imperative rule (`must` / `always` / `never` / `every` / `no` / `don't` / `required` / `non-negotiable` / `critical`) in:
- `CLAUDE.md` (root)
- `src/CLAUDE.md`
- `web/CLAUDE.md`
- `.claude/rules/architecture.md`
- `.claude/rules/conventions.md`
- `.claude/rules/judgment-boundaries.md`
- `.claude/rules/richmond.md`
- `.claude/rules/team-operations.md`

**Methodology:** Trust Ladder — extract claim → verify enforcement mechanism exists → run/inspect enforcement → measure observable drift in the codebase. **No code changes.**

**Sequel to:** [`2026-05-counter-audit.md`](2026-05-counter-audit.md) (Phase A), [`2026-05-idempotency-audit.md`](2026-05-idempotency-audit.md) (Phase B).

---

## Executive Summary

| Status | Count | What it means |
|---|---|---|
| **ENFORCED** (test/CI/type/runtime check exists and works) | 10 | The claim is backed by automation. Future violation fails CI. |
| **CONVENTION** (no automation, but practiced consistently in the codebase) | 3 | Holds today; will silently drift if someone forgets. |
| **ADVISORY** (intentionally not enforced — judgment-call territory) | 7 | OK to leave un-enforced; surface in operator review. |
| **ASPIRATIONAL** (claim exists, no enforcement, drift observed) | 8 | The slop layer. Either fix the rule or enforce it. |
| **DIRECT CONTRADICTION** between two rule files | 2 | One of the two is wrong; reader can't tell which. |
| **STALE** (refers to outdated service / pattern) | 3 | Mis-instructs new readers. |

**The headline finding:** **CLAUDE.md L34 says "Every architectural rule worth keeping needs tooling enforcement. If a rule can't be enforced, weaken the rule until it can be."** The audit found at least **8 unenforced rules + 3 enforced-by-convention-only**, meaning the project violates its own meta-rule on ~11 of ~30 substantive rules. This isn't a moral failure — it's the gap the audit exists to surface.

**Most acute drift:**
1. **C8: Budget lock claim** — `src/CLAUDE.md:163-166` says "every Anthropic call raises" via monkey-patch. **4 entry-point scripts call `messages.create` without importing the budget lock.** Cost rails leak through those paths.
2. **C1: FIPS filtering contradiction** — `web/CLAUDE.md:96` says "every query uses `.eq('city_fips', cityFips)`" but `conventions.md:6` says "internal queries no longer need `city_fips` filters." 115 active uses across 13 query files; the contradiction has been live since 2026-05-09 pivot.
3. **C5: Source-closest artifact declaration** — `conventions.md:83` requires "Every Python script in `src/` that reads input data must declare its input artifact." 13 of 102 src/*.py have any "Reads from" string; many of those are not the docstring form the rule requires.

---

## Methodology

For each rule:

1. **Extract** — grep for the imperative word + read the surrounding sentence
2. **Classify** as ENFORCED / CONVENTION / ADVISORY / ASPIRATIONAL / CONTRADICTORY / STALE
3. **Verify** — for ENFORCED, find the test/CI/type-check and confirm it exists; for others, find observable drift in the codebase

The Trust Ladder for docs is simpler than for data:
```
Claim ("every X must Y")
   ↓ verify enforcement exists (test? linter? CI? type?)
Enforcement file
   ↓ verify it actually fires (test runs? CI triggered? type catches?)
Runtime / build behavior
   ↓ verify the codebase actually does Y
Observable state
```

If any rung breaks, the rule is at-best ASPIRATIONAL. The audit reports the highest rung that holds.

---

## Findings

### ENFORCED — 10 rules with automated checks that work

| Rule (location) | Enforcement | Verified |
|---|---|---|
| Every commit adding a new public-facing table updates `d1-provenance-manifest.yaml` (conventions.md:48-49) | `tests/test_d1_provenance.py` | ✓ File exists, test framework in place |
| Every commit adding/modifying a sync source updates `pipeline-manifest.yaml` (conventions.md:55) | `tests/test_pipeline_manifest.py::TestSyncSourceCoverage` | ✓ File exists, asserts code↔manifest match |
| Critical owners must declare ≥1 liveness expectation (conventions.md:113, src/CLAUDE.md:120) | `tests/test_pipeline_manifest.py::TestLivenessExpectations::test_critical_owners_have_expectations` | ✓ Hardcoded list of 6 owners enforced |
| Migration numeric prefixes unique (conventions.md migrations section) | `tests/test_migration_discipline.py::test_no_duplicate_numeric_prefixes` | ✓ Active prefix-collision check |
| Hand-curated `types.ts` interfaces must anchor to generated row (conventions.md:107) | `web/src/lib/types.drift.test.ts` | ✓ vitest scans for unanchored interfaces; only `CommunityComment` exempted |
| Schema drift: regenerate `database.types.ts` after any migration touching schema (conventions.md, web/CLAUDE.md:36) | `.github/workflows/schema-drift.yml` | ✓ Runs on PRs touching `src/migrations/**` or `database.types.ts`; fails on diff |
| No `any` types in TypeScript (web/CLAUDE.md:95) | `web/tsconfig.json` `"strict": true` | ✓ Strict mode catches implicit any at compile time |
| Anon-role visibility test for public tables (conventions.md "Anon visibility") | `tests/test_anon_visibility.py` | ✓ Exists; SKIPS without anon creds, which means it passes in CI unless creds present — see CAVEAT below |
| RLS policy coverage on every table with RLS enabled | `tests/test_rls_policy_coverage.py` | ✓ File exists |
| Phase 2.1 `db/` submodule cross-imports declare their helpers | `tests/test_db_module_name_resolution.py` | ✓ NEW this session (commit `234868c`); AST-based check |

**CAVEAT on anon visibility:** the test skips when `SUPABASE_URL`/`SUPABASE_ANON_KEY` env vars are missing or set to "test..." placeholders. That means the test gives a green light in CI runs that don't have real Supabase creds (`tests/test_anon_visibility.py:40-48`). The enforcement is "real but conditional" — drift only surfaces locally or when creds ARE set in CI. Phase D candidate: gate the test on a flag and fail CI when the flag is set + creds are missing.

---

### CONVENTION — 3 rules upheld by practice but not automated

| Rule (location) | Practice |
|---|---|
| **Anthropic API calls must set `temperature` explicitly** (conventions.md:18) | All 24 src/*.py files that call `messages.create` also set `temperature=...`. 24 calls / 24 files = 100% adherence today. No linter catches the next file that forgets. |
| **Auto-generated, not AI-generated** (operator memory `feedback_auto_not_ai.md`) | Codebase grep finds only 1 occurrence of `AI-generated` — in `web/src/lib/types.ts:461`, inside a JSDoc comment that isn't user-facing. User-facing labels use "Auto-generated." Practice upheld; no test. |
| **No em-dashes in user-facing prose** (operator memory `feedback_no_em_dashes.md`) | 68 files contain em-dashes; spot checks (Nav.tsx, AgendaItemCard.tsx) found them only in code comments (`//` and `{/* */}`), not in JSX strings rendered to users. Rule appears upheld; no test. |

---

### ADVISORY — 7 rules intentionally left un-enforced (judgment-call territory)

| Rule | Why no automation |
|---|---|
| Every commit completing/advancing a PARKING-LOT.md item updates the parking lot (conventions.md:42) | Tracker discipline; AI-delegable but human-flexible; PARKING-LOT updates are textual and varied. |
| AI Parking Lot maintenance: every session captures observations (conventions.md:122, judgment-boundaries.md:32) | Session-level habit, not a code invariant. |
| Don't dump strategic content into task trackers (team-operations.md:41) | Process rule; not codifiable. |
| Every non-trivial decision gets logged with date and rationale (team-operations.md:165) | Process; AI-delegable. |
| Source credibility tiers tagged per data point (CLAUDE.md:48) | This IS partly enforced (D1 covers source_tier as NOT NULL for new public tables) but the rule extends beyond what the test captures — covers framing in summaries too. |
| Publication tier assignment for every new feature (CLAUDE.md:49, team-operations.md:63-91) | Judgment-call by design. |
| `Don't generate opinion or advocacy — comments are strictly factual` (CLAUDE.md:115) | Quality rule on AI output; not mechanically checkable. |

These are correctly un-enforced. Listing here to be explicit and avoid lumping with the aspirational ones.

---

### ASPIRATIONAL — 8 rules with NO enforcement and observable drift

These violate CLAUDE.md L34's meta-rule. Each needs operator decision: **enforce, weaken, or remove**.

#### C5 — "Every Python script in src/ that reads input data must declare its input artifact" (conventions.md:83)

**Evidence:** `grep '[Rr]eads (from|raw)' src/*.py` returns 13 files. `src/*.py` has 102 files. The rule applies to "every script that reads input data" — not every file. Even charitably scoping to entry-point scripts (~24 generators), the compliance is ~13/24 = 54%, and not all 13 are in the docstring format the rule prescribes (some are inline comments).

The plan-file note said: "47 scripts that should have a declaration; only 1 does." That was either older or counted only the exact docstring-pattern form.

**Recommendation:** Either ship an AST-based check that asserts every entry-point script's module docstring starts with "Reads from..." OR weaken the rule to "code reviewer should ask the question" + delete the strong claim from conventions.md.

#### C8 — "Every Anthropic call raises [via budget lock] / is auto-logged" (src/CLAUDE.md:163-166)

**Evidence:** 4 entry-point scripts call `messages.create` but do NOT import `anthropic_budget_lock`:

```
src/correct_recap_names.py
src/extract_agenda.py
src/extract_transcript_votes.py
src/appointment_extractor.py
```

Verified via:
```bash
comm -23 \
  <(grep -rln "messages\.create" src --include="*.py" | sort -u) \
  <(grep -rln "import anthropic_budget_lock" src --include="*.py" | sort -u)
```
(11 files in the comm output; 7 are library modules that get the monkey-patch indirectly via their importing entry points. The 4 above are CLI entry points that don't.)

**Impact:** Running `python src/extract_agenda.py` invokes Anthropic with NO budget cap. The "hard kill switch" claim is false for that invocation. The "auto-logged to pipeline_journal" claim is also false — those calls aren't journaled.

This is exactly the leak the PR #26/#27 rails were meant to plug. The audit found 4 surviving holes.

**Recommendation:** Either add the import to those 4 files OR ship a `tests/test_anthropic_budget_lock_coverage.py` AST check that fails if any src/*.py file imports `anthropic` (any path) without also importing `anthropic_budget_lock`.

#### C9 — "Every web search / external API query / news fetch must say 'Richmond, California' — never just 'Richmond'" (CLAUDE.md:41, conventions.md:5, architecture.md:36)

**Evidence:** This rule appears in THREE places (a sign someone thought it was important enough to triple-tag). **Zero tests scan the codebase for it.** Compliance is operator-judgment-time only.

Manual check would require: for every `requests.get`, `urllib`, web search call, etc. — assert the query string contains `"Richmond, California"` (not just `"Richmond"`).

**Recommendation:** Either ship a regex-based test on src/*.py files that grep for `Richmond` in obvious API-call contexts OR formally demote this to an advisory + code-review checklist item.

#### C2 — "Don't put `NEXT_PUBLIC_` secrets in client bundles" (CLAUDE.md:116, web/CLAUDE.md:56)

**Evidence:** No automated check. The audit found no test that scans for secrets-shaped strings under `NEXT_PUBLIC_*`. The Phase 0 lesson (2026-05-09) that prompted this rule was a real incident.

Partial enforcement: TypeScript will not warn about `process.env.NEXT_PUBLIC_*` use (any string is allowed). The only protection is human review.

**Recommendation:** Add a `web/src/lib/__tests__/no-public-secrets.test.ts` that scans `web/src/**/*.ts` for `process.env.NEXT_PUBLIC_*` patterns containing strings that LOOK like secrets (length > 20, no spaces, contains digit + letter). Or accept the residual risk.

#### C4 — "Don't invent spellings... use canonical_names.md" (conventions.md:100)

**Evidence:** No test. The rule depends on the human-curated `canonical_names.md` being appended to LLM prompts (the system prompt mechanism). The AUDIT WOULD NEED to verify every `transcript_recap` / `meeting_recap` / `comment_summary` prompt includes canonical_names — but there's no test.

**Recommendation:** Either add a test that imports each generator's prompt-builder and asserts canonical_names appears as a substring, OR weaken.

#### C6 — "Performative boundaries are worse than no boundaries" (CLAUDE.md:34) — META RULE

**Evidence:** The audit itself proves this rule isn't enforced — 8 aspirational rules persist (this list). The meta-rule says they should be weakened until they CAN be enforced; instead they live in CLAUDE.md as strong claims.

**Recommendation:** Either (a) make Phase D close most of these enforcement gaps, OR (b) explicitly tag each surviving aspirational rule with `[aspirational]` so readers know which ones lie.

#### C7 — "After every visual change, before committing: Use Claude Preview tools" (web/CLAUDE.md:84)

**Evidence:** Operator memory `feedback_skip_preview.md` says: "Skip preview_* verification; use `next build` instead." Direct contradiction between web/CLAUDE.md and operator memory.

**Recommendation:** Remove web/CLAUDE.md lines 82-91 (the entire Visual Verification section) OR update to match `next build` flow.

#### C10 — "Hand-curated lists should be replaced with pattern detection or database queries" (judgment-boundaries.md "Hardcoded data list maintenance")

**Evidence:** Pattern check would require finding all hardcoded lists in `src/` and `web/`. Spot evidence of compliance: city_config.py uses a FIPS-keyed dict, conflict_scanner uses Census surname data not hardcoded names. But MANY hardcoded lists exist in scanner exclusions, council member name lists, generic-employer-filter lists. No automation.

**Recommendation:** Demote to "code reviewer should check" advisory.

---

### DIRECT CONTRADICTION — 2 cases where two rule files disagree

#### C1 — FIPS filtering: required vs not-required

**Rule A** (`web/CLAUDE.md:96`): *"FIPS filtering everywhere. Even with single-city data, every query uses `.eq('city_fips', cityFips)`."*

**Rule B** (`CLAUDE.md:41`, `.claude/rules/conventions.md:6`, `.claude/rules/architecture.md:30-34`): *"Internal queries no longer need `city_fips` filters. The DB is single-tenant... New queries should drop the filter; existing queries migrate when touched."*

**Codebase reality:** 115 `city_fips` occurrences across 13 query files in `web/src/lib/queries/*.ts`. Rule A is being followed; Rule B is aspirational.

**Background:** The 2026-05-09 single-city pivot (per architecture.md) made `city_fips` filters useless for selectivity (one row in `cities`). Phase 3 of the rearchitecture plan is to drop ~30 `(city_fips)` indexes wholesale, which only makes sense if queries stop filtering.

**Recommendation:** This is the operator's call. Either:
- (A) Keep filtering — update root CLAUDE.md and conventions.md to revert
- (B) Stop filtering — update web/CLAUDE.md, AND tag all 115 existing filter uses for removal during Phase 3
- (C) "Stop adding new filters; old ones stay" — explicitly state that and update both files

The contradiction has lived since the 2026-05-09 pivot. Resolving it should happen before Phase 3 of the rearchitecture plan ships.

#### C3 — Visual verification: required vs skip

**Rule A** (`web/CLAUDE.md:84`): "After every visual change, before committing: Use Claude Preview tools to verify your work against design rules."

**Rule B** (operator memory `feedback_skip_preview.md`): "Skip preview_* verification; use `next build` instead (Supabase timeouts make preview useless)."

**Reality:** Operator memory wins (per the override-by-memory pattern). web/CLAUDE.md is stale.

**Recommendation:** Update web/CLAUDE.md.

---

### STALE — 3 docs reference outdated tools or patterns

#### C11 — Upstash rate-limiting comment in API routes section (web/CLAUDE.md:77)

**Evidence:** Line 77 reads: "`POST /api/feedback` — User feedback. Upstash-rate-limited."

**Reality:** Per web/CLAUDE.md:58-65 (later in the same file), the project moved to Postgres-backed rate limiting via `rate_limit_buckets` + `check_and_increment_rate_limit` RPC (migration 106). The "Upstash" reference is stale within the same file.

**Recommendation:** Change to "Postgres-rate-limited via `@/lib/rate-limit`."

#### C12 — System health "Documentation Drift" 14 stale references in web/CLAUDE.md (SessionStart report)

**Evidence:** The SessionStart hook reported 14 stale references including `meetings.ts`, `council.ts`, `elections.ts`, etc. **These files DO exist** in `web/src/lib/queries/`. The stale-reference detector seems to be looking in the wrong directory.

**Recommendation:** Either fix the detector to search `web/src/lib/queries/` OR add path prefixes in web/CLAUDE.md.

#### C13 — "Use Claude Code through the Claude desktop app, NOT VS Code extension" (conventions.md:160)

**Evidence:** Operator works in WSL/PowerShell environment. The "NOT VS Code extension" claim was relevant when the VS Code extension lagged; it may no longer be. Worth a quick verification with the operator.

**Recommendation:** Verify with operator whether still accurate; either keep, qualify, or remove.

---

## Cross-cutting observations

### Where the rules are densest, the enforcement is best

Rules about the **manifest + migrations + types** layer (D1 provenance, pipeline manifest sync, schema drift, types anchoring, migration discipline) have **multiple enforcing tests + CI workflows**. These are the rules that landed alongside their tests — the discipline held.

Rules about **process, voice, framing, source disambiguation** have **almost no enforcement**. These are the rules that landed in docs without a same-commit test. Pattern: when a rule is mechanically checkable but no test ships, the rule decays.

### The "every Anthropic call" claim is the most concerning

C8 directly negates the protection that PR #26/#27 was built to provide. Operator paid for the lesson; the rails were the response; 4 entry points still bypass them. Adding the import to those 4 files is a 4-line fix; the test that prevents future regressions is ~30 lines.

### Aspirational rules harm trust more than no rules

The audit's most uncomfortable finding (operator-perspective): rules that LOOK enforced but aren't are worse than rules that don't exist. A new contributor reading CLAUDE.md and seeing "Every X must Y" assumes Y is checked. When it isn't, the contributor (or future-me) will violate the rule unaware. The 8 aspirational rules listed above all have this property.

This is itself an instance of the broader "implemented vs. verified" problem the operator surfaced. Docs that claim "we always do X" without a check are exactly the kind of confident-wrong claim the audit was created to root out.

---

## Operator review — Phase C decisions

For each finding: **enforce** (write test/check), **weaken** (rephrase rule to match practice), **remove** (delete claim), or **defer**.

| ID | Class | Recommended action |
|---|---|---|
| C1  (FIPS filtering contradiction) | CONTRADICTION | **Resolve** — pick (A) or (B) explicitly, update both files |
| C2  (no NEXT_PUBLIC secrets test) | ASPIRATIONAL   | **Defer** or weaken to advisory — risk has been low post-2026-05-09 fix |
| C3  (visual verification stale) | STALE          | **Remove** stale section, replace with operator's `next build` flow |
| C4  (canonical_names not enforced) | ASPIRATIONAL | **Defer** — low risk; add test in Phase D if priority |
| C5  (source-closest declaration drift) | ASPIRATIONAL | **Enforce or weaken** — at 54% compliance the rule is half-broken |
| C6  (meta-rule violations) | ASPIRATIONAL | **Accept** outcome of this audit as the answer; tag survivors `[aspirational]` |
| C7  (visual-verification contradiction) | CONTRADICTION | Same as C3 |
| C8  (4 Anthropic budget-lock holes) | ASPIRATIONAL | **Enforce** — high-impact, cheap fix |
| C9  ("Richmond, California" rule unenforced) | ASPIRATIONAL | **Weaken** to advisory + add `src/CLAUDE.md` checklist |
| C10 (hardcoded-lists rule) | ASPIRATIONAL | **Weaken** to advisory |
| C11 (Upstash stale reference) | STALE | **Fix in same commit** as you fix C3 |
| C12 (system_health stale-doc detector wrong) | STALE | **Fix detector** in Phase D |
| C13 (VS Code extension claim) | STALE | **Verify with operator** |

---

## Phase D refactor themes from Phase C

Layered on top of Phase B's themes:

4. **`[enforced]` / `[advisory]` / `[aspirational]` tag on every CLAUDE.md rule.** This is the cheap version of Principle 3 from the audit plan. Future contributors can tell at a glance which rules will fail CI vs which are honor-system.

5. **AST coverage for project-wide invariants.** The pattern from `tests/test_db_module_name_resolution.py` (this session) and `web/src/lib/types.drift.test.ts` works. Apply to:
   - Anthropic budget lock import coverage (C8)
   - Source-closest artifact docstring (C5)
   - `process.env.NEXT_PUBLIC_*` secret-shaped strings (C2)
   - "Richmond" without "California" in API call sites (C9)

6. **Doc-drift sentinel test.** A test that fails when CLAUDE.md grows a new "every" / "always" rule without a citation to its enforcement file (`[enforced by tests/test_xxx.py]` pattern). Hardcodes the meta-rule.

---

## How to re-run this audit

1. Re-grep for imperative-word claims: `rg -n '\b(MUST|must|always|never|every|Every|required|non-negotiable|critical|Don.t|DO NOT)\b' CLAUDE.md .claude/rules/ src/CLAUDE.md web/CLAUDE.md`
2. For each new claim, check: does a `tests/` file or `.github/workflows/` file enforce it?
3. If yes, run the test to confirm green
4. If no, decide: ENFORCE / WEAKEN / REMOVE / ADVISORY

Time to re-run: ~30 min for the full pass.

---

## What this audit does NOT cover

- **`docs/` directory rules** (DESIGN-RULES-FINAL, DESIGN-DEBT, etc.). These are mostly process documents and reviewed at PR time; out of Phase C scope.
- **`docs/plans/` and `docs/specs/` claim verification.** Plans often promise future behavior; verifying a plan-claim is "in Phase 3 we will X" requires checking what Phase 3 actually did, which is a different audit.
- **README and external-facing docs.** Out of scope.
- **Skill/plugin files** in `~/.claude/`. Local to operator environment; not a Richmond Commons concern except via judgment-boundaries override.
- **Migration content rules** (idempotent SQL patterns). Covered by `tests/test_migration_*.py` series; not re-audited here.

---

## File pointer

- [`2026-05-counter-audit.md`](2026-05-counter-audit.md) — Phase A (counters)
- [`2026-05-idempotency-audit.md`](2026-05-idempotency-audit.md) — Phase B (idempotency)
- `~/.claude/plans/steady-crafting-island.md` — master audit plan

Next: **Operator review of A + B + C.** Once that produces `docs/audits/2026-05-fix-manifest.md`, Phase D refactor proceeds against the manifest.
