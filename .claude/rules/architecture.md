# Architecture Rules

## AI-Native Philosophy

This project is AI-native from the ground up — not "AI-assisted." Every architectural decision assumes AI does the work. Humans are reserved for decisions that require being human.

**What humans decide:** Creative/expressive decisions, values/ethics, relationship management (city government trust), trust calibration (is this finding credible enough to publish?), political capital allocation.

**Everything else is AI-driven** with human review at key checkpoints.

## Design Principles

1. **Schema as contract, AI fills the gaps.** Output schemas are strict. AI figures out how to populate them from diverse inputs.
2. **Prompts are config, not code.** Extraction prompts, conflict rules, comment templates are version-controlled. Re-run against historical data when prompts improve.
3. **Self-healing systems.** Scrapers detect failures and attempt recovery. Parsing logic is mutable artifacts an LLM can regenerate.
4. **Self-monitoring pipelines.** System detects anomalies in its own output ("30 items from a meeting that usually has 50").
5. **Graceful uncertainty.** Confidence scores on everything. Never guess silently. Conflict scanner tier system is the reference pattern.
6. **Human-in-the-loop at decision points only.** Pipeline runs autonomously. Humans review before publication, when confidence is low, or when system detects its own failure.
7. **AI-native scaling.** Human picks the city. AI discovers data sources, builds pipelines, monitors for failures. "Point Claude at the data" is thinking too small — the system should find the data itself.
8. **Build now, optimize compute later.** Get the prompts right first — they ARE the business logic. Don't optimize schema or processes for scale prematurely. Compute costs decrease as models get cheaper; correct extraction logic is the hard part. Optimize prompts for accuracy, not token count.

## Self-Advancing System

- **Model adaptation:** Auto-benchmark new models against existing output
- **Boundary management:** AI-to-AI comparison identifies which human processes could be automated
- **Cross-city intelligence:** Patterns from one city improve all cities
- **Autonomous city onboarding:** Given FIPS code → discover sources → propose pipeline config → human approves
- **Continuous self-examination:** Question foundations, not just execution. Follow evidence even when it challenges premises.

## Three-Layer Database

1. **Layer 1 — Document Lake:** Raw documents, JSONB metadata. Source of truth. Re-extractable.
2. **Layer 2 — Structured Core:** Normalized tables (cities, officials, meetings, agenda_items, votes, motions, speakers, donors, contributions, conflicts). Fast JOINs for conflict detection.
3. **Layer 3 — Embedding Index:** pgvector in PostgreSQL. Single query combines vector similarity + SQL filtering.

## Tech Stack

- **Database:** PostgreSQL + pgvector (Supabase)
- **LLM:** Claude Sonnet API (extraction, analysis, RAG)
- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS v4
- **Hosting:** Vercel (frontend), GitHub Actions + n8n (orchestration)
- **Scraping:** Playwright (NextRequest), requests + BeautifulSoup (eSCRIBE, CivicPlus)
- **Open data:** Socrata SODA API, NetFile Connect2 API, CAL-ACCESS bulk data

## Multi-City Architecture

- **`src/city_config.py`** is the central registry. Each city is a dict keyed by FIPS code.
- **Adding a new city:** Add entry to `CITY_CONFIGS` with data source configs (URLs, API IDs, portal slugs).
- **Config resolution:** `get_city_config(fips)` validates and resolves. `CityNotConfiguredError` for unknown FIPS.
- **All scrapers accept city config** instead of module-level constants. `DEFAULT_FIPS = "0660620"` for CLI backward compatibility.
