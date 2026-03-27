# Roadmap & Sprint Organization System — Portable Guide

_Exported from Richmond Commons. This document describes the complete roadmap/parking-lot/sprint system so it can be replicated in another project._

---

## Overview

The system uses **three files** with distinct ownership and purpose:

| File | Owner | Purpose |
|------|-------|---------|
| `docs/PARKING-LOT.md` | Human-managed | Sprint execution tracking — the authoritative roadmap |
| `docs/AI-PARKING-LOT.md` | AI-managed | Ideas, research, tech debt, predictions captured during sessions |
| `CLAUDE.md` | Shared | "What's Built" summary table kept in sync with sprint completions |

The parking lot is **not a task tracker** — it's a dependency-ordered execution plan with rich context. Each sprint entry captures *why* something is sequenced where it is, not just what needs doing.

---

## PARKING-LOT.md Structure

### Header Block

```markdown
# Parking Lot — Execution Sprints & Backlog

> **Restructured [date]** from [old structure] to dependency-ordered execution sprints.
>
> **Scoring:** Paths **A** = [Path 1], **B** = [Path 2], **C** = [Path 3].
> Three paths = highest priority. Zero = scope creep.
>
> **Publication tiers:** Public (users see it), Internal (team validates first),
> Graduated (starts internal, promoted after review).
>
> **Execution rhythm:** Each sprint produces both [backend capability] AND
> a visible [frontend/user-facing] feature.
```

**Key elements:**
- **Path scoring** — Every item is tagged with which strategic paths it serves. Three paths = highest priority. Zero paths = scope creep. This is the prioritization filter.
- **Publication tiers** — Every feature gets an explicit visibility assignment during scoping.
- **Execution rhythm** — The rule that prevents pure backend work from piling up without user-visible output.

### Sprint Block

Each sprint follows this template:

```markdown
## Sprint N — [Theme Name]

*[One-line vision statement.]*

**Why here:** [2-3 sentences explaining sequencing rationale — what this
sprint depends on and what depends on it.]

### [Status emoji] S[N].[M] Feature Name [was Old-ID]
- **Paths:** A, B, C
- **Description:** [What it is and why it matters]
- **Status:** [Current state with specific details — commit hashes, metrics, dates]
- **Depends on:** [Explicit prerequisite items]
- **Publication:** [Tier assignment with parenthetical reasoning]
```

### Status Conventions

| Prefix | Meaning |
|--------|---------|
| `✅` | Complete |
| `~~S12.5~~` | Dropped (with strikethrough + reason) |
| `⏸️` | Paused/blocked (with blocker noted) |
| _(no prefix)_ | Planned/in progress |

### What Makes Each Entry Rich

A good parking lot entry includes:

1. **Path tags** — Which strategic paths it serves
2. **"Why here" rationale** — Why this sprint is sequenced at this position
3. **Dependency chains** — Explicit `Depends on:` references to other items
4. **Status with evidence** — Not just "done" but *what was done*: metrics, commit hashes, test counts, key findings
5. **Publication tier** — Who sees this and why
6. **Dropped/deferred items** — Preserved with strikethrough and a reason. Never silently deleted.
7. **Key findings** — Discoveries made during implementation that change the plan
8. **Human action callouts** — Steps that can't be automated, with exact commands/URLs

### Sprint Sequencing Logic

Sprints are ordered by **dependency**, not priority. The parking lot header should explain the sequencing philosophy. Example progression:

```
S1: Foundation (data + infrastructure)
S2: Core intelligence (requires S1 data)
S3: User comprehension (requires S2 intelligence)
S4: Data quality (protects S1-S3 output)
S5: Deeper intelligence (requires S4 clean data)
S6: Cross-referencing (requires S2 + S5)
S7: Operator tools (more valuable after S1-S6 exist)
S8: More data sources (before UI redesign so design covers all types)
S9: Fix core engine (before exposing more data publicly)
...
```

### Backlog Section

After the numbered sprints, a `## Backlog` section holds items not yet sequenced:

```markdown
## Backlog

### B.1 Feature Name
- **Paths:** A, C
- **Description:** ...
- **Blocked by:** [what needs to happen first]
- **Priority estimate:** [Low/Medium/High]
```

Backlog items get promoted to sprints when their dependencies are met and they rank high on the path filter.

---

## AI-PARKING-LOT.md Structure

This is the AI's autonomous scratchpad. Every session adds observations. Items stay until promoted to the sprint backlog or explicitly discarded.

```markdown
# AI Parking Lot

_Ideas, research topics, and improvement suggestions captured by the AI
during implementation sessions. AI has full autonomy over this file.
Periodically reviewed and prioritized with the operator for roadmap integration._

_Convention: Every session adds observations here. Items stay until promoted
to the sprint backlog or explicitly discarded during a review._

---

## Research Topics

### R1. [Topic Name] [➜ Promoted to SX.Y / ✅ Done in SX.Y]
**Origin:** [Sprint/session] ([date]) | **Promoted:** [date] to [sprint item]
[Description of research question]
**Recommended approach:** [if known]
**Alternative approaches:** [list]

## Improvement Suggestions

### I1. [Improvement Name] [➜ Promoted / ✅ Done]
**Origin:** [Sprint/session] ([date]) | **Priority estimate:** [Low/Med/High]
[Description]

## Technical Debt / Cleanup

### D1. [Debt Item Name] [➜ Promoted / ✅ Fixed]
**Origin:** [context] ([date]) | **Priority estimate:** [priority]
[Description + root cause + proposed fix]

## Predictions / Validation Checkpoints

### V1. [Prediction Name]
**Origin:** [context] ([date]) | **Validate at:** [milestone]
[Expected outcome + key metrics to check]
```

