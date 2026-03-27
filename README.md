# Richmond Commons

**Making Richmond's public decisions genuinely accessible to the people they affect.**

Local journalism is disappearing. The information is technically public, but scattered across dozens of city portals in formats no one has time to read. Richmond Commons pulls it all into one place — plain-language meeting summaries, council member profiles, campaign finance connections, and conflict-of-interest detection — so residents can understand what their city government is doing and why it matters.

**City:** Richmond, California
**Site:** [richmondcommons.org](https://richmondcommons.org) · **License:** [AGPL-3.0](LICENSE)

---

## What It Does

**For residents:** Plain-language meeting summaries, council member voting records and profiles, campaign finance connections, commission tracking, and public records monitoring — all in one place, all free.

**Under the hood:** Automated ingestion of 15+ city data sources, structured extraction via Claude API, cross-referencing of votes against financial interests, confidence-scored findings, and operator-reviewed publication tiers to ensure accuracy before anything goes public.

---

## What's Built

### Frontend (live)

| Section | What you'll find |
|---------|-----------------|
| **Meetings** | Meeting index with calendar navigation, meeting detail with agenda items, votes, plain-language summaries, and topic labels |
| **Council** | Council member index, individual profiles with voting records, AI-generated bios, and campaign finance context |
| **About** | Methodology, data sources, credibility tiers |

Additional pages (influence maps, coalition analysis, commission tracking, public records, data quality) are available behind an operator gate while being validated.

### Pipeline (60+ Python modules, 487 tests)

- **Scraping:** eSCRIBE agendas, CivicPlus Archive Center minutes, NextRequest public records, commission rosters
- **Extraction:** Claude API-powered structured extraction from meeting documents (votes, motions, speakers, financials)
- **Campaign finance:** NetFile Connect2 API (22K+ local contributions), CAL-ACCESS (state PAC/IE data)
- **Conflict detection:** Multi-signal scanner with composite confidence scoring, temporal correlation, donor-vendor cross-reference, corroboration grouping
- **Analysis:** Coalition detection, voting pattern analysis, plain-language summarization, AI-generated bios
- **Quality:** Data freshness monitoring, completeness checks, bias audit, automated scheduling (daily/weekly/monthly/quarterly)

### Architecture

Three-layer database design:
1. **Document Lake** — Raw documents with JSONB metadata (source of truth, re-extractable)
2. **Structured Core** — Normalized tables for fast queries and conflict detection
3. **Embedding Index** — pgvector in PostgreSQL for semantic search

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Database | PostgreSQL + pgvector (Supabase) |
| LLM | Claude Sonnet API |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS v4 |
| Components | shadcn/ui + Radix UI |
| Hosting | Vercel (frontend), GitHub Actions (pipeline) |
| Scraping | Playwright, requests + BeautifulSoup |
| Open data | Socrata SODA API, NetFile Connect2 API, CAL-ACCESS |

---

## Design Principles

- **Narrative over numbers.** Plain-language descriptions of what happened and why it matters — not charts and dashboards.
- **Source credibility tiers.** Every piece of data is tagged by source reliability. Tier 3+ sources always disclose bias.
- **Confidence scores on everything.** Low-confidence findings never appear in summaries. Detail views show confidence indicators.
- **AI content is always labeled.** No exceptions.
- **Free public access.** Revenue comes from professional tools, never from paywalling public data.

---

## Documentation

| Doc | What's In It |
|-----|-------------|
| [Project Spec](docs/PROJECT-SPEC.md) | Full product spec — features, phases, credibility tiers, UX |
| [Architecture](docs/ARCHITECTURE.md) | Three-layer database, tech stack, disambiguation |
| [Business Model](docs/BUSINESS-MODEL.md) | Monetization paths, entity structure, budget estimates |
| [Data Sources](docs/DATA-SOURCES.md) | 15 sources assessed and prioritized by phase |
| [Decisions Log](docs/DECISIONS.md) | Key decisions and rationale |
| [Design Rules](docs/design/DESIGN-RULES-FINAL.md) | Enforceable frontend design rules |

---

## Status

Pre-launch. 16 of 18 sprints complete. Core pipeline operational with automated scheduling, frontend live, conflict scanner v3 shipped. Current focus: experience polish and launch infrastructure.

See [PARKING-LOT.md](docs/PARKING-LOT.md) for the full sprint tracker and backlog.

---

## Editorial Voice

The [project journal](JOURNAL.md) is written as an editorial — opinionated, reflective, and intentionally subjective. Like a newspaper's editorial board, it represents the perspective of the system and the AI behind it. This is a deliberate design choice: rather than pretending the system has no point of view, we disclose it. The journal is clearly labeled as editorial content, distinct from the factual data and analysis the platform provides.

---

## Built With Claude

Richmond Commons is co-authored by a human operator and Anthropic's Claude. The AI writes code, extracts data, detects patterns, generates plain-language explanations, and maintains the editorial journal. The human makes judgment calls about what to publish, how to frame findings, and how to maintain the project's relationship with city government.

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

---

## Contributing

Richmond Commons is in active development. Issues and pull requests are welcome, but response times may vary. If you're interested in adapting this for your city, open an issue — that's the most valuable signal right now.

---

## Contact

**Email:** hello@richmondcommons.org
**Site:** [richmondcommons.org](https://richmondcommons.org)

---

*Richmond Commons is a public benefit project. The platform is free for residents.*
