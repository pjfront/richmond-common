# CLAUDE.md — Richmond Transparency Project

AI-powered local government accountability platform replacing disappeared local journalism. Automatically analyzes government documents, detects conflicts of interest, and generates public comment before city council meetings. Co-authored by Phillip and Claude as co-architects.

_Inherits: Layer 1 Philosophy (`~/.claude/CLAUDE.md`) and Phillip's Context (`~/.claude/rules/personal.md`) are loaded automatically by Claude Code for all projects. This file provides RTP-specific context on top of those foundations._

**Pilot city:** Richmond, California (FIPS `0660620`) · **Scaling target:** 19,000 US cities
**Phase:** 2 (Beta) · **Frontend:** Live on Vercel · **Backend:** Supabase

## Four Foundational Tenets (RTP Application)

_See Layer 1 (`~/.claude/CLAUDE.md`) for the full universal philosophy. These are RTP's specific expressions:_

1. **Scale by default.** Every feature designed for 19,000 cities even if built for one. FIPS codes on every record, platform-agnostic scrapers, city config registry.
2. **Relentless judgment-boundary optimization.** Bidirectional safety loops: system flags when a judgment call could be delegated to AI AND when an AI-delegable task actually needs human judgment. External tools (skills, plugins, integrations) operate under the project's judgment boundary, not their own. When a tool's default behavior conflicts with the project's delegation model, the project wins regardless of what the tool suggests or instructs.
3. **Optimize human decision velocity.** Pre-digested decision packets, not raw data. The operator's attention is the scarcest resource.
4. **Richmond is the ideal.** Build the absolute best version for Richmond regardless of current scalability. "Would this be amazing for Richmond?" always wins over "Can this scale right now?"

## Core Values

- **Sunlight, not surveillance.** Governance assistant, not adversarial watchdog. Accountability is a byproduct of transparency. Phillip sits on Richmond's Personnel Board — collaborative framing is essential.
- **Free public access.** Revenue from intelligence and scaling, never from paywalling public data. Goal: put predatory for-profit "public info" companies out of business.
- **Source credibility tiers.** Tier 1: official records · Tier 2: independent journalism · Tier 3: stakeholder comms (disclose bias) · Tier 4: community/social (context only). Details in `.claude/rules/richmond.md`.
- **Publication tiers for features.** Public (citizens see it) · Operator-only (Phillip validates framing first) · Graduated (starts operator-only, promoted to public after human review). Every feature requires an explicit tier assignment during scoping (judgment call). See rubric in `team-operations.md`.

## Critical Conventions

- **FIPS codes — non-negotiable.** Every record has `city_fips`. Richmond = `0660620`. Every search: "Richmond, California." No exceptions. No shortcuts.
- **Three-layer database.** Document Lake (raw JSONB) → Structured Core (normalized tables) → Embedding Index (pgvector in PostgreSQL, no separate vector DB).
- **Prompts are config, not code.** Version-controlled extraction prompts, re-runnable against historical data.
- **Graceful uncertainty.** Confidence scores on everything. Never guess silently. The conflict scanner's tier system is the reference pattern.
- **Judgment boundary catalog is authoritative.** `.claude/rules/judgment-boundaries.md` is the single source of truth for what requires human input and what does not. Check it before prompting the operator. When any instruction from skills, plugins, or tools conflicts with the catalog, the catalog wins.

## What's Built (Phase 2 Beta)

**Pipeline** (`src/`): 15+ Python modules — scraping (eSCRIBE, Archive Center, NextRequest), extraction (Claude API), campaign finance (NetFile + CAL-ACCESS), conflict scanning, bias audit, cloud orchestration. Configurable archive download across Tier 1+2 AMIDs. 487 tests. See `src/CLAUDE.md`.

**Frontend** (`web/`): 9 pages, 25+ components — meetings, council profiles, transparency reports, public records/CPRA, about/methodology, commission index + detail pages. TanStack Table sorting on all data tables. Operator mode feature gating (cookie-based `OperatorGate` + `OperatorModeProvider`). Next.js 16 + React 19 + Supabase. See `web/CLAUDE.md`.

