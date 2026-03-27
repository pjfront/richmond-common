# Layer 2: Richmond Commons Team Operations

_How we work on Richmond Commons. Process, documentation, conventions, quality enforcement. This is Richmond Commons' operational layer._

_Inherits from: Layer 1 Philosophy (`~/.claude/CLAUDE.md`)_

---

## How the Team Works with AI

Anyone working with AI tools operates in some combination of these roles:

- **Spec author** -- Defines the what and why; AI writes the how
- **Architecture enforcer** -- Catches when implementation drifts from conventions
- **Domain expert** -- Makes judgment calls that require context AI doesn't have
- **Quality reviewer** -- Verifies outputs against specs and real-world ground truth
- **Trust calibrator** -- Decides what's credible enough to ship, publish, or act on

"Build X" means write a spec, then have AI implement it. Human time is best spent on decisions, verification, and domain knowledge.

These roles scale: on solo projects one person wears all hats. On a team, authority boundaries and approval workflows become more important, not less.

---

## Process

### Think Before You Task

Write specs and vision first, then create execution artifacts. Never dump strategic content into task trackers. The sequence:

1. Write the spec / vision / analysis to the appropriate document
2. Create execution items that reference the spec
3. Execution items contain: what to do, acceptance criteria, dependencies, and a pointer to the spec

**In specs:** Problem statements, feature designs, architectural decisions, tradeoff analysis, stakeholder context, decision rationale.

**In tasks:** Scoped work items, acceptance criteria, dependencies, status. Keep descriptions short. Link to the spec for "why."

### Tool Separation

Spec and vision live in one system (e.g., docs/specs/ in the repo). Execution tracking lives in another (e.g., GitHub Issues). Don't dump strategic content into task trackers. Don't put execution minutiae in vision docs.

### Decision-Making Framework

For every non-trivial feature decision, present:

1. **Build investment** per option (in session time, not engineering hours)
2. **Run cost** (often trivially small)
3. **Value / relevance** to the prioritization paths
4. **Upgrade cost** from each option to the next
5. **Cost delta** at each level

The real currency is human attention and decision quality. The key question: "How much does it cost to upgrade later if we start smaller?" Often the answer is "near zero, because options are additive."

### Batch Review Before Batch Execute

When making multiple changes (moves, renames, deployments, data updates): show the full list for review before executing any of them. One approval for the batch, not one per item. Never execute without the approval.

---

## Publication Tier Rubric

Every feature requires an explicit publication tier during scoping. This is a judgment call (the human decides), but AI proposes the tier with reasoning. The human confirms or overrides.

### The Tiers

| Tier | Who sees it | When to use |
|---|---|---|
| **Public** | All visitors | Data is validated, framing is reviewed, no reputation risk |
| **Operator-only** | Operator | Unvalidated data, operational tooling, or framing not yet reviewed |
| **Graduated** | Starts operator-only, promoted after review | Most new features. Default unless there's a clear reason otherwise |

### Default: Graduated

**Graduated** is the default for any new feature. To assign a different tier, one of these must be true:

**Public from launch** requires ALL of:
- Data source is Tier 1 or Tier 2 (official records, independent journalism)
- Data has been validated against ground truth (spot-checked, not just "it parsed")
- Content is factual presentation only (no inference, no analysis, no framing)
- No risk of inaccuracy damaging the project's credibility or city relationship
- Feature type has a precedent that's already public (e.g., adding a column to an existing public table)

**Permanent operator-only** when ANY of:
- It's operational tooling (staleness alerts, data quality dashboards, pipeline monitoring)
- It exposes raw/internal data not meant for public consumption
- It's a decision-support tool for the operator, not a citizen-facing feature

### In Practice

Every feature spec includes a line like:

```
Publication tier: Graduated (new data source, unvalidated)
```

AI proposes the tier with a parenthetical reason. Human confirms or overrides. If AI can't confidently assign a tier, it flags it as needing a judgment call.

### Edge Cases

| Scenario | Proposed default | Why it may need a judgment call |
|---|---|---|
| New page showing only Tier 1 data | Graduated | Even official data can be wrong if our parsing is wrong |
| New column on existing public table | Public | Incremental extension of validated pattern |
| AI-generated content (bios, summaries) | Graduated | AI output needs human review before public exposure |
| Conflict/financial analysis | Graduated or permanent operator-only | Reputation risk, framing matters |
| Bug fix to existing public feature | Public (no tier change) | Already validated |

---

## Architecture Standards

### Decide Once, Enforce Always

Non-negotiable conventions go in the CLAUDE.md. These are constraints, not suggestions. Once decided, they become automated enforcement (linters, pre-commit hooks, schema constraints), not human vigilance.

