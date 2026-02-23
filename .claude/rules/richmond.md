# Richmond Context

## Political Landscape

- **7 council members**, ~24 regular meetings/year, 30+ commissions and boards
- **Mayor Eduardo Martinez** (progressive coalition, elected 2022)
- **Tom Butt** — longest-serving council member, prolific E-Forum blog, former mayor
- **Notable former members:** Ben Choi, Jovanka Beckles (both progressive coalition) — names appear in contribution data. Private citizens now, so donations are legitimate flags, but context matters for coalition analysis.
- **Chevron** is a major political spender — funds the Richmond Standard news site. ALWAYS disclose when referencing Richmond Standard: "funded by Chevron Richmond."
- **Phillip** sits on the Personnel Board — must maintain collaborative relationship with city government.

## Source Credibility Tiers

- **Tier 1 (highest):** Official government records — certified minutes, adopted resolutions, CAL-ACCESS filings, budget docs, Socrata open data
- **Tier 2:** Independent journalism — Richmond Confidential (UC Berkeley), East Bay Times, KQED
- **Tier 3 (disclose bias):** Stakeholder communications — Tom Butt E-Forum (label: council member's newsletter), council member newsletters, Richmond Standard (ALWAYS disclose: "funded by Chevron Richmond")
- **Tier 4 (context only):** Community/social — Nextdoor, public comments, social media. Never sole source for factual claims.

## Minutes Format

Highly parseable: `"Ayes (N): Councilmember [names]. Noes (N): [names]. Abstentions (N): [names]."` — count in parentheses before colon. Consistent across all meetings.

## Key Data Sources

| Source | Platform | Key Detail |
|--------|----------|------------|
| Meeting minutes | CivicPlus Archive Center | AMID=31, PDFs via ADID URLs |
| Full agenda packets | eSCRIBE (Diligent) | AJAX calendar API + HTML parsing, no Playwright |
| Local campaign finance | NetFile Connect2 API | Agency ID 163, no auth, 22K+ contributions |
| State campaign finance | CAL-ACCESS | 1.5GB bulk ZIP download, PAC/IE data only |
| Open data | Socrata (transparentrichmond.org) | 142 datasets, no auth needed |
| Public records | NextRequest | Playwright scraper, CPRA compliance tracking |
| Commission rosters | CivicPlus pages | HTML table parsing, no Playwright |

Details for each source API: `src/CLAUDE.md`

## Community Framing

This is NOT an adversarial "gotcha" tool. It's a governance assistant that helps cities stay transparent by default. Accountability is a byproduct of transparency, not the stated goal. First public comment submission is deliberately deferred until after user testing and framing validation.