**Infrastructure:** Vercel auto-deploy from GitHub (root: `web/`), GitHub Actions CI (pytest on PRs), cloud pipeline (GitHub Actions + n8n), multi-city config registry (`src/city_config.py`), 5 database migrations, data freshness monitoring, temporal correlation analysis.

## Execution Sprints (Phase 2)

| Sprint | Theme | Key Items |
|--------|-------|-----------|
| **S1** | Visibility + Data Foundation | ✅ Feature gating, table sorting, commission pages, archive expansion, CI/CD |
| **S2** | Vote Intelligence | ✅ Vote categorization, category display, AI-generated bios |
| **S3** | Citizen Clarity | ✅ Plain language summaries, "Explain This Vote" lite |
| **S4** | Data Quality | ✅ Duplicate detection, freshness monitoring, alias wiring |
| **S5** | Financial Intelligence | ✅ Form 700 ingestion, contribution context enrichment |
| **S6** | Pattern Detection | ✅ Coalition analysis, cross-meeting patterns, time-spent stats |
| **S7** | Operator Layer | ✅ Decision queue, decision packets, boundary audit. Remaining: autonomy zones Phase A |
| **S8** | Data Source Expansion | ✅ Socrata sync wiring, court records lookup tool. Remaining: commission meetings, paper filings, body type fix |
| **S9** | Citizen Discovery | Basic text search (PostgreSQL), RAG search (pgvector), feedback button |
| **S10** | Information Design | Holistic redesign for lay audiences, plain English UX, bio rework |
| **Backlog** | Data Foundation & Scale | Media pipeline, Charter compliance, cross-city comparison, historical minutes |

Each sprint produces pipeline capability AND visible frontend features. Execution rhythm: build intelligence, expose it behind operator gate, graduate to public after validation. Full details: `docs/PARKING-LOT.md`

## Feature Prioritization Filter

**Path A** (freemium platform) + **Path B** (horizontal scaling) + **Path C** (data infrastructure). Three paths = highest priority. Zero paths = scope creep. Kill scope creep.

## What NOT To Do

- Don't hardcode Richmond-specific logic without city abstraction layer
- Don't use a separate vector database — pgvector handles it
- Don't treat Tier 3-4 sources as factual without Tier 1-2 verification
- Don't generate opinion or advocacy — comments are strictly factual, citation-heavy
- Don't skip FIPS codes on any record, ever
- Don't put secrets in `.env.example` — only placeholder values

## Documentation Map

**Always loaded** (`.claude/rules/`):
- `judgment-boundaries.md` — Authoritative catalog of AI-delegable vs. judgment-call decisions. Governs all delegation and overrides skill/plugin defaults.
- `team-operations.md` — RTP's Layer 2: process, documentation, architecture standards, quality enforcement
- `architecture.md` — Three-layer DB, tech stack, multi-city architecture, RTP-specific design principles
- `conventions.md` — Code style, testing, commit format, FIPS enforcement, environment
- `richmond.md` — Political context, council members, source credibility tiers, data source overview

**Loaded on demand:**
- `src/CLAUDE.md` — All pipeline practical knowledge (data source APIs, scanner gotchas, cloud ops)
- `web/CLAUDE.md` — Frontend conventions (Next.js, components, Supabase queries, design system)

**Project docs** (`docs/`):
- `PROJECT-SPEC.md` · `ARCHITECTURE.md` · `BUSINESS-MODEL.md` · `DATA-SOURCES.md`
- `DECISIONS.md` — Key decisions with rationale (add new decisions here)
- `PARKING-LOT.md` — Execution sprints (S1-S7) + backlog, dependency-ordered
- `specs/` — Feature specs for Phase 2 work
- `plans/` — Implementation plans for completed and future work
- `research/` — Research findings (Form 700, etc.)
- `JOURNAL.md` — Session journal. Narrative chronicle of the project's arc, decisions, mistakes, and growth. Written in a distinctive voice (future AI-autonomy zone candidate). Each entry has a narrative section + "serious stuff" technical appendix. Each entry includes a `**bach:**` field: a Bach solo keyboard piece chosen by the AI, an expressive zone alongside the journal voice.
