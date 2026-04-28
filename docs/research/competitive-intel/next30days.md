# Next30Days

**One-line:** Solo Seattle dev (ex-Amazon PM) using **Legistar** as a unified upstream source to translate upcoming agendas into participation calls; pre-meeting angle.
**URL:** [next30days.org](https://next30days.org)
**Last updated:** 2026-04-28
**Data confidence:** Medium (product + scope verified; founder full name still partial)

## Snapshot

| Field | Value |
|---|---|
| Founded | February 2026 (friends-and-family test) |
| Stage | Self-funded, very early |
| Total funding | None disclosed — bootstrap |
| Lead investor / backer | None |
| Headcount | 1 (founder) |
| HQ | Seattle, WA |
| Coverage | Seattle + Bellevue (operational); Tacoma, Redmond next |

## People

**Founder:**
- **Clayton** (last name not extracted) — Former Amazon product manager
  - Origin: doom-scrolling national news late 2025; realized local government is where individuals can actually move outcomes
  - Started friends-and-family test February 2026 → 30 flyers around downtown Seattle, South Lake Union, Capitol Hill, Belltown
  - Eyeing Tacoma + Redmond expansion if momentum holds

**Editorial / Staff:** None — solo.

**Advisors / Backers:** None disclosed.

**Name origin:** *"What is one action you can take within the next 30 days to become more engaged in your local government and active in your community?"*

**Key technical insight:** Uses **Legistar API** (Granicus-owned legislative management system used by Seattle, Bellevue, "thousands of cities nationwide") as a unified upstream source. Architecture is Legistar-portable — any Legistar city can be added with minimal city-specific code. Caps addressable market to Legistar cities only.

## Buyer & Distribution

- **Buyer profile:** B2C residential
- **Channels:** Web app + email digest
- **Format:** **Pre-meeting briefing** — pulls upcoming agendas, translates to plain English, gives a path to participate
- **Lag time:** N/A (pre-meeting)
- **Geographic strategy:** Seattle / Bellevue start, expansion plans unclear

## Product Surface

| Feature | Description |
|---|---|
| **Upcoming meeting digest** | Pulls upcoming agenda items |
| **Plain-English translation** | Of agenda items |
| **Participation pathway** | "How to show up" — directs residents toward involvement |

**Negative space (inferred):**
- No post-meeting summaries (their angle is pre-meeting).
- No campaign finance / conflicts.

## Technical Methodology

| Component | Choice |
|---|---|
| ASR / transcription | N/A (pre-meeting; no transcripts) |
| LLM | Unknown |
| Pipeline architecture | Unknown — presumably scrape municipal calendar + agenda packets + LLM-translate to plain English |
| Cost per meeting | Unknown |
| Provenance | Unknown |
| Open source? | Unknown |

## Pricing

Unknown — likely free residential.

## Constraints they operate under

- **Funding constraint:** Unknown source. Founder background (ex-Amazon PM) suggests possibly self-funded with intent to seek VC or grants.
- **Buyer constraint:** Currently residents-only; if/when they add B2B, the constraint shape will follow that buyer.
- **Geographic constraint:** Seattle / Bellevue for now; expansion likely follows founder's network or funding.

## What RC is free from by not being them

- **No commitment to "civic engagement / participation" framing.** Next30Days is *advocating* for participation; RC's stance is governance-assistant, neutral observer. Different stance.
- **No multi-region pilot pressure.**

## Borrowable technical infrastructure

- **Pre-meeting briefing as a product surface.** RC has `orientation_preview` artifact (per [`docs/PARKING-LOT.md`](../../PARKING-LOT.md)) which fills the same need. Worth comparing notes if more on Next30Days surfaces.
- **"How to show up" pathway** — if RC ever wants to surface a participation CTA on agenda items (e.g., "this is at the next meeting; here's how to comment"), Next30Days is the design reference.

## Anti-patterns — what RC should NOT borrow

- **Advocacy-flavored framing** ("Spark civic engagement" — per GeekWire headline). RC's collaborative stance is values-protected. Don't drift into advocacy framing.
- **Single-channel (pre-meeting only) focus.** RC covers pre + post + finance + conflicts; one-trick coverage is structurally narrower.

## Strategic Position

- **Buyer story:** Likely B2C residential, possibly evolving to B2B / B2G.
- **Differentiator:** Pre-meeting angle, ex-Amazon PM founder.
- **Weaknesses / gaps:** Single-channel; small geographic footprint.
- **Roadmap signals:** Unknown.

## Sources

- [GeekWire: "Can AI revive democracy?"](https://www.geekwire.com/2026/can-ai-revive-democracy-former-amazon-product-manager-builds-tool-to-spark-civic-engagement/) — primary source (not yet fully extracted in research)

## Open Questions / Research Gaps

**Significant gaps — this profile is mostly a stub:**

- Founder name + bio
- Actual product URL (next30days.org? next30days.app? other?)
- Funding stage + investors
- ASR / LLM stack
- Coverage detail (Seattle Council? all departments? Bellevue separately?)
- Subscriber count
- Whether expansion is planned beyond Seattle / Bellevue
- Pricing
- Relationship to other Pacific Northwest civic-tech (BetaNYC analog?)

**Action item:** Re-fetch the GeekWire article and visit the actual product URL on next research pass.

## Notes

- The pre-meeting angle is genuinely interesting and underexplored. If they execute well, they could carve a defensible niche.
- RC's `orientation_preview` artifact addresses similar need; comparison would be useful when more product detail surfaces.
- This is the lowest-confidence profile in the directory — flag for re-research.
