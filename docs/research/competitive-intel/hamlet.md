# Hamlet

**One-line:** B2B regulatory intelligence — sells meeting search to real-estate developers and data center site selectors; only player not selling to residents.
**URL:** [myhamlet.com](https://www.myhamlet.com) · [Hamlet GovCenter](https://gov.myhamlet.com) · [LinkedIn](https://www.linkedin.com/company/hamlettech)
**Last updated:** 2026-04-27
**Data confidence:** Medium (product positioning clear; founders / funding not public)

## Snapshot

| Field | Value |
|---|---|
| Founded | Unknown |
| Stage | Unknown |
| Total funding | Not disclosed |
| Lead investor / backer | Not disclosed |
| Headcount | Unknown |
| HQ | California |
| Coverage | **1,800+ governing bodies, 50+ states, 33,000+ meeting transcripts** |

## People

**Founders / Team:** Not publicly identified. Hiring "Hamlet" via LinkedIn.

**Advisors / Backers:** Not disclosed.

## Buyer & Distribution

- **Buyer profile:** **B2B-only.** Not selling to residents directly.
- **Named buyer types:**
  - Real estate developers
  - **Data center site selectors**
  - Government affairs teams
  - Legal researchers
  - Non-profit advocacy organizations
  - Retail / franchise expansion teams
- **B2G partnerships (free public face):** Saratoga, CA + Palo Alto, CA — produces free AI-powered city council summaries for these cities; the partnerships are customer-acquisition / brand-building, not the revenue model.
- **Channels:** Web platform + Hamlet GovCenter (public-facing per partner city) + weekly newsletter "The District"
- **Format:** **Search-first** — "Search by company name, project address, topic, or keyword"
- **Lag time:** Unknown
- **Geographic strategy:** National search index across 50+ states

## Product Surface

| Feature | Description |
|---|---|
| **Transcript Search** | 33,000+ meeting transcripts searchable by company / project address / topic / keyword |
| **Video Navigation** | Jump to specific moments rather than watch full recording |
| **Keyword Alerts** | Email notifications when new meetings mention specified projects/companies |
| **Regulatory Velocity Index (RVI)** | Proprietary score of approval speed + predictability per jurisdiction |
| **Regulatory Friction Index (RFI)** | Proprietary score of opposition frequency + project resistance per jurisdiction |
| **AI Editorial Analysis** | Pattern analysis of city regulatory behavior |
| **The District** newsletter | Weekly trend analysis |
| **Hamlet GovCenter** (partner cities) | Free public-facing AI summaries (Saratoga, Palo Alto) |

**Negative space:**
- No resident-facing product.
- No campaign finance overlay.
- No conflict-of-interest detection (per agenda item).
- No public records / CPRA tracking.

## Technical Methodology

| Component | Choice |
|---|---|
| ASR / transcription | Not disclosed |
| LLM | Not disclosed |
| Pipeline architecture | Transcript ingestion + indexing + search + RVI/RFI scoring |
| Eval / accuracy framework | Not disclosed |
| Cost per meeting | Not disclosed |
| Provenance / source labeling | Source links to original meeting; basic |
| Hallucination defense | "AI and human oversight" — specifics not disclosed |
| Open source? | No |

## Pricing

| Tier | Price | Limits / features |
|---|---|---|
| Free trial | 14 days | Pro features |
| Pro | Not disclosed | Search + alerts + RVI/RFI |
| Enterprise | Custom | Full suite |

## Constraints they operate under

- **Funding constraint:** Likely VC-backed (operating at 1,800-body scale). Buyers expect ROI from RVI/RFI scoring.
- **Buyer constraint:** Real estate developers + data center site selectors think in terms of company names + project addresses — product is built around that buyer's mental model. Citizens are not the user.
- **Growth / scale constraint:** B2B sales cycle is slow but high-value. Have to demonstrate ROI per account.
- **Brand / framing constraint:** "Civic intelligence" framing is commercial; couldn't easily reposition as a citizen tool without losing buyers.
- **Buyer-content alignment constraint:** RVI/RFI scoring quality matters more than transcript fidelity to their buyers; product priorities reflect this.

## What RC is free from by not being them

- **No data-center-site-selector buyer.** RC has no buyer at all. Free to focus on residents without justifying value-per-search-query to a developer.
- **No RVI/RFI maintenance overhead.** Scoring schemas have to evolve as developers' priorities shift; that's product work RC doesn't carry.
- **No B2G partnership obligations.** Saratoga / Palo Alto partnerships are reputation-managed by Hamlet for customer acquisition. RC's relationship with the City of Richmond is operator-maintained collaborative, not contractual.

## Borrowable technical infrastructure

- **Search-by-company-name pattern as navigation primitive.** Useful for RC's influence-map UX — "what has Chevron come up in?" is a better entry point than "browse all meetings." Worth borrowing the affordance even though we're not selling to developers.
- **Per-jurisdiction scoring as lens.** RVI/RFI is a developer's metric, but the *concept* of jurisdiction-level metrics (ours could be: vote-volatility, public-comment-volume, finance-conflict-rate) could be useful navigation aids.

## Anti-patterns — what RC should NOT borrow

- **B2B regulatory intelligence as a business model.** Different vertical, different ethics. Selling expansion-friction data to data-center developers actively works against community-side transparency.
- **RVI / RFI scoring framework.** Their scoring is calibrated for "which jurisdictions are easy to build in." That framing privileges developer interests over community interests. RC scoring should serve residents, not site selectors.
- **B2B sales cycle / enterprise pricing.** Carries multi-year contract pressure that distorts product roadmap.
- **Geographic breadth as primary metric.** They're at 50+ states because that's what their B2B buyers need; RC doesn't have that need.

## Strategic Position

- **Buyer story:** Real-estate developers + data center site selectors + government affairs teams pay for advance warning + scoring of jurisdictional regulatory environments. Free public summaries (Saratoga, Palo Alto) are customer acquisition.
- **Differentiator:** Coverage breadth + RVI/RFI scoring + search-by-company-name pattern. Only B2B player serving expansion-decision use case.
- **Weaknesses / gaps:** Opaque founders / funding. Not residents-facing. Easy to characterize as "expansion tool for developers" — branding risk.
- **Roadmap signals:** Continued state-level expansion. Likely more verticals (retail expansion already mentioned).

## Sources

- [myhamlet.com](https://www.myhamlet.com) · [Hamlet GovCenter](https://gov.myhamlet.com)
- [PublicCEO: Hamlet x Saratoga (2023)](https://www.publicceo.com/2023/09/hamlet-elevates-saratogas-civic-engagement-with-ai-powered-city-council-summaries/)
- [PublicCEO: Hamlet x Palo Alto (2024)](https://www.publicceo.com/2024/06/hamlet-partners-with-the-city-of-palo-alto-to-provide-ai-powered-city-council-summaries/)
- [Govlaunch: Palo Alto pilot](https://govlaunch.com/projects/palo-alto-ca-pilots-ai-powered-city-council-summaries)
- [Saratoga Hamlet GovCenter](https://gov.myhamlet.com/ca/santa-clara-county/saratoga)
- [Palo Alto Hamlet GovCenter](https://gov.myhamlet.com/ca/santa-clara-county/palo-alto)

## Open Questions / Research Gaps

- Founders + funding — not in public sources
- Customer count + named B2B clients (vs partner cities)
- ASR / LLM stack
- RVI / RFI scoring methodology
- Pricing details
- Whether "AI and human oversight" means full-time editors or per-meeting QA
- How they got Saratoga / Palo Alto partnerships (procurement? donation? B2C demand?)
- Relationship between MyHamlet (B2B platform) and Hamlet GovCenter (B2G public face) — separate products or one product two skins?

## Notes

- **Hamlet is the player least competing with RC.** Different vertical entirely. They're after developers; RC is after residents.
- Their existence is *useful for RC's positioning*: when explaining to a Richmond resident why RC is different from "the AI startups doing this," "Hamlet helps developers find easy-to-permit cities; RC helps you understand your city" is a clean line.
- Worth tracking only if they ever pivot to residents-facing or if their RVI/RFI scoring leaks into resident-facing UX.
