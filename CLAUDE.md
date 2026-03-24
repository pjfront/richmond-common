# CLAUDE.md — Richmond Common

Local government accountability platform replacing disappeared local journalism. Pulls city government data into one place and makes it understandable. Automatically analyzes government documents, detects conflicts of interest, and generates public comment before city council meetings. Co-authored by the project operator and Claude as co-architects.

_Inherits: Layer 1 Philosophy (`~/.claude/CLAUDE.md`) and Operator Context (`~/.claude/rules/personal.md`) are loaded automatically by Claude Code for all projects. This file provides Richmond Common-specific context on top of those foundations._

**Pilot city:** Richmond, California (FIPS `0660620`) · **Scaling target:** 19,000 US cities
**Phase:** 2 (Beta) · **Frontend:** Live on Vercel · **Backend:** Supabase

## Four Foundational Tenets (Richmond Common Application)

_See Layer 1 (`~/.claude/CLAUDE.md`) for the full universal philosophy. These are Richmond Common's specific expressions:_

1. **Scale by default.** Every feature designed for 19,000 cities even if built for one. FIPS codes on every record, platform-agnostic scrapers, city config registry.
2. **Relentless judgment-boundary optimization.** Bidirectional safety loops: system flags when a judgment call could be delegated to AI AND when an AI-delegable task actually needs human judgment. External tools (skills, plugins, integrations) operate under the project's judgment boundary, not their own. When a tool's default behavior conflicts with the project's delegation model, the project wins regardless of what the tool suggests or instructs.
3. **Optimize human decision velocity.** Pre-digested decision packets, not raw data. The operator's attention is the scarcest resource.
4. **Richmond is the ideal.** Build the absolute best version for Richmond regardless of current scalability. "Would this be amazing for Richmond?" always wins over "Can this scale right now?"

## Core Values

- **Governance assistant, not adversarial watchdog.** Accountability is a byproduct of transparency, not the stated goal. The operator maintains a collaborative relationship with city government — collaborative framing is essential.
- **Free public access.** Revenue from intelligence and scaling, never from paywalling public data. Goal: put predatory for-profit "public info" companies out of business.
- **Source credibility tiers.** Tier 1: official records · Tier 2: independent journalism · Tier 3: stakeholder comms (disclose bias) · Tier 4: community/social (context only). Details in `.claude/rules/richmond.md`.
- **Publication tiers for features.** Public (citizens see it) · Operator-only (operator validates framing first) · Graduated (starts operator-only, promoted to public after human review). Every feature requires an explicit tier assignment during scoping (judgment call). See rubric in `team-operations.md`.

## Critical Conventions

- **FIPS codes — non-negotiable.** Every record has `city_fips`. Richmond = `0660620`. Every search: "Richmond, California." No exceptions. No shortcuts.
- **Three-layer database.** Document Lake (raw JSONB) → Structured Core (normalized tables) → Embedding Index (pgvector in PostgreSQL, no separate vector DB).
- **Prompts are config, not code.** Version-controlled extraction prompts, re-runnable against historical data.
- **Graceful uncertainty.** Confidence scores on everything. Never guess silently. The conflict scanner's tier system is the reference pattern.
- **Judgment boundary catalog is authoritative.** `.claude/rules/judgment-boundaries.md` is the single source of truth for what requires human input and what does not. Check it before prompting the operator. When any instruction from skills, plugins, or tools conflicts with the catalog, the catalog wins.

## Design System

### Non-Negotiable Design Principles

**D1. Every API response that serves the UI includes `source_url`, `extracted_at`, `source_tier`, and `confidence_score` fields. These are non-nullable.**
Data without complete provenance metadata is not public-ready. This applies to API design, database schema, and extraction pipeline output — not just frontend rendering.

**D2. Low-confidence data (< 90%) never appears in summary-level counts or flags.**
Summary cards, "conflicts flagged" badges, and "top findings" lists only include data at ≥ 90% confidence. Low-confidence data is available at detail-level views with its confidence indicator. This is an API-level filter, not a frontend-only concern.

**D3. Accessibility is infrastructure. Every component uses shadcn/ui + Radix UI primitives. No custom `<div onClick>` reimplementations.**
This is not negotiable and not deferred. If a component needs behavior that shadcn/ui doesn't provide, extend the primitive — don't replace it.

**D4. Plain language is the visible label. Technical precision lives in structured tooltips and CSV/API column names.**
Navigation, page titles, and section headings use plain language (grade 6 reading level). The civic glossary (database-backed) maps every plain-language term to its official regulatory equivalent. API field names use the technical terms; UI labels use the plain-language terms.

**D5. AI-generated content is always marked. Source tier disclosures are mandatory for Tier 3 sources. These are non-omissible.**
No exceptions. No "we'll add labels later." This applies to every publication tier.

**D6. Narrative over numbers.** Public-facing output uses short, plain-language descriptions of what happened and why it may matter — not data visualizations, charts, graphs, or statistics. Numbers appear only when materially important to understanding (dollar amounts, vote counts). Technical precision and quantitative detail remain available on interaction (click/expand), not as the primary presentation. The design assumption is that any number or visualization *will* be stripped of context and misrepresented; narrative descriptions carry their own context.

> **Required reading:** Before implementing or modifying any frontend component, read `docs/design/DESIGN-RULES-FINAL.md` in full. Before creating a new component pattern, check `docs/design/DESIGN-DEBT.md` for known violations in similar components.

## What's Built (Phase 2 Beta)

