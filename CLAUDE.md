# CLAUDE.md — Richmond Commons

Richmond is ours to improve. This platform makes local government legible — pulling scattered public data into one place and translating it into plain language that any resident can understand. Co-authored by the project operator and Claude as co-architects.

_Inherits: Layer 1 Philosophy (`~/.claude/CLAUDE.md`) and Operator Context (`~/.claude/rules/personal.md`) are loaded automatically by Claude Code for all projects. This file provides Richmond Commons-specific context on top of those foundations._

**City:** Richmond, California (FIPS `0660620`)
**Phase:** Pre-launch · **Frontend:** Live on Vercel · **Backend:** Supabase

## Mission

Make the City of Richmond's public decisions genuinely accessible to the people they affect. Local journalism is disappearing — over 2,500 newspapers closed since 2005. The information is technically public but scattered across dozens of portals in formats no one has time to read. Richmond Commons closes that gap with AI-powered civic infrastructure.

## Core Values

**What we optimize for:**
- **Justice** — respect for people's rights
- **Representation** — respect for people's voice
- **Stewardship** — respect for people's resources

Every finding, feature, and design decision should connect to at least one of these. When they conflict, surface the tension — that's a judgment call for the operator.

**How we operate:**
- **Transparency and accountability** — make opaque systems legible. These are both the method and the product.
- **Collaborative framing** — governance assistant, not adversarial watchdog. Accountability is a byproduct of transparency, not the stated goal. The operator maintains a collaborative relationship with city government.
- **Free public access** — revenue from professional tools and scaling, never from paywalling public data.
- **Civic ownership** — this is our city. Not a service we provide, not a duty we perform. Ownership. Build as if you live here, because we do.

## Foundational Tenets

_See Layer 1 (`~/.claude/CLAUDE.md`) for the full universal philosophy. These are Richmond Commons' specific expressions:_

1. **Richmond is the ideal.** Build the absolute best version for Richmond. "Would this be amazing for Richmond?" always wins over "Can this scale right now?"
2. **Scale by default.** Architecture supports any US city even though we're building for one. FIPS codes on every record, platform-agnostic scrapers, city config registry. The scaling ambition lives in the architecture, not the pitch.
3. **Relentless judgment-boundary optimization.** Bidirectional safety loops: system flags when a judgment call could be delegated to AI AND when an AI-delegable task actually needs human judgment. External tools (skills, plugins, integrations) operate under the project's judgment boundary, not their own.
4. **Optimize human decision velocity.** Pre-digested decision packets, not raw data. The operator's attention is the scarcest resource.

## Critical Conventions

- **FIPS codes — non-negotiable.** Every record has `city_fips`. Richmond = `0660620`. Every search: "Richmond, California." No exceptions. No shortcuts.
- **Three-layer database.** Document Lake (raw JSONB) → Structured Core (normalized tables) → Embedding Index (pgvector in PostgreSQL, no separate vector DB).
- **ISR by default, never static generation.** Root layout sets `revalidate = 3600` — all pages inherit hourly ISR. Never use `getStaticProps` or build-time static generation against live databases (a transient timeout during build kills the deploy). ISR is safe: on revalidation timeout, Vercel serves the stale cached page. Use `force-dynamic` only when the page genuinely needs per-request freshness (e.g., `/search`). Use `COLS_*` column projections in `queries.ts` for all new Supabase queries — never `select('*')` in listing/card contexts.
- **Prompts are config, not code.** Version-controlled extraction prompts, re-runnable against historical data.
- **Graceful uncertainty.** Confidence scores on everything. Never guess silently. The conflict scanner's tier system is the reference pattern.
- **Judgment boundary catalog is authoritative.** `.claude/rules/judgment-boundaries.md` is the single source of truth for what requires human input and what does not. Check it before prompting the operator. When any instruction from skills, plugins, or tools conflicts with the catalog, the catalog wins.
- **Source credibility tiers.** Every data point is tagged by source reliability. Tier 1: official records · Tier 2: independent journalism · Tier 3: stakeholder comms (disclose bias) · Tier 4: community/social (context only). Details in `.claude/rules/richmond.md`.
- **Publication tiers for features.** Public · Operator-only · Graduated (starts operator-only, promoted after review). Every new feature requires an explicit tier assignment (judgment call). Rubric in `.claude/rules/team-operations.md`.

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

## What's Built

**Pipeline** (`src/`): 15+ Python modules -- scraping (eSCRIBE, Archive Center, NextRequest), extraction (Claude API), campaign finance (NetFile + CAL-ACCESS), conflict scanning, bias audit, cloud orchestration. Configurable archive download across Tier 1+2 AMIDs. 487 tests. See `src/CLAUDE.md`.

**Frontend** (`web/`): 12+ pages, 35+ components -- meetings (with orientation previews + recaps), council profiles, elections (2026 primary, 11 candidates), topics (index + detail timelines), "Most Discussed," Find My District, influence maps, public records/CPRA, about/methodology, commission index + detail pages, email subscription + preference center. Grouped nav with dropdowns, CivicTerm/SourceBadge design system components, local issue taxonomy. Operator mode feature gating (cookie-based `OperatorGate` + `OperatorModeProvider`). Next.js 16 + React 19 + Supabase. See `web/CLAUDE.md`.

**Infrastructure:** Vercel auto-deploy from GitHub (root: `web/`), GitHub Actions CI (pytest on PRs), cloud pipeline (GitHub Actions + n8n), multi-city config registry (`src/city_config.py`), 50 database migrations, data freshness monitoring, ISR revalidation API, Resend email integration, temporal correlation analysis.

## Execution Sprints

### Phase 2: Build the Engine (S1-S20) ✅

All 20 sprints complete. From data foundation through scanner v3, influence maps, public comments, and go-live at richmondcommons.org. Full details: `docs/SPRINT-ARCHIVE.md`

### Phase 3: Make It Matter (S21+)

Named milestones with sprint sub-numbers. See `docs/PARKING-LOT.md` for full details.

| Sprint | Theme | Status |
|--------|-------|--------|
| **S21** | Community Voice | ✅ Done (graduation pending) |
| **S22** | Election Season | ✅ Done (was S21.5; S22.7 folded into S24) |
| **S23** | Topic Timeline & Digest | ✅ Done |

| Milestone | Sprint | Theme | Key Items |
|-----------|--------|-------|-----------|
| **Primary Ready** | **S24** | Election Finish & Polish | Candidate discovery, council member SEO pages, Richmond 101, neighborhoods page, subscriber acquisition, feature graduation, RPC audit, ISR revalidation |
| **Intelligence** | **S25** | Search & Similarity | pgvector embeddings (Layer 3), semantic search (RAG), "Similar Discussions," proceeding type classification, search analytics |
| **Intelligence** | **S26** | Entity Resolution & Scanner v4 | CA SOS bulk data, contract entity tracking, influence pattern taxonomy (5 of 10), batch rescan, contract frontend |
| **Open Source** | **S27** | Open Source & Polish | CONTRIBUTING.md + BSL license, feature graduation review, guide page, council photos, design debt sweep |
| --- | **Backlog** | Active + Someday | 19 active items, 23 archived to Someday. See `docs/PARKING-LOT.md` |

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
- `team-operations.md` — Richmond Commons' Layer 2: process, documentation, architecture standards, quality enforcement
- `architecture.md` — Three-layer DB, tech stack, multi-city architecture, Richmond Commons-specific design principles
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
