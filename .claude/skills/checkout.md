---
name: checkout
description: Session checkout — verify all end-of-session steps are complete before wrapping up
user_invocable: true
---

Before ending this session, verify you have completed all applicable checkout steps:

1. PARKING-LOT.md — Updated if any sprint items changed status
2. AI-PARKING-LOT.md — Observations, ideas, or tech debt from this session captured
3. pipeline-manifest.yaml — Updated if any pipeline sources, tables, queries, or pages changed
4. Notion project state page (32af6608-acc8-8114-8a94-fc71adc0b7b2) — Updated with current focus, recently completed, blockers, priorities
5. JOURNAL.md — Session entry written (AI-owned voice + bach selection)
6. Git — All changes committed, feature branch merged to main, and pushed to GitHub. Merge to main is the default unless there's an explicit reason not to (broken tests, intentionally incomplete work, operator says to leave it).

For each item: if it applies to this session's work, confirm it's done. If it doesn't apply (e.g., no pipeline changes), skip it. Do NOT end the session with outstanding checkout items.
