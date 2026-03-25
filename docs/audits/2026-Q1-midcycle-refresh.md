# Judgment-Boundary Audit: Q1 2026 Mid-Cycle Refresh

**Date:** 2026-03-25
**Auditor:** Claude (AI-delegable per S7.3 spec)
**Baseline:** Q1 2026 audit (2026-03-07), 69 decision points, 88% correctly delegated
**Scope:** Focused refresh — 300+ commits since baseline (S9-S16, public/operator split, values restructure, advisory opinions)
**Type:** Addendum to Q1 audit, not a replacement

---

## Executive Summary

The judgment boundary catalog is in good shape. The Q1 audit's 5 recommendations were all incorporated into the catalog. The values restructure (justice/representation/stewardship) and advisory opinion mechanism (AO1-AO7) represent the most significant governance evolution since the audit.

| Area | Finding |
|---|---|
| Q1 pending items | JC-1 resolved, JC-2 open (confidence_tier_desync), JC-3 resolved |
| Decision queue | 4 pending (1 high, 3 medium) — 2 actionable, 2 informational |
| New decision categories | 2 identified (autonomy boundary changes, open-source governance) |
| Values integration | Judgment calls annotated with value alignment |
| Advisory opinions (AO1-AO7) | 6 validated, 1 new proposed (AO8) |

---

## 1. Q1 Audit Item Resolution

### JC-1: Publication tier for 3 ungated pages — RESOLVED

**Status:** Resolved (2026-03-07, same session as audit).

The public/operator split (completed ~March 22) restructured the entire publication surface:
- **Public:** Meetings, Council, About/Methodology only
- **Operator-gated:** Scanner results, data quality, coalitions, patterns, influence map, commissions, public records, search — 9 pages total behind OperatorGate

The 3 pages flagged (Data Quality, Coalitions, Patterns) are now **all behind OperatorGate**. This is more conservative than the audit's question suggested — the operator chose to restrict rather than confirm public status, consistent with the go-live strategy of starting narrow and graduating features.

**Resolution:** Operator confirmed all three as operator-only during public/operator split. Decision logged in DECISIONS.md (2026-03-07 entry). No further action.

### JC-2: Threshold synchronization — OPEN (now in decision queue)

**Status:** Open. Reappears as `confidence_tier_desync` (high severity) in the automated decision queue.

The Q1 audit identified a gap between scanner tier assignment (Tier 1 at ≥0.6) and frontend display (Tier 1 at ≥0.7). Since then, S9 (Scanner v3) shipped with a complete signal architecture overhaul:
- New thresholds: Strong ≥0.85, Moderate ≥0.70, Low ≥0.50
- Three-tier badge system (Strong/Moderate/Low) replaced the old Tier 1/2/3 system
- Scanner now produces `RawSignal` objects with composite confidence
- Frontend labels updated to "Strong Pattern" / "Moderate Pattern" / "Low-Confidence Pattern"

The `confidence_tier_desync` in the decision queue likely reflects residual data from pre-v3 scans where the old `publication_tier` column doesn't match the new confidence bands. This is a **data migration issue**, not a design issue — v3 resolved the design-level synchronization gap.

**Recommendation:** Run batch rescan to update all historical flags to v3 confidence model (AI-delegable — this is routine pipeline operations). Then verify the decision queue auto-resolves when the data quality check passes. The Q1 audit's Option D+C recommendation is effectively implemented: scanner and frontend now share a common tier model, and the three-tier badge system makes the design explicit.

**Decision packet for operator:** Confirm that running a batch rescan to clear legacy tier assignments is the right resolution. If confirmed, this becomes AI-delegable execution.

### JC-3: Comment template initial approval — RESOLVED

**Status:** Resolved (2026-03-07, same session as audit).

Per DECISIONS.md: "Comment template: Approved as-is. Submission remains gated behind dry_run=True. Will be re-reviewed before private beta opens."

**Resolution:** Template approved. Submission deferred. No further action until private beta.

---

## 2. Decision Queue Review (4 Pending)

