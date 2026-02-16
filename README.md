# Richmond Transparency Project

**AI-powered local government accountability platform**
**Pilot city: Richmond, California (FIPS 0660620)**

> *A persistent, AI-powered accountability layer for local government.*

---

## What This Repo Is

This is the living source of truth for the Richmond Transparency Project. Every strategic decision, feature scope, architecture choice, and business model concept lives here. If it's not documented here, it's not real yet.

| Doc | What's In It |
|-----|-------------|
| [Project Spec](docs/PROJECT-SPEC.md) | Full product spec — features, phases, credibility tiers, UX |
| [Architecture](docs/ARCHITECTURE.md) | Three-layer database, tech stack, disambiguation, scaling |
| [Business Model](docs/BUSINESS-MODEL.md) | Monetization paths, entity structure, budget estimates |
| [Data Sources](docs/DATA-SOURCES.md) | 15 sources assessed and prioritized by phase |
| [Decisions Log](docs/DECISIONS.md) | Key decisions and rationale |

---

## Mission

Replace the investigative function of disappeared local journalism with AI-powered automated accountability infrastructure. Not a "gotcha" tool — a governance assistant that helps cities stay transparent by default. Accountability is a natural consequence of transparency, not the stated goal.

---

## The Product in One Paragraph

Ingest every public document a city produces (minutes, agendas, budgets, campaign finance, economic interest disclosures). Extract structured data (every vote by every official on every issue). Cross-reference against contributions and financial interests. Detect conflicts of interest. Generate formal public comment letters before each meeting. Surface everything through official profile pages, searchable archives, and alert subscriptions. Start with Richmond. Scale to 19,000 US cities.

---

## Current Status: Pre-build / Spec Complete

- [x] Product vision and mission defined
- [x] Architecture designed (document lake + structured core + embedding index)
- [x] 15 data sources assessed for Richmond
- [x] Three monetization paths identified
- [x] Budget estimates for all phases
- [x] Source credibility hierarchy (4 tiers)
- [x] News/media integration architecture
- [x] Extraction prompt prototyped and tested
- [x] City disambiguation solved (FIPS codes)
- [ ] Validate extraction accuracy on 3-5 more meetings
- [ ] Establish Socrata API connection
- [ ] Pull CAL-ACCESS campaign finance bulk data
- [ ] Generate first real transparency comment
- [ ] Deploy Richmond MVP
