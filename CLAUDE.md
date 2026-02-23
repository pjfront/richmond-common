# CLAUDE.md — Richmond Transparency Project

AI-powered local government accountability platform replacing disappeared local journalism. Automatically analyzes government documents, detects conflicts of interest, and generates public comment before city council meetings. Co-authored by Phillip and Claude as co-architects.

**Pilot city:** Richmond, California (FIPS `0660620`) · **Scaling target:** 19,000 US cities
**Phase:** 2 (Beta) · **Frontend:** Live on Vercel · **Backend:** Supabase

## Four Foundational Tenets

1. **Scale by default.** Vibecoding makes massive scale a best practice. Every feature designed for 19,000 cities even if built for one. FIPS codes on every record, platform-agnostic scrapers, city config registry.
2. **Relentless human-unique boundary optimization.** AI does everything except creative, expressive, values, ethical, relationship, and trust-calibration decisions. Continuously question both what IS and what ISN'T human-unique. Bidirectional safety loops: system flags when a "human" task could be automated AND when an "automated" task needs human review.
3. **Optimize human decision velocity.** Every human touchpoint presents minimum information for fastest correct decision. Pre-digested decision packets, not raw data. The operator's attention is the scarcest resource.
4. **Richmond is the ideal.** Build the absolute best version for Richmond regardless of current scalability. Richmond is the testing ground and the standard we figure out how to scale. "Would this be amazing for Richmond?" always wins over "Can this scale right now?"

## Core Values

- **Sunlight, not surveillance.** Governance assistant, not adversarial watchdog. Accountability is a byproduct of transparency. Phillip sits on Richmond's Personnel Board — collaborative framing is essential.
- **Free public access.** Revenue from intelligence and scaling, never from paywalling public data. Goal: put predatory for-profit "public info" companies out of business.
- **Source credibility tiers.** Tier 1: official records · Tier 2: independent journalism · Tier 3: stakeholder comms (disclose bias) · Tier 4: community/social (context only). Details in `.claude/rules/richmond.md`.
- **Publication tiers for features.** Public (citizens see it) · Operator-only (Phillip validates framing first) · Graduated (starts operator-only, promoted to public after human review).

## Critical Conventions

- **FIPS codes — non-negotiable.** Every record has `city_fips`. Richmond = `0660620`. Every search: "Richmond, California." No exceptions. No shortcuts.
- **Three-layer database.** Document Lake (raw JSONB) → Structured Core (normalized tables) → Embedding Index (pgvector in PostgreSQL, no separate vector DB).
- **Prompts are config, not code.** Version-controlled extraction prompts, re-runnable against historical data.
- **Graceful uncertainty.** Confidence scores on everything. Never guess silently. The conflict scanner's tier system is the reference pattern.

## What's Built (Phase 2 Beta)

**Pipeline** (`src/`): 15+ Python modules — scraping (eSCRIBE, Archive Center, NextRequest), extraction (Claude API), campaign finance (NetFile + CAL-ACCESS), conflict scanning, bias audit, cloud orchestration. 400+ tests. See `src/CLAUDE.md`.

**Frontend** (`web/`): 7 pages, 21+ components — meetings, council profiles, transparency reports, public records/CPRA, about/methodology. Next.js 16 + React 19 + Supabase. See `web/CLAUDE.md`.

**Infrastructure:** Cloud pipeline (GitHub Actions + n8n), multi-city config registry (`src/city_config.py`), 5 database migrations, data freshness monitoring, temporal correlation analysis.

## Priority Groups (Phase 2)

| Group | Focus | Key Items |
|-------|-------|-----------|
| **0** | Meta/Infrastructure | CI/CD, architecture self-assessment, auto-documentation |
| **1** | Operator Layer | Decision queue, pre-digested packets, boundary audit |
| **2** | Category Unlock | Vote categorization, plain language summaries, Form 700, coalition analysis |
| **3** | Deep Conflict Intelligence | Cross-meeting patterns, contribution context, court records, Charter compliance |
| **4** | Citizen-Facing Richness | Table sorting, "Explain This Vote", RAG search, commission pages, alerts |
| **5** | Data Foundation | Website monitoring, media sources, news integration, archive expansion |
| **6** | Future/Scale | External API/MCP, speaker diarization, cross-city policy comparison |

Full details with all items: `docs/PARKING-LOT.md`

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
- `architecture.md` — AI-native philosophy, design principles, three-layer DB, tech stack, self-advancing system
- `conventions.md` — Code style, testing, commit format, FIPS enforcement, environment
- `richmond.md` — Political context, council members, source credibility tiers, data source overview

**Loaded on demand:**
- `src/CLAUDE.md` — All pipeline practical knowledge (data source APIs, scanner gotchas, cloud ops)
- `web/CLAUDE.md` — Frontend conventions (Next.js, components, Supabase queries, design system)

**Project docs** (`docs/`):
- `PROJECT-SPEC.md` · `ARCHITECTURE.md` · `BUSINESS-MODEL.md` · `DATA-SOURCES.md`
- `DECISIONS.md` — Key decisions with rationale (add new decisions here)
- `PARKING-LOT.md` — All parked/future items organized by priority group
- `specs/` — Feature specs for Phase 2 work
- `plans/` — Implementation plans for completed and future work
- `research/` — Research findings (Form 700, etc.)