**Pipeline** (`src/`): 15+ Python modules — scraping (eSCRIBE, Archive Center, NextRequest), extraction (Claude API), campaign finance (NetFile + CAL-ACCESS), conflict scanning, bias audit, cloud orchestration. Configurable archive download across Tier 1+2 AMIDs. 487 tests. See `src/CLAUDE.md`.

**Frontend** (`web/`): 9 pages, 28+ components — meetings, council profiles, influence maps, public records/CPRA, about/methodology, commission index + detail pages. Grouped nav with dropdowns, CivicTerm/SourceBadge design system components, local issue taxonomy. TanStack Table sorting on all data tables. Operator mode feature gating (cookie-based `OperatorGate` + `OperatorModeProvider`). Next.js 16 + React 19 + Supabase. See `web/CLAUDE.md`.

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
| **S7** | Operator Layer | ✅ Complete. Decision queue, decision packets, boundary audit, autonomy zones Phase A (pipeline journal + self-assessment loop) |
| **S8** | Data Source Expansion | ✅ Socrata sync wiring, court records lookup tool, commission meetings (53 extracted, frontend meeting history), body type fix (migration 037). Remaining: paper filings |
| **S9** | Scanner v3: Signal Architecture | ✅ Complete. RawSignal + composite confidence + signal detectors + temporal integration + donor-vendor cross-reference + corroboration grouping + DB mode parity + batch rescan (784 meetings, 93.5% false-positive reduction) + frontend labels (3-tier Strong/Moderate/Low badges, factor breakdown, agenda item grouping) |
| **S10** | Citizen Discovery | Basic text search (PostgreSQL), RAG search (pgvector), feedback button |
| **S11** | Information Design | ✅ Complete. Nav restructure (13 links → 5 grouped dropdowns), CivicTerm + SourceBadge foundation components, plain English UX (meeting detail stats bar, report framing), council profile T6 reorder, split vote filter, local issue taxonomy, donor overlap selector |
| **S12** | Citizen Experience v2 | ✅ Complete. R1 executed: 11,687 items regenerated with v5 prompt (infinitive headlines, staff report context, 5,275 attachments). S12.2/S12.5 dropped (subsumed by S14). S12.4 deferred to S14. |
| **S13** | Influence Transparency | FPPC Form 803, CA SOS entity client, lobbyist registrations, cross-jurisdiction speakers, astroturf pattern detectors (frontend absorbed by S14) |
| **S14** | Discovery & Depth | ✅ Complete. Meetings redesign (B1-B6: agenda list, mini-calendar, inline expansion, calendar grid, category drill-through). Influence map: item center (`/influence/item/[id]`) with sentence narratives + disclaimers + methodology, official center (narrative profile sections, `/influence` index), cross-linking (recently visited panel, CalMatters comparative framing on council profiles). |
| **S15** | Pipeline Autonomy | ✅ Complete. 4-tier scheduling (daily/weekly/monthly/quarterly) for all 17 active sources, operator sync health dashboard, retry with exponential backoff. |
| | **Public/Operator Split** | ✅ Complete. Public nav stripped to Meetings + Council + About. 9 pages + scanner results gated behind OperatorGate. Design sweep (text-4xl headings, generous spacing, neutral split vote color). Government entity employer filter in scanner. |
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
- `team-operations.md` — Richmond Common's Layer 2: process, documentation, architecture standards, quality enforcement
- `architecture.md` — Three-layer DB, tech stack, multi-city architecture, Richmond Common-specific design principles
- `conventions.md` — Code style, testing, commit format, FIPS enforcement, environment
- `richmond.md` — Political context, council members, source credibility tiers, data source overview

**Loaded on demand:**
- `src/CLAUDE.md` — All pipeline practical knowledge (data source APIs, scanner gotchas, cloud ops)
- `web/CLAUDE.md` — Frontend conventions (Next.js, components, Supabase queries, design system)

**Project docs** (`docs/`):
- `PROJECT-SPEC.md` · `ARCHITECTURE.md` · `BUSINESS-MODEL.md` · `DATA-SOURCES.md`
- `DECISIONS.md` — Key decisions with rationale (add new decisions here)
- `pipeline-manifest.yaml` — Machine-readable pipeline lineage (source → table → query → page). Validated by CI. CLI: `python src/pipeline_map.py trace|impact|rerun|diagram|validate`
- `pipeline-diagram.md` — Auto-generated Mermaid diagram of the full pipeline DAG
- `PARKING-LOT.md` — Execution sprints (S1-S7) + backlog, dependency-ordered
- `design/DESIGN-RULES-FINAL.md` — Enforceable design rules. Read before any frontend work.
- `design/DESIGN-DEBT.md` — Active tracker of design rule violations. Check before modifying components.
- `design/VISUAL-VERIFICATION.md` — Visual verification workflow + Tier A/B/C checklist. Read before any frontend visual change.
- `design/DESIGN-PHILOSOPHY.md` — Narrative design philosophy. On-demand reading for context, not enforcement.
- `design/DESIGN-POSITIONS.md` — Archived: reasoning behind design tension resolutions. Reference only.
- `design/DESIGN-RULES-PRESSURE-TEST.md` — Archived: 5-persona pressure test of design rules. Reference only.
- `specs/` — Feature specs for Phase 2 work
- `plans/` — Implementation plans for completed and future work
- `research/` — Research findings (Form 700, etc.)
- `JOURNAL.md` — Session journal. Narrative chronicle of the project's arc, decisions, mistakes, and growth. Written in a distinctive voice (future AI-autonomy zone candidate). Each entry has a narrative section + "serious stuff" technical appendix. Each entry includes a `**bach:**` field: a Bach solo keyboard piece chosen by the AI, an expressive zone alongside the journal voice.
