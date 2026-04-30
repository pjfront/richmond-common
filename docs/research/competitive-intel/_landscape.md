# Civic-AI Market Landscape — A Negative Map

**Updated:** 2026-04-27
**Scope:** Public-facing AI tools for local government transparency.

This document is **not** a "what to build toward" map. It's a "what not to build toward" map. The point is to make the **constraints** that shape every other player visible — so RC can use their *technical* infrastructure freely without inheriting their *business* infrastructure.

The deepest finding from the research:

> Every product compromise visible in the field traces back to a constraint the player operates under — investors, buyers, runway, advisors, growth metrics. Richmond Commons doesn't have those constraints, and the operator does this for fun. That difference is the moat the rest of the field structurally cannot replicate.

Read this alongside [`_self.md`](./_self.md), which audits RC on the same axes.

## Market shape

The space is **fragmented and fast-emerging**. No single player has dominant share. The largest by coverage (Aware, ~3,835 cities) covers <2% of US local elected bodies. Per Locunity's claim, the TAM is ~90,000 elected bodies in the US alone.

Most products were founded **2023–2025**, post-GPT-4. The category did not exist at scale before LLMs became cheap enough to process multi-hour meetings for under $20.

Critical ecosystem fact: **the field is pre-Series A.** Most disclosed rounds are pre-seed / seed. The constraints the players carry today are *founder-stage* constraints — runway pressure, investor optionality, brand framing for the next round. Those constraints will tighten, not loosen, as players raise. RC's structural freedom *increases* relative to the field as competitors raise more money and accept more constraints.

## Segments — by buyer (which encodes the constraint)

The field splits along **buyer**, and the buyer determines what each player has to do:

### 1. Resident-facing meeting summarizers (B2C top-of-funnel)
Free for residents; the residential tier feeds B2B revenue. The constraint they carry: residents are loss leaders, so the *real* product is calibrated for advocacy/business buyers. What residents see is downstream of what advocacy groups will pay for.
- **[Locunity](./locunity.md)** — Smart Brevity, Bay Area + KY, freemium. Has to deliver SAIF a venture-scale outcome.
- **[Civic Sunlight](./civic-sunlight.md)** — Maine, ~20 towns, free. Has to recover from public hallucinations.
- **[Aware](./aware.md)** — 3,835 cities, freemium. Has to justify $400+/mo gov contracts.
- **[citymeetings.nyc](./citymeetings-nyc.md)** — solo dev, NYC, free with planned freemium. Has to eventually fund Vikram's time.

### 2. Pre-meeting / agenda-forward (B2C)
- **[Next30Days](./next30days.md)** — Seattle/Bellevue.

### 3. Open-source civic infrastructure (nonprofit)
- **[OpenCouncil](./opencouncil.md)** — Greek nonprofit, AGPL-3.0. Has to satisfy Helidoni Foundation grant terms.

### 4. B2B regulatory intelligence
- **[Hamlet](./hamlet.md)** — Real-estate developers, data center site selectors. Has to deliver Regulatory Velocity / Friction scores buyers actually use.

### 5. B2G clerk tooling (supply side)
- **[HeyGov ClerkMinutes](./heygov.md)** — Sells to clerks producing minutes. Has to win RFPs.

### 6. Incumbent govtech vendors embedding AI
- **[CivicPlus](./civicplus.md)** — PE-backed, mature. Has to defend existing renewals.

### Where Richmond Commons sits

Primarily Segment 1 (resident-facing) plus depth in Segment 4-flavored *intelligence* (campaign finance, conflict scanning) without selling B2B. Plans to enter Segment 3 (open source) at S27.

**Critically: RC is in those segments structurally but not constraint-wise.** The operator chooses to do resident-facing work; the operator chooses to expose finance/conflict data. The operator could choose otherwise tomorrow.

## What each player *has to* do

The same data sliced by **constraint** rather than feature. This is the meat of the negative map.

