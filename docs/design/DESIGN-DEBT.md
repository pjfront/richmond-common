# Design Debt Tracker

_Track violations of `DESIGN-RULES-FINAL.md` discovered during development, testing, or review. Each entry references a specific rule, describes the violation, and defines when it should be resolved._

---

## How to Use This Document

1. When you notice a design rule violation during development or review, add an entry with the next sequential ID.
2. Assign severity: **P0** blocks a core user task, **P1** degrades the experience for a significant user group, **P2** is cosmetic or affects edge cases only.
3. Set a **payback trigger** — the condition under which this debt must be repaid. Avoid "someday" triggers; tie payback to specific events (component modification, pre-launch audit, sprint milestone).
4. When resolved, update the status and add the resolved date. Do not delete entries — the history is useful for pattern detection.

---

## Debt Register

| ID | Rule Violated | Component / Page | Severity | Description | Payback Trigger | Status | Resolved Date |
|----|---------------|------------------|----------|-------------|-----------------|--------|---------------|
| DD-001 | C2, A6 | Campaign finance bar chart | P1 | Chart lacks "View as table" toggle. Screen reader users cannot access the underlying data. Color-only category encoding (no patterns). | Before public launch. Non-negotiable — blocks accessibility audit pass. | Open | — |
| DD-002 | U3 | Council member profile card | P1 | Card displays 7 data points (name, district, photo, party, votes, donations, attendance, conflicts flagged) without progressive disclosure. Should show exactly 3 KPIs with visual hierarchy per U3; remaining data points belong on the Layer 2 detail page. | Next time the council member card component is modified. | Open | — |
| DD-003 | U1, C6 | Meeting summary cards | P0 | Source attribution badge missing on 12 meeting summary cards generated during initial data import. Cards display AI-generated summaries without source link, timestamp, or tier badge. Violates U1 (non-nullable provenance) and C6 (badge on every card). These cards should be operator-only until attributed per U1. | Immediate — P0 because data without provenance must not be public-tier. Demote to operator-only or add attribution before next deployment. | Open | — |

---

## Severity Definitions

| Level | Definition | Response Time |
|-------|-----------|---------------|
| **P0** | Blocks a core user task or violates trust infrastructure (U1, U8, U12, U14). Data without provenance visible to public. Accessibility failure that prevents task completion. | Fix before next deployment. |
| **P1** | Degrades experience for a significant user group. Accessibility gap that doesn't fully block use but reduces usability. Missing benchmarks on public metrics. Missing responsive behavior on primary pages. | Fix within current sprint or before public launch, whichever comes first. |
| **P2** | Cosmetic inconsistency, minor spacing deviation, tooltip missing from a low-traffic term. Does not affect task completion or trust. | Fix next time the component is touched. |

---

## Pattern Detection

_Review this section monthly. If 3+ entries share the same violated rule, that rule needs better enforcement — either through a component abstraction, a linter rule, or a Claude Code instruction update._

| Rule | Open Violations | Pattern Notes |
|------|----------------|---------------|
| — | — | _No patterns detected yet._ |