### 2.1 confidence_tier_desync (HIGH) — Actionable

See JC-2 above. This is the continuation of the Q1 audit's highest-priority finding, now tracked automatically by the data quality system.

**Value at stake:** Stewardship — accurate representation of financial connections.
**Proposed resolution:** Batch rescan + verify auto-resolution. Judgment call: confirm approach.

### 2.2 duplicate_contributions (MEDIUM) — Actionable

Duplicate contribution records detected (same donor, amount, date, committee appearing 2+ times). This inflates financial connection signals in the scanner.

**Value at stake:** Justice — overstated financial connections could unfairly characterize an official's relationships.
**Assessment:** This is a data pipeline bug, not a judgment call. Deduplication logic in the contribution sync should be audited and fixed. The decision queue correctly flagged it, but resolution is AI-delegable (fix the dedup bug, verify, auto-resolve).

**Proposed resolution:** Investigate dedup logic in `data_sync.py` contribution loading. Fix, re-sync, verify decision auto-resolves.

### 2.3 & 2.4 Assessment finding: anomaly (MEDIUM × 2) — Informational

Two anomaly findings from the self-assessment system (March 23 and March 24). These are LLM-generated observations about pipeline journal entries — they flag statistical deviations or unexpected patterns.

**Assessment:** Self-assessment anomaly findings are informational by design. They surface observations that *might* need attention. Without specific detail in the decision queue about what the anomalies are, these should be reviewed by reading the self-assessment output, then either:
- Resolved as "acknowledged — no action needed" if the anomaly is expected (e.g., sprint velocity change)
- Escalated to a specific action item if the anomaly reveals a real issue

**Proposed resolution:** Review self-assessment output. Likely "acknowledged" — the heavy commit velocity of S14-S16 would naturally produce anomaly signals.

---

## 3. New Decision Categories (Since March 7)

### 3.1 Autonomy Boundary Promotion/Demotion

**What's new:** The advisory opinion mechanism (added in Entry 33) creates a formal path for boundary evolution: advisory opinions with >90% agreement over 20+ instances become candidates for AI-delegable promotion. But the catalog doesn't explicitly categorize the **decision to act on these promotions.**

**Current gap:** The Boundary Review section says "Boundary changes are judgment calls" (line 83), which is correct but vague. With the advisory opinion tracking now active, we need to be specific about what "boundary changes" means.

**Recommendation:** Add to Judgment Calls: "Promoting advisory opinions to AI-delegable or demoting AI-delegable items to judgment calls, based on quarterly audit evidence." The audit itself (gathering data, computing rates) remains AI-delegable. The decision to change the catalog is the judgment call.

**Value at stake:** Representation — the delegation model determines whose voice shapes which decisions.

### 3.2 Open-Source Governance Decisions

**What's new:** The project is going open-source (per memory: `project_open_source_strategy.md`). This introduces a new class of decisions: what to expose publicly in the repo, how to frame the project for external contributors, license choice, what documentation to include.

**Current gap:** The catalog covers publication tiers for *features* but not for *code and documentation*. Open-sourcing the repo is a one-time event, but the ongoing decisions about contributor guidelines, issue templates, and code comments that reference internal processes are new.

**Recommendation:** This is a judgment call by nature (first-commit-of-new-category for the open-source posture). Add a note under "First commit of a new feature category" that this extends to open-source governance decisions. The specific items (CONTRIBUTING.md framing, license choice, what to redact from commit history) are judgment calls. Once the framework is established, applying it to new files is AI-delegable.

**Value at stake:** Stewardship — open-source governance shapes whether the project can sustain community contributions.

### 3.3 Topic Label Content Curation (Considered, NOT added)

S16 introduced AI-extracted topic labels (1-2 word subjects per agenda item). These are generated by LLM extraction prompts. Under the existing catalog, **running** the generator is AI-delegable and **modifying the prompt voice** is a judgment call. Topic label curation fits cleanly into the existing framework — no new category needed.

---

## 4. Values Integration

