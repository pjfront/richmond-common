# HeyGov ClerkMinutes

**One-line:** Sells AI minutes-drafting to *city clerks* (supply side); part of HeyGov govtech suite. Different angle entirely from resident-facing players.
**URL:** [heygov.com](https://heygov.com) · [ClerkMinutes blog post](https://heygov.com/post/the-future-of-local-governance-ai-powered-meeting-minutes-with-clerkminutes)
**Last updated:** 2026-04-27
**Data confidence:** Low–Medium (product positioning clear; funding / pricing not public)

## Snapshot

| Field | Value |
|---|---|
| Founded | Unknown |
| Stage | Unknown |
| Total funding | Not disclosed |
| Lead investor / backer | Not disclosed |
| Headcount | Unknown |
| HQ | Unknown |
| Coverage | "Several innovative municipalities" — no named clients in public materials |

## People

Not publicly identified in research pass.

## Buyer & Distribution

- **Buyer profile:** **B2G — sells to city clerks.** Supply side, not demand side.
- **Named customers:** "Several innovative municipalities" — none named publicly.
- **Channels:** Direct sales to municipalities; integrates with existing recording infrastructure.
- **Format:** Auto-generated meeting minutes; clerks edit before distribution.
- **Lag time:** Real-time draft; final lag depends on clerk review cycle.
- **Geographic strategy:** Wherever city clerks adopt; no geographic limits stated.

## Product Surface

**HeyGov suite:**

| Product | What it does |
|---|---|
| **HeyLicense** | Permit / license workflows |
| **HeyGov Pay** | Online payments |
| **Hey311** | Citizen reporting |
| **HeyReserve** | Facility rental payments |
| **ClerkMinutes** | Meeting documentation (the AI piece) |

**ClerkMinutes specifics:**
- "AI-powered natural language processing" auto-transcribes meeting audio
- Produces detailed meeting summaries
- Identifies "the most pertinent details from the meeting, such as agenda items"
- **Clerks retain editorial control** — can edit, delete, add information before distribution
- Integrates with existing recording infrastructure
- White-glove onboarding + consultation

**Negative space:**
- **Not citizen-facing** — output goes to clerks for distribution via existing municipal channels
- No campaign finance / conflict scanning
- No source-tier discipline (output is a municipal document, not a citizen-facing artifact)

## Technical Methodology

| Component | Choice |
|---|---|
| ASR / transcription | "Advanced natural language processing algorithms" — vendor not disclosed |
| LLM | Not disclosed |
| Pipeline architecture | Audio → transcription → summary → clerk review |
| Cost per meeting | Not disclosed |
| Provenance | N/A — output is the municipal record |
| Hallucination defense | Clerks review and edit before distribution |
| Open source? | No |

## Pricing

Not disclosed publicly. Likely RFP-based municipal procurement.

## Constraints they operate under

- **Funding constraint:** Govtech is a long-cycle sales market. Investors expect renewals, not just initial sales.
- **Buyer constraint:** **City clerks via RFP procurement.** Product priorities reflect what shows up in municipal RFPs (integrations with existing infrastructure, FedRAMP-style compliance language, white-glove onboarding).
- **Suite-bundle constraint:** ClerkMinutes is one of five products. Feature investment competes with HeyLicense, HeyGov Pay, etc. Roadmap is determined by which suite product has the easiest enterprise upsell.
- **Brand constraint:** "HeyGov" is a govtech-vendor brand. Repositioning toward citizens would require new brand.

## What RC is free from by not being them

- **No clerk buyer.** RC doesn't have to satisfy a municipal RFP, doesn't need integrations with HeyGov Pay, doesn't need white-glove onboarding.
- **No suite product line to maintain.** RC isn't building a govtech bundle.
- **No procurement-cycle pacing.** RC ships when interesting, not when an RFP closes.
- **No "official municipal record" status to defend.** RC's recap is *interpretation*, not the record.

## Borrowable technical infrastructure

Not much directly relevant — they're solving a different problem (clerk-side minutes drafting):

- **Possibly:** Their integration patterns with municipal recording infrastructure (Granicus, eSCRIBE) — may have insights useful for RC's scrapers. Not currently a need; flag for future if RC ever expands to a city using HeyGov's stack.

## Anti-patterns — what RC should NOT borrow

- **B2G clerk-side product positioning.** The clerk is not the user we serve; selling to clerks aligns the product with clerk workflows, not resident understanding.
- **Procurement-friendly product features** (white-glove onboarding, RFP compliance language, suite integrations). Different buyer, different feature set.

## Strategic Position

- **Buyer story:** Clerks pay for time savings + consistency in minutes drafting. Suite cross-sell to other HeyGov products is the upsell.
- **Differentiator:** Clerk-side workflow integration; suite breadth.
- **Weaknesses / gaps:** Doesn't reach citizens directly. AI quality depends on clerk review. Likely procurement-cycle slow.
- **Roadmap signals:** Unknown — typical govtech vendors expand suite breadth over time.

## Sources

- [HeyGov ClerkMinutes blog post](https://heygov.com/post/the-future-of-local-governance-ai-powered-meeting-minutes-with-clerkminutes)

## Open Questions / Research Gaps

- Founders + funding
- Customer count (clerks using ClerkMinutes specifically)
- ASR / LLM stack
- Pricing / typical contract value
- Relationship to other clerk-side AI tools (CivicPlus AI Editing Assistant; OpenGov)
- Whether they integrate with citizen-facing portals (Granicus, etc.)
- Whether they've shipped with any of Richmond's neighbor cities

## Notes

- **Strategically less competitive with RC than the other players.** They don't compete for resident attention; they compete for clerk RFPs. But they're worth tracking because:
  - If their AI minutes start appearing in cities RC scrapes (via Archive Center / eSCRIBE), the upstream input quality changes.
  - If clerks adopt at scale, the official municipal record itself becomes AI-generated, which has provenance implications RC should think about (the source-closest-artifact rule may need to evolve when "the source" is itself AI-drafted).
- Together with CivicPlus, they represent the **clerk-side AI** segment that RC should monitor for *upstream* effects on RC's input data, not as direct competition.