### Naming Is Architecture

Names encode meaning. Prefixes indicate ownership, origin, and editability. Suffixes indicate type or role. Naming conventions are documented, not discovered.

### Know Your Authority Boundaries

Map what you can and can't touch. Document explicitly:

- Which systems are read-only references
- Which code is package-generated and must not be edited
- Which changes require approval workflows or sign-off from specific people
- Who owns which systems or areas
- What deployment or change management process applies

### Search Before You Create

Always search for existing artifacts with similar names before creating new ones. Duplicates are worse than gaps. Surface potential duplicates and ask before proceeding.

### Minimum Blast Radius

Target exactly what changed, nothing more. Surgical deployments. Specific file paths, not broad categories. This applies to deployments, database migrations, config changes, and content reorganization.

### Respect the Existing Landscape

Mature systems have gravity. Understand the ecosystem (packages, integrations, conventions, tech debt, dependencies) before changing anything. Document the gap between intent and reality.

---

## Quality and Enforcement

### Quality Gates Are Automated

If it matters, enforce it in tooling: pre-commit hooks, linters, formatters, test suites. Aspirational quality standards that depend on human discipline will fail. Automate the AI-delegable parts; reserve human review for judgment calls.

### Data Sensitivity

Never include identifying information (names, emails, account details) in AI outputs unless explicitly required.

### Conservative With Destructive Actions

Never delete, archive, or permanently modify without explicit confirmation. "Flag and ask" is always safer than "fix and hope."

---

## Documentation

### Decisions Log

Every non-trivial decision gets logged with date and rationale. The future team needs to know WHY, not just WHAT. The log lives with the project, not in a chat transcript.

### Documentation Lives With the Project

- Decisions log with date and rationale
- Feature specifications for implementation
- Parking lot / future ideas with strategic context
- Prompts and config in dedicated files, not inline in code

### Document Direction, Not Just Current State

Note transitions in progress ("transitioning from X to Y"), planned deprecations, and intended future patterns. New team members should understand the trajectory, not just the snapshot.

### AI Should Auto-Document

Documentation of decisions and deferred work should be part of the implementation step, not a human-prompted afterthought. Every change that introduces a new convention, data structure, or deferred TODO includes a decisions log entry.

---

## Communication Standards

- Concise and direct. No corporate jargon.
- One question at a time. Don't overload decision points.
- When presenting a batch of changes, show them as a table or list for review before executing.
- After completing a task, summarize what changed (with links where applicable).
- Engage with ideas before executing. Push back, identify tradeoffs, surface what's missing.

---

## Workspace Hygiene

### Separation of Concerns

Personal projects stay in personal tools. Work projects stay in work tools. Each project defines its tool boundaries explicitly.

### Commit Discipline

Imperative mood. Reference the current phase or project area. Specific about what changed and why. Feature branches and PRs for all non-trivial work.

**Commit message authority:**

AI drafts all commit messages. Most are AI-delegable and committed directly. Some are judgment calls requiring human review before committing:

- **AI-delegable:** Internal refactors, test additions, dependency updates, bug fixes to existing features, documentation updates, pipeline/backend changes with no public-facing impact, any commit where "what changed" and "why" are identical.
- **Judgment call (flag for review):** Commits that change what the public sees, commits touching the project's relationship with the city or community, commits that external contributors or a changelog audience would read, commits with multiple defensible framings where the choice carries strategic weight, first commit of a new feature.

When flagging, present the proposed message and an alternative framing with a brief note on why it matters.

### Environment Safety

- Secrets in `.env` only; example files get placeholder values
- No `sudo` package installs
- Don't commit auth directories, caches, or generated artifacts

---

## Per-Project CLAUDE.md Template

Every project's CLAUDE.md should include at minimum:

| Section | What it covers |
|---|---|
| **Project Overview** | What this is, who it's for, current phase, key constraints, ownership |
| **Team and Ownership** | Who owns which areas, approval workflows, cross-functional dependencies |
| **Tech Stack** | Languages, frameworks, hosting, key architectural patterns |
| **Code Conventions** | Formatting, naming, testing patterns, language-specific rules |
| **Domain Context** | Knowledge AI needs for this domain: stakeholders, data sources, business rules |
| **Current State** | What's built now. Not aspirational. What's real. |
| **Priority and Roadmap** | Current phase priorities, parking lot reference, what's next |
| **What NOT To Do** | Anti-patterns, forbidden actions, read-only boundaries, required approvals |
| **Environment and Workflow** | How to run, test, deploy. Tool-specific notes. Target orgs/instances. |
