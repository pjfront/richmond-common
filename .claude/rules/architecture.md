# Architecture Rules

_Core AI-native philosophy and design principles inherited from Layer 1 (`~/.claude/CLAUDE.md`). This file covers Richmond Commons-specific architecture._

## Richmond Commons-Specific Design Principles

_Extends Layer 1's universal design principles with Richmond Commons context:_

- **Self-knowledge, not self-monitoring (yet).** Today `system_health.py`, `data_quality_checks.py`, and `staleness_monitor.py` run *next to* the pipeline, not *inside* it — they report after the fact, they do not gate writes. The honest framing today is "self-reporting + decision-queue routing." The aspirational target is **self-knowledge**: baselines, expectation-gated writes, reflective digest, drift sentinel. See `docs/plans/2026-05-09-rearchitecture-plan.md` Phase 5 for the structural implementation. Until that ships, do not describe the system as "self-monitoring."
- **Graceful uncertainty is the reference pattern.** The conflict scanner's tier system (confidence scores, source tiers, never-guess-silently) is the model every new generator/extractor should imitate.

**Judgment calls in Richmond Commons:** Creative/expressive decisions, values/ethics, relationship management (city government trust), trust calibration (is this finding credible enough to publish?), political capital allocation, publication tier assignment for new features.

## Three-Layer Database

1. **Layer 1 — Document Lake:** Raw documents, JSONB metadata. Source of truth. Re-extractable.
2. **Layer 2 — Structured Core:** Normalized tables (cities, officials, meetings, agenda_items, votes, motions, speakers, donors, contributions, conflicts). Fast JOINs for conflict detection.
3. **Layer 3 — Embedding Index:** pgvector in PostgreSQL. Single query combines vector similarity + SQL filtering. Embedding columns will migrate to sidecar tables (`*_embeddings`) in Phase 2.10 of the re-architecture plan to stop bleeding ~6 KB per row into Layer 2 list queries.

## Tech Stack

- **Database:** PostgreSQL + pgvector (Supabase)
- **LLM:** DeepSeek API via `src/llm_client.py` — `deepseek-chat` (V3, primary extraction/generation), `deepseek-reasoner` (R1, self-assessment). OpenAI-compatible SDK. Migrated 2026-07 from Anthropic (Claude Sonnet/Haiku).
- **Frontend:** Next.js 16, React 19, TypeScript, Tailwind CSS v4, Radix UI primitives (shadcn/ui adoption in progress — Phase 2.8)
- **Hosting:** Vercel (frontend), GitHub Actions + n8n (orchestration)
- **Scraping:** Playwright (NextRequest), requests + BeautifulSoup (eSCRIBE, CivicPlus)
- **Open data:** Socrata SODA API, NetFile Connect2 API, CAL-ACCESS bulk data
- **Auth + rate limit:** iron-session httpOnly cookie for operator auth; Postgres `check_and_increment_rate_limit` RPC for rate limiting (no Upstash, no in-memory `Map()`).

## Richmond-Only Scope (2026-05-09 pivot)

The project is single-city by design. Multi-city abstractions are scope creep, not foresight.

- `src/city_config.py` exists today as a Richmond config holder. Its plumbing (`get_city_config()`, `get_data_source_config()`, `DEFAULT_FIPS` kwarg threaded through every scraper) will be simplified to module constants in Phase 3 of the re-architecture plan.
- The `cities` table (one row) and `city_fips` columns stay as cheap provenance metadata — ripping them out cascades through 24 FK targets for no benefit. New queries do **not** need to filter by `city_fips`; new code should **not** add multi-city indirection.
- External-source disambiguation still matters: web searches, news fetches, and external API queries must say "Richmond, California" — there are 27 Richmonds in the US.
- The `src/city_config.py` registry shape (FIPS-keyed dict) can stay as a pattern for the rare case where Richmond's own configuration grows multiple environments (test vs prod, mock fixtures), but it is no longer the central abstraction it was billed as.