| Player | Has to | Why (constraint) | Therefore… |
|---|---|---|---|
| **Locunity** | Build action-marketplace where advocacy groups pay to be the recommended action | $125K SAIF → next round needs venture-scale story | Their welcome email already hints at this: *"connecting with organizations, events, and opportunities tied to the exact issues you're tracking"* |
| **Locunity** | Use Axios-style Smart Brevity voice | B2B buyers (chambers, advocacy orgs, government affairs) read Axios — that's the format they expect | Voice is calibrated for commercial buyers, not residents |
| **Aware** | Build hardware kit (Aware Capture) | Procurement officers respond to verification claims; hardware justifies $1,000/mo line items | They built a tablet because procurement needed something tangible |
| **Aware** | Add blockchain hashing | Procurement-friendly story for "tamper-proof records" | Cryptographically theatrical; not solving a real problem |
| **citymeetings.nyc** | Plan a paid pro tier for lobbyists/journalists/government affairs | Vikram needs to fund his time eventually | The freemium pivot is locked in even though the free tier is great today |
| **Hamlet** | Optimize search around company names + project addresses | Real-estate developers think in those entity types | Citizens are not the user; product reflects this |
| **Hamlet** | Maintain RVI / RFI scores | Their B2B buyers use those scores in expansion decisions | Scoring quality matters more than transcript fidelity |
| **HeyGov / CivicPlus** | Sell to city clerks via RFPs | Govtech procurement is the revenue path | Product priorities reflect what city clerks ask for, not residents |
| **Civic Sunlight** | Add human review (Midcoast Villager partnership) | Public hallucination story (CJR Nov 2024); reputational pressure | Pivoted under pressure, not by choice |
| **Civic Sunlight** | Demonstrate "90–95% accuracy" claim | Recovery messaging; investor / partner trust | Claim is now a public commitment that constrains them |
| **OpenCouncil** | Generate WhatsApp / TikTok / Reels output | Greek civic communication mandate; that's where Greek citizens are | Multimodal isn't a strategic choice; it's a deployment requirement |
| **Locunity** | Cover ~100 jurisdictions and growing | Coverage is the metric SAIF tracks for next round | Has to scale even when depth would serve users better |

In every case the constraint is **legible from the structure of who funds them**. The infrastructure they build is real and reusable. The shape they take is downstream of constraints we don't have.

## What's converging across the field

### 1. Pure-AI is losing to AI + human-in-the-loop
- **Civic Sunlight** had public hallucinations (CJR Nov 2024) — pivoted to human review.
- **citymeetings.nyc** founder Vikram Oberoi: *"I don't believe using AI alone is a great way to use AI today."*
- **Locunity** has editorial layer from day one.
- **Hamlet** uses "AI and human oversight."

**Implication for RC:** Pure-auto with provenance discipline + source-closest-artifact rule is a *structural* defense (not a process one). RC's defense doesn't require an editor on payroll, which is good because RC isn't paying anyone. It requires holding D1/D2/D5 design rules and the source-closest-artifact rule. **Holding the line is the load-bearing trade.**

### 2. Email-first delivery
Most B2C players lead with email; web is the archive. Locunity's primary product *is* the email. Civic Sunlight is a newsletter.

**RC is web-first** — opposite. This isn't necessarily wrong; it's a choice the operator can revisit. The negative-map question: would going email-first carry any of *their* constraints? No — email-first as a delivery choice doesn't bind RC to a B2B funnel or scaling logic. **Borrowable.**

### 3. B2B revenue funds the residential free tier
Locunity, Aware, citymeetings.nyc all going freemium with paid B2B tiers.

**RC's bet:** No B2B funnel. Free forever. Funded out-of-pocket. The aligned-incentive question doesn't arise because there are no incentives to align.

### 4. No one has solved depth
Every player is at the **meeting-summary** layer. No one integrates campaign finance, conflicts, contracts, public records, or temporal correlation.

**Why?** Because depth costs engineering time that doesn't justify against B2B subscription revenue. Depth doesn't sell to chambers of commerce. Depth sells to nobody. RC is the only player who can afford to build depth, *because RC isn't trying to make money.*

This is the clearest expression of the negative-map insight: depth is unjustifiable against business constraints, and RC has no business constraints.

### 5. Hardware capture is the long-tail unlock
**Aware** has it; nobody else does. Why? Because building a hardware kit is unjustifiable except against a procurement buyer who'll pay $1,000/mo. RC won't ever build hardware *as a business*. But the operator could borrow the *pattern* — "if a city doesn't publish its stream, we capture it" — without the procurement model.

