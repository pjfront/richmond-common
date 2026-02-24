# Architecture Rules

_Core AI-native philosophy and design principles inherited from Layer 1 (`~/.claude/CLAUDE.md`). This file covers RTP-specific architecture._

## RTP-Specific Design Principles

_Extends Layer 1's universal design principles with RTP context:_

- **Self-monitoring pipelines.** System detects anomalies in its own output ("30 items from a meeting that usually has 50"). The conflict scanner's tier system is the reference pattern for graceful uncertainty.
- **AI-native scaling.** Human picks the city. AI discovers data sources, builds pipelines, monitors for failures. "Point Claude at the data" is thinking too small. The system should find the data itself.

**What humans decide in RTP:** Creative/expressive decisions, values/ethics, relationship management (city government trust), trust calibration (is this finding credible enough to publish?), political capital allocation.

## Self-Advancing System (RTP)

- **Cross-city intelligence:** Patterns from one city improve all cities
- **Autonomous city onboarding:** Given FIPS code, discover sources, propose pipeline config, human approves

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