The Q1 audit predated the values restructure (justice/representation/stewardship replaced the previous unnamed value set). Each judgment call should reference which value is at stake, helping the operator prioritize when multiple judgment calls queue up.

### Judgment Calls with Value Alignment

| Judgment Call | Primary Value | Secondary | Reasoning |
|---|---|---|---|
| Publication tier assignment | **Stewardship** | Justice | Responsible use of public attention; avoid unfair exposure of individuals |
| Publication tier graduation | **Representation** | Stewardship | Citizens' right to see data vs. risk of premature publication |
| Commit messages (public-facing) | **Stewardship** | — | Framing shapes public trust in the institution |
| City/community relationship | **Representation** | Stewardship | Collaborative governance serves the community's voice |
| First commit of new feature | **Stewardship** | — | Precedent-setting requires care |
| Strategic multi-framing decisions | All three | — | By definition, these involve value tensions |
| Trust calibration | **Justice** | Stewardship | Premature publication can harm individuals; withholding can harm accountability |
| Creative/expressive decisions | **Representation** | — | Voice and tone shape whose perspective is centered |
| Public-facing labels | **Representation** | Justice | Labels frame how citizens understand governance actions |
| Prompt voice/framing | **Representation** | — | AI voice shapes the narrative |
| Comment template framing | **Representation** | Stewardship | City communications represent the project to government |
| Confidence thresholds | **Justice** | Stewardship | Thresholds determine who gets flagged and at what certainty |
| Values and ethics | All three | — | Core value decisions |
| Credibility-risking actions | **Stewardship** | — | Existential risk to the project |

**Key pattern:** Justice dominates threshold/flag decisions (who gets flagged). Representation dominates voice/framing decisions (how things are said). Stewardship dominates institutional decisions (publication, credibility, city relationship). When all three are in play, it's a sign the decision is genuinely hard and deserves extra attention.

---

## 5. Advisory Opinion Validation (AO1-AO7)

### Validated — Keep as-is

| AO | Area | Status | Notes |
|---|---|---|---|
| AO1 | Publication tier proposals | **Active, validated** | Exercised during public/operator split. Working well — AI proposes tier, operator confirms. |
| AO2 | Source tier assignment | **Active, validated** | Exercised for Socrata, court records. Clean analogical reasoning pattern. |
| AO3 | Framing sensitivity detection | **Active, validated** | Exercised during pre-public audit (commit a652501). Caught "transparency report" language needing neutralization. |
| AO4 | Confidence threshold recommendations | **Active, validated** | Exercised during S9 v3 (0.85/0.70/0.50 thresholds). Statistical evidence + value reasoning worked. |
| AO5 | Feature prioritization reasoning | **Active, validated** | Exercised in S14-S16 sequencing. DECISIONS.md restructuring advisory opinion (this session) is an AO5 instance. |
| AO6 | Scanner signal credibility | **Active, validated** | Exercised during signal significance architecture (S9). Levine Act research informed credibility tiers. |
| AO7 | Push vs. collaborate | **Active, not yet exercised in anger** | No instance where the AI needed to argue for publication over operator's instinct to withhold. Retain — this is a safety valve. |

### Proposed Addition: AO8

**AO8: Open-source readiness assessment.** As the project moves toward open-source, the AI should proactively flag:
- Code comments or commit messages that reference internal processes inappropriately
- Documentation that assumes operator context a contributor wouldn't have
- Architecture decisions that would be confusing to external contributors without context

**Value:** Stewardship — sustainable open-source governance.
**Risk if wrong:** Over-flagging slows development; under-flagging exposes internal assumptions publicly.
**Trigger:** Add when open-source preparation begins in earnest (S18 or post-launch).

### Agreement Rate Tracking

No formal tracking infrastructure exists yet. Advisory opinions have been issued informally throughout S9-S16 sessions. The quarterly audit (Q2 2026) should establish a structured tracking mechanism — even a simple tally in the audit report would suffice.

**Recommendation:** The Q2 audit should include a section: "Advisory opinions issued this quarter" with accept/override/modify counts per AO area.

---

## 6. Catalog Update Recommendations

