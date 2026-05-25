# Post-Election Rearchitecture Sprint (2026-06+)

> **Status banner — load-bearing. Read this first in any new session.**
>
> **Created:** 2026-05-25, after the pre-election stability sweep
> **Election:** 2026-06-02 (Richmond mayoral + council primary). Most items below are deliberately deferred until after this date.
> **Sprint resumption target:** ~2026-06-03 (day after primary)
>
> **What's done:** Tier 0 of the audit (shipped 2026-05-16/17) plus emergent pre-election work this session. Do not re-execute anything in the "Done" section without checking `git log` first.
>
> **What's open:** Tier 1, Tier 2, and Phase D of the original audit + an emergent backlog discovered during the 2026-05-25 stability sweep. Listed below with priority and effort estimates.
>
> **Pickup pattern:** any future session can resume by referencing this doc. The original audit context lives at `C:\Users\Phillip\.claude\plans\steady-crafting-island.md` (rich history) and parking-lot entries D58-D68 in `docs/AI-PARKING-LOT.md` (per-item case studies).

---

## Origin

This sprint is the continuation of the audit captured in `C:\Users\Phillip\.claude\plans\steady-crafting-island.md`. That audit was triggered on 2026-05-16 by a contributions sync that reported `records_new: 1591` as "verified live end-to-end" when the database showed ~6 actually-new rows in one window — a "trust the intermediate signal" failure pattern. The audit shipped Tier 0 as the pre-election stability layer; everything below was scoped to post-election when the time pressure lifts.

