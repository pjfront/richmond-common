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

We're proving the extraction pipeline works on Richmond data. Focus on data pipeline reliability — don't build Phase 2 features (frontend, alerts, subscriptions) yet.

### Done

- **Extraction pipeline end-to-end:** Discover → download → extract text → Claude Sonnet API → structured JSON. Tested on Sept 23, 2025 council meeting. Cost: ~$0.06 per meeting (~10.5K input + ~8.9K output tokens).
- **Socrata API client:** `src/socrata_client.py` — connects to Transparent Richmond portal (142 actual datasets). Tested against expenditures, vendors, payroll. No auth required for public data.
- **CAL-ACCESS client:** `src/calaccess_client.py` — downloads statewide bulk ZIP (~1.5GB), extracts FILER_CD/RCPT_CD tables, filters for Richmond. Not yet tested against real data (requires download).
- **Project scaffolding:** requirements.txt, .env.example, .gitignore, CLAUDE.md
- **PostgreSQL schema:** `src/schema.sql` — all three layers (Document Lake, Structured Core, Embedding Index). 20+ tables, indexes, views for conflict detection. Seeds Richmond as city. `src/db.py` — database loader that maps extracted JSON into Layer 2 tables (meetings, agenda items, motions, votes, attendance, closed session, public comments). CLI: `python db.py init` and `python db.py load <json_file>`.
- **Conflict scanner:** `src/conflict_scanner.py` — cross-references agenda items against campaign contributions and Form 700 interests. Entity name matching with normalization and employer cross-referencing. Two modes: JSON mode (pre-database testing) and DB mode (queries Layer 2). Land-use detection excludes commission/board appointments to prevent false positives. Tested against sample data — correctly flags vendor/donor matches. CLI: `python conflict_scanner.py <meeting.json> --contributions <contribs.json>`.
- **Council member profiles:** `src/council_profiles.py` — aggregates voting records, attendance, motions made/seconded, split vote positions, and category breakdowns from extracted meeting JSON. Coalition analysis identifies who votes together on non-unanimous votes. Tested on Sept 23, 2025 meeting — shows Jimenez+Wilson 100% agreement, Brown+Zepeda 75% agreement on split votes. CLI: `python council_profiles.py <directory_or_files>`.
- **Comment generator:** `src/comment_generator.py` — generates formatted public comment from `ScanResult` (conflict scanner) + missing document detection. Delegates conflict analysis to `conflict_scanner.py`, handles document completeness checks (resolutions without linked text, policies referenced for revision). Jinja2 template with methodology statement, legal disclaimers, and evidence citations. CLI: `python comment_generator.py <meeting.json> --contributions <file> --form700 <file> [--send] [--output file]`.
- **Test data fixtures:** `src/test_data/` — synthetic campaign contributions and Form 700 interest data for testing the full pipeline without real CAL-ACCESS data. Designed to match entities in the Sept 23 sample meeting.

### Remaining

1. Run pipeline against 10+ meetings to validate extraction consistency
2. Download CAL-ACCESS bulk data and identify Richmond filer IDs
3. Generate and submit first real transparency public comment

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
- Use feature branches and PRs going forward (initial scaffolding was committed directly to main)

## What NOT To Do

- Don't hardcode Richmond-specific logic without a city abstraction layer
- Don't build UI before the data pipeline is reliable
- Don't use a separate vector database — pgvector in PostgreSQL handles it
- Don't treat Tier 3-4 sources as factual without Tier 1-2 verification
- Don't generate opinion or advocacy content — comments are strictly factual, citation-heavy
- Don't use `sudo npm install` for anything
- Don't skip FIPS codes on any record, ever
- Don't put secrets in `.env.example` — only placeholder values like `sk-ant-...`

## Practical Knowledge (Learned from Implementation)

### Richmond Archive Center (Council Minutes)

- **Base URL:** `https://www.ci.richmond.ca.us/ArchiveCenter/`
- **Minutes archive:** `?AMID=31` (Archive Module ID for Regular Meeting Minutes)
- **Document links use `ADID=` pattern** (Archive Document ID), NOT `ViewFile/Item/`
- **Direct PDF URL:** `https://www.ci.richmond.ca.us/Archive.aspx?ADID={id}`
- ADID URLs serve raw PDFs directly (no intermediate page)

### PDF Parsing

- **Use PyMuPDF (`fitz`), NOT pdfplumber.** Government PDFs often use Type3 fonts that pdfplumber can't decode (produces `(cid:XX)` garbled output).
- PyMuPDF handles TrueType fonts correctly. Type3 fonts (image-based glyphs) are still garbled — those need OCR (future work).
- The pipeline detects Type3 fonts per page and logs a warning.
- Older meetings (pre-2024) tend to have TrueType fonts and extract cleanly. Some newer meetings use Type3.

### Socrata API (Transparent Richmond)

- **Domain:** `www.transparentrichmond.org` (NOT `data.ci.richmond.ca.us`)
- **Portal has 142 actual datasets** (637 total including derived views)
- No auth required for public data; app token is optional but recommended for rate limits
- Uses `sodapy` Python library. SoQL queries for filtering.
- Key dataset IDs are mapped in `src/socrata_client.py` DATASETS dict

### CAL-ACCESS (Campaign Finance)

- **No REST API exists.** Must download statewide bulk ZIP (~1.5GB) from `campaignfinance.cdn.sos.ca.gov/dbwebexport.zip`
- ZIP expands to ~10GB. Tables are tab-delimited TSV files inside `CalAccess/DATA/`
- Key tables: `FILER_CD` (committee registration), `RCPT_CD` (contributions/receipts), `EXPN_CD` (expenditures)
- Filter for Richmond by keyword matching on filer name, city fields
- `calaccess-raw-data` PyPI package is Django-only — too heavy. We parse TSV directly with csv module.

### Environment & Dependencies

- **`python-dotenv` is required** — `os.getenv()` alone doesn't read from `.env` files. Import and call `load_dotenv()` at the top of entry points.
- Run pipeline scripts from `src/` directory (relative imports: `from extraction import ...`)
- Extraction prompt template uses `.format()` with keys: `schema` and `minutes_text`
- **Windows compatibility:** Use `python -X utf8` flag when running scripts that output Unicode characters. Comment generator uses ASCII-only formatting for cross-platform compatibility.

### Pipeline Cost Estimates

- Single meeting extraction: ~$0.06 (Claude Sonnet, ~10.5K input + ~8.9K output tokens)
- At 24 meetings/year: ~$1.44/year for Richmond extraction alone
- Budget headroom for re-extraction as prompts improve