### Add to Judgment Calls

1. **Boundary promotion/demotion decisions.** Changing the catalog itself — promoting advisory opinions to AI-delegable or adding new judgment calls — based on quarterly audit evidence. The audit process (gathering evidence, computing agreement rates) is AI-delegable. The decision to change the delegation model is a judgment call. **Value: Representation.**

### Add to AI-Delegable

1. **Decision queue triage for data quality items.** When a data quality check produces a decision queue entry that traces to a clear pipeline bug (not a threshold or framing question), fixing the bug is AI-delegable. The decision queue correctly surfaces the issue; resolution doesn't require human judgment when the fix is mechanical.

### Clarify Existing Items

1. Under "First commit of a new feature category," note that this extends to **open-source governance** decisions (CONTRIBUTING.md framing, license choice, issue template language, what to include/exclude from public repo).

2. Under Boundary Review, strengthen the audit history format to include advisory opinion tracking.

---

## 7. Pending Operator Decisions

### PD-1: Confirm batch rescan for confidence_tier_desync (HIGH)

**Decision:** Approve running a batch rescan of all historical meetings to update legacy `publication_tier` values to the v3 confidence model?

**Context:** S9 shipped a new signal architecture with different tier boundaries. Legacy data from pre-v3 scans has mismatched tiers. The data quality system correctly flags this as `confidence_tier_desync`.

**Options:**
- **A (recommended): Batch rescan + auto-resolve.** ~784 meetings, AI-delegable execution. Clears the desync and the decision queue item. Cost: ~$50-70 in API calls.
- **B: Manual spot-check first.** Review a sample of legacy flags before rescanning all. Adds a session but validates v3 output quality.
- **C: Defer until post-launch.** Accept the desync for now. Scanner results are operator-only, so citizens don't see the inconsistency.

**Value at stake:** Stewardship (data accuracy). Justice (accurate flag representation).

### PD-2: Acknowledge duplicate_contributions (MEDIUM)

**Decision:** Confirm that fixing the contribution dedup bug is AI-delegable?

**Context:** Duplicate contributions inflate financial connection signals. This is a pipeline bug, not a framing question.

**Recommendation:** Approve as AI-delegable. Fix will be investigated and applied in a future session.

### PD-3: Acknowledge self-assessment anomalies (MEDIUM × 2)

**Decision:** Acknowledge the two anomaly findings as expected sprint-velocity artifacts?

**Context:** S14-S16 shipped ~300 commits in 18 days. The self-assessment system flagged this as anomalous, which is correct — it IS anomalous relative to the pre-S9 baseline. But it's expected anomalous, not concerning anomalous.

**Recommendation:** Resolve both as "acknowledged — sprint velocity expected during go-live push."

---

## Appendix: Sprint Activity Since Baseline

| Sprint | Theme | Key Governance Impact |
|---|---|---|
| S9 | Scanner v3 Signal Architecture | New confidence model, three-tier badges, batch rescan |
| S10 | Citizen Discovery | Search infrastructure (no new governance decisions) |
| S11 | Information Design | Nav restructure, CivicTerm/SourceBadge components |
| S12 | Citizen Experience v2 | R1 regeneration (11,687 items), prompt voice (AO exercised) |
| S13 | Influence Transparency | Form 803, lobbyist regs, astroturf detectors |
| S14 | Discovery & Depth | Meetings redesign, influence map, narrative profiles |
| S15 | Pipeline Autonomy | 4-tier scheduling, health dashboard |
| S16 | Content That Clicks | Topic labels, plain English expansion |
| — | Public/Operator Split | 9 pages gated, public nav narrowed to 3 sections |
| — | Values Restructure | Justice/representation/stewardship framework adopted |

**Commits:** ~300 since 2026-03-07
**New decision points estimated:** ~15-20 (mostly AI-delegable, following established patterns)
**Boundary violations observed:** 0 clear under-prompts, 0 clear over-prompts

---

_Next full audit: Q2 2026 (target: June 2026). Should include formal advisory opinion agreement tracking._