**Key conventions:**
- **Numbering by category** — R#, I#, D#, V# (Research, Improvement, Debt, Validation)
- **Origin tracking** — Every item records where it came from and when
- **Lifecycle markers** — `➜ Promoted to SX.Y` or `✅ Done in SX.Y` or `➜ RESOLVED`
- **Items are never deleted** — They're marked as promoted, done, or resolved. History preserved.
- **AI has full autonomy** — No approval needed to add, edit, or reorganize this file
- **Periodic review** — Operator and AI review together to promote items to the sprint backlog

---

## CLAUDE.md "What's Built" Sync

The project's CLAUDE.md has a table that mirrors sprint status:

```markdown
## What's Built

| Sprint | Theme | Key Items |
|--------|-------|-----------|
| **S1** | Foundation | ✅ Feature gating, table sorting, data expansion |
| **S2** | Intelligence | ✅ Vote categorization, AI bios |
| **S3** | Clarity | ✅ Plain language summaries |
| **S4** | Data Quality | ✅ Duplicate detection, freshness monitoring |
| **S5** | [Current] | Form 700 ingestion (in progress) |
```

---

## Enforcement Rules

These rules make the system work. Without them, the parking lot goes stale.

### 1. Progress Tracking Sync (Mandatory)

> **Every commit that completes or substantially advances a PARKING-LOT.md item
> must update the parking lot in the same commit.** Mark items ✅, add status lines,
> update descriptions.

Same applies to the CLAUDE.md "What's Built" section when sprint status changes.

### 2. AI Parking Lot Capture (Every Session)

> **Every session:** Note ideas, research topics, improvement suggestions,
> and technical debt observations in `AI-PARKING-LOT.md`. Commit with regular work.

### 3. Dropped Items Are Preserved

Never silently remove an item. Use strikethrough + reason:

```markdown
### ~~S12.5 Meeting Summaries~~ — DROPPED
- **Status:** Dropped (2026-03-19). S14 A3 is a better replacement.
```

### 4. Sprint Overlap Resolution

When sprints overlap (a later sprint absorbs an earlier one's work), document it explicitly:

```markdown
**S13 overlap (resolved 2026-03-21):** S13.6 absorbed into S14.
S13 is now a pure pipeline sprint.
```

### 5. Path Scoring as Kill Switch

> **Path A** + **Path B** + **Path C** = highest priority.
> Zero paths = scope creep. Kill scope creep.

Every proposed feature gets scored against the paths. If it serves zero paths, it doesn't go in the parking lot.

---

## How to Bootstrap This for a New Project

### Step 1: Define Your Paths (3 max)

Paths are your strategic directions. Examples:
- **SaaS:** A = User value, B = Revenue, C = Platform
- **Open source:** A = Contributor experience, B = Adoption, C = Ecosystem
- **Internal tool:** A = User productivity, B = Maintenance cost, C = Integration

### Step 2: Define Publication Tiers

Who sees each feature and when:
- **Public** — End users see it
- **Internal/Beta** — Team validates first
- **Graduated** — Starts internal, promoted after review (default for new features)

### Step 3: Create PARKING-LOT.md

Start with:
1. Header block (paths, tiers, execution rhythm)
2. Sprint 1 with 3-5 items
3. A backlog section with everything else

### Step 4: Create AI-PARKING-LOT.md

Empty template with the four sections (Research, Improvements, Debt, Validation).

### Step 5: Add Sync Rules to CLAUDE.md

Add the enforcement rules to your project's CLAUDE.md or equivalent:
- Parking lot sync on every completing commit
- AI parking lot capture every session
- Dropped items preserved with rationale

### Step 6: Add "What's Built" Table to CLAUDE.md

A sprint-level summary that stays current as the canonical "where are we" reference.

---

## What Makes This System Work

1. **Dependency ordering, not priority ordering.** Sprints are sequenced by what they unlock, not by what seems most important in isolation.

2. **Rich status, not checkboxes.** Each item captures what happened, what was learned, and what changed — not just "done/not done."

3. **Two parking lots.** The human-managed one tracks execution. The AI-managed one captures everything the AI notices during work. Periodic reviews promote AI observations to the execution roadmap.

4. **Preservation over deletion.** Dropped items, resolved debt, completed research — all stay visible with lifecycle markers. The parking lot is a historical record of the project's evolution.

5. **Path scoring as discipline.** Every feature must justify its existence against strategic paths. This prevents scope creep naturally.

6. **Same-commit sync.** The parking lot is updated in the same commit as the work it tracks. This prevents staleness from accumulating.