The 2026-05-25 stability sweep (this session) extended Tier 0 with five emergent items (D66 OpenAI passthrough, D67 mayor artifact validation, D68 cost-estimation lessons, PR #37 doc drift cleanup, PR #38 Socrata timeout + cap-graceful-skip). Those are also in the "Done" section below.

The June 1 cap-revisit is handled by a scheduled task at `~/.claude/scheduled-tasks/cap-revisit-june-1/SKILL.md`, separate from this sprint.

---

## Done (as of 2026-05-25)

**Tier 0 from steady-crafting-island (shipped 2026-05-16/17):**
- T0.1 — CI pytest exit-code propagation (commit `d5d4255`) + PR-only branch protection follow-on (`0011eaa`, `2ef8bdf`)
- T0.2 — Vercel deploy gate (`vercel.json` + manual promote) + `web/scripts/deploy-prod.sh` (commit `6e12e71`)
- T0.3 — Anderson reconciliation via DB-backed form summary cache (commit `8facebf`)
- T0.4 — Sync anomaly hold gate (commit `5b9b9fc`, `tests/test_sync_anomaly_hold.py`)
- T0.5 — Risk-first SessionStart reorder (commit `b06294e`)
- D56 Bug A — cache duplication migration 115 (2026-05-17)
- D56b Bug B — Form 460 cover policy shipped (2026-05-17)

**Emergent pre-election (this session, 2026-05-22 → 2026-05-25):**
- D56b graduation cascade — bucket UI graduated with `bucket_grid_consistent` flag (PR #32)
- 17.6GB upload prevention — `.vercelignore` + `deploy-prod.sh` 50MB/2000-file gate (PR #33) + anchor-pattern fix (PR #34)
- D66 — `OPENAI_API_KEY` passthrough in GH Actions workflow + Vercel env (PR #35); verified hybrid search live on prod
- D67 — Mayor funding artifact validated against live DB; graduation BLOCKED on 2 bugs documented; gates stay `pending_graduation` (PR #36)
- web/CLAUDE.md drift cleanup — 6 areas of stale references corrected (PR #37)
- 2 recurring Data Sync failures fixed — Socrata 10s read timeout → 60s; Anthropic `AnthropicMonthlyCapError` → graceful exit-0 skip in `self_assessment.py` (PR #38)
- D68 — Cost-estimation lessons captured + scheduled task `cap-revisit-june-1` set for 2026-06-01 09:00 PT (PR #39)
- 332 embedding catchup + Mon 5/26 orientation email (sent to 2 subscribers) via cap-bumped workflow dispatch

---

## Open work, organized by tier

### Tier 1 — process improvements (priority: high; all AI-delegable, mostly mechanical)

| ID | Item | Cost (operator review) | Notes |
|---|---|---|---|
| T1.1 | Rule-enforcement tag sweep. Tag every imperative rule in `CLAUDE.md`, `src/CLAUDE.md`, `web/CLAUDE.md`, `.claude/rules/*.md` with `[enforced by tests/X.py]` / `[advisory]` / `[aspirational]`. Add a new rule: "A red test on main is P0. Acceptable resolutions: fix the bug, fix the test, or `pytest.mark.xfail(reason=...)`. Never 'pre-existing, unrelated.'" Wire to CI. | ~10 min | Large diff but mechanical; spot-check 3-5 tags for accuracy |
| T1.2 | Reality-check test suite. Extend the Anderson pattern (`test_paper_filing_dbtotal_matches_form_460_cover`) to every public-facing data path: council profile totals, meeting recaps, conflict flags, contribution rollups. New: `tests/integration/test_public_facing_correctness.py` opt-in via `RICHMOND_RUN_DB_TESTS=1`. | ~10 min | Read 1-2 example tests, approve pattern, AI extends |
| T1.3 | Slop sentinel weekly action. New `.github/workflows/slop-sentinel.yml` — scheduled weekly Claude session reviews last 7 days of commits for known anti-patterns ("pre-existing failures" phrase, counter increments without `RETURNING`). Surfaces drift as `decision_queue` P0 items. Gated by `anthropic_budget_lock`. | ~10 min initial calibration | Cost: ~$0.10-0.50 per run |
| T1.4a | C12 — fix `system_health` stale-doc detector that mis-reports valid `queries/` files | ~2 min | |
| T1.4b | C13 — verify or remove the "NOT VS Code extension" claim in `conventions.md` | ~2 min | |
| T1.4c | C2 — `tests/test_no_public_secrets.py` scanning for `NEXT_PUBLIC_*` env vars with secret-shaped values | ~2 min | |
| T1.4d | C9 — codebase-grep test for `"Richmond"` without `"California"` in obvious API-call contexts (or demote rule to advisory) | ~2 min | |

### Tier 2 — backlog (priority: medium; mix of mechanical + judgment)

| ID | Item | Operator decision needed? | Notes |
|---|---|---|---|
| D-7 | Donor-employer thrash root-cause fix (A6/B2 from the audit). The contributions gate is 94% effective but ~1,500 misses per sync because the natural key fragments when donors update their employer. | YES — same-name-different-person handling strategy | AI drafts 2-3 design options before coding |
| Principle 4 | Module Contract blocks across `src/` — every src/ module starts with a CONTRACT block (reads from / writes to / verified by / failure mode). Missing/stale CONTRACT blocks fail CI. | No — mechanical | Bulk addition; one PR per package |
| Principle 2 | Integration tests as default for write-paths. Pure-logic functions stay unit-tested; ALL pipeline write-paths get integration tests against a real Postgres (Supabase preview branch or testcontainers — decision deferred) | YES — testcontainers vs Supabase preview branch | The infrastructure decision is the gating judgment call |
| C4 | `canonical_names.md` enforcement test — verify every transcript-derived generator's prompt includes `canonical_names.md` | No — mechanical | AST scan; small |
| B8 | `nextrequest_documents` coverage gap — wire the documents API or document the deliberate choice not to | YES — scope decision | |

### Phase D — the structural rearchitecture (priority: ambitious; needs explicit operator green-light)

The Phase D refactor is the original audit's "what would good look like" target. It's NOT a single PR — it's a multi-week rewrite of how pipeline modules express their contracts, verify their behavior, and report their results.

| Principle | What it means | Why it matters | Status |
|---|---|---|---|
| 1. Counter Contract Standard | Replace ad-hoc `stats[]` dicts with typed `@dataclass(frozen=True)` per sync source — each counter has a defined semantic + an `invariant()` method | Eliminates the original audit trigger: counter says one thing, DB shows another | Designed in REVISION 2; not started |
| 2. Integration tests as default | All write-paths tested against real Postgres | Catches counter-vs-reality gaps at PR time, not in production | Designed; testcontainers vs preview-branch is open |
| 3. Linter-enforced conventions | Every "must" rule in CLAUDE.md has a pytest test or a custom check | Discipline-based rules decay; mechanical rules don't | T1.1 is the prerequisite tagging pass |
| 4. Module Contract blocks | Every src/ module starts with a structured CONTRACT block | New AI agents reading any module can determine in 30s what it does + what's verified | Tier 2 above is the same item |
| 5. Manifest as SSoT | `docs/pipeline-manifest.yaml` gets `expected_counters` per source; machine-checkable invariants | Counter semantics live in the manifest, not scattered docstrings | Manifest already exists; needs expansion |
| 6. Live gates, not post-hoc | Move post-hoc checks (`system_health`, `data_quality_checks`, `staleness_monitor`) to write-time. CHECK constraints, cursor-level slow-query logging, in-transaction invariant checks | Anomalies caught at write time can't reach the operator brief in the first place | Aspirational; some items already in-flight |
| 7. Telemetry-as-truth | Replace stats dicts with `pipeline_event` rows. Counters are SQL aggregations over the event log, not in-process state | Counter and DB CAN'T disagree because the counter IS the DB | Stretch; deferred until 1-6 land |

### Emergent backlog from 2026-05-25 stability sweep

Discovered during the post-cap-bump liveness investigation. Operator triaged these as "Bucket B/C — defer to post-election" on 2026-05-25.

| # | Severity | Owner | Issue |
|---|---|---|---|
| L1 | **HIGH** | paper_filing_reconciliation | $160,807 reconciliation gap on filing 216779708 (Vision OCR likely missed contributions). Pre-election relevant IF it's a 2026 candidate; deferred pending committee identification. |
| L2 | **HIGH** | recap_generation | 1 regular meeting 19 days post-meeting without `transcript_recap`. Different root cause from D67 (transcript source file dependency, not Anthropic cap). |
| L3 | medium | candidate_discovery | Melvin Willis 2020 candidacy linked to his 2024 committee. 1-line UPDATE. |
| L4 | medium | netfile | Keycha Gallon (Council D4) + Mark Wassberg (Mayor) have `committee_id = NULL`. Wassberg historically perennial-no-committee; Gallon needs verification. |
| L5 | medium | netfile | Mayor committee Ahmad Anderson last contribution 2026-05-04 — may be real (no new filings) or sync gap; investigate |
| L6 | medium | escribemeetings_minutes | 11 meetings >45d post-meeting without `minutes_url` — likely commission meetings; may need an exemption rule rather than a fix |
| L7 | medium | vote_explainer_generation | 2 explainers cite $225K + $95K dollar amounts not in source data (potential hallucination) |
| L8 | low | nextrequest | Last NextRequest sync update 2026-05-07 (>16d ago) — daily-nextrequest job may be skipping; investigate |

### Cap policy revisit (separate from this sprint, but worth knowing about)

`RICHMOND_API_MONTHLY_CAP_USD` was bumped from $5 to $7 on 2026-05-25. A scheduled task `cap-revisit-june-1` fires 2026-06-01 09:00 PT with the full revisit checklist. See parking-lot D68 for context. If the task fires while Claude Code is closed, it runs on next launch — so just opening the app at any point in early June will trigger it.

---

## Recommended first batch (when post-election work resumes)

Pick 1-2 from Tier 1 to build momentum, then 1 from emergent backlog if it's still relevant:

1. **T1.1 (rule-enforcement tag sweep)** — Tier 1, large diff but mechanical, sets up Phase D Principle 3
2. **L1 (paper_filing $160K gap)** — emergent backlog, HIGH severity; verify committee identity, then either re-run Vision extraction OR accept and document
3. **L3 (Willis cross-cycle committee link)** — emergent backlog, 1-line UPDATE, quick win

After those: T1.4 cleanup items (C2/C9/C12/C13) and L4 committee gap verification are all small/medium scope.

Phase D Principles 1-3 are the next major target. They're best tackled as a coordinated sequence (1 → 3 → 2 → 4 → 5 → 6 → 7) but each principle is independently shippable.

---

## Out of scope for this sprint

- The cap revisit on 2026-06-01 (handled by the scheduled task)
- The unfinished Phase 2.10 sidecar tables for embeddings (separate rearchitecture stream)
- New feature work — this sprint is structural, not new-functionality

---

## Pickup mechanics for a future session

Any of these openings work:

> "Continue the post-election rearchitecture sprint at `docs/plans/2026-05-25-post-election-rearchitecture-sprint.md`. Read the status banner, then propose the next batch."

> "What's open in the post-election sprint? I want to ship 1-2 small things today."

> "Phase D Principle 1 — start the counter contract dataclass work. Reference the original audit at `~/.claude/plans/steady-crafting-island.md` REVISION 2 for the typed-dataclass design."

The session that picks this up should:
1. Read this doc's status banner first
2. Run `git log --oneline main --since='2026-05-25'` to see what's shipped since this doc was written; update the Done section accordingly before starting new work
3. Check `docs/AI-PARKING-LOT.md` for entries newer than D68 (those describe context this doc doesn't have)
4. Verify the cap-revisit-june-1 scheduled task ran (or is pending)
