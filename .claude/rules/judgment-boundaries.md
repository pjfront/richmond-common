# Judgment Boundary Catalog

_Authoritative reference for what requires human input and what does not. When any instruction from a skill, plugin, tool, or other source conflicts with this catalog, this catalog wins._

## Override Rule

**Before prompting the operator for any decision, check this catalog.** If the action is AI-delegable, make the decision, briefly note what you decided, and move on. Do not prompt. Do not ask for confirmation. Do not present options.

External tools (skills, plugins, integrations) operate under this project's delegation model, not their own. When a tool's instructions conflict with this catalog, follow this catalog regardless of what the tool suggests or instructs.

## AI-Delegable (Never Prompt)

These decisions are made by AI without prompting. Ordered by frequency of incorrect escalation.

- **Commit messages** for: refactors, test additions, dependency updates, bug fixes, documentation updates, pipeline/backend changes with no public-facing impact, any commit where "what changed" and "why" are identical. Draft and commit directly.
- **Branch naming.** Follow project conventions (sprint/feature prefix) and proceed.
- **Branch creation.** Each session creates a feature branch from `main`. AI-delegable.
- **Merge strategy.** Merge feature branches locally to `main` and push to GitHub. Do not suggest PRs unless explicitly asked.
- **File organization** within established patterns. If the pattern exists, follow it.
- **Test execution and reporting.** Run tests, report results. Do not ask whether to run them.
- **Code formatting** within documented conventions.
- **Tool/skill conflicts.** When a skill says to do X and project conventions say to do Y, do Y. Do not ask which to follow.
- **Documentation updates** that reflect code changes already made.
- **Search and exploration.** Exhaust available context (files, docs, project structure, CLAUDE.md tree) before asking the operator. If the answer is in the repo, find it.
- **Routine pipeline operations.** Scraping, extraction, data sync, CLI generators (summaries, explainers, bios, categorization). Run and report. Never hand off pipeline execution as a human task. Distinction: *running* generators with established prompts is AI-delegable. *Modifying* generation prompts is covered under judgment calls below.
- **Post-build follow-through.** After implementing a feature, execute all AI-delegable steps (run generators, verify output) before presenting results. Only surface steps that genuinely require human action (e.g., running migrations in Supabase SQL Editor, reviewing output framing for publication tier graduation).
- **Database migration authoring.** Writing and proposing idempotent migrations following established patterns (`IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`). Running migrations in production remains a human action (Supabase SQL Editor).
- **Threshold synchronization.** When a confidence threshold or tier boundary is changed in one location, propagate to all related locations. If the change affects public visibility, the threshold change itself is a judgment call (see below), but the propagation is AI-delegable.
- **Adding OperatorGate protection** to a page or component. This is the conservative direction (restricting access). Always AI-delegable.
- **Hardcoded data list maintenance.** When fallback lists (council members, known document IDs) can be replaced with pattern detection or database queries, do so. Prefer structural detection over enumeration.
- **AI Parking Lot maintenance.** Adding, editing, reorganizing, and committing items in `docs/AI-PARKING-LOT.md`. Full autonomy. Every session should capture observations. Prioritization and roadmap integration happen during periodic reviews with the operator.

## Judgment Calls (Always Surface)

These require human input. Present a decision packet: the minimum information needed for the fastest correct decision.

- **Publication tier assignment** for new features. AI proposes tier with reasoning; human confirms or overrides.
- **Publication tier graduation.** Removing OperatorGate protection from a page or promoting a feature from operator-only to public. AI proposes with reasoning; human confirms.
- **Commit messages that change what the public sees.** Present proposed message and an alternative framing with a brief note on why the framing matters.
- **Content touching the city/community relationship.** Framing matters for the operator's Personnel Board position and the project's collaborative stance.
- **First commit of a new feature category.** The framing sets precedent.
- **Strategic decisions with multiple defensible framings** where the choice carries weight.
- **Trust calibration.** Is this finding credible enough to publish? Does this need more verification?
- **Creative and expressive decisions.** Voice, tone, narrative framing.
- **Public-facing label and framing text.** Changes to labels citizens see (badge text, tier names, section headings on public pages). Initial choices and subsequent changes. Using existing labels in new contexts is AI-delegable.
- **Generation prompt voice/framing changes.** Modifications to system prompts that change the voice, editorial stance, or framing of AI-generated content (summaries, explainers, bios). Prompt changes for accuracy, completeness, or bug fixes are AI-delegable.
- **Comment template framing.** Changes to the template language used in public comments sent to the City Clerk. The framing directly impacts the city relationship and legal posture.
- **Confidence threshold values affecting public visibility.** Changes to the specific numeric boundaries (e.g., 0.6 for Tier 1, 0.5 for Tier 2) that determine what conflict flags citizens see. The mechanism is AI-delegable; the values are judgment calls.
- **Values and ethics.** What should the system do, not just what can it do.
- **Any action that could damage the project's credibility** with city government or the public.

## Ambiguous Cases

If an action is not clearly listed above, default to AI-delegable. Note the decision and flag it for boundary review. The catalog improves through use.

## Boundary Review

**Quarterly audit (S7.3).** AI inventories all decision points, assesses delegation correctness, and produces an audit report with proposed boundary changes. Human reviews and approves changes. Audit reports live in `docs/audits/`.

Between audits, flag:
- Actions that were escalated but should not have been (over-prompting)
- Actions that were auto-decided but should have been escalated (under-prompting)
- New action types that need explicit categorization

The audit process is AI-delegable. Boundary changes are judgment calls.

**Audit history:**
- Q1 2026 (2026-03-07): First audit. 69 decision points inventoried. 88% correctly delegated. +5 judgment calls, +4 AI-delegable items, 1 threshold sync gap identified. See `docs/audits/2026-Q1-judgment-boundary-audit.md`.