### 6. Multimodal output is emerging
**OpenCouncil** generates podcasts, TikToks, Reels, WhatsApp.

**For RC:** D6 ("narrative over numbers") points the same direction. Multimodal expansion is an option for whenever the operator finds it interesting.

## What's missing from the field

Things no current player does well — open territory:

- **Mandatory provenance metadata** as architectural constraint (D1) — RC has it.
- **Source credibility tiering with bias disclosures** — RC has it.
- **Conflict-of-interest detection per agenda item** — RC has it.
- **Public records / CPRA pipeline** — RC has it.
- **Open-source civic infrastructure in the US** — only OpenCouncil (Greece) does this; RC's S27 plan would be the US default.
- **Multi-city architecture with FIPS-keyed registry** — RC has it.

Each of these is unjustifiable against B2B revenue and therefore structurally hard for the rest of the field to copy. Each of these is build-it-because-it's-interesting work, which is exactly what RC is for.

## What's saturated — don't compete here

- **Generic meeting summaries.** Aware is at 3,835 cities.
- **Email newsletter format.** Multiple polished players.
- **Smart Brevity / Axios voice.** Locunity has it; replicable but not a moat.
- **Free + freemium for residents.** Standard.

These are not where RC wins. RC wins where the rest can't afford to be — depth, provenance, source-tier discipline, integrated finance, conflict scanning, public records, open source, FIPS-keyed multi-city architecture.

## Risks visible in the landscape

- **CivicPlus embedding AI into platforms cities already pay for** is a structural threat to all *external* civic-AI products. If platform vendors solve good-enough summaries, external vendors lose pull-through. RC's depth is the moat that survives.
- **Hallucination incidents → CJR-style coverage** is a reputational risk shared by everyone. RC's defense (D1/D2/D5/source-closest-artifact) is documented and structural.
- **VC pressure on advocacy framing.** Locunity's "Shape what's next" framing is advocacy-flavored; sustainable only if SAIF doesn't push for action-marketplace monetization that biases what residents see. **Watch for the moment they ship the action layer.**
- **Open-source AGPL competition.** OpenCouncil exists. If RC takes too long on S27, OpenCouncil becomes the open-source default in the US too. Timing matters — but it's the operator's timing, not anyone else's.

## How to use this when making a decision

When a feature decision comes up, in this order:

1. **Is this borrowed *technical* infrastructure?** (Prompt structure, ASR vendor, chunking strategy, time-marker format, open-source library, eval pattern.) → **Take it freely.**
2. **Is this borrowed *business* infrastructure?** (Buyer alignment, advocacy framing, growth funnel, action marketplace, scaling pressure, B2B story.) → **Don't take it.** The constraint will follow the shape.
3. **Does this preserve or reduce optionality?** (Can RC stop doing this in 6 months without pain? Can the operator pivot without breaking external promises?) → **Optionality-preserving choices win.**

That's the negative map.

## Sources

- Per-company profiles in this directory.
- [CJR on Civic Sunlight hallucinations](https://www.cjr.org/analysis/ai-local-news-civic-sunlight-maine.php)
- [Nieman Lab on civic AI](https://www.niemanlab.org/2025/03/local-newsrooms-are-using-ai-to-listen-in-on-public-meetings/)
- [Vikram Oberoi technical writeup](https://vikramoberoi.com/posts/how-citymeetings-nyc-uses-ai-to-make-it-easy-to-navigate-city-council-meetings/)
- [Maximum NY interview](https://www.maximumnewyork.com/p/citymeetings-interview)
- [Geoff Ralston / SAIF — TechCrunch](https://techcrunch.com/2025/04/17/former-y-combinator-president-geoff-ralston-launches-new-ai-safety-fund/)
- [GeekWire on Next30Days / civic AI](https://www.geekwire.com/2026/can-ai-revive-democracy-former-amazon-product-manager-builds-tool-to-spark-civic-engagement/)
- [CivicPlus AI announcement](https://www.civicplus.com/news/nn/civicplus-announces-ai-capabilities-with-six-new-intelligent-product-releases/)
