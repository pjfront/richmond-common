# OpenCouncil

**One-line:** Greek nonprofit, fully open-source AGPL-3.0, generates AI podcasts/TikToks/Reels/WhatsApp updates from council meetings; the closest US-equivalent doesn't exist yet.
**URL:** [opencouncil.gr](https://opencouncil.gr) · [GitHub: schemalabz/opencouncil](https://github.com/schemalabz/opencouncil) · [Schema Labs](https://schemalabs.gr)
**Last updated:** 2026-04-27
**Data confidence:** High (open-source code is verifiable; some governance details opaque)

## Snapshot

| Field | Value |
|---|---|
| Founded | ~2024 (recent Greek launch) |
| Stage | Nonprofit operational, active development |
| Total funding | Helidoni Foundation grants (amounts not disclosed) |
| Lead investor / backer | Helidoni Foundation (Greek civic-tech philanthropy) |
| Headcount | Small team (Schema Labs civic-tech engineers; specific count unclear) |
| HQ | Athens, Greece |
| Coverage | 10 Greek municipalities including Athens |

## People

**Organization:** Schema Labs — Greek non-profit "Technology for Democracy & Public Sector Innovation"

**Team / Staff:** Civic Tech Software Engineer position posted on Hacker News (Athens, Greece, hybrid). Specific team members not enumerated publicly.

**Backers:** Helidoni Foundation (Greek civic-tech philanthropy)

## Buyer & Distribution

- **Buyer profile:** Nonprofit civic infrastructure. Free for citizens; municipalities adopt as a public service.
- **Named customers:** Athens + 9 other Greek municipalities (specific list not extracted)
- **Channels:** Web platform + **Discord** + **WhatsApp** (personalized neighborhood updates) + AI chat assistant + auto-generated **podcasts, TikToks, Reels** to social
- **Format:** Multimodal — text summaries + AI podcasts + short video for social + WhatsApp messaging
- **Lag time:** Not disclosed
- **Geographic strategy:** Greek municipalities, expanding within Greece. Not US-focused.

## Product Surface

| Feature | Description |
|---|---|
| **Auto transcription** | With speaker recognition via voiceprints |
| **AI summaries** | Of statements + automatic subject categorization |
| **Custom video clips** | Generate + share clips of council moments with auto editing |
| **AI podcasts / TikToks / Reels** | "AI journalist" generates multimedia from meetings |
| **WhatsApp updates** | Personalized by neighborhood / interest |
| **AI chat assistant** | Q&A over council meetings |
| **Diavgeia integration** | Links to Greece's official transparency portal |
| **Full-text search** | Across all meetings |
| **Notification system** | Configurable alerts |
| **Role-based access** | Granular permissions for different user types |
| **Multilingual support** | In development |

**Negative space:**
- No campaign finance integration (different regulatory regime).
- No US data sources (CAL-ACCESS / NetFile / FPPC are US-specific).
- No conflict scanning (different legal context).

## Technical Methodology

| Component | Choice |
|---|---|
| Stack | **Next.js 14 + TypeScript + PostgreSQL+PostGIS + Prisma** (97% TypeScript) |
| Architecture | **Separate task server** for media + AI; main Next.js for web. Distributed for async heavy operations. |
| ASR / transcription | Diarization with **voiceprint speaker recognition** |
| LLM | Specific model not disclosed in public README |
| Eval / accuracy framework | Tests via Jest with integration test configs |
| Cost per meeting | Not disclosed |
| Provenance / source labeling | Diavgeia portal links (Greek government transparency standard) |
| Hallucination defense | Not disclosed in public docs; presumably some review process given Greek regulatory context |
| Open source? | **Yes — AGPL-3.0** |
| Other infrastructure | Docker support, **Nix flakes** for dev environment |

**Repository activity (as of April 2026):**
- 1,350+ commits on main
- 48 stars, 22 forks
- Latest release: 2026.4.3 (April 2026 — actively maintained)
- 68 open issues
- Comprehensive `/docs` directory

## Pricing

Free for citizens. Municipality cost structure not public — likely funded via Helidoni grant + municipal partnership agreements.

## Constraints they operate under

- **Funding constraint:** Helidoni Foundation grants. Grant terms shape what gets built and how it's framed. Greek civic mandate.
- **Buyer constraint:** Greek municipalities. Product priorities reflect Greek civic needs (Diavgeia integration, WhatsApp distribution because that's where Greek citizens are, multilingual for migrant communities).
- **Growth / scale constraint:** Mission-driven, not revenue-driven, but still has to demonstrate impact for grant renewal.
- **Brand / framing constraint:** Public-good civic infrastructure framing in Greece. Different than commercial framing in US — but still binds them to "civic-mandate" output formats.

Notable: **OpenCouncil's constraints are softer than Locunity's** because nonprofits don't have to deliver venture exits. But they still have *some* constraints (grant terms, civic mandate, geographic mission).

## What RC is free from by not being them

- **No grant cycle.** RC doesn't have to renew anything.
- **No civic mandate from a foundation** — RC's mission is the operator's, not a backer's.
- **No multilingual requirement** — Richmond is English-primary; RC can choose to add languages or not.
- **No WhatsApp distribution requirement** — RC distributes via web + email; doesn't have to chase a specific channel.

## Borrowable technical infrastructure

OpenCouncil is the **richest source of borrowable code in the field** — it's open source on AGPL-3.0:

- **Read their repository directly.** Architecture decisions, prompts, eval framework, integration patterns. All visible at [github.com/schemalabz/opencouncil](https://github.com/schemalabz/opencouncil).
- **Voiceprint speaker recognition** — they've built diarization with consistent speaker identity across meetings. Useful pattern for council members who appear in dozens of meetings.
- **Custom video clip generation from meetings** — auto-editing pipeline. Useful if RC ever does multimodal output.
- **WhatsApp / TikTok / Reels output pipelines** — code is open. RC can read it whether or not RC ever ships those channels.
- **Distributed architecture (separate task server for media+AI)** — pattern reference for offloading heavy ops from Next.js.
- **Nix flakes for dev environment** — reproducibility pattern.

## Anti-patterns — what RC should NOT borrow

- **AGPL-3.0 license decision is its own choice** — RC's S27 license decision is open between BSL and AGPL. Each carries different downstream constraints. AGPL forces derivative works to also be open; BSL is more permissive. **OpenCouncil's choice doesn't bind RC's choice.**
- **Greek regulatory context** — Diavgeia integration is Greek-specific. RC would integrate California's equivalents (NetFile, CAL-ACCESS, FPPC, ArcGIS).
- **Multimodal output as a *requirement*** — for OpenCouncil it's a deployment mandate (Greek citizens are on WhatsApp). For RC it's an option to exercise when interesting.
- **Foundation-grant funding model** — would carry grant-cycle constraints. RC's out-of-pocket model is constraint-free.

## Strategic Position

- **Buyer story:** Helidoni Foundation grants + Greek municipal partnerships. No direct revenue.
- **Differentiator:** Only fully open-source civic-AI infrastructure currently shipping. Multimodal output is unmatched.
- **Weaknesses / gaps:** Greek-only. US municipalities can't adopt without significant adaptation (different data sources, different regulatory regime, different language). Smaller mindshare in US civic-tech community.
- **Roadmap signals:** Multilingual support in development. Continued municipality additions.

## Sources

- [opencouncil.gr](https://opencouncil.gr) · [GitHub repo](https://github.com/schemalabz/opencouncil) · [Schema Labs](https://schemalabs.gr) · [Helidoni Foundation Schema Labs program](https://www.helidonifoundation.org/programs/schema-labs)
- [Civic Tech Guide listing](https://directory.civictech.guide/listing/opencouncil)
- [Hacker News engineer hiring post](https://news.ycombinator.com/item?id=47220401)
- [Open Government Partnership Greece commitment GR0055](https://www.opengovpartnership.org/members/greece/commitments/GR0055/)
- [OECD AI civic participation report](https://www.oecd.org/en/publications/2025/06/governing-with-artificial-intelligence_398fa287/full-report/ai-in-civic-participation-and-open-government_51227ce7.html)

## Open Questions / Research Gaps

- Specific LLM model used (GPT-4? Claude? Gemini? Open-weights?)
- Cost per meeting / annual operating cost
- Number of monthly active users / WhatsApp subscribers
- Helidoni grant amount + terms
- Whether they'd be open to RC peering / collaboration on US-specific architecture
- Specific Greek municipalities besides Athens (which 9 others?)

## Notes

- **The S27 open-source decision should look at OpenCouncil first.** If RC chooses AGPL-3.0, RC and OpenCouncil could be peer projects with shared license. If RC chooses BSL, they're orthogonal.
- The fact that they exist also means **RC isn't first to civic-AI open source globally**, only first in the US if S27 ships before someone else does it. Time matters.
- Worth a deep technical read of the repo before any S27 work begins.
