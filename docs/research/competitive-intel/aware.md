# Aware

**One-line:** Largest player by coverage (3,835 cities, 5 countries); blockchain-hashed transcripts; only player with hardware kit for cities lacking streams.
**URL:** [awarenow.ai](https://www.awarenow.ai)
**Last updated:** 2026-04-27
**Data confidence:** Medium (coverage + pricing verified; founders + funding not public)

## Snapshot

| Field | Value |
|---|---|
| Founded | Unknown |
| Stage | Unknown (operating at scale, suggests post-seed) |
| Total funding | Not disclosed |
| Lead investor / backer | Not disclosed |
| Headcount | Unknown |
| HQ | Unknown |
| Coverage | **3,835 cities, ~195M people, 5 countries** (US, Canada, UK, Australia, NZ); 3,463 town governments + 1,395 school boards |

## People

**Founders / Team:** Not identified in public materials. Notable opacity for a player at this scale.

**Advisors / Backers:** Not disclosed.

## Buyer & Distribution

- **Buyer profile:** Hybrid B2C + B2G. Tiered residential subscriptions + government-side platform sales.
- **Named customers:** Cities mentioned: Denver CO, Auckland NZ, Bath UK, Humble TX, Millburn NJ, West Palm Beach FL, Atherton CA, Estevan SK, Kennebunk ME, Tasmania AU, Roselle Park NJ, Washington DC, Redmond WA, Sioux Falls SD, University City MO, Napa CA. (No named "customers" — references "partner cities.")
- **Channels:** Web platform + email + dashboard. Mobile app (likely).
- **Format:** Plain-language summaries, focusing on decisions/votes "without editorializing."
- **Lag time:** Not disclosed.
- **Geographic strategy:** Aggressive horizontal expansion; biggest in the field.

## Product Surface

| Feature | Description |
|---|---|
| **Summarize** | AI-generated meeting summaries focused on decisions / votes |
| **Aware Explain** | Translates legal/bureaucratic terminology into plain English |
| **Ask Aware** | Q&A across thousands of meetings |
| **Meeting Feed** | Searchable stream of local government updates |
| **Aware Capture** | **Hardware kit** — tablet preloaded with recording app for cities without published streams |

**Negative space:**
- No campaign finance overlay.
- No conflict-of-interest detection.
- No public records / CPRA pipeline.
- No source-tier disclosure framework.
- No multi-city architecture exposed publicly (their platform is monolithic).

## Technical Methodology

| Component | Choice |
|---|---|
| ASR / transcription | "Advanced speech-to-text models" — vendor not disclosed |
| LLM | Not disclosed |
| Pipeline architecture | Record → auto-upload → transcription → summarization → plain-English recap → publication |
| Eval / accuracy framework | Not disclosed |
| Cost per meeting | Not disclosed |
| Lag from meeting to publication | Not disclosed |
| Provenance / source labeling | **Blockchain hash verification** — generates unique hash codes for transcripts, publishes hashes to public blockchain as permanent records, links summaries to blockchain fingerprints |
| Hallucination defense | Not disclosed beyond blockchain (which doesn't actually defend against hallucinations — it just makes the hash immutable, regardless of whether the content is accurate) |
| Open source? | No |

## Pricing

**For individuals (monthly; 15% off annual; supports USD/GBP/CAD/AUD/NZD):**

| Tier | Price | Features |
|---|---|---|
| Snapshot | $0 | Basic access |
| Insight | $9/mo | Mid tier |
| Intelligence | $17/mo | "BEST" — most-promoted |
| Intelligence Pro | $210/mo | 5 users |

**For governments:**

| Tier | Price | Features |
|---|---|---|
| Aware Platform | from $400/mo | Software platform |
| Aware Capture | from $1,000/mo | Hardware + software kit |
| Custom annual | varies | |

## Constraints they operate under

- **Funding constraint:** Operating at 3,835-city scale requires meaningful investment. Investors expect coverage growth + revenue traction.
- **Buyer constraint:** Procurement officers at municipalities. Procurement responds to "verification claims" and "permanent records" — hence blockchain hashing as marketing differentiator. Hardware (Aware Capture) is also procurement-friendly because it's a tangible deliverable for $1,000/mo line items.
- **Growth / scale constraint:** Have to keep adding cities; coverage is the metric.
- **Brand / framing constraint:** "We are the everywhere civic-AI vendor" framing requires breadth, even when depth would serve users better.

## What RC is free from by not being them

- **No procurement officer to please.** RC doesn't have to invent verification theater (blockchain hashing) for a buyer that needs to justify a contract.
- **No hardware product line to defend.** Aware Capture is now revenue; killing it costs money. RC could borrow the *pattern* (capture for streamless cities) without owning a hardware roadmap.
- **No coverage-growth mandate.** RC stays one city without justifying TAM.
- **No 5-country product complexity.** Locale + currency + regulatory variation per country is overhead RC doesn't carry.

## Borrowable technical infrastructure

- **Hardware-capture pattern reference** — *if* RC ever expands to a city without published streams, the conceptual pattern is "physical recording device → upload pipeline." Don't build a hardware business; just steal the pattern.
- **Tiered residential pricing model structure** — Snapshot/Insight/Intelligence/Pro is a clean ladder. Useful reference *if* RC ever needs paid tiers (currently doesn't).
- **Multi-currency UX patterns** — for the unlikely case RC ever expands internationally.

## Anti-patterns — what RC should NOT borrow

- **Blockchain hashing for transcript verification.** Cryptographically theatrical. Doesn't actually defend against hallucinations; just makes the (potentially wrong) hash immutable. RC's source-closest-artifact rule + provenance metadata is the actual defense.
- **Hardware capture as a business** (Aware Capture). Pulls RC into procurement vertical it doesn't want.
- **B2G procurement model.** Aligns product with city-clerk buyers, biases away from residents.
- **Coverage-growth-first framing** — "we're at 3,835 cities" is the wrong metric for RC.
- **Opaque founder identity.** Notable that no founder is publicly identified. RC operates with operator transparency.

## Strategic Position

- **Buyer story:** Tiered residential subscriptions ($0–$210) + B2G platform + hardware ($400–$1,000+/mo). Real revenue is government side; residents are funnel.
- **Differentiator:** Sheer coverage (3,835 cities). Hardware kit (only player with one). Blockchain verification (procurement-friendly story).
- **Weaknesses / gaps:** Opaque founders. No public technical methodology. Blockchain claims are weak as actual hallucination defense. No depth — just summaries.
- **Roadmap signals:** Continued horizontal expansion. International (already 5 countries; likely more).

## Sources

- [awarenow.ai](https://www.awarenow.ai)
- (Founder / funding research not yet completed — see Open Questions)

## Open Questions / Research Gaps

- **Founders + funding** — not in public sources I've checked. Worth deeper Crunchbase / Pitchbook lookup.
- ASR vendor (Whisper? Deepgram? Other?)
- LLM (GPT-4? Claude? Gemini? Llama?)
- Cost per meeting at scale
- Hallucination incident history (any like Civic Sunlight's?)
- Actual technology behind Aware Capture (just a tablet + cellular upload?)
- Customer count by tier (free vs paid; gov vs individual)
- Their privacy policy / data retention practices

## Notes

- The biggest player in the field by coverage but also the most opaque. Worth periodic re-research as more info surfaces.
- **Their hardware kit is the most strategically interesting product detail in the field** — it's the only player solving the "city has no published stream" problem. If RC ever expands to a small or rural city, this is the missing capability.
- Their blockchain hashing is a useful study in *pretending to solve* a problem that's still open. Real provenance discipline (D1-style) is harder but actually works.
