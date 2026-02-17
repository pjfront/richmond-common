# CLAUDE.md — Richmond Transparency Project

## What This Is

AI-powered local government accountability platform. Replaces the investigative function of disappeared local journalism by automatically analyzing government documents, detecting conflicts of interest, and generating public comment before city council meetings.

**Pilot city:** Richmond, California (FIPS `0660620`)
**Scaling target:** 19,000 US cities

This is NOT an adversarial "gotcha" tool. It's a governance assistant that helps cities stay transparent by default. Accountability is a byproduct of transparency, not the stated goal. This framing matters — the creator (Phillip) sits on Richmond's Personnel Board and must maintain a collaborative relationship with city government.

## Read These First

The full specs live in `/docs/`. Read the relevant doc before making architectural or feature decisions:

- `docs/PROJECT-SPEC.md` — Features, phases, credibility tiers, what this is NOT
- `docs/ARCHITECTURE.md` — Three-layer database, tech stack, FIPS disambiguation, scaling
- `docs/BUSINESS-MODEL.md` — Three monetization paths, entity structure, budgets
- `docs/DATA-SOURCES.md` — 15 Richmond data sources assessed and prioritized
- `docs/DECISIONS.md` — Key decisions with rationale (add new decisions here)

## Critical Conventions

### FIPS Codes — Non-Negotiable

Every database record MUST include `city_fips`. Richmond CA = `0660620`. This is cheap now and catastrophically expensive to retrofit at city #50. There are 27 Richmonds in the US.

- Every web search query: include "Richmond, California" — never just "Richmond"
- Every table: has a `city_fips` column
- Every API response: includes city context
- No exceptions. No shortcuts. No "we'll add it later."

### Three-Layer Database

1. **Layer 1 — Document Lake:** Raw documents preserved exactly as received. JSONB metadata. Source of truth. Re-extractable when prompts improve.
2. **Layer 2 — Structured Core:** Normalized tables (cities, officials, meetings, agenda_items, votes, motions, speakers, donors, contributions, conflicts). Fast JOINs for conflict detection.
3. **Layer 3 — Embedding Index:** pgvector in PostgreSQL. No separate vector DB. Single query combines vector similarity + SQL filtering.

### Source Credibility Tiers

All ingested content must be tagged with its tier. RAG retrieval weights by tier.

- **Tier 1 (highest):** Official government records — certified minutes, adopted resolutions, CAL-ACCESS filings, budget docs
- **Tier 2:** Independent journalism — Richmond Confidential (UC Berkeley), East Bay Times, KQED
- **Tier 3 (disclose bias):** Stakeholder communications — Tom Butt E-Forum (label as council member's newsletter), council member newsletters, Richmond Standard (ALWAYS disclose: "funded by Chevron Richmond")
- **Tier 4 (context only):** Community/social — Nextdoor, public comments, social media. Never sole source for factual claims.

### Tech Stack

- **Database:** PostgreSQL + pgvector (Supabase or Railway)
- **LLM:** Claude Sonnet API (extraction, analysis, RAG)
- **Frontend:** Next.js
- **Hosting:** Vercel
- **Transcription:** Deepgram or Whisper (meeting audio)
- **Browser automation:** Playwright (scraping government sites)
- **Open data:** Socrata SODA API (Transparent Richmond portal)
- **Orchestration:** n8n (pipeline scheduling)

## Current Phase: Phase 1 — Personal Pilot

We're proving the extraction pipeline works on Richmond data. Current priorities:

1. Validate extraction accuracy on 3-5+ council meetings
2. Establish Socrata API connection (Transparent Richmond, 300+ datasets)
3. Pull CAL-ACCESS campaign finance bulk data
4. Generate and submit first real transparency public comment
5. Build basic council member profiles from extracted data

Don't build Phase 2 features (frontend, alerts, subscriptions) yet. Focus on data pipeline reliability.

## Feature Prioritization Filter

Before building any feature, ask: does it serve one of the three monetization paths?

1. **Path A — Freemium Platform:** Does this make the citizen product more valuable?
2. **Path B — Horizontal Scaling:** Does this work for any city, not just Richmond?
3. **Path C — Data Infrastructure:** Does this add to the structured dataset?

Features hitting all three = highest priority. Features hitting zero = scope creep. Kill scope creep.

## Richmond-Specific Context

- **7 council members**, ~24 regular meetings/year
- Minutes format is highly parseable: "Ayes: [names]. Noes: [names]. Abstentions: [names]."
- Mayor Eduardo Martinez (progressive coalition, elected 2022)
- Tom Butt — longest-serving council member, prolific E-Forum blog, former mayor
- Chevron is a major political spender in Richmond — funds the Richmond Standard news site
- Richmond Confidential is UC Berkeley journalism program covering Richmond — independent, well-sourced
- Transparent Richmond Socrata portal has 300+ open datasets with API access

## Code Style & Practices

- Python for backend/pipeline code
- TypeScript for frontend (Next.js)
- Use type hints in Python, strict TypeScript
- Extraction prompts go in dedicated prompt files, not inline strings
- All database queries must filter by `city_fips`
- Log decisions in `docs/DECISIONS.md` with date and rationale
- Commit messages: imperative mood, reference the phase ("Phase 1: add CAL-ACCESS ingestion")

## What NOT To Do

- Don't hardcode Richmond-specific logic without a city abstraction layer
- Don't build UI before the data pipeline is reliable
- Don't use a separate vector database — pgvector in PostgreSQL handles it
- Don't treat Tier 3-4 sources as factual without Tier 1-2 verification
- Don't generate opinion or advocacy content — comments are strictly factual, citation-heavy
- Don't use `sudo npm install` for anything
- Don't skip FIPS codes on any record, ever
