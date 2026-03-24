# Richmond Common

**A governance assistant that helps cities stay transparent by default.**

Pulls city government data into one place and makes it understandable. Automatically analyzes government documents, detects conflicts of interest, and generates plain-language explanations of what your city council is doing and why it matters.

**Pilot city:** Richmond, California · **Scaling target:** 19,000 US cities
**Live:** [richmondcommon.org](https://richmondcommon.org) · **License:** [AGPL-3.0](LICENSE)

---

## Why This Exists

Local journalism is disappearing. Over 2,500 newspapers have closed since 2005, leaving most cities with no one watching what local government does. The information is technically public, but scattered across dozens of portals in formats no one has time to read.

Richmond Common replaces that investigative function with AI-powered infrastructure. Not a "gotcha" tool — a governance assistant that helps cities stay transparent by default. Accountability is the natural consequence of making public information actually accessible.

---

## What It Does

**For citizens:** Plain-language meeting summaries, council member voting records and profiles, conflict-of-interest detection, campaign finance connections, commission tracking, and public records monitoring — all in one place, all free.

**For the system:** Automated ingestion of 7+ city data sources, structured extraction via Claude API, cross-referencing of votes against financial interests, confidence-scored findings, and operator-reviewed publication tiers to ensure accuracy before anything goes public.

---

## What's Built

### Frontend (18 pages, live)

| Section | Pages |
|---------|-------|
| **Meetings** | Meeting index, meeting detail with agenda items/votes/summaries |
| **Council** | Council index, individual profiles, coalition analysis, voting patterns, time-spent stats |
| **Influence Map** | Campaign finance connections by official and agenda item |
| **Financial** | Financial connections explorer, donor overlap analysis |
| **Commissions** | Commission index, commission detail with meeting history |
| **Public Records** | CPRA request tracking via NextRequest |
| **Search** | Full-text + semantic search (PostgreSQL + pgvector) |
| **About** | Methodology, data sources, credibility tiers |
| **Operator Tools** | Decision queue, data quality dashboard (gated) |

### Pipeline (60+ Python modules, 487 tests)

- **Scraping:** eSCRIBE agendas, CivicPlus Archive Center minutes, NextRequest public records, commission rosters
- **Extraction:** Claude API-powered structured extraction from meeting documents (votes, motions, speakers, financials)
- **Campaign finance:** NetFile Connect2 API (22K+ local contributions), CAL-ACCESS (state PAC/IE data)
- **Conflict detection:** Multi-signal scanner with composite confidence scoring, temporal correlation, donor-vendor cross-reference, corroboration grouping (93.5% false-positive reduction over v1)
- **Analysis:** Coalition detection, voting pattern analysis, plain-language summarization, AI-generated bios
- **Quality:** Bias audit, data freshness monitoring, completeness checks, self-assessment loop
- **Infrastructure:** Multi-city config registry (FIPS-based), cloud orchestration (GitHub Actions + n8n), pipeline journaling

### Architecture

Three-layer database design:
1. **Document Lake** — Raw documents with JSONB metadata (source of truth, re-extractable)
2. **Structured Core** — Normalized tables for fast queries and conflict detection
3. **Embedding Index** — pgvector in PostgreSQL for semantic search (no separate vector DB)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Database | PostgreSQL + pgvector (Supabase) |
| LLM | Claude Sonnet API |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS v4 |
| Components | shadcn/ui + Radix UI |
| Hosting | Vercel (frontend), GitHub Actions + n8n (pipeline) |
| Scraping | Playwright, requests + BeautifulSoup |
| Open data | Socrata SODA API, NetFile Connect2 API, CAL-ACCESS |

---

## Design Principles

- **Narrative over numbers.** Plain-language descriptions of what happened and why it matters — not charts and dashboards.
- **Source credibility tiers.** Every piece of data is tagged with its source tier (official records → independent journalism → stakeholder comms → community/social). Tier 3+ sources always disclose bias.
- **Confidence scores on everything.** Low-confidence findings (< 90%) never appear in summaries. Detail views show confidence indicators.
- **AI content is always labeled.** No exceptions.
- **Free public access.** Revenue comes from professional tools and scaling, never from paywalling public data.

---

## Documentation

| Doc | What's In It |
|-----|-------------|
| [Project Spec](docs/PROJECT-SPEC.md) | Full product spec — features, phases, credibility tiers, UX |
| [Architecture](docs/ARCHITECTURE.md) | Three-layer database, tech stack, disambiguation, scaling |
| [Business Model](docs/BUSINESS-MODEL.md) | Monetization paths, entity structure, budget estimates |
| [Data Sources](docs/DATA-SOURCES.md) | 15 sources assessed and prioritized by phase |
| [Decisions Log](docs/DECISIONS.md) | Key decisions and rationale |
| [Design Rules](docs/design/DESIGN-RULES-FINAL.md) | Enforceable frontend design rules |

---

## Status

Phase 2 Beta. 12 of 12 planned sprints scoped, 11 complete. Core pipeline operational, frontend live, conflict scanner v3 shipped. Current focus: citizen experience polish and plain-language improvements.

See [PARKING-LOT.md](docs/PARKING-LOT.md) for the full sprint tracker and backlog.

---

## Editorial Voice

The [project journal](JOURNAL.md) is written as an editorial — opinionated, reflective, and intentionally subjective. Like a newspaper's editorial board, it represents the perspective of the system and the AI behind it. This is a deliberate design choice: rather than pretending the system has no point of view, we disclose it. The journal is clearly labeled as editorial content, distinct from the factual data and analysis the platform provides.

---

## Built With Claude

Richmond Common is co-authored by a human operator and Anthropic's Claude. The AI writes code, extracts data, detects patterns, generates plain-language explanations, and maintains the editorial journal. The human makes judgment calls about what to publish, how to frame findings, and how to maintain the project's relationship with city government.

This is documented transparently because it's core to how the project works, not an implementation detail to hide.

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- A [Supabase](https://supabase.com) project (free tier works)
- An [Anthropic API key](https://console.anthropic.com)

### Setup

```bash
git clone https://github.com/pjfront/richmond-common.git
cd richmond-common
cp .env.example .env
# Fill in your Supabase and Anthropic API credentials
```

**Pipeline (Python):**
```bash
cd src
pip install -r requirements.txt
```

**Frontend (Next.js):**
```bash
cd web
npm install
npm run dev
```

**Database migrations:**
```bash
supabase db push         # Apply all migrations
supabase db push --dry-run  # Preview first
```

### Adding a New City

Every city is a configuration entry in `src/city_config.py`, keyed by [FIPS code](https://www.census.gov/library/reference/code-lists/ansi.html):

```python
config = get_city_config("0660620")  # Richmond, CA
```

Add an entry to `CITY_CONFIGS` with data source URLs, API IDs, and portal slugs. All scrapers accept city config — no hardcoded city logic.

---

## Contributing

Richmond Common is a solo project in active development. Issues and pull requests are welcome, but response times may vary. If you're interested in adapting this for your city, open an issue — that's the most valuable contribution right now.

---

## Contact

**Email:** hello@richmondcommon.org
**Site:** [richmondcommon.org](https://richmondcommon.org)

---

*Richmond Common is a public benefit project. The platform is free for citizens. Professional features fund operating costs and maintenance.*
